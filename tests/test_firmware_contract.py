"""Static protocol/safety regressions for the proposed, unflashed tray firmware.

These enforce the broker/collector interface and disabled bench defaults. They
do not establish that a physical sensor, wiring, TLS session or actuator works;
ESPHome configuration validation and a hardware bench test remain separate.
Only the committed example is inspected; provisioned credentials are not read.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = (ROOT / "integration" / "esphome" / "tray.example.yaml").read_text(encoding="utf-8")


def section(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\r?\n(.*?)(?=^\S|\Z)", EXAMPLE, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"Missing top-level firmware section: {name}")
    return match.group(1)


class FirmwareContractTests(unittest.TestCase):
    def test_tls_and_authenticated_device_namespace_have_no_plaintext_fallback(self):
        mqtt = section("mqtt")
        self.assertRegex(mqtt, r"(?m)^  port: 8883$")
        self.assertRegex(mqtt, r"(?m)^  certificate_authority: !secret mqtt_ca_certificate$")
        self.assertRegex(mqtt, r"(?m)^  skip_cert_cn_check: false$")
        self.assertRegex(mqtt, r"(?m)^  enable_on_boot: false$")
        for credential in ("mqtt_broker", "mqtt_username", "mqtt_password"):
            self.assertIn(f"!secret {credential}", mqtt)
        self.assertIn("topic_prefix: astra-bio/devices/${device_id}", mqtt)
        self.assertIn("topic: astra-bio/devices/${device_id}/command", mqtt)
        self.assertNotRegex(mqtt, r"(?m)^  (discovery|discover_ip): true$")
        self.assertNotRegex(EXAMPLE, r"(?m)^(api|web_server):")

    def test_tls_date_validation_waits_for_a_device_time_source(self):
        framework = section("esp32")
        self.assertIn('CONFIG_MBEDTLS_HAVE_TIME: "y"', framework)
        self.assertIn('CONFIG_MBEDTLS_HAVE_TIME_DATE: "y"', framework)
        time_source = section("time")
        self.assertIn("platform: sntp", time_source)
        self.assertIn("!secret ntp_server", time_source)
        self.assertIn("on_time_sync:", time_source)
        self.assertIn("return id(tray_time).now().is_valid();", time_source)
        self.assertIn("- mqtt.enable:", time_source)

    def test_outputs_are_internal_and_disabled_until_explicit_firmware_change(self):
        globals_text = section("globals")
        actuation = re.search(r"- id: actuation_enabled\n(.*?)(?=  - id:|\Z)", globals_text, re.DOTALL).group(1)
        self.assertIn("restore_value: false", actuation)
        self.assertIn("initial_value: 'false'", actuation)
        self.assertNotRegex(EXAMPLE, r"id\(actuation_enabled\)\s*=(?!=)")
        switches = section("switch")
        self.assertEqual(switches.count("restore_mode: ALWAYS_OFF"), 3)
        self.assertEqual(switches.count("internal: true"), 3)
        for output in ("pump_output", "fan_output", "light_output"):
            self.assertIn(f"switch.turn_off: {output}", section("esphome"))

    def test_pump_commands_require_clock_expiry_id_and_safe_local_state(self):
        command = section("mqtt")
        for requirement in (
            "!id(actuation_enabled)", "!now.is_valid()", "expires <= now.timestamp",
            "expires > now.timestamp + 15", "seconds < 1 || seconds > 10",
            "command_id == id(last_command_id)", "id(pump_busy)",
            "!id(low_water).has_state()", "id(low_water).state", "id(local_stop).state",
        ):
            self.assertIn(requirement, command)
        self.assertIn('if (action == "stop")', command)
        guarded = section("script")
        self.assertIn("mode: single", guarded)
        self.assertIn("duration_ms <= 10000", guarded)
        self.assertIn("id(local_stop).has_state()", guarded)
        self.assertIn("!id(low_water).state", guarded)
        self.assertIn("switch.turn_off: pump_output", guarded)

    def test_disconnect_float_and_local_stop_make_outputs_safe(self):
        mqtt = section("mqtt")
        disconnected = mqtt.split("  on_disconnect:\n", 1)[1].split("  on_json_message:", 1)[0]
        for output in ("pump_output", "fan_output", "light_output"):
            self.assertIn(f"switch.turn_off: {output}", disconnected)
        sensors = section("binary_sensor")
        for sensor_id in ("low_water", "local_stop"):
            sensor = re.search(rf"id: {sensor_id}\n(.*?)(?=  - platform:|\Z)", sensors, re.DOTALL).group(1)
            self.assertIn("on_press:", sensor)
            self.assertIn("script.stop: guarded_pump", sensor)
            self.assertIn("switch.turn_off: pump_output", sensor)
        self.assertIn("millis() - id(pump_started_ms)", section("interval"))
        self.assertIn(">= 10000", section("interval"))

    def test_sensor_models_match_selected_bench_hardware(self):
        sensors = section("sensor")
        platforms = re.findall(r"(?m)^  - platform: (\w+)$", sensors)
        self.assertEqual(set(platforms), {"sht3xd", "dallas_temp", "veml7700", "ina260"})
        self.assertEqual(len(platforms), 4)
        for address in ("0x44", "0x10", "0x40"):
            self.assertIn(f"address: {address}", sensors)
        self.assertIn("platform: gpio", section("one_wire"))
        self.assertIn("id: low_water", section("binary_sensor"))
        self.assertIn("board: esp32-s3-devkitc-1", section("esp32"))

    def test_telemetry_is_nonretained_provenance_labelled_and_missing_readings_omitted(self):
        telemetry = section("interval").split("mqtt.publish_json:", 1)[1]
        self.assertIn("topic: astra-bio/devices/${device_id}/telemetry", telemetry)
        self.assertIn("qos: 1", telemetry)
        self.assertIn("retain: false", telemetry)
        self.assertIn('root["device_id"] = "${device_id}";', telemetry)
        self.assertIn('root["source"] = "hardware";', telemetry)
        # ESPTime.strftime() is non-const in the pinned ESPHome release.
        self.assertRegex(telemetry, r"(?m)^\s+auto now = id\(tray_time\).now\(\);$")
        self.assertIn("if (now.is_valid())", telemetry)
        self.assertIn('root["timestamp_origin"] = "device";', telemetry)
        self.assertIn('root["clock_synced"] = now.is_valid();', telemetry)
        for sensor_id in (
            "air_temperature", "air_humidity", "solution_temperature", "tray_lux",
            "actuator_voltage", "actuator_current", "actuator_power",
        ):
            self.assertIn(f"id({sensor_id}).has_state() && std::isfinite(id({sensor_id}).state)", telemetry)
        self.assertIn('if (id(low_water).has_state()) root["low_water"]', telemetry)


if __name__ == "__main__":
    unittest.main()
