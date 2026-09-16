# Poolex TSOL-MX800 Balcony Home Assistant integration

This custom integration locally polls the Tuya-enabled **Poolex PV-KITPNP-900 / TSUN TSOL-MX800 Balcony** inverter and exposes its two PV inputs, AC output, grid measurements, alarm state, temperature, output limit, and every additional raw datapoint reported by the device.

Communication is local only: Home Assistant connects directly to the inverter over Tuya protocol 3.5 on TCP port 6668. No Tuya cloud API is used for polling.

The integration uses a fresh Tuya LAN session for every poll to avoid stale firmware sessions.

## Disclaimer

This is an independent personal project created for personal use and is not affiliated with, endorsed by, sponsored by, or supported by Poolex, TSUN, Tuya, or any of their affiliates. Poolex, TSUN, Tuya, and related names and marks belong to their respective owners. The integration is provided "as is", without support, warranty, guarantee, or assurance of compatibility, safety, accuracy, or continued operation. Use it at your own risk.

The project icon is an original solar-inverter illustration and is not the Poolex logo. For official product information, visit [Poolex](https://www.poolex.fr/en).

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

The integration opens a fresh authenticated Tuya LAN session for each poll, sends the vendor status query, drains the response for the proprietary telemetry frame, and closes the session afterward. This avoids stale-session failures on firmware that does not reliably keep TCP sessions alive. After a failed poll, it performs up to three short fresh-session retries before returning to the normal interval. It does not write configuration values or enable a push stream. If the inverter is unreachable, entities become unavailable and Home Assistant retries on the configured interval.

The device must be reachable from Home Assistant across the local network or VLAN. A DHCP reservation is recommended because the configured IP address is used directly.

Setup is non-blocking: the device and zero-production `Idle` entities are registered immediately, while the first local telemetry query runs in the background.

## Troubleshooting

Run a TCP check from the Home Assistant host or Terminal add-on against the inverter on port `6668`:

```text
nc -vz <inverter-ip> 6668
```

For detailed Tuya response diagnostics, temporarily enable these loggers in Home Assistant:

```yaml
logger:
  logs:
    custom_components.poolex: debug
    tinytuya: debug
```

`914` responses indicate a device ID, local key, or protocol mismatch. `902` responses indicate that the configured host did not receive a reply. If the port is reachable and the credentials are correct, stop other local Tuya clients while testing because the inverter may only allow one session.

After a successful setup, up to ten consecutive polling failures are treated as transient (normally around 10-15 minutes): the last successful values are retained while the session is rebuilt. If the inverter remains silent beyond that threshold, the integration assumes no solar production, reports zero for normal production/measurement sensors, and sets Status to `Idle`. Raw datapoints and diagnostic entities remain unavailable. A later successful frame automatically restores live values.

## Development

The protocol-only tests can be run without Home Assistant:

```text
python -m unittest discover -s tests
```

Home Assistant installs the `tinytuya` requirement automatically from `manifest.json`.
