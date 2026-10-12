# Connect an ASTRA-BIO tray

The software path is **ESP32 → MQTT → Node-RED validation → SQLite → Live tray**.
Planning stays separate from sensor logging. The default firmware measures
sensors and keeps outputs off.

## Start on this laptop

Open PowerShell in D:\Seds\astra-bio:

~~~powershell
.\setup-mqtt.ps1 -LanHost 192.168.1.8
.\run-stack.ps1
~~~

Keep the stack terminal open. The supervisor starts the workspace broker and
Node-RED, and starts Streamlit if port 8501 does not already have a healthy app.
It stops only the processes it owns. In another terminal:

~~~powershell
.\test-mqtt.ps1
.\test-mqtt.ps1 -Tls
.\simulate-device.ps1 -Count 0 -Interval 5
~~~

Count 0 sends continuous **synthetic** readings. Use Ctrl+C to stop the
simulator. To stop the managed stack cleanly, use .\stop-stack.ps1.

Open the app at http://127.0.0.1:8501, choose **Live tray**, then select
synthetic / demo-tray-01. The label **SYNTHETIC MQTT TEST** distinguishes
broker-delivered generated data from recorded hardware measurements.
The local Node-RED editor is at http://127.0.0.1:1880.

The check requires an actual tagged SQLite receipt; PUBACK alone is insufficient.
It also tests authentication, topic permissions, retained telemetry rejection,
and the test collector's reconnect/resubscribe behavior. A TLS check from the
laptop verifies encryption and certificate trust; it does not prove another
device can cross the Windows firewall.

## Connect the ESP32-S3

Tray-01 is already provisioned, and its sensor-only firmware has compiled
successfully. It has not been flashed or bench-tested. To add another tray:

~~~powershell
.\provision-device.ps1 -DeviceId tray-02
~~~

Restart the stack after adding an account. Each device gets its own password and
only its own topics. Generated files are private and ignored by Git:

~~~text
runtime/hardware/tray-01/tray.yaml        ESPHome configuration
runtime/hardware/tray-01/secrets.yaml     enter Wi-Fi details here
runtime/hardware/tray-01/connection.json  for alternative Arduino/Python firmware
~~~

1. Put the laptop and board on the same trusted 2.4 GHz Wi-Fi network.
2. Enter your Wi-Fi SSID/password in that device's secrets.yaml. Keep the
   generated MQTT password and CA certificate. Configure a reachable NTP server:
   valid device time is required before cold-boot TLS connection.
3. Check the sample pin mapping and exact sensor board models against your wiring.
4. If Windows blocks inbound device connections, run
   .\enable-hardware-firewall.ps1 once in an elevated PowerShell. It allows
   only this broker's TCP 8883 on the configured private address from the local
   subnet on the Private network profile. It does not open the app/editor.
5. Use the pinned ESPHome helper (uv installs its tooling on first use):

   ~~~powershell
   .\firmware.ps1 -DeviceId tray-01 -Action Validate
   .\firmware.ps1 -DeviceId tray-01 -Action Flash
   ~~~

   The second command builds and flashes a physically attached board. Review
   its output locally. For a build without flashing, use -Action Build.
6. Choose hardware / tray-01 in Live tray after its first valid packet.

If the laptop's Wi-Fi IP changes, rerun setup with its new private IPv4 address,
restart the stack, and rebuild/reflash the affected devices. Setup updates
the server certificate and device connection files while preserving device
passwords and locally entered Wi-Fi settings. A reserved IP on your router
avoids this repeated step.

## Connection contract

| Setting | Value |
| --- | --- |
| Device broker | Current laptop private IPv4; TLS port **8883** |
| Collector broker | Authenticated loopback 127.0.0.1:1883 |
| Hardware username | Device ID, e.g. tray-01 |
| Simulator username | astra-simulator; reserved device demo-tray-01 |
| Collector username | astra-collector; read access only |
| Telemetry | astra-bio/devices/&lt;id&gt;/telemetry, QoS 1, **retain false** |
| Availability | astra-bio/devices/&lt;id&gt;/availability, online/offline, retained |
| Command | astra-bio/devices/&lt;id&gt;/command; device can read, no writer configured |

Hardware packets must contain matching device_id, source: "hardware" and at
least one finite sensor measurement. Only demo-tray-01 may use the synthetic
source on the device topic namespace. Missing sensors remain null, not zero.
The collector rejects retained telemetry and conflicting source/identity fields.
Hardware observation timestamps are collector receipt time; a device-supplied
clock is preserved separately as device_ts_utc. Neither authenticated identity
nor freshness proves sensor calibration or physical origin.

Retained availability is the **last reported state**. An online status alone
does not prove a fresh sensor packet. The UI shows selected-device packet age
separately, and expires an old collector-health check after 120 seconds.

## Sensors and limits

| Hardware | Measurement |
| --- | --- |
| ESP32-S3-DevKitC-1 | Wi-Fi telemetry |
| SHT31-D | Air temperature and relative humidity |
| DS18B20 | Solution temperature |
| VEML7700 | Illuminance in lux; not PPFD |
| INA260 | DC bus voltage/current/power; not whole-habitat energy |
| Float switch | Low-water state; not remaining liters |

Sample I2C pins are GPIO8/9; float GPIO4; DS18B20 GPIO5. Reserved pump/fan/light
driver inputs are GPIO6/7/10; optional STOP is GPIO16. This is a sample mapping,
not validated wiring. The code fixes actuation disabled and restores outputs off.
Sensor-only bench testing, physical calibration, reboot/disconnect behavior and
electrical default-off behavior still need the real board.

The laptop supervisor is foreground software, not a Windows service. No service
or firewall is installed automatically. Private credential files and CA keys
have restricted local permissions. Node-RED stores a separate unencrypted local
credential copy inside that restricted runtime directory; do not share
runtime/mqtt, runtime/hardware, or generated Node-RED flow credential files.

Mosquitto's official Windows payload is extracted into the workspace without
executing its installer. Version, source URLs, local integrity hashes and notices
are retained in runtime/mqtt/BINARY_PROVENANCE.json.
