"""Tuya and proprietary telemetry decoding for the Poolex TSOL-MX800."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from typing import Any

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
    TELEMETRY_OUTER_DPS,
)


def decode_records(payload: str | bytes) -> dict[int, int]:
    """Decode the device's Base64 DP 21 value into raw register values.

    The observed frame has a two-byte header followed by six-byte records:
    ``01 03 30 <datapoint> <value high> <value low>``.  Resynchronising on
    the record marker keeps later datapoints readable if firmware inserts
    padding or an optional field.
    """
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, TypeError, ValueError):
        return {}

    if len(raw) < 8 or raw[:2] != b"\x03\x01":
        return {}

    records: dict[int, int] = {}
    marker = b"\x01\x03\x30"
    offset = 2
    while offset + 6 <= len(raw):
        if raw[offset : offset + 3] == marker:
            datapoint = raw[offset + 3]
            records[datapoint] = int.from_bytes(raw[offset + 4 : offset + 6], "big")
            offset += 6
        else:
            offset += 1
    return records


def extract_outer_datapoints(result: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return the outer Tuya datapoints from a decoded TinyTuya response."""
    if not isinstance(result, Mapping):
        return {}

    datapoints = result.get("dps")
    if isinstance(datapoints, Mapping):
        return datapoints

    data = result.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("dps"), Mapping):
        return data["dps"]
    return {}


def extract_telemetry_payload(result: Mapping[str, Any] | None) -> str | None:
    """Find the long raw telemetry payload in a Tuya response."""
    datapoints = extract_outer_datapoints(result)
    for outer_dp in TELEMETRY_OUTER_DPS:
        payload = datapoints.get(str(outer_dp))
        if payload is None:
            payload = datapoints.get(outer_dp)
        if isinstance(payload, str) and payload and decode_records(payload):
            return payload
    return None


def _scaled(records: Mapping[int, int], datapoint: int, divisor: float) -> float | None:
    """Return a scaled datapoint, preserving missing values as ``None``."""
    value = records.get(datapoint)
    if value is None:
        return None
    return round(value / divisor, 2 if divisor >= 100 else 1)


def decode_telemetry(payload: str | bytes) -> dict[str, Any] | None:
    """Decode one live Poolex telemetry frame into Home Assistant values."""
    records = decode_records(payload)
    if not records:
        return None

    pv1_power = _scaled(records, DP_PV1_POWER, 10)
    pv2_power = _scaled(records, DP_PV2_POWER, 10)
    dc_input_power = (
        round(sum(value for value in (pv1_power, pv2_power) if value is not None), 1)
        if pv1_power is not None or pv2_power is not None
        else None
    )

    alarm_code = records.get(DP_ALARM_CODE)
    ac_output_power = _scaled(records, DP_AC_POWER, 10)
    status = "alarm" if alarm_code else (
        "producing"
        if (ac_output_power or 0) > 0 or (dc_input_power or 0) > 0
        else "idle"
    )

    return {
        "communication_ok": True,
        "status": status,
        "ac_output_power": ac_output_power,
        "dc_input_power": dc_input_power,
        "ac_voltage": _scaled(records, DP_AC_VOLTAGE, 10),
        "ac_current": _scaled(records, DP_AC_CURRENT, 100),
        "ac_frequency": _scaled(records, DP_AC_FREQUENCY, 100),
        "ac_power_factor": _scaled(records, DP_POWER_FACTOR, 1),
        "pv1_voltage": _scaled(records, DP_PV1_VOLTAGE, 10),
        "pv1_current": _scaled(records, DP_PV1_CURRENT, 100),
        "pv1_power": pv1_power,
        "pv2_voltage": _scaled(records, DP_PV2_VOLTAGE, 10),
        "pv2_current": _scaled(records, DP_PV2_CURRENT, 100),
        "pv2_power": pv2_power,
        "output_power_limit": _scaled(records, DP_OUTPUT_LIMIT, 1),
        "inverter_temperature": _scaled(records, DP_TEMPERATURE, 1),
        "alarm_code": alarm_code,
        "raw_dps": dict(sorted(records.items())),
        "raw_payload": (
            payload.decode("ascii") if isinstance(payload, bytes) else payload
        ),
    }
