"""Sensor entities for the Poolex local solar inverter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    DOMAIN,
    SENSOR_DEFINITIONS,
    UNKNOWN_RAW_DP_IDS,
    build_device_info,
)
from .coordinator import PoolexCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Poolex sensors."""
    coordinator: PoolexCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        PoolexSensor(coordinator, entry, definition)
        for definition in SENSOR_DEFINITIONS
    ]
    entities.extend(
        PoolexRawDatapointSensor(coordinator, entry, datapoint)
        for datapoint in UNKNOWN_RAW_DP_IDS
    )
    entities.append(PoolexRawFrameSensor(coordinator, entry))
    async_add_entities(entities)


class PoolexSensor(CoordinatorEntity[PoolexCoordinator], SensorEntity):
    """A decoded Poolex sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolexCoordinator,
        entry: ConfigEntry,
        definition: dict[str, Any],
    ) -> None:
        """Initialize a decoded sensor."""
        super().__init__(coordinator)
        key = definition["key"]
        self._key = key
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = build_device_info(entry)
        self._attr_device_class = definition.get("device_class")
        self._attr_native_unit_of_measurement = definition.get("unit")
        self._attr_state_class = definition.get("state_class")
        self._attr_entity_category = definition.get("entity_category")
        if definition.get("options") is not None:
            self._attr_options = definition["options"]
        if "icon" in definition:
            self._attr_icon = definition["icon"]
        if "precision" in definition:
            self._attr_suggested_display_precision = definition["precision"]

    @property
    def native_value(self) -> Any:
        """Return the current decoded value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        """Only expose a value while a fresh telemetry frame is available."""
        return super().available and self.native_value is not None


class PoolexRawDatapointSensor(
    CoordinatorEntity[PoolexCoordinator], SensorEntity
):
    """Expose an observed but not yet semantically mapped raw datapoint."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: PoolexCoordinator,
        entry: ConfigEntry,
        datapoint: int,
    ) -> None:
        """Initialize a raw datapoint sensor."""
        super().__init__(coordinator)
        self._datapoint = datapoint
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_raw_dp_{datapoint}"
        self._attr_name = f"Raw Datapoint {datapoint}"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> int | None:
        """Return the raw unsigned 16-bit datapoint value."""
        if self.coordinator.data is None:
            return None
        raw_dps = self.coordinator.data.get("raw_dps", {})
        return raw_dps.get(self._datapoint)

    @property
    def available(self) -> bool:
        """Report unavailable until this datapoint has been observed."""
        return super().available and self.native_value is not None


class PoolexRawFrameSensor(
    CoordinatorEntity[PoolexCoordinator], SensorEntity
):
    """Diagnostic sensor containing the complete decoded frame."""

    _attr_has_entity_name = True
    _attr_translation_key = "raw_frame"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:code-braces"

    def __init__(
        self, coordinator: PoolexCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the raw frame sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_raw_frame"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> float | None:
        """Use AC output power as the compact sensor state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("ac_output_power")

    @property
    def available(self) -> bool:
        """Keep the raw diagnostic unavailable for fallback idle data."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("communication_ok", True)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return raw datapoints and the original Base64 frame."""
        if self.coordinator.data is None:
            return None
        return {
            "raw_dps": self.coordinator.data.get("raw_dps", {}),
            "raw_payload": self.coordinator.data.get("raw_payload"),
            "alarm_code": self.coordinator.data.get("alarm_code"),
        }
