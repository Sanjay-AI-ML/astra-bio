#pragma once
// Copy the generated runtime/mongodb/device-tray-01-config.h here as config.h.
// Or privately fill these values. Never copy an Atlas URI to the microcontroller.
#define WIFI_SSID "REPLACE_WITH_2_4_GHZ_WIFI_NAME"
#define WIFI_PASSWORD "REPLACE_WITH_WIFI_PASSWORD"
#define GATEWAY_URL "https://192.168.1.50:8502/v1/telemetry"
#define DEVICE_ID "tray-01"
#define DEVICE_TOKEN "REPLACE_WITH_GENERATED_DEVICE_TOKEN"
#define ROOT_CA "-----BEGIN CERTIFICATE-----\n" \
                "REPLACE_WITH_GATEWAY_CA_CERTIFICATE\n" \
                "-----END CERTIFICATE-----\n"

// Optional explicit URL; otherwise /v1/telemetry is replaced by /v1/images.
// #define IMAGE_GATEWAY_URL "https://192.168.1.50:8502/v1/images"
// One Wi-Fi upload on boot. Thereafter serial `c` captures/uploads on request.
#define CAMERA_UPLOAD_ON_BOOT true
// Zero disables automatic recurring photos. Optional intervals must be >=60 sec.
#define CAMERA_UPLOAD_INTERVAL_MS 0
