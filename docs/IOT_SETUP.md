# ASTRA-BIO tray integration

Start with the [MQTT hardware quickstart](MQTT_QUICKSTART.md). It contains the
setup, simulator, device provisioning, network and ESPHome commands.
[Dashboard status guide](HARDWARE_DASHBOARD.md) explains source selection and
freshness. This integration is a terrestrial prototype, not a tested
spaceflight system.

## Implemented software boundary

~~~text
ESPHome → authenticated TLS MQTT → Node-RED → shared SQLite → Live tray
Simulator → authenticated local/TLS MQTT ──^
Manual synthetic inject ───────────────────^
~~~

Node-RED acquires, validates and logs observations. Streamlit reads them.
Telemetry refresh does not run the optimizer or issue actuator commands.
Planning inputs, health targets and synthetic crop models stay separate.

The collector checks topic/device identity, explicit source, valid finite
readings, reasonable ranges, flags, payload size and timestamp format. Missing
measurements remain null. Prepared SQL binds values rather than treating
payloads as SQL. MQTT 5 retain-as-published preserves the retain flag so the
collector rejects both retained live telemetry and retained replay.

Hardware rows record UTC collector receipt, while device time remains in
device_ts_utc. Synthetic packets preserve their supplied UTC timestamp.
raw_json records transport and receipt metadata. The reserved simulator topic
cannot be accepted as hardware. These checks establish format and account
isolation; a credential alone does not prove physical sensor origin.

## Device-local boundaries

- Actuation is fixed disabled and cannot be enabled by MQTT. Internal pump,
  fan and light outputs restore ALWAYS_OFF. The dashboard has no actuator UI,
  and the broker has no authorized command writer.
- The proposed pump-pulse implementation requires valid time, a fresh expiry
  within 15 seconds, duration 1–10 seconds, a new command ID, no busy pulse,
  adequate known water and inactive local STOP. It never runs while the
  hardcoded enable flag is false.
- Low water, local STOP and MQTT disconnect stop outputs on the device.
  A 250 ms watchdog reinforces the pump duration limit. The pulse script
  has a two-second cooldown and rejects overlap.
- A remote STOP handler can only make outputs off. It is not enabled as a
  dashboard command by this integration.
- GPIO restore mode does not guarantee electrical behavior at boot or power
  loss. Hardware driver pull-downs, wiring and physical cutoffs need bench tests.

Keep actuator power on suitably rated MOSFET drivers and a separate DC supply;
GPIO does not supply motor/light power. The sample float expects adequate water
to close to GND; an open switch/cable means low water. Verify actual polarity.

## Firmware preparation

The example uses ESP32-S3-DevKitC-1 with Arduino, SHT31-D, DS18B20, VEML7700,
INA260, float and local STOP. The sample GPIO/bus mapping is in the quickstart.
TLS verifies the generated CA and broker hostname/IP. MQTT starts after SNTP
establishes valid device time; a reachable NTP service is needed on cold boot.
Collector timestamps cannot bootstrap TLS certificate date verification.

The example passed configuration validation with ESPHome 2026.9.1. Validation
checks syntax/components; physical sensor behavior and electrical cutoffs require
the actual tray. Firmware build status and latest transport evidence are recorded
in [BUILD_STATUS.md](BUILD_STATUS.md).

SHT31-D initialization on ESP32-S3 requires bench verification. The previously
researched [ESPHome issue #17865](https://github.com/esphome/esphome/issues/17865)
reports SHT3xD initialization problems; switching framework is not an established
universal fix. Verify the exact sensor model and firmware combination.

## Measurement scope

Lux measures illuminance, not PPFD or nutrients. A float reports low water,
not remaining liters or net consumption. INA260 covers its instrumented DC bus,
excluding the laptop and supply losses; energy requires time integration of
power. Crop loss scenarios do not demonstrate disease diagnosis. No pH/EC,
nutrient dosing, camera analysis or clinical deficiency detector is implemented.

## Runtime and upstreams

The pinned local runtime uses Mosquitto 2.1.2, Node-RED 5.0.8,
node-red-node-sqlite 2.0.1 and Paho Python 2.1.0. Installation extracts official
vendor payloads without executing the Windows installers. It keeps original
notices and provenance. The foreground supervisor owns its subprocesses and
leaves existing healthy Streamlit instances alone. No service or firewall is
installed automatically.

The acquisition approach follows official
[Node-RED broker examples](https://cookbook.nodered.org/mqtt/connect-to-broker).
TLS follows [ESPHome MQTT guidance](https://esphome.io/components/mqtt/#tls-esp32).
Authentication/topic ACL configuration follows the
[Mosquitto manual](https://mosquitto.org/man/mosquitto-conf-5.html).
Upstream licenses remain in distributions and source clones. Applicable
firmware source/license obligations remain relevant if distributing the binary.
