# ESP32-S3 camera → MongoDB Atlas

This firmware captures a real JPEG from the camera and sends it to ASTRA-BIO's authenticated HTTPS image gateway. The gateway stores the photograph and its metadata in MongoDB Atlas; database credentials stay on the laptop. It has no actuator commands and does not assign any other sensor GPIOs.

## Confirmed processor / candidate camera map

The attached device was identified by the parent hardware task on 12 October 2026 as ESP32-S3 revision 0.2 with 16 MB quad flash and 8 MB embedded octal PSRAM. The build overrides the generic DevKitC-1 N8 board description to the **N16R8 / `qio_opi`** memory profile. `BOARD_HAS_PSRAM`, the 16 MB partition table and UART serial bridge are configured in `platformio.ini`. Carrier identity and image sensor identification are separate checks.

The pin map below is exactly the map supplied from the user's camera test. It is now physically verified with the detected GC2145 sensor (PID 0x2145):

| Camera signal | ESP32 GPIO |
| --- | --- |
| SIOD / SCCB SDA | 4 |
| SIOC / SCCB SCL | 5 |
| VSYNC | 6 |
| HREF | 7 |
| PCLK | 13 |
| XCLK | 15 |
| D0–D7 | 11, 9, 8, 10, 12, 18, 17, 16 |
| PWDN, RESET | -1, -1 (not assigned) |

XCLK remains **10 MHz**, matching the supplied test. Capture first tries native JPEG, VGA (640×480), quality 12, one frame buffer and PSRAM. If PSRAM is unavailable, it selects QVGA and DRAM. If the sensor explicitly rejects JPEG with `ESP_ERR_NOT_SUPPORTED` (0x106), it deinitializes and retries **RGB565 QQVGA (160×120)** using the same supplied pins. The RGB565 frame is converted with Espressif's `frame2jpg(..., 80, ...)` to an owned JPEG buffer; the raw camera buffer is immediately returned, and the encoded bytes remain unchanged until acknowledged/discarded. Other initialization errors do not trigger random pin changes. Each requested new capture drops a possibly queued old buffer first. This low fallback resolution is for reliable initial connectivity, and must be assessed before using photographs for plant/fruit screening.

## Private configuration and compile

1. Copy `runtime/mongodb/device-tray-01-config.h` from the application root to this directory's `include/config.h`. The existing generated `WIFI_SSID`, `WIFI_PASSWORD`, `GATEWAY_URL`, `DEVICE_ID`, `DEVICE_TOKEN` and `ROOT_CA` names are reused. `config.h` is ignored by Git.
2. Set Wi-Fi details privately. The device needs a reachable **2.4 GHz** network. If the laptop address changes, regenerate the gateway certificate/device configuration so its certificate covers the address used in the URL.
3. The firmware derives `/v1/images` from the generated `/v1/telemetry` endpoint. Alternatively define `IMAGE_GATEWAY_URL` explicitly in the private header. TLS verification stays enabled; there is no `setInsecure()` fallback. UTC must synchronize by NTP before TLS.
4. Compile from the application root:

```powershell
.\integration\esp32-camera-mongodb\build.ps1
```

The compile-only helper reuses pinned PlatformIO Core 6.2.0 and the Espressif32 7.1.3 toolchain under `runtime/hardware/esp32-mongodb-tooling/`. It reuses the checked short junction `D:\Seds\p` to avoid the Windows compiler command-length limit. It does not open a serial port or flash the board. Without a private header it creates the placeholder header for compile verification; camera/USB capture still works, but Wi-Fi uploads remain disabled until configured.

Only flash after checking the physical board and keeping a recovery copy of its previous firmware. The parent task owns physical upload and COM-port checks. An ordinary CH343 UART bridge uses baud **115200** for diagnostics and binary capture; this build does not redirect `Serial` to native USB CDC.

## Network capture behavior

By default, one photograph is captured and uploaded after Wi-Fi and UTC are ready. No recurring camera loop is enabled. Send `c` plus newline over serial for another capture/upload. A JPEG is sent as the raw POST body to `/v1/images` with:

```text
Content-Type: image/jpeg
Authorization: Bearer <private device token>
X-Device-Id: <registered device id>
X-Sample-Id: cam-<random boot id>-<sequence>
X-Source: hardware
X-Transport: wifi_https
X-Captured-At: <UTC timestamp, when available>
```

Photographs must be at most 2 MiB. The device computes SHA-256 and keeps the **same frame bytes and sample ID** while a request is unresolved. A 200 or 201 response clears the buffer only when JSON has `id` (or `image_id`) and matching `sha256`, either at the top level or inside `image`. Normal retries use exponential backoff and jitter, up to five attempts. A permanent 4xx error pauses uploading and keeps the frame. `r` retries that same frame; `d` deliberately discards it. Missing Wi-Fi or UTC pauses transport, while USB commands remain available.

The pending frame lives in RAM/PSRAM. It survives retry attempts, **not a reboot or power loss**. This is a single pending image, not a persistent offline image queue. To enable deliberate periodic uploads later, set `CAMERA_UPLOAD_INTERVAL_MS` to at least 60000 in the private header; zero is the default. This option should only be enabled with an appropriate image retention/storage plan.

## USB capture fallback

Use `s` plus newline to receive an actual camera JPEG over USB without Wi-Fi. It captures a frame if none is pending, or retransmits the exact existing pending frame. Framing is:

```text
ASTRA_JPEG_BEGIN:<byte_length>:<sha256>:<sample_id>:<width>:<height>\n
<exactly byte_length binary JPEG bytes>
\nASTRA_JPEG_END\n
```

The laptop must parse the declared length, verify SHA-256, decode/check JPEG dimensions, and send the image to the same authenticated HTTPS endpoint. It should declare `X-Source: hardware` and `X-Transport: serial_bridge`, so the stored record distinguishes this path from board Wi-Fi.

Only after the server confirms storage, send `a <sample_id>` plus newline. The firmware releases the pending frame only when this acknowledgment matches. An interrupted serial download can be retried with `s` using the same bytes/sample; no new image is silently substituted. `d` explicitly abandons the pending frame. There is no unauthenticated camera HTTP server or continuous video stream.

The reusable `capture_usb.py` helper performs this fallback without resetting the board. Close any serial monitor first, then use a Python environment that includes `pyserial`:

```powershell
python .\integration\esp32-camera-mongodb\capture_usb.py --port COM8
```

Use the COM port actually identified for the connected board. The default private header is this firmware's ignored `include/config.h`; `--config` may name a different generated private header. The helper requests one frame with `s`, waits at most 60 seconds, verifies byte length, SHA-256, JPEG markers and encoded dimensions, then posts the exact bytes using the configured HTTPS LAN endpoint and trusted root CA. The gateway fully decodes the JPEG before storage. Redirects and external gateway addresses are refused. Only a matching MongoDB record ID, sample ID, hash, dimensions, device and hardware source allows `a <sample_id>`. An exact server-confirmed duplicate may retain its original `wifi_https` transport; the helper prints the actual stored transport rather than claiming a Wi-Fi success. No capture timestamp is invented from the laptop clock.

Images stay in memory by default. To deliberately keep a local copy, add `--output runtime/camera/capture.jpg`; the path must be a new JPEG file inside the ignored project runtime directory. Private token, Wi-Fi password, certificate and complete configuration are never printed. This path verifies **USB serial → laptop HTTPS gateway → Atlas**, while direct board Wi-Fi remains a separate check. The helper is optional and never runs automatically or opens a port when imported. Its unit tests use fake serial/HTTP streams only.

| Serial command | Behavior |
| --- | --- |
| `i` | Chip, flash, PSRAM, camera, network/UTC and pending-frame diagnostics |
| `c` | Capture if no pending image; request verified Wi-Fi upload |
| `s` | Export exact pending/new JPEG through the framed USB protocol |
| `r` | Restart bounded upload retries for the existing pending JPEG |
| `a <sample_id>` | Confirm that the laptop bridge stored this pending image |
| `d` | Explicitly discard a pending image |

Serial diagnostics include detected camera PID, frame dimensions/length, sample ID, hash, Wi-Fi local IP, current UTC and HTTP status. On a negative HTTP transport status, they also include the secure client's bounded generic mbedTLS error code/description, so TCP reachability and certificate failures can be investigated separately. They do not print tokens, passwords, request headers or database credentials. The installed framework's secure-client timeout accepts seconds (`15`); HTTPClient's connect/read timeout values accept milliseconds (`10000` / `15000`). TLS verification remains enabled during diagnosis.

## Compile evidence and physical verification

**Physical Wi-Fi/Atlas verification passed on 12 October 2026.** The final diagnostics firmware was flashed on COM8 after retaining the original 16 MiB flash image privately. The GC2145 RGB565/software-JPEG path produced a 160×120, 3,457-byte frame; verified HTTPS returned 201 and Atlas stored its original bytes. MongoDB and dashboard content readback matched the board SHA-256. An exact retry returned 200 with one document for that sample. Three intentional boot-test images are stored. The Windows rule is scoped to the camera IP and port 8502. The gateway certificate now includes exact-IP DNS SANs as well as IP SANs for compatibility with this older TLS client; CA trust and certificate verification remain enabled. See [physical evidence](../../docs/CAMERA_VERIFICATION.json) and [operation guide](../../docs/CAMERA_MONGODB.md).

The default remains one capture after boot/network readiness. Pressing RESET triggers that boot capture; send `c` plus newline at 115200 for another frame. Keep the laptop API and HTTPS gateway running, then refresh **Live devices → Camera images**. Additional numerical sensors and physical USB relay execution remain unverified.

The release compile passed on 12 October 2026 with placeholder network values, using the N16R8 overrides and the installed Arduino ESP32 2.0.17 framework. The final adjusted source reported 50,216/327,680 bytes static RAM and 945,009/6,553,600 bytes application flash. Compilation confirms toolchain compatibility; the parent task must report separately whether camera initialization, JPEG transfer and Atlas readback succeeded on the attached hardware. A private configuration build changes the firmware checksum; credentials remain in the ignored device header and device binary.

The parent's first physical boot established Wi-Fi, UTC and 8 MB PSRAM, but the sensor rejected native JPEG with 0x106. The RGB565/software-JPEG fallback above was then implemented and release-compiled using the existing private header. The parent then physically identified **GC2145 (PID 0x2145)** and captured a 160×120, 1,693-byte software-encoded JPEG. Before the scoped firewall and TLS compatibility fixes, direct Wi-Fi uploading returned HTTP transport status `-1` despite Wi-Fi/NTP connection. A diagnostic build, with secure-client error reporting, passed compilation at 58,272/327,680 bytes static RAM and 957,397/6,553,600 bytes application flash. That diagnostics build was subsequently flashed and the direct Wi-Fi/Atlas path passed the physical check above. The USB bridge is an optional tested software fallback.

## Primary implementation references

- [Espressif camera driver](https://github.com/espressif/esp32-camera) documents JPEG's lower memory pressure during Wi-Fi and buffer ownership (`esp_camera_fb_get` / `esp_camera_fb_return`).
- [Espressif CameraWebServer example](https://github.com/espressif/arduino-esp32/tree/master/libraries/ESP32/examples/Camera/CameraWebServer) provides the Arduino camera configuration pattern.
- [PlatformIO DevKitC-1 profile](https://docs.platformio.org/en/latest/boards/espressif32/esp32-s3-devkitc-1.html) is the generic base; it does not determine this carrier's camera pinout.
- [Espressif secure network client](https://github.com/espressif/arduino-esp32/tree/master/libraries/NetworkClientSecure) documents certificate verification rather than insecure TLS.
