"""Coordinator for local Poolex telemetry."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import tinytuya

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_IP,
    CONF_LOCAL_KEY,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    TUYA_STREAM_ARM_DP,
    TUYA_STREAM_ARM_VALUE,
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
FAST_SESSION_ATTEMPTS = 2
FAST_QUERY_RECEIVE_ATTEMPTS = 3
FAST_RETRY_FAILURES = 3
POLL_TIMEOUT_SECONDS = 30
PASSIVE_RECEIVE_ATTEMPTS = 1


class PoolexCommunicationError(Exception):
    """Raised when a local telemetry frame cannot be obtained."""


class PoolexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage one persistent Tuya LAN session and decoded telemetry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self._normal_update_interval = timedelta(
            seconds=entry.options.get(
                CONF_POLL_INTERVAL,
                entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._normal_update_interval,
        )
        self.entry = entry
        self._device: tinytuya.Device | None = None
        self._device_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._poll_in_progress = False

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
    def _set_device_timeout(
        device: tinytuya.Device, deadline: float
    ) -> bool:
        """Bound the next TinyTuya socket operation by the poll deadline."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        timeout = max(0.1, min(QUERY_RECEIVE_TIMEOUT, remaining))
        device.set_socketTimeout(timeout)
        if device.socket is not None:
            device.socket.settimeout(timeout)
        return True

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
        deadline: float | None = None,
    ) -> tuple[dict[str, Any] | None, set[str], set[str]]:
        """Drain the persistent response socket for one telemetry frame."""
        local_deadline = time.monotonic() + QUERY_RECEIVE_TIMEOUT * attempts
        if deadline is None:
            deadline = local_deadline
        else:
            deadline = min(deadline, local_deadline)
        outer_datapoints: set[str] = set()
        errors: set[str] = set()
        while time.monotonic() < deadline:
            if not self._set_device_timeout(device, deadline):
                break
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
        self,
        device: tinytuya.Device,
        *,
        receive_attempts: int = QUERY_RECEIVE_ATTEMPTS,
        include_fallbacks: bool = True,
        deadline: float | None = None,
    ) -> tuple[dict[str, Any] | None, set[str], set[str]]:
        """Use passive listening, the vendor query, and LAN refresh fallbacks."""
        outer_datapoints: set[str] = set()
        errors: set[str] = set()

        # The vendor app arms the inverter's periodic telemetry report with
        # this raw local command. It does not change output or configuration.
        device.set_value(
            TUYA_STREAM_ARM_DP,
            TUYA_STREAM_ARM_VALUE,
            nowait=True,
        )
        telemetry, seen, response_errors = self._drain_frame(
            device, attempts=PASSIVE_RECEIVE_ATTEMPTS, deadline=deadline
        )
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        if deadline is not None and not self._set_device_timeout(device, deadline):
            return None, outer_datapoints, errors
        device.send(self._query_payload(device))
        telemetry, seen, response_errors = self._drain_frame(
            device, attempts=receive_attempts, deadline=deadline
        )
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        if not include_fallbacks:
            return None, outer_datapoints, errors

        # Some firmware revisions only publish DP 21 after a LAN DP refresh.
        if deadline is not None and not self._set_device_timeout(device, deadline):
            return None, outer_datapoints, errors
        refresh_result = device.updatedps([4103])
        self._summarize_response(refresh_result, outer_datapoints, errors)
        payload = extract_telemetry_payload(refresh_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry, outer_datapoints, errors
        telemetry, seen, response_errors = self._drain_frame(
            device, attempts=receive_attempts, deadline=deadline
        )
        outer_datapoints.update(seen)
        errors.update(response_errors)
        if telemetry is not None:
            return telemetry, outer_datapoints, errors

        # AP_CONFIG is a read-only product/status request on this device and
        # has returned the same current DP 21 frame on observed firmware.
        if deadline is not None and not self._set_device_timeout(device, deadline):
            return None, outer_datapoints, errors
        product_result = device.product()
        self._summarize_response(product_result, outer_datapoints, errors)
        payload = extract_telemetry_payload(product_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry, outer_datapoints, errors
        telemetry, seen, response_errors = self._drain_frame(
            device, attempts=receive_attempts, deadline=deadline
        )
        outer_datapoints.update(seen)
        errors.update(response_errors)
        return telemetry, outer_datapoints, errors

    def _poll_sync(self) -> dict[str, Any]:
        """Poll the inverter with short fresh-session retries."""
        outer_datapoints: set[str] = set()
        errors: set[str] = set()
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

        for attempt in range(FAST_SESSION_ATTEMPTS):
            if time.monotonic() >= deadline:
                break
            self._close_device()
            try:
                device = self._get_device()
                _LOGGER.debug(
                    "Starting Poolex fresh session attempt %d/%d",
                    attempt + 1,
                    FAST_SESSION_ATTEMPTS,
                )
                telemetry, seen, response_errors = self._read_frame(
                    device,
                    receive_attempts=FAST_QUERY_RECEIVE_ATTEMPTS,
                    include_fallbacks=False,
                    deadline=deadline,
                )
                outer_datapoints.update(seen)
                errors.update(response_errors)
                if telemetry is not None:
                    return telemetry
            except (
                OSError,
                TimeoutError,
                ValueError,
                RuntimeError,
                tinytuya.DecodeError,
            ) as err:
                errors.add(f"{type(err).__name__}: {str(err)[:120]}")
                _LOGGER.debug(
                    "Poolex fresh session attempt %d failed: %s",
                    attempt + 1,
                    err,
                )
            finally:
                self._close_device()

        # Keep the slower legacy paths for initial compatibility discovery, but
        # do not pay their full timeout on every already-established outage.
        if self._consecutive_failures == 0 and time.monotonic() < deadline:
            try:
                device = self._get_device()
                telemetry, seen, response_errors = self._read_frame(
                    device,
                    include_fallbacks=True,
                    deadline=deadline,
                )
                outer_datapoints.update(seen)
                errors.update(response_errors)
                if telemetry is not None:
                    return telemetry
            except (
                OSError,
                TimeoutError,
                ValueError,
                RuntimeError,
                tinytuya.DecodeError,
            ) as err:
                errors.add(f"{type(err).__name__}: {str(err)[:120]}")
                _LOGGER.debug("Poolex compatibility poll failed: %s", err)
            finally:
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

    @staticmethod
    def _build_no_production_data(
        last_successful_poll: datetime | None,
    ) -> dict[str, Any]:
        """Build a safe idle state when the inverter is silent at night."""
        return {
            "communication_ok": False,
            "last_successful_poll": last_successful_poll,
            "status": "idle",
            "ac_output_power": 0.0,
            "dc_input_power": 0.0,
            "ac_voltage": 0.0,
            "ac_current": 0.0,
            "ac_frequency": 0.0,
            "ac_power_factor": 0.0,
            "pv1_voltage": 0.0,
            "pv1_current": 0.0,
            "pv1_power": 0.0,
            "pv2_voltage": 0.0,
            "pv2_current": 0.0,
            "pv2_power": 0.0,
            "inverter_temperature": 0.0,
            "alarm_code": None,
            "raw_dps": {},
            "raw_payload": None,
        }

    @classmethod
    def initial_data(cls) -> dict[str, Any]:
        """Return the immediate zero-production state before the first poll."""
        return cls._build_no_production_data(None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Run one single-flight poll and skip overlapping refresh requests."""
        if self._poll_in_progress:
            _LOGGER.debug("Skipping overlapping Poolex poll request")
            return self.data if self.data is not None else self.initial_data()

        self._poll_in_progress = True
        try:
            return await self._async_update_data_single()
        finally:
            self._poll_in_progress = False

    async def _async_update_data_single(self) -> dict[str, Any]:
        """Fetch and decode one local telemetry frame."""
        async with self._device_lock:
            try:
                data = await self.hass.async_add_executor_job(self._poll_sync)
            except PoolexCommunicationError as err:
                self._consecutive_failures += 1
                self.update_interval = (
                    timedelta(seconds=5)
                    if self._consecutive_failures <= FAST_RETRY_FAILURES
                    else self._normal_update_interval
                )
                last_successful_poll = (
                    self.data.get("last_successful_poll")
                    if self.data is not None
                    else None
                )
                _LOGGER.warning(
                    "Poolex poll failed (%d); switching to zero-production "
                    "Idle state: %s",
                    self._consecutive_failures,
                    err,
                )
                return self._build_no_production_data(last_successful_poll)

            failed_polls = self._consecutive_failures
            if failed_polls:
                _LOGGER.info(
                    "Poolex telemetry restored after %d failed poll(s)",
                    failed_polls,
                )
                self._consecutive_failures = 0
            self.update_interval = self._normal_update_interval
            return {
                **data,
                "last_successful_poll": datetime.now(timezone.utc),
            }

    async def async_shutdown(self) -> None:
        """Close the local session when the config entry is unloaded."""
        await super().async_shutdown()
        async with self._device_lock:
            await self.hass.async_add_executor_job(self._close_device)
