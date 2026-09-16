"""Binary sensor entities for the Poolex local solar inverter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN, build_device_info
from .coordinator import PoolexCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Poolex alarm entity."""
    coordinator: PoolexCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolexAlarmSensor(coordinator, entry)])


class PoolexAlarmSensor(
    CoordinatorEntity[PoolexCoordinator], BinarySensorEntity
):
    """Report the device alarm code as a Home Assistant problem sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "alarm"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(
        self, coordinator: PoolexCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the alarm entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_alarm"
        self._attr_device_info = build_device_info(entry)

    @property
    def is_on(self) -> bool | None:
        """Return whether a non-zero alarm code is present."""
        if self.coordinator.data is None:
            return None
        alarm_code = self.coordinator.data.get("alarm_code")
        return alarm_code is not None and alarm_code != 0

    @property
    def available(self) -> bool:
        """Report unavailable until a frame with an alarm code is received."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("communication_ok", True)
            and self.coordinator.data.get("alarm_code") is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the numeric alarm code for troubleshooting."""
        if self.coordinator.data is None:
            return None
        return {"alarm_code": self.coordinator.data.get("alarm_code")}
