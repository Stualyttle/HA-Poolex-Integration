"""Constants for the Poolex local solar inverter integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from .protocol_constants import (
    DP_AC_CURRENT,
    DP_AC_FREQUENCY,
    DP_AC_POWER,
    DP_AC_VOLTAGE,
    DP_ALARM_CODE,
    DP_OUTPUT_LIMIT,
    DP_POWER_FACTOR,
    DP_PV1_CURRENT,
    DP_PV1_POWER,
    DP_PV1_VOLTAGE,
    DP_PV2_CURRENT,
    DP_PV2_POWER,
    DP_PV2_VOLTAGE,
    DP_TEMPERATURE,
)

DOMAIN = "poolex"
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)

CONF_DEVICE_ID = "device_id"
CONF_DEVICE_IP = "device_ip"
CONF_LOCAL_KEY = "local_key"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 30
MIN_POLL_INTERVAL = 10
MAX_POLL_INTERVAL = 300

TUYA_PORT = 6668
TUYA_VERSION = 3.5
RAW_DP_IDS = tuple(range(9, 56))

DEVICE_NAME = "Poolex TSOL-MX800 Balcony"
DEVICE_MANUFACTURER = "Poolex / TSUN"
DEVICE_MODEL = "PV-KITPNP-900 / TSOL-MX800"

KNOWN_RAW_DP_IDS = frozenset(
    {
        DP_AC_VOLTAGE,
        DP_AC_CURRENT,
        DP_AC_FREQUENCY,
        DP_POWER_FACTOR,
        DP_ALARM_CODE,
        DP_OUTPUT_LIMIT,
        DP_AC_POWER,
        DP_PV1_VOLTAGE,
        DP_PV1_CURRENT,
        DP_PV1_POWER,
        DP_PV2_VOLTAGE,
        DP_PV2_CURRENT,
        DP_PV2_POWER,
        DP_TEMPERATURE,
    }
)
UNKNOWN_RAW_DP_IDS = tuple(dp_id for dp_id in RAW_DP_IDS if dp_id not in KNOWN_RAW_DP_IDS)


def build_device_info(entry) -> dict:
    """Return common device information for all entities."""
    return {
        "identifiers": {(DOMAIN, entry.data[CONF_DEVICE_ID])},
        "name": DEVICE_NAME,
        "manufacturer": DEVICE_MANUFACTURER,
        "model": DEVICE_MODEL,
    }


SENSOR_DEFINITIONS = (
    {
        "key": "status",
        "device_class": SensorDeviceClass.ENUM,
        "options": ("producing", "idle", "alarm"),
        "icon": "mdi:solar-power",
    },
    {
        "key": "ac_output_power",
        "dp_id": DP_AC_POWER,
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:transmission-tower-export",
    },
    {
        "key": "dc_input_power",
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:solar-power",
    },
    {
        "key": "ac_voltage",
        "dp_id": DP_AC_VOLTAGE,
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": "V",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 1,
    },
    {
        "key": "ac_current",
        "dp_id": DP_AC_CURRENT,
        "device_class": SensorDeviceClass.CURRENT,
        "unit": "A",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 2,
    },
    {
        "key": "ac_frequency",
        "dp_id": DP_AC_FREQUENCY,
        "device_class": SensorDeviceClass.FREQUENCY,
        "unit": "Hz",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 2,
    },
    {
        "key": "ac_power_factor",
        "dp_id": DP_POWER_FACTOR,
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "unit": "%",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 1,
    },
    {
        "key": "pv1_voltage",
        "dp_id": DP_PV1_VOLTAGE,
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": "V",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 1,
    },
    {
        "key": "pv1_current",
        "dp_id": DP_PV1_CURRENT,
        "device_class": SensorDeviceClass.CURRENT,
        "unit": "A",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 2,
    },
    {
        "key": "pv1_power",
        "dp_id": DP_PV1_POWER,
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:solar-panel",
    },
    {
        "key": "pv2_voltage",
        "dp_id": DP_PV2_VOLTAGE,
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": "V",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 1,
    },
    {
        "key": "pv2_current",
        "dp_id": DP_PV2_CURRENT,
        "device_class": SensorDeviceClass.CURRENT,
        "unit": "A",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 2,
    },
    {
        "key": "pv2_power",
        "dp_id": DP_PV2_POWER,
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:solar-panel",
    },
    {
        "key": "output_power_limit",
        "dp_id": DP_OUTPUT_LIMIT,
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "inverter_temperature",
        "dp_id": DP_TEMPERATURE,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": "°C",
        "state_class": SensorStateClass.MEASUREMENT,
        "precision": 1,
    },
)
