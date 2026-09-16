"""Coordinator for local Poolex telemetry."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import tinytuya

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_IP,
    CONF_LOCAL_KEY,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    TUYA_VERSION,
)
from .protocol import (
    decode_telemetry,
    extract_outer_datapoints,
    extract_telemetry_payload,
)

_LOGGER = logging.getLogger(__name__)

QUERY_RECEIVE_TIMEOUT = 3
QUERY_RECEIVE_ATTEMPTS = 4
PASSIVE_RECEIVE_ATTEMPTS = 1
MAX_TRANSIENT_FAILURES = 3


class PoolexCommunicationError(Exception):
    """Raised when a local telemetry frame cannot be obtained."""


class PoolexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage one persistent Tuya LAN session and decoded telemetry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.entry = entry
        self._device: tinytuya.Device | None = None
        self._device_lock = asyncio.Lock()
        self._consecutive_failures = 0

    def _get_device(self) -> tinytuya.Device:
        """Create the persistent TinyTuya client in the executor thread."""
        if self._device is None:
            self._device = tinytuya.Device(
                self.entry.data[CONF_DEVICE_ID],
                self.entry.data[CONF_DEVICE_IP],
                self.entry.data[CONF_LOCAL_KEY],
                version=TUYA_VERSION,
                connection_timeout=QUERY_RECEIVE_TIMEOUT,
                connection_retry_limit=1,
                connection_retry_delay=0,
                persist=True,
            )
            self._device.set_socketPersistent(True)
            self._device.set_socketTimeout(QUERY_RECEIVE_TIMEOUT)
            self._device.set_sendWait(0.1)
        return self._device

    def _close_device(self) -> None:
        """Close and forget the local client."""
        if self._device is not None:
            self._device.close()
            self._device = None

    @staticmethod
    def _query_payload(device: tinytuya.Device):
        """Build the vendor status query accepted by the TSOL-MX800."""
        return device.generate_payload(
            tinytuya.CONTROL_NEW,
            rawData={"dps": {}},
        )

    @staticmethod
    def _summarize_response(
        result: Any,
        outer_datapoints: set[str],
        errors: set[str],
    ) -> None:
        """Record safe response diagnostics without retaining credentials."""
        if not isinstance(result, Mapping):
            return

        outer_datapoints.update(
            str(datapoint) for datapoint in extract_outer_datapoints(result)
        )
        error = result.get("Error")
        if error:
            code = result.get("Err")
            summary = f"{code}: {error}" if code else str(error)
            errors.add(summary[:160])

    def _drain_frame(
        self,
        device: tinytuya.Device,
        attempts: int = QUERY_RECEIVE_ATTEMPTS,
    ) -> tuple[dict[str, Any] | None, set[str], set[str]]:
        """Drain the persistent response socket for one telemetry frame."""
        deadline = time.monotonic() + QUERY_RECEIVE_TIMEOUT * attempts
        outer_datapoints: set[str] = set()
        errors: set[str] = set()
        while time.monotonic() < deadline:
            result = device.receive()
            self._summarize_response(result, outer_datapoints, errors)
            payload = extract_telemetry_payload(result)
            if payload is None:
                continue
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry, outer_datapoints, errors
        if outer_datapoints or errors:
            _LOGGER.debug(
                "Poolex response summary: outer_datapoints=%s errors=%s",
                sorted(outer_datapoints),
                sorted(errors),
            )
        return None, outer_datapoints, errors

    def _read_frame(
        self, device: tinytuya.Device
    ) -> tuple[dict[str, Any] | None, set[str], set[str]]:
        """Use passive listening, the vendor query, and LAN refresh fallbacks."""
        outer_datapoints: set[str] = set()
        errors: set[str] = set()

        telemetry, seen, response_errors = self._drain_frame(
            device, attempts=PASSIVE_RECEIVE_ATTEMPTS
        )
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        device.send(self._query_payload(device))
        telemetry, seen, response_errors = self._drain_frame(device)
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        # Some firmware revisions only publish DP 21 after a LAN DP refresh.
        refresh_result = device.updatedps([4103])
        self._summarize_response(refresh_result, outer_datapoints, errors)
        payload = extract_telemetry_payload(refresh_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry, outer_datapoints, errors
        telemetry, seen, response_errors = self._drain_frame(device)
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        # AP_CONFIG is a read-only product/status request on this device and
        # has returned the same current DP 21 frame on observed firmware.
        product_result = device.product()
        self._summarize_response(product_result, outer_datapoints, errors)
        payload = extract_telemetry_payload(product_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry, outer_datapoints, errors
        telemetry, seen, response_errors = self._drain_frame(device)
        outer_datapoints.update(seen)
        errors.update(response_errors)
        return telemetry, outer_datapoints, errors

    def _poll_sync(self) -> dict[str, Any]:
        """Poll the inverter from a worker thread."""
        try:
            device = self._get_device()
            telemetry, outer_datapoints, errors = self._read_frame(device)
        except (
            OSError,
            TimeoutError,
            ValueError,
            RuntimeError,
            tinytuya.DecodeError,
        ) as err:
            self._close_device()
            _LOGGER.debug(
                "Poolex Tuya LAN request raised %s: %s",
                type(err).__name__,
                err,
            )
            raise PoolexCommunicationError("Tuya LAN request failed") from err

        if telemetry is None:
            self._close_device()
            details = []
            if outer_datapoints:
                details.append(f"outer datapoints={sorted(outer_datapoints)}")
            if errors:
                details.append(f"tuya_responses={sorted(errors)}")
            detail_text = f" ({'; '.join(details)})" if details else ""
            raise PoolexCommunicationError(
                f"The inverter did not return a telemetry frame{detail_text}"
            )
        return telemetry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and decode one local telemetry frame."""
        async with self._device_lock:
            try:
                data = await self.hass.async_add_executor_job(self._poll_sync)
            except PoolexCommunicationError as err:
                self._consecutive_failures += 1
                if (
                    self.data is not None
                    and self._consecutive_failures <= MAX_TRANSIENT_FAILURES
                ):
                    _LOGGER.warning(
                        "Poolex poll failed (%d/%d); retaining the last "
                        "successful telemetry frame: %s",
                        self._consecutive_failures,
                        MAX_TRANSIENT_FAILURES,
                        err,
                    )
                    return self.data

                _LOGGER.error(
                    "Poolex telemetry unavailable after %d consecutive poll "
                    "failure(s): %s",
                    self._consecutive_failures,
                    err,
                )
                raise UpdateFailed(str(err)) from err

            if self._consecutive_failures:
                _LOGGER.info(
                    "Poolex telemetry restored after %d failed poll(s)",
                    self._consecutive_failures,
                )
                self._consecutive_failures = 0
            return data

    async def async_shutdown(self) -> None:
        """Close the local session when the config entry is unloaded."""
        await super().async_shutdown()
        async with self._device_lock:
            await self.hass.async_add_executor_job(self._close_device)
