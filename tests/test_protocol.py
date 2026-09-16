"""Tests for the Poolex telemetry decoder."""

from __future__ import annotations

import base64
import unittest

from custom_components.poolex.protocol import (
    decode_records,
    decode_telemetry,
    extract_telemetry_payload,
)


def encoded_records(*records: tuple[int, int]) -> str:
    """Build a valid Poolex frame for a decoder test."""
    payload = bytearray((0x03, 0x01))
    for datapoint, value in records:
        payload.extend((0x01, 0x03, 0x30, datapoint))
        payload.extend(value.to_bytes(2, "big"))
    return base64.b64encode(payload).decode()


class ProtocolTests(unittest.TestCase):
    """Validate raw and scaled Poolex values."""

    def test_decode_records(self) -> None:
        payload = encoded_records((9, 2288), (15, 705), (28, 32))
        self.assertEqual(
            decode_records(payload),
            {9: 2288, 15: 705, 28: 32},
        )

    def test_decode_telemetry(self) -> None:
        payload = encoded_records(
            (9, 2288),
            (10, 30),
            (11, 5002),
            (12, 78),
            (13, 0),
            (14, 800),
            (15, 705),
            (16, 283),
            (17, 111),
            (18, 316),
            (19, 284),
            (20, 150),
            (21, 427),
            (28, 32),
        )
        telemetry = decode_telemetry(payload)

        self.assertIsNotNone(telemetry)
        assert telemetry is not None
        self.assertTrue(telemetry["communication_ok"])
        self.assertEqual(telemetry["status"], "producing")
        self.assertEqual(telemetry["ac_voltage"], 228.8)
        self.assertEqual(telemetry["ac_current"], 0.3)
        self.assertEqual(telemetry["ac_frequency"], 50.02)
        self.assertEqual(telemetry["ac_power_factor"], 78.0)
        self.assertEqual(telemetry["ac_output_power"], 70.5)
        self.assertEqual(telemetry["dc_input_power"], 74.3)
        self.assertEqual(telemetry["inverter_temperature"], 32.0)

    def test_extract_telemetry_from_outer_dp25(self) -> None:
        payload = encoded_records((9, 2304), (15, 5009), (28, 49))
        self.assertEqual(
            extract_telemetry_payload({"dps": {"25": payload}}),
            payload,
        )

    def test_invalid_payload_is_ignored(self) -> None:
        self.assertEqual(decode_records("not-base64"), {})
        self.assertIsNone(decode_telemetry("not-base64"))


if __name__ == "__main__":
    unittest.main()
