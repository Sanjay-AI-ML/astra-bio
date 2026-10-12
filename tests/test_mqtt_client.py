"""MQTT client regressions without a broker, private accounts or real telemetry."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from astra_bio import mqtt_client


class FakeClient:
    def __init__(self, **options):
        self.options = options
        self.subscribed = []
        self.published = []
        self.publish_reason = None
        self.publish_mid = 91
        self.subscription_mid = 7

    def reconnect_delay_set(self, **options):
        self.reconnect_options = options

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def subscribe(self, topic, qos):
        self.subscribed.append((topic, qos))
        return mqtt_client.mqtt.MQTT_ERR_SUCCESS, self.subscription_mid

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        if self.publish_reason is not None:
            # Deliberately race the caller: ACK arrives before publish returns.
            self.on_publish(self, None, self.publish_mid,
                ReasonCode(PacketTypes.PUBACK, identifier=self.publish_reason), None)
        return SimpleNamespace(rc=mqtt_client.mqtt.MQTT_ERR_SUCCESS, mid=self.publish_mid)


@pytest.fixture
def fake_session(monkeypatch):
    monkeypatch.setattr(mqtt_client.mqtt, "Client", FakeClient)

    def create(subscriptions=()):
        return mqtt_client.MQTTSession(mqtt_client.BrokerSettings(), subscriptions)

    return create


def connected(session):
    session._on_connect(session.client, None, SimpleNamespace(session_present=False),
        ReasonCode(PacketTypes.CONNACK, identifier=0), None)


def suback(session, identifier=1):
    session._on_subscribe(session.client, None, session.client.subscription_mid,
        [ReasonCode(PacketTypes.SUBACK, identifier=identifier)], None)


def test_fast_denied_puback_is_preserved_before_publish_returns(fake_session):
    session = fake_session()
    connected(session)
    session.client.publish_reason = mqtt_client.NOT_AUTHORIZED

    code = session.publish(mqtt_client.TELEMETRY,
        mqtt_client.synthetic_payload(probe_id="fast-ack"), timeout=0.01)

    assert code == 135
    assert session.client.publish_mid not in session.publish_acks
    topic, body, qos, retain = session.client.published[-1]
    assert topic == mqtt_client.TELEMETRY
    assert json.loads(body)["probe_id"] == "fast-ack"
    assert qos == 1
    assert retain is False
    assert session.client.options["callback_api_version"] is mqtt_client.mqtt.CallbackAPIVersion.VERSION2
    assert session.client.options["protocol"] == mqtt_client.mqtt.MQTTv5


def test_reused_mid_cannot_satisfy_publish_with_an_old_ack(fake_session):
    session = fake_session()
    connected(session)
    session.publish_acks[session.client.publish_mid] = (0, mqtt_client.time.monotonic() - 60)

    with pytest.raises(TimeoutError, match="matching MQTTv5 PUBACK"):
        session.publish(mqtt_client.TELEMETRY, "test-only", timeout=0.01)


def test_reconnect_needs_fresh_suback_even_when_mid_is_reused(fake_session):
    session = fake_session((mqtt_client.TELEMETRY,))
    connected(session)
    suback(session)
    assert session.wait_subscriptions(timeout=0) == {mqtt_client.TELEMETRY: [1]}

    session._on_disconnect(session.client, None, None,
        ReasonCode(PacketTypes.DISCONNECT, identifier=0), None)
    assert not session.connected.is_set()
    connected(session)

    assert session.connection_count == 2
    assert session.connected.is_set()
    assert session.client.subscribed == [(mqtt_client.TELEMETRY, 1)] * 2
    with pytest.raises(TimeoutError, match="current connection"):
        session.wait_subscriptions(timeout=0)

    suback(session, identifier=135)
    assert session.wait_subscriptions(timeout=0) == {mqtt_client.TELEMETRY: [135]}


@pytest.mark.parametrize("passed,expected", [(True, "passed"), (False, "failed")])
def test_delivery_status_roundtrips_json_with_newline_and_excludes_secrets(tmp_path, passed, expected):
    path = tmp_path / "runtime" / "mqtt-status.json"
    path.parent.mkdir()
    public = {"broker_host": "127.0.0.1", "broker_port": 1883, "profile": "loopback",
        "running": True, "checked_at_utc": "2026-10-11T12:00:00Z",
        "config_path": "runtime/mqtt/local.conf", "topic": mqtt_client.TELEMETRY,
        "lan_host": "test-host.local"}
    private = {"collector_password": "private-collector", "simulator_password": "private-simulator",
        "password": "private-password", "devices": {"fake-unit": "private-device"},
        "credentials": {"token": "private-token"}}
    path.write_text(json.dumps(public | private), encoding="utf-8")

    mqtt_client.write_delivery_status(passed, path)

    written = path.read_bytes()
    status = json.loads(written)
    assert written.endswith(b"\n")
    assert not written.endswith(b"\\n")
    assert {key: status[key] for key in public} == public
    assert set(status) == set(public) | {"latest_delivery_check"}
    check = status["latest_delivery_check"]
    assert set(check) == {"status", "checked_at_utc", "source", "device_id"}
    assert check["status"] == expected
    assert check["source"] == "synthetic"
    assert check["device_id"] == "demo-tray-01"
    assert check["checked_at_utc"].endswith("Z")
    assert all(value.encode() not in written for value in
        ["private-collector", "private-simulator", "private-password", "private-device", "private-token"])
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("previous", ["not JSON", "[]"])
def test_delivery_status_recovers_from_invalid_existing_status(tmp_path, previous):
    path = tmp_path / "mqtt-status.json"
    path.write_text(previous, encoding="utf-8")

    mqtt_client.write_delivery_status(False, path)

    status = json.loads(path.read_text(encoding="utf-8"))
    assert set(status) == {"latest_delivery_check"}
    assert status["latest_delivery_check"]["status"] == "failed"


def test_delivery_status_retries_windows_replace_contention(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "mqtt-status.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"running": True}), encoding="utf-8")
    original_replace = Path.replace
    attempts = []
    sleeps = []

    def temporarily_locked_replace(temporary, destination):
        attempts.append((temporary, Path(destination)))
        if len(attempts) <= 2:
            raise PermissionError("Simulated Windows reader holds the destination")
        return original_replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", temporarily_locked_replace)
    monkeypatch.setattr(mqtt_client.mqtt_runtime.time, "sleep", sleeps.append)

    mqtt_client.write_delivery_status(True, path)

    status = json.loads(path.read_text(encoding="utf-8"))
    assert status["running"] is True
    assert status["latest_delivery_check"]["status"] == "passed"
    assert status["latest_delivery_check"]["source"] == "synthetic"
    assert status["latest_delivery_check"]["device_id"] == "demo-tray-01"
    assert len(attempts) == 3
    assert all(destination == path for _, destination in attempts)
    assert len({temporary for temporary, _ in attempts}) == 1
    assert len(sleeps) == 2
    assert all(delay > 0 for delay in sleeps)
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("index", [0, 26, 1000000])
def test_generated_payload_is_synthetic_with_outputs_off(index):
    payload = mqtt_client.synthetic_payload(index, probe_id="unit-test")

    assert payload["device_id"] == "demo-tray-01"
    assert payload["source"] == "synthetic"
    assert payload["timestamp_origin"] == "publisher"
    assert payload["probe_id"] == "unit-test"
    assert all(payload[key] is False for key in
        ("low_water", "pump_on", "fan_on", "light_on", "actuation_enabled"))
    assert "no physical sensors" in payload["note"]
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert not any("password" in key or "credential" in key for key in payload)


def test_broker_settings_repr_never_contains_password():
    settings = mqtt_client.BrokerSettings(username="test-account", password="sentinel-private-password")

    rendered = repr(settings)
    assert "test-account" in rendered
    assert "sentinel-private-password" not in rendered
    assert "password=" not in rendered
