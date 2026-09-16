"""Coordinator for local Poolex telemetry."""

from __future__ import annotations

import asyncio
import logging
import time
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

    def _drain_frame(self, device: tinytuya.Device) -> dict[str, Any] | None:
        """Drain the persistent response socket for one telemetry frame."""
        deadline = time.monotonic() + QUERY_RECEIVE_TIMEOUT * QUERY_RECEIVE_ATTEMPTS
        outer_datapoints: set[str] = set()
        while time.monotonic() < deadline:
            result = device.receive()
            outer_datapoints.update(
                str(datapoint) for datapoint in extract_outer_datapoints(result)
            )
            payload = extract_telemetry_payload(result)
            if payload is None:
                continue
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry
        if outer_datapoints:
            _LOGGER.debug(
                "No recognized Poolex telemetry frame in outer Tuya datapoints: %s",
                sorted(outer_datapoints),
            )
        return None

    def _read_frame(self, device: tinytuya.Device) -> dict[str, Any] | None:
        """Use the vendor query and the two known LAN refresh fallbacks."""
        device.send(self._query_payload(device))
        telemetry = self._drain_frame(device)
        if telemetry is not None:
            return telemetry

        # Some firmware revisions only publish DP 21 after a LAN DP refresh.
        refresh_result = device.updatedps([4103])
        payload = extract_telemetry_payload(refresh_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry
        telemetry = self._drain_frame(device)
        if telemetry is not None:
            return telemetry

        # AP_CONFIG is a read-only product/status request on this device and
        # has returned the same current DP 21 frame on observed firmware.
        product_result = device.product()
        payload = extract_telemetry_payload(product_result)
        if payload is not None:
            telemetry = decode_telemetry(payload)
            if telemetry is not None:
                return telemetry
        return self._drain_frame(device)

    def _poll_sync(self) -> dict[str, Any]:
        """Poll the inverter from a worker thread."""
        try:
            device = self._get_device()
            telemetry = self._read_frame(device)
        except (
            OSError,
            TimeoutError,
            ValueError,
            RuntimeError,
            tinytuya.DecodeError,
        ) as err:
            self._close_device()
            raise PoolexCommunicationError("Tuya LAN request failed") from err

        if telemetry is None:
            self._close_device()
            raise PoolexCommunicationError(
                "The inverter did not return a telemetry frame"
            )
        return telemetry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and decode one local telemetry frame."""
        async with self._device_lock:
            try:
                return await self.hass.async_add_executor_job(self._poll_sync)
            except PoolexCommunicationError as err:
                raise UpdateFailed(str(err)) from err

    async def async_shutdown(self) -> None:
        """Close the local session when the config entry is unloaded."""
        await super().async_shutdown()
        async with self._device_lock:
            await self.hass.async_add_executor_job(self._close_device)
