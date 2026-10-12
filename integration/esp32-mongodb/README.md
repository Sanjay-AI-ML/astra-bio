# ESP32-S3 HTTPS telemetry starter

This is the firmware starting point for the confirmed **ESP32-S3 WROOM** board. It sends flat JSON over verified HTTPS to ASTRA-BIO's gateway. The gateway holds the MongoDB Atlas credentials and writes the database records. No MongoDB URI goes on the ESP32.

Use the complete [setup guide](../../docs/ESP32_MONGODB.md) for Atlas, TLS and application configuration.

## Configure and build

1. From the application root, run `setup-mongodb.ps1` and configure the gateway.
2. Copy the generated `runtime/mongodb/device-tray-01-config.h` to `integration/esp32-mongodb/include/config.h`. Alternatively, copy `include/config.example.h` and fill the placeholders privately. `config.h` is Git-ignored.
3. Confirm the carrier board, flash/PSRAM variant and USB/upload settings. The PlatformIO `esp32-s3-devkitc-1` profile is a **generic toolchain starting point**, not a confirmed pinout for every ESP32-S3 WROOM board. The current profile describes the DevKitC-1 N8 variant without PSRAM. No sensor GPIO is assigned.
4. From this firmware directory, compile without flashing using the project's Python environment and `uv`:

```powershell
.\build.ps1
```

The helper pins PlatformIO Core 6.2.0 and keeps downloaded tooling under `runtime/hardware/esp32-mongodb-tooling/`. It uses a short workspace junction (`D:\Seds\p` in this checkout) to avoid the Windows Xtensa compiler's command-length failure when expanding the framework's many include paths. The actual toolchain stays in `runtime/`; an existing alias is reused only if it points to that exact directory, otherwise the helper stops without changing it. If no private header exists, it copies the placeholder header for compilation only. An existing private header is preserved. It never uploads firmware.

Alternatively, open this folder with PlatformIO in VS Code, or use an existing PlatformIO CLI:

```powershell
pio run
# After confirming the actual board/upload port:
pio run --target upload --upload-port COM7
pio device monitor --port COM7 --baud 115200
```

`COM7` is an example; use the port shown for your board. First build downloads the pinned platform/toolchain and ArduinoJson dependency if absent. To use Arduino IDE instead, copy `src/main.cpp` as an `.ino` file in a sketch directory, keep `config.h` alongside it, install ArduinoJson 7.4.3 and the Espressif Arduino board package, then select the actual ESP32-S3 board variant.

## Hardware and explicit demo modes

`TELEMETRY_SYNTHETIC_DEMO` defaults to `false`. Add confirmed sensor initialization to `beginHardwareSensors()` and measured values to `readHardwareMeasurements()` in `src/main.cpp`. The starter's empty hook returns no readings and refuses to upload. `NAN` measurements and `-1` flags are omitted. Failed sensors never become zero values.

For a deliberate connection test before sensors are available, set `TELEMETRY_SYNTHETIC_DEMO` to `true` in your private `config.h`, rebuild and flash. Serial output warns that fixture values are synthetic, and each record has `source: "synthetic"`. Set it back to `false` for real sensors. A synthetic record already pending in NVS keeps its original source and content when replayed.

## Retry behavior

The uploader saves one serialized sample in ESP32 Preferences/NVS before sending. It uses a random boot identifier plus sequence for `sample_id`, and preserves the exact payload across retries and restarts. HTTP 201 means created; HTTP 200 means the same sample was already accepted. Only those acknowledgements clear the pending record. Retries back off from 2 seconds to 60 seconds with jitter; Wi-Fi reconnects and NTP resynchronization are bounded attempts. HTTPS connection/handshake/read timeouts are set; no infinite connection-wait loop is used.

This is a **single pending sample**, not an offline historical queue: sampling pauses while that sample awaits acknowledgement, so measurements during an outage are not recorded. NVS writes also have a finite flash lifetime; the 15-second interval is for initial integration. Plan an appropriate interval and buffered batching/flash storage if long outages or continuous high-rate recording are required.

Permanent request errors (most 4xx responses) pause uploads and retain the record. Fix credentials/configuration or inspect rejected data before restarting. A pending sample belonging to another device disables uploads. Changing its content under the same `sample_id` is deliberately prohibited. Erasing the board's NVS will discard pending data; only do so after inspecting or intentionally abandoning that sample.

UTC clock synchronization is required before the verified TLS connection starts. The payload contract allows the timestamp to be omitted and assigned by the server, but that does not remove TLS certificate validity checks. Use a reachable NTP server or a trusted RTC if your Wi-Fi network blocks NTP.

## Verification status

On 12 October 2026 the uploader **passed an actual release compile** using `build.ps1`, PlatformIO Core 6.2.0, the pinned dependencies and a placeholder header. The generic `esp32-s3-devkitc-1` N8/no-PSRAM profile produced `firmware.bin` and `firmware.elf`. Reported usage was 45,460 of 327,680 RAM bytes (13.9%) and 885,793 of 3,342,336 application flash bytes (26.5%). The initial Windows compiler command-length failure was resolved with the checked short workspace junction; the example CA macro was corrected during compilation. This confirms that the starter builds for that generic profile. **It has not been flashed or verified on the physical ESP32-S3**, and the actual carrier/flash/PSRAM variant must still be confirmed. Earlier ESPHome builds belong to a different integration.

The implementation follows [Espressif's certificate verification guidance](https://github.com/espressif/arduino-esp32/blob/master/libraries/NetworkClientSecure/README.md). The toolchain profile is documented by [PlatformIO](https://docs.platformio.org/en/latest/boards/espressif32/esp32-s3-devkitc-1.html); platform and JSON versions are pinned to [Espressif32 7.1.3](https://github.com/platformio/platform-espressif32/releases/tag/v7.1.3) and [ArduinoJson 7.4.3](https://github.com/bblanchon/ArduinoJson/releases/tag/v7.4.3).

