# Poolex TSOL-MX800 Balcony Home Assistant integration

This custom integration locally polls the Tuya-enabled **Poolex PV-KITPNP-900 / TSUN TSOL-MX800 Balcony** inverter and exposes its two PV inputs, AC output, grid measurements, alarm state, temperature, output limit, and every additional raw datapoint reported by the device.

Communication is local only: Home Assistant connects directly to the inverter over Tuya protocol 3.5 on TCP port 6668. No Tuya cloud API is used for polling.

## HACS installation

1. Open HACS in Home Assistant.
2. Open **Integrations**, select the three-dot menu, and choose **Custom repositories**.
3. Add `https://github.com/Stualyttle/HA-Poolex-Integration` with category **Integration**.
4. Install **Poolex Solar Inverter** and restart Home Assistant.
5. Add **Poolex TSOL-MX800 Balcony** from **Settings > Devices & services > Add integration**.

## Configuration

The setup form requires:

| Field | Value |
| --- | --- |
| Device IP address | The inverter's reserved DHCP address, for example `192.168.1.100` |
| Tuya device ID | The device's virtual ID from the Tuya or Poolex app |
| Tuya local key | The 16-character local key from the Tuya IoT Platform |
| Poll interval | 30 seconds is recommended; the supported range is 10-300 seconds |

The local key is stored in Home Assistant's config entry and is never part of this repository. Keep it private and rotate it if it is disclosed.

## Entities

The integration creates a single device with these decoded entities:

- AC output power, voltage, current, frequency, and power factor
- DC input power and PV input 1/2 voltage, current, and power
- Inverter status (`Producing`, `Idle`, or `Alarm`)
- Alarm problem binary sensor with the numeric alarm code
- Inverter temperature
- Output power limit reported by the inverter
- Raw diagnostic sensors for every observed inner datapoint that does not yet have a confirmed semantic mapping
- An optional disabled-by-default raw telemetry frame sensor containing the complete Base64 frame and decoded values

The observed DP 21 payload is a proprietary binary frame. The mappings currently confirmed from the supplied live device are:

| Inner DP | Meaning | Conversion |
| ---: | --- | --- |
| 9 | AC voltage | raw / 10 V |
| 10 | AC current | raw / 100 A |
| 11 | AC frequency | raw / 100 Hz |
| 12 | AC power factor | raw % |
| 13 | Alarm code | zero means no alarm |
| 14 | Output power limit | raw W |
| 15 | AC output power | raw / 10 W |
| 16-18 | PV input 1 voltage/current/power | /10 V, /100 A, /10 W |
| 19-21 | PV input 2 voltage/current/power | /10 V, /100 A, /10 W |
| 28 | Inverter temperature | raw °C |

Unmapped datapoints are intentionally retained as numeric diagnostic entities so future firmware discoveries cannot silently lose information.

## Local polling behavior

The integration maintains one authenticated persistent Tuya LAN session, sends the vendor status query, and drains the response for the proprietary telemetry frame. It does not write configuration values or enable a push stream. If the inverter is unreachable, entities become unavailable and Home Assistant retries on the configured interval.

The device must be reachable from Home Assistant across the local network or VLAN. A DHCP reservation is recommended because the configured IP address is used directly.

## Development

The protocol-only tests can be run without Home Assistant:

```text
python -m unittest discover -s tests
```

Home Assistant installs the `tinytuya` requirement automatically from `manifest.json`.
