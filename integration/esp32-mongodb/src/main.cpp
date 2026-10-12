// ASTRA-BIO ESP32-S3 Wi-Fi -> verified HTTPS gateway -> MongoDB Atlas.
// No actuation, MongoDB credentials, guessed sensor drivers or guessed GPIOs.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if __has_include("config.h")
#include "config.h"
#else
#error "Copy include/config.example.h or the generated device config to include/config.h first."
#endif

namespace {
constexpr uint32_t SAMPLE_INTERVAL_MS = 15000;
constexpr uint32_t INITIAL_RETRY_MS = 2000;
constexpr uint32_t MAX_RETRY_MS = 60000;
constexpr uint32_t WIFI_RETRY_MS = 15000;
constexpr uint32_t CLOCK_RETRY_MS = 60000;
constexpr size_t MAX_PAYLOAD_BYTES = 1024;

struct SensorSnapshot {
  // NAN means unavailable and is omitted. Never replace missing data with zero.
  double air_temp_c = NAN;
  double relative_humidity_pct = NAN;
  double solution_temp_c = NAN;
  double light_lux = NAN;
  double bus_voltage_v = NAN;
  double bus_current_a = NAN;
  double bus_power_w = NAN;
  // -1 means unknown; 0/1 are actual observed states.
  int low_water = -1;
  int pump_on = -1;
  int fan_on = -1;
  int light_on = -1;
};

void beginHardwareSensors() {
  // Add the confirmed sensor initialization here, using your verified GPIOs.
}

SensorSnapshot readHardwareMeasurements() {
  SensorSnapshot readings;
  // Add actual sensor driver calls here, e.g. readings.air_temp_c = measuredValue.
  // Keep unavailable/failed readings NAN, and leave unobserved flags at -1.
  // No sensors or pin assignments have been supplied yet.
  return readings;
}

SensorSnapshot syntheticFixture() {
  SensorSnapshot readings;
  readings.air_temp_c = 23.5;
  readings.relative_humidity_pct = 60.0;
  readings.solution_temp_c = 21.0;
  readings.light_lux = 12000.0;
  return readings;
}

Preferences pendingStore;
String pendingPayload;
char bootId[33] = {0};
uint64_t sequence = 0;
uint32_t nextSampleAt = 0;
uint32_t nextAttemptAt = 0;
uint32_t nextWiFiAt = 0;
uint32_t nextClockAt = 0;
uint32_t retryMs = INITIAL_RETRY_MS;
bool ready = false;
bool requestPaused = false;
bool previouslyConnected = false;
bool clockNoticePrinted = false;

bool due(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool validIdentifier(const char *value, size_t maximum) {
  if (!value || !*value || strlen(value) > maximum) return false;
  for (const char *cursor = value; *cursor; ++cursor) {
    const char c = *cursor;
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
  }
  return true;
}

bool configured() {
  const String ssid(WIFI_SSID);
  const String password(WIFI_PASSWORD);
  const String endpoint(GATEWAY_URL);
  const String token(DEVICE_TOKEN);
  const String ca(ROOT_CA);
  return ssid.length() && !ssid.startsWith("REPLACE_") &&
         !password.startsWith("REPLACE_") && endpoint.startsWith("https://") &&
         endpoint.endsWith("/v1/telemetry") && token.length() >= 32 &&
         !token.startsWith("REPLACE_") && validIdentifier(DEVICE_ID, 64) &&
         ca.length() >= 300 && ca.indexOf("REPLACE_") < 0 &&
         ca.indexOf("-----BEGIN CERTIFICATE-----") >= 0 &&
         ca.indexOf("-----END CERTIFICATE-----") >= 0;
}

bool appendReading(JsonObject document, const char *key, double value,
                   double minimum, double maximum, unsigned &readingCount) {
  if (isnan(value)) return true;
  if (!isfinite(value) || value < minimum || value > maximum) {
    Serial.printf("Invalid reading for %s; sample not uploaded.\n", key);
    return false;
  }
  document[key] = value;
  ++readingCount;
  return true;
}

bool appendFlag(JsonObject document, const char *key, int value) {
  if (value == -1) return true;
  if (value != 0 && value != 1) {
    Serial.printf("Invalid state for %s; sample not uploaded.\n", key);
    return false;
  }
  document[key] = value;
  return true;
}

bool makePendingSample() {
  const SensorSnapshot readings = TELEMETRY_SYNTHETIC_DEMO
      ? syntheticFixture() : readHardwareMeasurements();
  JsonDocument document;
  JsonObject fields = document.to<JsonObject>();
  unsigned readingCount = 0;
  bool valid = true;
  valid &= appendReading(fields, "air_temp_c", readings.air_temp_c, -50, 80, readingCount);
  valid &= appendReading(fields, "relative_humidity_pct", readings.relative_humidity_pct, 0, 100, readingCount);
  valid &= appendReading(fields, "solution_temp_c", readings.solution_temp_c, -10, 60, readingCount);
  valid &= appendReading(fields, "light_lux", readings.light_lux, 0, 200000, readingCount);
  valid &= appendReading(fields, "bus_voltage_v", readings.bus_voltage_v, 0, 36, readingCount);
  valid &= appendReading(fields, "bus_current_a", readings.bus_current_a, 0, 15, readingCount);
  valid &= appendReading(fields, "bus_power_w", readings.bus_power_w, 0, 540, readingCount);
  valid &= appendFlag(fields, "low_water", readings.low_water);
  valid &= appendFlag(fields, "pump_on", readings.pump_on);
  valid &= appendFlag(fields, "fan_on", readings.fan_on);
  valid &= appendFlag(fields, "light_on", readings.light_on);
  if (!valid || !readingCount) {
    if (!readingCount) Serial.println("No measured sensor readings. Connect sensors and implement readHardwareMeasurements(); upload refused.");
    return false;
  }

  char sampleId[64];
  snprintf(sampleId, sizeof(sampleId), "%s_%llu", bootId,
           static_cast<unsigned long long>(sequence++));
  fields["device_id"] = DEVICE_ID;
  fields["sample_id"] = sampleId;
  fields["source"] = TELEMETRY_SYNTHETIC_DEMO ? "synthetic" : "hardware";

  const time_t now = time(nullptr);
  if (now >= 1704067200) {
    struct tm utc;
    gmtime_r(&now, &utc);
    char timestamp[32];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
    fields["ts_utc"] = timestamp;
  }

  String serialized;
  serializeJson(document, serialized);
  if (document.overflowed() || !serialized.length() || serialized.length() > MAX_PAYLOAD_BYTES) {
    Serial.println("Sample serialization failed; upload refused.");
    return false;
  }
  // Save once before sending. Retry exactly these bytes, even after a reboot.
  if (pendingStore.putString("pending", serialized) != serialized.length()) {
    Serial.println("Could not persist the pending sample; upload refused.");
    return false;
  }
  pendingPayload = serialized;
  nextAttemptAt = millis();
  return true;
}

void retryLater() {
  nextAttemptAt = millis() + retryMs + (esp_random() % 501);
  retryMs = retryMs >= MAX_RETRY_MS / 2 ? MAX_RETRY_MS : retryMs * 2;
}

void uploadPending() {
  WiFiClientSecure connection;
  connection.setCACert(ROOT_CA);
  connection.setHandshakeTimeout(8);
  HTTPClient request;
  request.setConnectTimeout(5000);
  request.setTimeout(10000);
  request.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (!request.begin(connection, GATEWAY_URL)) {
    Serial.println("HTTPS request setup failed; retaining sample.");
    retryLater();
    return;
  }
  request.addHeader("Content-Type", "application/json");
  request.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  const int status = request.POST(pendingPayload);
  bool acknowledged = false;
  if (status == 201 || status == 200) {
    JsonDocument acknowledgement;
    const DeserializationError error = deserializeJson(acknowledgement, request.getString());
    const char *storedId = acknowledgement["id"] | "";
    acknowledged = !error && *storedId && acknowledgement["duplicate"].is<bool>() &&
        acknowledgement["duplicate"].as<bool>() == (status == 200);
  }
  request.end();
  connection.stop();

  if (acknowledged) {
    if (!pendingStore.remove("pending")) {
      Serial.println("Sample acknowledged but local queue could not clear; will retry the same sample.");
      retryLater();
      return;
    }
    pendingPayload = "";
    retryMs = INITIAL_RETRY_MS;
    nextSampleAt = millis() + SAMPLE_INTERVAL_MS;
    Serial.println(status == 201 ? "Sample stored by gateway." : "Same sample already stored; duplicate safely acknowledged.");
    return;
  }
  if (status == 201 || status == 200) {
    Serial.println("Gateway acknowledgement is incomplete; retaining the same sample for retry.");
    retryLater();
    return;
  }
  // Do not drop or rewrite a rejected sample. Fix configuration/data first.
  if (status >= 400 && status < 500 && status != 408 && status != 429) {
    requestPaused = true;
    Serial.printf("Gateway rejected sample (HTTP %d). Upload paused; pending sample retained. Correct configuration/data before restarting.\n", status);
    return;
  }
  Serial.printf("Upload unavailable (code %d); identical sample will retry.\n", status);
  retryLater();
}

void maintainWiFiAndClock(uint32_t now) {
  if (WiFi.status() != WL_CONNECTED) {
    previouslyConnected = false;
    if (due(now, nextWiFiAt)) {
      Serial.println("Connecting to Wi-Fi...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      nextWiFiAt = now + WIFI_RETRY_MS;
    }
    return;
  }
  if (!previouslyConnected) {
    Serial.println("Wi-Fi connected. Synchronizing UTC clock for certificate verification.");
    previouslyConnected = true;
    nextClockAt = now;
    nextAttemptAt = now;
  }
  nextWiFiAt = now;
  if (time(nullptr) >= 1704067200) nextClockAt = now;
  if (time(nullptr) < 1704067200 && due(now, nextClockAt)) {
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    nextClockAt = now + CLOCK_RETRY_MS;
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println("ASTRA-BIO ESP32-S3 HTTPS telemetry uploader");
  if (TELEMETRY_SYNTHETIC_DEMO) {
    Serial.println("SYNTHETIC CONNECTIVITY TEST: fixture values are NOT real sensor measurements. Every record is labeled synthetic.");
  } else {
    Serial.println("Hardware mode: missing sensor values are omitted; an empty hook cannot upload.");
  }
  if (!configured()) {
    Serial.println("Configuration missing or invalid. Fill private include/config.h; credentials are never printed.");
    return;
  }
  if (!pendingStore.begin("astra-tlm", false)) {
    Serial.println("Cannot open durable telemetry queue; upload disabled.");
    return;
  }
  pendingPayload = pendingStore.getString("pending", "");
  if (pendingPayload.length()) {
    JsonDocument saved;
    const DeserializationError error = deserializeJson(saved, pendingPayload);
    const char *source = saved["source"] | "";
    if (error || pendingPayload.length() > MAX_PAYLOAD_BYTES ||
        strcmp(saved["device_id"] | "", DEVICE_ID) != 0 ||
        !validIdentifier(saved["sample_id"] | "", 96) ||
        (strcmp(source, "synthetic") && strcmp(source, "hardware"))) {
      Serial.println("Saved pending sample is invalid or belongs to another device. Upload disabled; inspect/reset the queue deliberately.");
      return;
    }
    Serial.printf("Restored one pending %s sample; it will be retried unchanged.\n", source);
  }
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  for (unsigned i = 0; i < 4; ++i) {
    snprintf(bootId + i * 8, 9, "%08lx", static_cast<unsigned long>(esp_random()));
  }
  if (!TELEMETRY_SYNTHETIC_DEMO) beginHardwareSensors();
  ready = true;
}

void loop() {
  if (!ready) {
    delay(50);
    return;
  }
  const uint32_t now = millis();
  maintainWiFiAndClock(now);
  if (!requestPaused && WiFi.status() == WL_CONNECTED) {
    if (time(nullptr) < 1704067200) {
      if (!clockNoticePrinted) {
        Serial.println("Waiting for UTC clock. HTTPS verification stays enabled; no upload until time is ready.");
        clockNoticePrinted = true;
      }
    } else {
      clockNoticePrinted = false;
      if (!pendingPayload.length() && due(now, nextSampleAt)) {
        if (!makePendingSample()) nextSampleAt = now + SAMPLE_INTERVAL_MS;
      }
      if (pendingPayload.length() && due(millis(), nextAttemptAt)) uploadPending();
    }
  }
  delay(10);
}
