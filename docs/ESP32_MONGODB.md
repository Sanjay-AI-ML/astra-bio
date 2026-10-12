# ESP32-S3 Wi-Fi → ASTRA-BIO gateway → MongoDB Atlas

The ESP32-S3 WROOM board collects the sensors' actual readings and sends them over Wi-Fi using HTTPS. The Python gateway validates each sample, authenticates the device and stores it in MongoDB Atlas. ASTRA-BIO reads the telemetry through its backend; the browser and ESP32 do not receive database credentials.

```text
ESP32-S3 WROOM + confirmed sensors
            │ Wi-Fi / verified HTTPS / device-specific token
            ▼
https://<laptop-LAN-IP>:8502/v1/telemetry
            │ Python gateway / PyMongo / TLS
            ▼
       MongoDB Atlas
            │ backend telemetry queries
            ▼
      ASTRA-BIO Devices screen
```

The laptop gateway must be running and reachable on the same Wi-Fi for this local setup. Cloud storage does not make a local gateway reachable when the laptop sleeps or leaves the network. A future hosted gateway can use the same payload contract with a public HTTPS hostname and its appropriate CA certificate.

## 1. Configure Atlas

1. Create your MongoDB Atlas project and a cluster using the Atlas account you control.
2. Create a dedicated database user with `readWrite` access only to the application's database, normally `astra_bio`. Use a strong generated password. This database user is different from your Atlas login.
3. In Network Access, allow the **public outbound IP of the laptop/gateway**. Atlas sees the gateway connection, not the ESP32's private Wi-Fi address. Add a specific IP rather than opening access to every IP. If your router's public IP changes, update the Atlas allowlist.
4. Open the cluster's Connect → Drivers → Python instructions and copy its `mongodb+srv://...` connection string. Substitute the database username/password; percent-encode reserved characters in credentials according to the driver instructions.
5. Keep that URI in private server configuration. Do not paste it into chat, slides, frontend code, firmware or screenshots.

Atlas requires TLS, database user authentication and an allowed network origin. These steps follow [MongoDB's cluster security documentation](https://www.mongodb.com/docs/atlas/setup-cluster-security/) and [the official Python connection guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/).

## 2. Prepare the local gateway

From `D:\Seds\astra-bio`, run:

```powershell
.\setup-mongodb.ps1 -DeviceId tray-01
```

The setup prompts privately for the Atlas connection string and can collect the Wi-Fi details. It prepares the local gateway TLS certificate, device token and a private firmware header at:

```text
runtime/mongodb/device-tray-01-config.h
```

Setup saves configuration but does not claim a successful Atlas connection. Check the database connection and required indexes first:

```powershell
.\.venv\Scripts\python.exe -m astra_bio.mongo_runtime check
```

Then start the gateway in its own terminal:

```powershell
.\run-gateway.ps1
```

To select a specific private Wi-Fi address during setup, use `-LanHost 192.168.1.50` with your laptop's actual address. Provisioning the same device again rotates its token; copy the newly generated header and reflash that device.

With the gateway running, a second terminal can test the complete software path without a board:

```powershell
.\test-mongodb.ps1 -DeviceId tray-01
```

This intentionally inserts **one synthetic reading** through verified HTTPS, resends it and queries MongoDB to confirm there is exactly one matching record. It never claims physical sensor validation. View it under Live devices → Synthetic test / replay.

Use the gateway's displayed LAN URL on the ESP32. `127.0.0.1` refers to the ESP32 itself when used from firmware and cannot reach your laptop. The certificate must cover the exact IP/hostname in the URL. If that LAN IP changes, regenerate the certificate/configuration and update the board. A router DHCP reservation is useful for keeping the gateway's LAN address stable.

Allow inbound TCP port 8502 for this gateway on your trusted private network if Windows Firewall blocks the device. Do not expose the unauthenticated local dashboard as a public service. Start/restart the main app with the generated MongoDB configuration loaded to use Atlas as its telemetry source.

The ESP32 receives the gateway's **public CA certificate** and its own device token. Only the gateway needs the Atlas URI and private TLS key. The firmware uses `setCACert()` for server verification, following [Espressif's HTTPS client guidance](https://github.com/espressif/arduino-esp32/blob/master/libraries/NetworkClientSecure/README.md).

Provisioning an existing device rotates its token, so copy its regenerated header and rebuild/flash the board. Authentication reloads the private device registry on each request; the old token stops working immediately. Restart the gateway after changing its LAN IP, port or TLS certificate. An already running HTTPS listener keeps its loaded certificate until restart.

## 3. Flash the sensor-independent starter

The firmware is in `integration/esp32-mongodb/`. Copy the generated header to `integration/esp32-mongodb/include/config.h`, then build using the [firmware README](../integration/esp32-mongodb/README.md).

Only the board family is known so far. Confirm the exact carrier/flash/PSRAM variant and connected sensor models before selecting board settings or wiring GPIOs. No sensor driver or pin assignment is guessed. The hardware hook is empty and refuses to upload until at least one real measurement is supplied.

For a connection test, explicitly enable `TELEMETRY_SYNTHETIC_DEMO` in the private header. The uploader prints a clear warning and stores the test fixture as `source: "synthetic"`. Disable that option when wiring real sensor reads; never relabel fixture values as hardware.

## Payload contract

Send `POST /v1/telemetry` with:

```http
Authorization: Bearer <this-device-token>
Content-Type: application/json
```

An example **synthetic** connection test:

```json
{
  "device_id": "tray-01",
  "sample_id": "demo_boot_0001",
  "source": "synthetic",
  "ts_utc": "2026-10-12T09:00:00Z",
  "air_temp_c": 23.5,
  "relative_humidity_pct": 60.0
}
```

Use a current timestamp when sending a test. For real hardware, `source` is `hardware` and the values come from real sensor reads. The fields are flat JSON, not nested under `measurements`. Omit unmeasured fields. `sample_id` is 1–96 letters, digits, `_` or `-`; `device_id` is 1–64 of those characters and must match the device token. `ts_utc` is an optional ISO timestamp with an explicit timezone; without it the server assigns a timestamp.

At least one finite numeric measurement is required. The existing telemetry limits apply:

| Field | Unit | Accepted range |
| --- | --- | --- |
| `air_temp_c` | °C | −50 to 80 |
| `relative_humidity_pct` | % | 0 to 100 |
| `solution_temp_c` | °C | −10 to 60 |
| `light_lux` | lux | 0 to 200,000 |
| `bus_voltage_v` | V | 0 to 36 |
| `bus_current_a` | A | 0 to 15 |
| `bus_power_w` | W | 0 to 540 |

Optional observed-state fields `low_water`, `pump_on`, `fan_on` and `light_on` accept 0/1. These flags do not issue actuator commands. Lux is not PAR/PPFD; bus power is not whole-habitat energy consumption. Water-level flags are not water-volume measurements. Sensor calibration and any physical conversion must be established for the real hardware.

HTTP 201 acknowledges a new stored sample. HTTP 200 acknowledges an identical duplicate. Retries must keep the same `sample_id`, content, provenance and timestamp. Reusing the ID with changed content is a conflict, not a new observation. The starter persists one pending sample and only clears it after acknowledgement.

## Confirm the complete path

1. Start the gateway and confirm its authenticated health endpoint reports the database connection as ready.
2. With the gateway running, run `.\.venv\Scripts\python.exe -m astra_bio.mongo_runtime probe --device-id tray-01` from another terminal. This deliberately inserts one synthetic test record through verified HTTPS, repeats the identical request and checks that only one record exists in Atlas. It does not validate the physical ESP32 or sensors.
3. Check that synthetic record in the Devices screen. You can also explicitly enable the firmware fixture mode to test Wi-Fi delivery from the board.
4. Implement the actual sensor driver hook, disable synthetic demo mode and flash the confirmed board profile.
5. Compare displayed readings with the sensor's local measurements/reference instrument, then disconnect/reconnect Wi-Fi to check retry behavior.

The gateway and sensor readings provide an input path. They do not establish autonomous actuator safety or make the crop/health models physically validated. Mission planning still requires appropriate nutrient, crop and resource inputs; displaying current temperature/humidity does not automatically recalibrate those models.

## Current limits

On 12 October 2026 Atlas was configured locally and the live software-path test passed: one synthetic sample through verified HTTPS, a duplicate retry acknowledged without an extra record, authenticated gateway health and dashboard readback. The [verification report](MONGODB_VERIFICATION.json) contains no credentials. The current laptop already had working Atlas network access; its access list was not changed. A measured cold connection exceeded the original three-second deadline, so remote operations now allow eight seconds while local MongoDB retains three seconds. These are per-operation bounds, not a guarantee for a whole HTTP request or all initial DNS lookups.

The physical sensor models, board variant and Wi-Fi credentials still require confirmation/configuration. The new uploader passed an actual release compile with isolated PlatformIO 6.2.0, pinned dependencies and a placeholder header on the generic ESP32-S3 DevKitC-1 N8/no-PSRAM profile. A checked short workspace junction resolved the initial Windows compiler command-length failure. The firmware has not been flashed. Existing ESPHome firmware validation is separate. The source includes verified TLS, explicit provenance, range checks, per-device authorization headers, bounded retries and a one-sample persistent queue; board flashing, confirmed sensor drivers and end-to-end measurements remain the hardware integration steps.
