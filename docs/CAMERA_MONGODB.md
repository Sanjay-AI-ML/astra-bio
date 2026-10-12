# ESP32 camera photographs in MongoDB Atlas

ASTRA-BIO accepts a JPEG captured or encoded from the camera through the authenticated HTTPS device gateway, stores those exact JPEG bytes in Atlas, and displays photographs in the local **Live devices → Camera images** view. Numerical readings remain in their existing telemetry collection. A camera-only board does not need to invent temperature, humidity or other measurements to send a photograph.

## Current verification status

On 12 October 2026, **120 backend tests passed** across `test_camera_storage.py`, `test_telemetry_gateway.py` and `test_mongo_telemetry.py`. These include 40 camera cases covering complete JPEG validation, byte-exact readback, timestamps, duplicate handling, source/device filters, auth, request limits and redacted errors. Certificate tests also verify exact IP/DNS identity scope and preservation of the existing CA during server certificate regeneration. These software tests use an injected in-memory MongoDB stand-in; the separate physical verification below used the attached board and live Atlas.

**Physical camera capture → board Wi-Fi → verified HTTPS → Atlas → local JPEG readback succeeded.** The attached ESP32-S3 N16R8 on COM8 initialized its **GC2145 (PID `0x2145`)**. This sensor does not provide native JPEG in the installed driver configuration, so the firmware captured **RGB565 at 160×120** and encoded JPEG in software.

The final verified capture was **3,457 bytes**, sample `cam-f238b9fa4863d24f-1`, stored as MongoDB ObjectId `6acca54b0f50c943a8491277`. Its SHA-256 was `bad4236992d9ed2482c53b8c7be684dc60a1b31ced2ba5806241d044374a0b2b`. The board received HTTP **201**, the MongoDB Binary and local HTTP image bytes matched the board checksum, and the JPEG fully decoded. Replaying the exact frame returned HTTP **200** with the same ID; the sample document count remained **one**. There are three hardware Wi-Fi images from deliberate boot/capture tests. Byte-exact verification concerns the encoded JPEG, not the raw RGB565 buffer.

The machine-readable evidence is [CAMERA_VERIFICATION.json](CAMERA_VERIFICATION.json); it contains safe metadata and hashes, without a physical photograph or credentials. Other physical sensor readings remain unverified. The USB helper has **26 passing software tests** but its physical serial-to-Atlas path was not exercised during this verification.

## Data path

```text
ESP32 camera → original JPEG → verified HTTPS /v1/images
             → existing per-device token authentication
             → Atlas / existing database / camera_images collection
             → localhost /api/camera-images + JPEG content endpoint
             → Live devices camera view
```

The verified path is board Wi-Fi (`transport: wifi_https`). The firmware also supports a framed USB capture; the laptop bridge then posts to the **same** authenticated HTTPS endpoint and declares `transport: serial_bridge`. This fallback is implemented and covered by software tests, with physical verification still pending. Keep these paths distinct in demonstrations and evidence.

Database credentials stay in the server's private MongoDB configuration. The ESP32 has only its Wi-Fi details, gateway URL, gateway CA certificate and a device-specific token in an ignored `include/config.h`. It never connects directly to Atlas or embeds a MongoDB URI.

## Run the software

From the application root, start each service in its own terminal:

```powershell
# Local dashboard/API at http://127.0.0.1:8501/
.\run.ps1
```

```powershell
# HTTPS device ingress at the private LAN address in existing settings
.\run-gateway.ps1
```

Existing Atlas/device provisioning is reused; **no new environment variable or database password** is required for camera images. The camera store borrows the existing process-local MongoDB client and uses the same selected database with a separate `camera_images` collection. If the laptop's LAN address changes, update private provisioning and regenerate the matching gateway certificate/device header before reconnecting the device.

The gateway certificate generator retains proper `IPAddress` SANs and includes the exact same IPv4 strings as `dNSName` SANs for the pinned ESP32 framework's older Mbed TLS verifier; this compatibility behavior is documented in [Mbed TLS issue #5082](https://github.com/Mbed-TLS/mbedtls/issues/5082). The only names are the configured gateway IPv4 address, `127.0.0.1` and `localhost`. This compatibility change was physically tested: regenerating the server certificate while preserving the original CA enabled the retained real frame's verified board upload. Certificate and hostname verification remain enabled.

The ESP32 and gateway must be reachable over the network. The board needs a compatible 2.4 GHz Wi-Fi network. A USB connection powers/programs the board; it does not automatically grant Wi-Fi connectivity. The laptop must remain running while it hosts the gateway.

Windows Firewall also requires an inbound rule for the gateway. The tested rule is restricted to **TCP 8502**, laptop address **172.16.58.241**, board address **172.16.59.109**, the Wi-Fi interface and its current Public network profile. It permits that board to reach the gateway; it does not expose the local planning API. If either DHCP address, interface or network profile changes, update the scoped rule and gateway/device configuration accordingly.

Firmware compilation, memory settings, the supplied camera pin map, recovery procedure and private header setup are documented in [the camera firmware guide](../integration/esp32-camera-mongodb/README.md). Camera GPIOs are the user's supplied candidate map; do not assign other sensors to those pins without checking the board and wiring. Flashing is a separate explicit hardware operation from the compile-only helper.

## Capture and upload

The camera firmware defaults to one capture/upload after Wi-Fi and UTC synchronization. Recurring capture is disabled. Its serial commands use 115200 baud:

| Command | Purpose |
| --- | --- |
| `i` | Show camera, memory, network/UTC and pending-frame diagnostics |
| `c` | Request a capture and verified Wi-Fi upload |
| `r` | Retry the same pending frame/sample ID |
| `s` | Export the pending/new JPEG through the framed USB protocol |
| `a <sample_id>` | Acknowledge storage after a verified USB bridge upload |
| `d` | Deliberately discard the pending frame |

The device keeps the same JPEG bytes and sample ID across retries. An acknowledgment must match its SHA-256 before the pending frame is released. The pending frame lives in RAM/PSRAM, not a persistent offline queue; rebooting can lose it.

### Device upload API

`POST https://<private-gateway-host>:8502/v1/images` accepts raw JPEG bytes, not a multipart form or base64 JSON:

```text
Authorization: Bearer <private device token>
Content-Type: image/jpeg
X-Device-Id: <provisioned device ID>
X-Sample-Id: <unique capture ID>
X-Source: hardware
X-Transport: wifi_https
X-Captured-At: <optional ISO timestamp including timezone>
```

`X-Source` must be `hardware` or `synthetic`. `X-Transport` must be `wifi_https` or `serial_bridge`; it defaults to `wifi_https` if omitted. A token may publish only for its registered `X-Device-Id`. HTTPS and certificate verification remain enabled. Browser `Origin` requests are rejected at the device ingress.

Successful response shape:

```json
{
  "id": "<Mongo ObjectId>",
  "duplicate": false,
  "storage": "mongodb",
  "image": {
    "id": "<Mongo ObjectId>",
    "device_id": "tray-01",
    "source": "hardware",
    "sample_id": "<capture ID>",
    "received_at_utc": "<server receipt timestamp>",
    "captured_at_utc": null,
    "width": 640,
    "height": 480,
    "bytes": 48000,
    "sha256": "<SHA-256 of original JPEG>",
    "transport": "wifi_https",
    "content_url": "/api/camera-images/<Mongo ObjectId>/content"
  },
  "automatic_analysis": false,
  "actuation_enabled": false
}
```

This is a **shape example**, not a captured frame or hardware test result; actual dimensions and byte count come from the JPEG. `captured_at_utc` is `null` when no device timestamp is supplied. `received_at_utc` always comes from the gateway. Supplied capture timestamps are normalized to UTC with BSON millisecond precision.

| Status | Meaning |
| --- | --- |
| 201 | New frame stored and acknowledged |
| 200 | Exact retry acknowledged without another document |
| 400 | Invalid declared content length |
| 401 / 403 | Missing/bad token, another device ID, browser origin or unverified HTTP path |
| 413 | JPEG exceeds 2 MiB |
| 415 | Content type is not `image/jpeg` |
| 422 | Invalid/incomplete JPEG, excessive pixels, invalid metadata or conflicting sample ID |
| 503 | MongoDB storage is unavailable; retry the same frame later |

The unique identity is `(device_id, source, sample_id)`. The same ID with changed bytes or an explicitly supplied conflicting capture timestamp is rejected. A replay may omit the optional device capture timestamp, such as when a USB bridge retries a frame already accepted through Wi-Fi; the exact JPEG is acknowledged and the **first stored capture time, receipt time and transport are preserved**. An explicit timestamp also conflicts if the original record had no capture timestamp. Synthetic and hardware captures never share an identity or default display source.

## Atlas storage and dashboard access

In Atlas Data Explorer, open the existing ASTRA-BIO database and **camera_images**. Each document holds the original `image_data` as BSON Binary, `content_type: image/jpeg`, dimensions, byte count, SHA-256, device/source/sample identity, UTC timestamps, transport and disabled automation flags. Since uploads are capped at 2 MiB, each image fits within a regular MongoDB document; this implementation does not use GridFS. Atlas's document view shows binary data rather than a photo gallery; view the JPEG through ASTRA-BIO.

The local API returns metadata separately from binary content:

```text
GET /api/camera-images?source=hardware&device_id=tray-01&limit=24
GET /api/camera-images/<24-hex-Mongo-ObjectId>/content
```

The list response is `{items, device_id, source, storage}`. `items` uses the image metadata shown above; it contains no BSON bytes, base64 image, tokens, MongoDB URI or private document fields. Images are ordered by newest server receipt first. The default source is `hardware`; `limit` is bounded to 1–100. The optional camera device filter works independently of numerical telemetry streams.

The content endpoint returns byte-exact `image/jpeg` after checking the stored length and SHA-256. Both metadata and image responses use `Cache-Control: no-store`; the local API remains bound to localhost. Storage errors are redacted. There is no deletion endpoint or automatic retention policy in this feature.

## Verify one physical capture

1. Identify the attached board, keep a recovery copy of existing firmware, compile the private camera configuration and flash the correct COM port.
2. Confirm the detected camera PID, PSRAM and a complete JPEG in serial diagnostics. This may be native JPEG on a supported sensor, or RGB565 converted to JPEG in software for the attached GC2145. A successful compile alone does not establish camera compatibility.
3. Trigger a Wi-Fi upload. Record sample ID, device frame byte count/SHA-256 and gateway status. If using USB fallback, record that path explicitly.
4. In Atlas, find exactly one `camera_images` document with the matching device, source and sample ID.
5. Read its JPEG through the local content endpoint and compare length/SHA-256 with the board frame; open the photograph in the dashboard.
6. Retry that same sample. Confirm HTTP 200/`duplicate: true` and that no extra document appears.

Photograph capture and storage do not automatically run leaf screening or fruit monitoring, update crop mass/food reserves, identify pathogens or issue actuator commands. Those remain separate, deliberate workflows. This feature stores the camera's actual visual input; additional sensor models and wiring must be confirmed before assigning any other GPIOs or reporting their readings.
