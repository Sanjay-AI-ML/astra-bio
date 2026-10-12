// ASTRA-BIO: camera JPEG -> verified HTTPS -> gateway -> MongoDB Atlas.
// USB serial is also an explicit capture transport when Wi-Fi is unconfigured.
// No sensor/actuator GPIOs are guessed. No database URI is stored on this board.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>
#include <time.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "config.h"

#ifndef CAMERA_UPLOAD_ON_BOOT
#define CAMERA_UPLOAD_ON_BOOT true
#endif
#ifndef CAMERA_UPLOAD_INTERVAL_MS
#define CAMERA_UPLOAD_INTERVAL_MS 0
#endif

// Exact candidate map from the user's working initialization/capture sketch.
// It must be tested on this attached carrier, not applied to arbitrary S3 boards.
constexpr int CAM_SIOD = 4, CAM_SIOC = 5;
constexpr int CAM_VSYNC = 6, CAM_HREF = 7, CAM_PCLK = 13, CAM_XCLK = 15;
constexpr int CAM_D0 = 11, CAM_D1 = 9, CAM_D2 = 8, CAM_D3 = 10;
constexpr int CAM_D4 = 12, CAM_D5 = 18, CAM_D6 = 17, CAM_D7 = 16;
constexpr int CAM_PWDN = -1, CAM_RESET = -1;

namespace {
constexpr size_t MAX_IMAGE_BYTES = 2 * 1024 * 1024;
constexpr uint8_t MAX_UPLOAD_ATTEMPTS = 5;
constexpr uint32_t MAX_RETRY_MS = 60000;
camera_fb_t *pendingFrame = nullptr;
camera_fb_t convertedFrame = {};
uint8_t *ownedJpeg = nullptr;
char pendingSha[65] = {}, pendingId[96] = {}, capturedAt[32] = {};
char bootId[17] = {};
uint32_t sequence = 0, nextUploadAt = 0, nextWiFiAt = 0, nextClockAt = 0;
uint32_t nextIntervalAt = 0;
uint8_t attempts = 0;
bool cameraReady = false, networkConfigured = false, uploadRequested = false;
bool uploadsPaused = false, bootCaptureRequested = CAMERA_UPLOAD_ON_BOOT;
String command;

bool due(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool validId(const char *value) {
  if (!value || !*value || strlen(value) > 64) return false;
  for (const char *c = value; *c; ++c) {
    if (!(isalnum(static_cast<unsigned char>(*c)) || *c == '-' || *c == '_')) return false;
  }
  return true;
}

String imageEndpoint() {
#ifdef IMAGE_GATEWAY_URL
  return String(IMAGE_GATEWAY_URL);
#else
  String url(GATEWAY_URL);
  if (url.endsWith("/v1/telemetry")) {
    url.remove(url.length() - strlen("/v1/telemetry"));
    url += "/v1/images";
  }
  return url;
#endif
}

bool configured() {
  const String ssid(WIFI_SSID), password(WIFI_PASSWORD), token(DEVICE_TOKEN), ca(ROOT_CA);
  const String url = imageEndpoint();
  return ssid.length() && !ssid.startsWith("REPLACE_") &&
         !password.startsWith("REPLACE_") && token.length() >= 32 &&
         !token.startsWith("REPLACE_") && validId(DEVICE_ID) &&
         url.startsWith("https://") && url.endsWith("/v1/images") &&
         ca.length() >= 300 && ca.indexOf("REPLACE_") < 0 &&
         ca.indexOf("-----BEGIN CERTIFICATE-----") >= 0;
}

bool clockReady() { return time(nullptr) >= 1735689600; }

void returnFrame(camera_fb_t *frame) {
  if (frame == &convertedFrame) {
    free(ownedJpeg);
    ownedJpeg = nullptr;
    convertedFrame = {};
  } else if (frame) {
    esp_camera_fb_return(frame);
  }
}

void releasePending() {
  returnFrame(pendingFrame);
  pendingFrame = nullptr;
  pendingSha[0] = pendingId[0] = capturedAt[0] = 0;
  uploadRequested = false;
  uploadsPaused = false;
  attempts = 0;
}

void diagnostics() {
  Serial.printf("Chip: %s revision %u; flash %u bytes; PSRAM %u bytes; free heap %u bytes\n",
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getFlashChipSize(),
                ESP.getPsramSize(), ESP.getFreeHeap());
  Serial.printf("Camera: %s; Wi-Fi: %s; clock: %s; private network config: %s\n",
                cameraReady ? "initialized" : "unavailable",
                WiFi.status() == WL_CONNECTED ? "connected" : "not connected",
                clockReady() ? "UTC synchronized" : "not synchronized",
                networkConfigured ? "present" : "absent/placeholders");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi local IP: %s\n", WiFi.localIP().toString().c_str());
  }
  if (clockReady()) {
    time_t now = time(nullptr);
    struct tm utc;
    char currentUtc[32] = {};
    gmtime_r(&now, &utc);
    strftime(currentUtc, sizeof(currentUtc), "%Y-%m-%dT%H:%M:%SZ", &utc);
    Serial.printf("Current UTC: %s\n", currentUtc);
  }
  if (pendingFrame) Serial.printf("Pending: %s; %u bytes; SHA256 %s; attempts %u\n",
                                 pendingId, pendingFrame->len, pendingSha, attempts);
}

bool initializeCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAM_D0; config.pin_d1 = CAM_D1;
  config.pin_d2 = CAM_D2; config.pin_d3 = CAM_D3;
  config.pin_d4 = CAM_D4; config.pin_d5 = CAM_D5;
  config.pin_d6 = CAM_D6; config.pin_d7 = CAM_D7;
  config.pin_xclk = CAM_XCLK; config.pin_pclk = CAM_PCLK;
  config.pin_vsync = CAM_VSYNC; config.pin_href = CAM_HREF;
  config.pin_sccb_sda = CAM_SIOD; config.pin_sccb_scl = CAM_SIOC;
  config.pin_pwdn = CAM_PWDN; config.pin_reset = CAM_RESET;
  config.xclk_freq_hz = 10000000;  // Preserve the user's working test frequency.
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  esp_err_t err = esp_camera_init(&config);
  if (err == ESP_ERR_NOT_SUPPORTED) {
    Serial.println("Sensor does not support native JPEG. Retrying supplied RGB565 QQVGA capture; JPEG will be encoded in software.");
    esp_camera_deinit();
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAMESIZE_QQVGA;
    config.fb_count = 1;
    config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    err = esp_camera_init(&config);
  }
  if (err != ESP_OK) {
    Serial.printf("Camera initialization failed: 0x%x. Check carrier pin map/cable/sensor.\n", err);
    return false;
  }
  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) Serial.printf("Detected sensor PID: 0x%04X; capture format: %s\n", sensor->id.PID,
                            config.pixel_format == PIXFORMAT_JPEG ? "native JPEG" : "RGB565 -> software JPEG");
  delay(500); // Let auto-exposure settle before the first requested frame.
  return true;
}

bool capturePending() {
  if (pendingFrame) return true; // Reuse exact pending bytes/id after ambiguous delivery.
  if (!cameraReady) { Serial.println("Camera not initialized; capture refused."); return false; }
  // fb_count=1 may contain a queued image from before this explicit request.
  // Drop that first buffer so this capture starts after the command/boot trigger.
  camera_fb_t *stale = esp_camera_fb_get();
  if (stale) esp_camera_fb_return(stale);
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) { Serial.println("Image capture failed."); return false; }
  if (frame->format == PIXFORMAT_RGB565) {
    uint8_t *jpeg = nullptr;
    size_t jpegSize = 0;
    if (!frame2jpg(frame, 80, &jpeg, &jpegSize) || !jpeg || jpegSize > MAX_IMAGE_BYTES) {
      free(jpeg);
      esp_camera_fb_return(frame);
      Serial.println("Software JPEG conversion failed or exceeded size limit.");
      return false;
    }
    convertedFrame = *frame;
    convertedFrame.buf = jpeg;
    convertedFrame.len = jpegSize;
    convertedFrame.format = PIXFORMAT_JPEG;
    ownedJpeg = jpeg;
    esp_camera_fb_return(frame); // RGB camera buffer no longer needed; retain exact encoded JPEG.
    frame = &convertedFrame;
    Serial.printf("RGB565 image converted to JPEG: %u bytes.\n", jpegSize);
  }
  if (frame->format != PIXFORMAT_JPEG || frame->len < 4 || frame->len > MAX_IMAGE_BYTES ||
      frame->buf[0] != 0xff || frame->buf[1] != 0xd8) {
    Serial.println("Capture is not a supported bounded JPEG; upload refused.");
    returnFrame(frame);
    return false;
  }
  unsigned char hash[32];
  if (mbedtls_sha256_ret(frame->buf, frame->len, hash, 0) != 0) {
    returnFrame(frame);
    Serial.println("Image checksum failed.");
    return false;
  }
  for (size_t i = 0; i < sizeof(hash); ++i) snprintf(pendingSha + 2 * i, 3, "%02x", hash[i]);
  snprintf(pendingId, sizeof(pendingId), "cam-%s-%lu", bootId, static_cast<unsigned long>(++sequence));
  capturedAt[0] = 0;
  if (clockReady()) {
    time_t captured = time(nullptr);
    struct tm utc;
    gmtime_r(&captured, &utc);
    strftime(capturedAt, sizeof(capturedAt), "%Y-%m-%dT%H:%M:%SZ", &utc);
  }
  pendingFrame = frame;
  attempts = 0;
  uploadsPaused = false;
  Serial.printf("IMAGE CAPTURE SUCCESSFUL: %ux%u JPEG %u bytes; sample %s; SHA256 %s\n",
                frame->width, frame->height, frame->len, pendingId, pendingSha);
  return true;
}

void sendSerialImage() {
  if (!capturePending()) return;
  Serial.printf("ASTRA_JPEG_BEGIN:%u:%s:%s:%u:%u\n", pendingFrame->len, pendingSha,
                pendingId, pendingFrame->width, pendingFrame->height);
  Serial.flush();
  size_t sent = 0;
  while (sent < pendingFrame->len) {
    const size_t amount = min(static_cast<size_t>(1024), pendingFrame->len - sent);
    const size_t written = Serial.write(pendingFrame->buf + sent, amount);
    if (!written) { Serial.println("\nASTRA_JPEG_ABORT\n"); return; }
    sent += written;
    delay(1);
  }
  Serial.print("\nASTRA_JPEG_END\n");
  Serial.flush();
  Serial.println("Pending image retained. Acknowledge with `a <sample_id>` after MongoDB storage.");
}

void maintainNetwork(uint32_t now) {
  if (!networkConfigured) return;
  if (WiFi.status() != WL_CONNECTED) {
    if (due(now, nextWiFiAt)) {
      nextWiFiAt = now + 20000;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      Serial.println("Wi-Fi connection attempt started.");
    }
    return;
  }
  if (!clockReady() && due(now, nextClockAt)) {
    nextClockAt = now + 60000;
    configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
    Serial.println("Wi-Fi connected; synchronizing UTC before verified HTTPS.");
  }
}

void scheduleRetry(uint32_t now) {
  if (attempts >= MAX_UPLOAD_ATTEMPTS) {
    uploadsPaused = true;
    Serial.println("Five attempts exhausted; exact image retained. Use `r` to retry, `s` for USB, or `d` to discard.");
    return;
  }
  const uint32_t backoff = min(MAX_RETRY_MS, static_cast<uint32_t>(2000u << (attempts - 1)));
  nextUploadAt = now + backoff + esp_random() % 750;
}

void uploadPending(uint32_t now) {
  if (!pendingFrame || !uploadRequested || uploadsPaused || !due(now, nextUploadAt)) return;
  if (!networkConfigured || WiFi.status() != WL_CONNECTED || !clockReady()) return;
  ++attempts;
  WiFiClientSecure client;
  client.setCACert(ROOT_CA);
  client.setHandshakeTimeout(12);
  client.setTimeout(15); // This framework's secure-client API accepts seconds.
  HTTPClient request;
  request.setConnectTimeout(10000);
  request.setTimeout(15000);
  request.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (!request.begin(client, imageEndpoint())) {
    Serial.println("HTTPS client initialization failed; pending image retained.");
    scheduleRetry(now);
    return;
  }
  request.addHeader("Content-Type", "image/jpeg");
  request.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  request.addHeader("X-Device-Id", DEVICE_ID);
  request.addHeader("X-Sample-Id", pendingId);
  request.addHeader("X-Source", "hardware");
  request.addHeader("X-Transport", "wifi_https");
  if (capturedAt[0]) request.addHeader("X-Captured-At", capturedAt);
  const int status = request.POST(pendingFrame->buf, pendingFrame->len);
  Serial.printf("Image upload HTTP status: %d (attempt %u)\n", status, attempts);
  if (status < 0) {
    char secureError[160] = {};
    const int secureErrorCode = client.lastError(secureError, sizeof(secureError));
    // mbedTLS provides a generic code description, never request headers/tokens.
    // Sanitize control characters and keep the output bounded for serial parsing.
    for (size_t i = 0; i < sizeof(secureError) - 1 && secureError[i]; ++i) {
      if (static_cast<unsigned char>(secureError[i]) < 32 ||
          static_cast<unsigned char>(secureError[i]) > 126) secureError[i] = ' ';
    }
    Serial.printf("Secure client error: %d; %s\n", secureErrorCode,
                  secureError[0] ? secureError : "No TLS-specific error reported (check TCP reachability).");
    diagnostics();
  }
  bool acknowledged = false;
  if ((status == 200 || status == 201) && request.getSize() >= 0 && request.getSize() <= 2048) {
    JsonDocument response;
    if (!deserializeJson(response, request.getStream())) {
      const char *sha = response["sha256"] | "";
      if (!*sha) sha = response["image"]["sha256"] | "";
      const char *id = response["id"] | "";
      if (!*id) id = response["image_id"] | "";
      if (strcmp(sha, pendingSha) == 0 && *id) {
        Serial.printf("MongoDB image acknowledged: %s; SHA256 %s\n", id, sha);
        acknowledged = true;
      }
    }
  }
  request.end();
  if (acknowledged) { releasePending(); return; }
  if (status >= 400 && status < 500 && status != 408 && status != 429) {
    uploadsPaused = true;
    Serial.println("Gateway rejected upload. Exact image retained; correct configuration before retry.");
    return;
  }
  scheduleRetry(millis());
}

void handleCommand(const String &input) {
  if (input == "s") { sendSerialImage(); return; }
  if (input == "i") { diagnostics(); return; }
  if (input == "d") { releasePending(); Serial.println("Pending image explicitly discarded."); return; }
  if (input.startsWith("a ")) {
    if (pendingFrame && input.substring(2) == pendingId) {
      Serial.println("Laptop confirmed pending image storage; frame released.");
      releasePending();
    } else Serial.println("Acknowledgment sample_id mismatch; pending frame retained.");
    return;
  }
  if (input == "c" || input == "r") {
    if (input == "r" && !pendingFrame) { Serial.println("No pending frame to retry."); return; }
    if (!capturePending()) return;
    attempts = 0; uploadsPaused = false; uploadRequested = true; nextUploadAt = millis();
    if (!networkConfigured) Serial.println("Private Wi-Fi config is absent; use `s` for USB bridge or configure/rebuild for HTTPS.");
    return;
  }
  if (input.length()) Serial.println("Commands: i diagnostics; c capture/upload; s USB JPEG; r retry; a <sample_id> ACK; d discard.");
}
} // namespace

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(2000);
  Serial.println("\n=== ASTRA-BIO CAMERA / MONGODB ===");
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", static_cast<unsigned long>(esp_random()),
           static_cast<unsigned long>(esp_random()));
  networkConfigured = configured();
  cameraReady = initializeCamera();
  if (networkConfigured) { WiFi.mode(WIFI_STA); WiFi.setSleep(false); }
  else bootCaptureRequested = false;
  diagnostics();
  Serial.println("Commands: i diagnostics; c capture/upload; s USB JPEG; r retry; a <sample_id> ACK; d discard.");
  if (CAMERA_UPLOAD_INTERVAL_MS && CAMERA_UPLOAD_INTERVAL_MS < 60000) {
    Serial.println("Automatic interval below 60 sec ignored.");
  }
  nextIntervalAt = millis() + CAMERA_UPLOAD_INTERVAL_MS;
}

void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') { handleCommand(command); command = ""; }
    else if (command.length() < 128) command += c;
    else { command = ""; Serial.println("Command too long; discarded."); }
  }
  const uint32_t now = millis();
  maintainNetwork(now);
  if (cameraReady && bootCaptureRequested && WiFi.status() == WL_CONNECTED && clockReady()) {
    bootCaptureRequested = false;
    if (capturePending()) { uploadRequested = true; nextUploadAt = now; }
  }
  if (cameraReady && networkConfigured && CAMERA_UPLOAD_INTERVAL_MS >= 60000 &&
      !pendingFrame && due(now, nextIntervalAt)) {
    nextIntervalAt = now + CAMERA_UPLOAD_INTERVAL_MS;
    if (capturePending()) { uploadRequested = true; nextUploadAt = now; }
  }
  uploadPending(now);
  delay(10);
}
