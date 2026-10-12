# Hardware telemetry in the dashboard

The Live tray page reads validated local observations. The current demo can send generated readings through the MQTT broker. A successful synthetic message verifies the transport path; it does not establish that an ESP32 or physical sensors are connected.

## Select the right stream

1. Open **Live tray**.
2. Choose **Hardware sensors** or **Synthetic test / replay**.
3. Choose the device ID. The prepared hardware configuration uses `tray-01`; the simulator uses `demo-tray-01`.
4. Click **Refresh device list** after connecting a new device.

The chosen stream refreshes every 10 seconds. Changing the selection or refreshing observations never runs a planning comparison. Use **Run comparison** on the What-if comparison page to submit planning inputs.

The device list includes recorded streams and reported availability. A device reporting online without a sensor packet still shows **No measurements received**. History and CSV export are filtered to the selected device and source, so frequent synthetic messages cannot hide an older hardware tray.

## Prepare a physical tray

Run from the project folder in PowerShell:

```powershell
.\setup-mqtt.ps1
.\provision-device.ps1 -DeviceId tray-01
.\run-stack.ps1
```

Provisioning prepares local device files and credentials. Add Wi-Fi settings to the generated local secrets, then flash the prepared sensor-only ESPHome configuration. Provisioning does not flash hardware or establish calibration. Follow the wiring instructions for the selected sensors and use the same network as the broker computer. After the first hardware message, refresh the device list and choose **Hardware sensors → tray-01**.

## Read connection status correctly

| Dashboard status | Meaning |
| --- | --- |
| MQTT collector is connected | A recent runtime health check reports a collector connection to the broker. It does not prove device delivery. |
| Broker status unknown | The health file is absent, invalid or older than 120 seconds, or its clock is more than 120 seconds in the future. |
| Latest delivery check | A recorded check with its own timestamp, device and source. A synthetic check does not validate hardware. |
| Last reported device status: online / offline | The last recorded retained MQTT availability state. It does not prove a current connection. Packet freshness is checked separately. |
| Stale telemetry | No valid receipt/record within 120 seconds. Saved readings remain visible. |
| No reading | The latest packet omitted that sensor value. Missing values are not replaced with zero or a previous reading. |
| SYNTHETIC MQTT TEST | Generated data passed through MQTT. There are no physical sensor observations in this stream. |
| SYNTHETIC REPLAY | Stored generated data; this label makes no MQTT delivery claim. |

For MQTT hardware packets, Node-RED records collector UTC and receipt time. A supplied device timestamp is shown separately. A recent packet does not establish that every sensor works or has been calibrated.

## Declared sensors and units

| Observation | Prepared sensor | Unit |
| --- | --- | --- |
| Air temperature / relative humidity | SHT31 | °C / % |
| Solution temperature | DS18B20 | °C |
| Light trend | VEML7700 | lux; not PPFD |
| DC bus voltage / current / power | INA260 | V / A / W |
| Low-water flag | Float switch | 0 / 1; missing means unknown |

The DC power reading covers only the instrumented circuit. Lux does not directly measure photosynthetic photon flux. A low-water flag is a tray observation, not a measurement of the whole habitat's available water.

## Transport and scope

The prepared path is **ESP32 sensors → local MQTT broker → Node-RED validation → SQLite → Live tray**. Telemetry and retained availability use device-scoped topics:

```text
astra-bio/devices/<device-id>/telemetry
astra-bio/devices/<device-id>/availability
```

Keep device credentials in local secrets. The dashboard reads only allowlisted public broker status fields and never displays the broker configuration or credentials. Telemetry CSV exports omit the raw JSON payload.

Hardware observations do not automatically change nutritional targets, infer crop nutrient content, diagnose deficiencies or run the planner. Actuation remains disabled; this dashboard has no output-enabling or actuator-control UI. Crew, food composition and crop-yield estimates remain explicit planning inputs until validated integrations are implemented.
