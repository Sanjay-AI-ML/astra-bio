"""Generated MQTT telemetry and reason-code-aware checks; never hardware data."""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import socket
import sqlite3
import ssl
import threading
import time
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from astra_bio import mqtt_runtime
from astra_bio.storage import DEFAULT_DB, init_db

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runtime/mqtt/credentials.json"
STATUS = ROOT / "runtime/mqtt-status.json"
CA = ROOT / "runtime/mqtt/tls/ca.crt"
DEVICE_ID = "demo-tray-01"
TELEMETRY = f"astra-bio/devices/{DEVICE_ID}/telemetry"
AVAILABILITY = f"astra-bio/devices/{DEVICE_ID}/availability"
NOT_AUTHORIZED = 0x87


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_credentials(path: Path = PRIVATE) -> dict:
    try:
        credentials = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Private MQTT setup is unavailable; run setup-mqtt.ps1 first.") from exc
    if not isinstance(credentials, dict) or any(not isinstance(credentials.get(key), str) or not credentials[key]
        for key in ("collector_password", "simulator_password", "lan_host")):
        raise RuntimeError("Private MQTT setup is incomplete; run setup-mqtt.ps1 again.")
    devices = credentials.get("devices", {})
    if not isinstance(devices, dict) or any(not isinstance(key, str) or not isinstance(value, str)
        for key, value in devices.items()):
        raise RuntimeError("The private device account registry is invalid.")
    return credentials


@dataclass(frozen=True)
class BrokerSettings:
    host: str = "127.0.0.1"
    port: int = 1883
    tls: bool = False
    ca_file: Path = CA
    username: str | None = None
    password: str | None = field(default=None, repr=False)


class MQTTSession:
    """Own one network loop; collect broker ACKs rather than assuming permission."""
    def __init__(self, settings: BrokerSettings, subscriptions: tuple[str, ...] = (), availability: bool = False):
        self.settings = settings
        self.condition = threading.Condition(threading.RLock())
        self.connected = threading.Event()
        self.connack: int | None = None
        self.connection_count = 0
        self.publish_acks: dict[int, tuple[int, float]] = {}
        self.subscription_acks: dict[int, list[int]] = {}
        self.subscription_mids: dict[str, int] = {}
        self.messages = deque(maxlen=1000)
        self.subscriptions = subscriptions
        self.availability = availability
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"astra-check-{uuid4().hex[:20]}", protocol=mqtt.MQTTv5)
        self.client.connect_timeout = 4
        self.client.reconnect_delay_set(min_delay=1, max_delay=8)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        if settings.username is not None:
            self.client.username_pw_set(settings.username, settings.password)
        if settings.tls:
            context = ssl.create_default_context(cafile=str(settings.ca_file))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
            self.client.tls_set_context(context)
        elif settings.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Use verified TLS for every non-loopback MQTT host.")
        if availability:
            self.client.will_set(AVAILABILITY, "offline", qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        with self.condition:
            self.connack = reason_code.value
            if self.connack == 0:
                self.connection_count += 1
                self.subscription_mids.clear()
                for topic in self.subscriptions:
                    result, mid = client.subscribe(topic, qos=1)
                    if result == mqtt.MQTT_ERR_SUCCESS:
                        self.subscription_acks.pop(mid, None)
                        self.subscription_mids[topic] = mid
                if self.availability:
                    client.publish(AVAILABILITY, "online", qos=1, retain=True)
                self.connected.set()
            else:
                self.connected.clear()
            self.condition.notify_all()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected.clear()
        with self.condition:
            self.condition.notify_all()

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        with self.condition:
            self.publish_acks[mid] = (reason_code.value, time.monotonic())
            if len(self.publish_acks) > 1000:
                self.publish_acks.pop(next(iter(self.publish_acks)))
            self.condition.notify_all()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        with self.condition:
            self.subscription_acks[mid] = [code.value for code in reason_codes]
            self.condition.notify_all()

    def _on_message(self, client, userdata, message):
        with self.condition:
            self.messages.append((message.topic, bytes(message.payload), message.retain))
            self.condition.notify_all()

    def start(self, timeout: float = 10) -> int:
        properties = Properties(PacketTypes.CONNECT)
        properties.SessionExpiryInterval = 0
        self.client.connect_async(self.settings.host, self.settings.port, keepalive=15,
            clean_start=True, properties=properties)
        self.client.loop_start()
        with self.condition:
            if not self.condition.wait_for(lambda: self.connack is not None, timeout=timeout):
                raise TimeoutError("No broker CONNACK received; verify endpoint, TLS and stack status.")
            return self.connack

    def require_connection(self, timeout: float = 10) -> None:
        code = self.start(timeout)
        if code != 0:
            raise RuntimeError(f"Broker rejected authentication (CONNACK {code}).")

    def wait_subscriptions(self, timeout: float = 10) -> dict[str, list[int]]:
        with self.condition:
            ready = lambda: len(self.subscription_mids) == len(self.subscriptions) and all(
                mid in self.subscription_acks for mid in self.subscription_mids.values())
            if not self.condition.wait_for(ready, timeout=timeout):
                raise TimeoutError("No matching SUBACK received for the current connection.")
            return {topic: self.subscription_acks[mid] for topic, mid in self.subscription_mids.items()}

    def publish(self, topic: str, payload: str | dict, *, retain: bool = False, timeout: float = 10) -> int:
        if not self.connected.wait(timeout):
            raise TimeoutError("MQTT session did not reconnect before publishing.")
        body = json.dumps(payload, allow_nan=False) if isinstance(payload, dict) else payload
        # Call Paho without our callback lock: its own outgoing-message lock can
        # be held while invoking on_publish. Holding both can deadlock.
        started = time.monotonic()
        info = self.client.publish(topic, body, qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish could not be queued (code {int(info.rc)}).")
        with self.condition:
            # A fast ACK may arrive before publish() returns. Timestamps also
            # exclude an old birth/timeout ACK when a message ID is reused.
            ready = lambda: info.mid in self.publish_acks and self.publish_acks[info.mid][1] >= started
            if not self.condition.wait_for(ready, timeout=timeout):
                raise TimeoutError("No matching MQTTv5 PUBACK received.")
            return self.publish_acks.pop(info.mid)[0]

    def wait_probe(self, probe_id: str, timeout: float = 5) -> bool:
        def received():
            for topic, body, retained in self.messages:
                try:
                    payload = json.loads(body)
                except (UnicodeError, ValueError):
                    continue
                if topic == TELEMETRY and not retained and isinstance(payload, dict) and payload.get("probe_id") == probe_id:
                    return True
            return False
        with self.condition:
            return self.condition.wait_for(received, timeout=timeout)

    def interrupt_socket(self, timeout: float = 12) -> None:
        """Break this check's own transport; leave the shared broker running."""
        before = self.connection_count
        connection = self.client.socket()
        if connection is None:
            raise RuntimeError("No owned MQTT socket is available for the reconnect check.")
        connection.shutdown(socket.SHUT_RDWR)
        with self.condition:
            if not self.condition.wait_for(lambda: self.connection_count > before, timeout=timeout):
                raise TimeoutError("The test client did not automatically reconnect after socket interruption.")
        self.wait_subscriptions(timeout)

    def close(self) -> None:
        if self.availability and self.connected.is_set():
            try:
                self.publish(AVAILABILITY, "offline", retain=True, timeout=3)
            except (RuntimeError, TimeoutError):
                pass
        self.client.disconnect()
        self.client.loop_stop()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def synthetic_payload(index: int = 0, probe_id: str | None = None) -> dict:
    """Generated readings; output flags are always off, not control instructions."""
    return {"ts_utc": utc_now(), "device_id": DEVICE_ID, "source": "synthetic",
        "timestamp_origin": "publisher", "probe_id": probe_id or uuid4().hex,
        "air_temp_c": round(23.5 + .5 * math.sin(index / 13), 2),
        "relative_humidity_pct": round(62 + 3 * math.sin(index / 26), 2),
        "solution_temp_c": round(21 + .25 * math.cos(index / 13), 2),
        "light_lux": round(11500 + 500 * math.sin(index / 13), 2),
        "bus_voltage_v": 12.0, "bus_current_a": 1.5, "bus_power_w": 18.0,
        "low_water": False, "pump_on": False, "fan_on": False, "light_on": False,
        "actuation_enabled": False, "note": "Generated MQTT test; no physical sensors or hardware commands."}


def simulate(settings: BrokerSettings, count: int = 1, interval: float = 5, timeout: float = 10) -> int:
    if count < 0 or not math.isfinite(interval) or interval <= 0:
        raise ValueError("Count must be nonnegative and interval must be positive.")
    delivered = 0
    with MQTTSession(settings, availability=True) as publisher:
        publisher.require_connection(timeout)
        while count == 0 or delivered < count:
            code = publisher.publish(TELEMETRY, synthetic_payload(delivered), timeout=timeout)
            if code >= 128:
                raise RuntimeError(f"Broker denied synthetic telemetry (PUBACK {code}).")
            delivered += 1
            print(f"Synthetic MQTT telemetry acknowledged: {delivered}; no hardware sensors.", flush=True)
            if count == 0 or delivered < count:
                time.sleep(interval)
    return delivered


def wait_sqlite_probe(probe_id: str, path: Path = DEFAULT_DB, timeout: float = 10) -> int | None:
    init_db(path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with closing(sqlite3.connect(path, timeout=2)) as connection:
            rows = connection.execute("SELECT id,raw_json FROM observations WHERE device_id=? AND source='synthetic' "
                "AND instr(raw_json,?)>0 ORDER BY id DESC LIMIT 5", (DEVICE_ID, probe_id)).fetchall()
        for row_id, raw in rows:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("probe_id") == probe_id and payload.get("transport") == "mqtt" and payload.get("received_at_utc"):
                return row_id
        time.sleep(.1)
    return None


def write_delivery_status(passed: bool, path: Path = STATUS) -> None:
    """Merge only a safe result summary, using a unique atomic-write temporary."""
    try:
        previous = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    allowed = ("broker_host", "broker_port", "profile", "running", "checked_at_utc", "config_path", "topic", "lan_host")
    public = {key: previous[key] for key in allowed if key in previous}
    public["latest_delivery_check"] = {"status": "passed" if passed else "failed",
        "checked_at_utc": utc_now(), "source": "synthetic", "device_id": DEVICE_ID}
    mqtt_runtime.atomic_json(path, public)


def run_checks(settings: BrokerSettings, credentials: dict, *, db_path: Path = DEFAULT_DB,
               status_path: Path = STATUS, timeout: float = 10, reconnect: bool = True) -> dict:
    """Check the running stack; all valid observations belong to the simulator."""
    report = {"transport": "TLS with CA and hostname verification" if settings.tls else "authenticated loopback",
        "hardware_attached": "not established; every observation published here is synthetic", "checks": {}}
    checks = report["checks"]
    collector_settings = replace(settings, username="astra-collector", password=credentials["collector_password"])
    simulator_settings = replace(settings, username="astra-simulator", password=credentials["simulator_password"])
    delivered = False
    hardware_dummy_probe = None
    try:
        with MQTTSession(collector_settings, (TELEMETRY,)) as collector, MQTTSession(simulator_settings, availability=True) as simulator:
            collector.require_connection(timeout)
            if any(code >= 128 for values in collector.wait_subscriptions(timeout).values() for code in values):
                raise RuntimeError("The authorized collector subscription was rejected.")
            simulator.require_connection(timeout)
            probe = uuid4().hex
            code = simulator.publish(TELEMETRY, synthetic_payload(probe_id=probe), timeout=timeout)
            broker_received = code < 128 and collector.wait_probe(probe, timeout)
            row_id = wait_sqlite_probe(probe, db_path, timeout) if broker_received else None
            delivered = row_id is not None
            checks["synthetic_node_red_sqlite_delivery"] = {"passed": delivered, "puback": code,
                "collector_received": broker_received, "sqlite_row_id": row_id}
            for name, user, password in [("anonymous_connection_denied", None, None),
                ("wrong_password_connection_denied", "astra-simulator", uuid4().hex)]:
                with MQTTSession(replace(settings, username=user, password=password)) as rejected:
                    reason = rejected.start(timeout)
                checks[name] = {"passed": reason in (0x86, NOT_AUTHORIZED), "connack": reason}
            other_device = sorted(credentials.get("devices", {}))[0] if credentials.get("devices") else "unauthorized-tray"
            dummy = {"probe_id": uuid4().hex, "test_only": True, "device_id": DEVICE_ID, "source": "synthetic"}
            for name, session, topic in [
                ("cross_device_publish_denied", simulator, f"astra-bio/devices/{other_device}/telemetry"),
                ("simulator_command_publish_denied", simulator, f"astra-bio/devices/{DEVICE_ID}/command"),
                ("collector_publish_denied", collector, TELEMETRY),
            ]:
                reason = session.publish(topic, dummy, timeout=timeout)
                checks[name] = {"passed": reason == NOT_AUTHORIZED, "puback": reason}
            devices = credentials.get("devices", {})
            if devices:
                hardware_id = sorted(devices)[0]
                # No hardware telemetry, will, birth or retained availability is emitted by this account.
                with MQTTSession(replace(settings, username=hardware_id, password=devices[hardware_id]), (TELEMETRY,)) as forbidden:
                    forbidden.require_connection(timeout)
                    subacks = forbidden.wait_subscriptions(timeout)[TELEMETRY]
                    hardware_dummy_probe = uuid4().hex
                    hardware_dummy = {"probe_id": hardware_dummy_probe, "test_only": True,
                        "device_id": hardware_id, "note": "ACL probe only; deliberately no source or sensor readings."}
                    for name, topic, allowed in [
                        ("device_own_telemetry_publish_allowed", f"astra-bio/devices/{hardware_id}/telemetry", True),
                        ("device_cross_device_publish_denied", TELEMETRY, False),
                        ("device_command_publish_denied", f"astra-bio/devices/{hardware_id}/command", False),
                    ]:
                        reason = forbidden.publish(topic, hardware_dummy, timeout=timeout)
                        checks[name] = {"passed": reason < 128 if allowed else reason == NOT_AUTHORIZED,
                            "puback": reason, "payload": "Invalid sensor payload; broker permission test only."}
                    probe = uuid4().hex
                    reason = simulator.publish(TELEMETRY, synthetic_payload(probe_id=probe), timeout=timeout)
                    positive = reason < 128 and collector.wait_probe(probe, timeout)
                    leaked = forbidden.wait_probe(probe, 2)
                    explicitly_rejected = any(code >= 128 for code in subacks)
                    valid_negative = explicitly_rejected or forbidden.connected.is_set()
                    checks["device_wrong_topic_read_denied"] = {"passed": positive and not leaked and valid_negative,
                        "suback": subacks, "authorized_collector_received": positive, "unauthorized_device_received": leaked,
                        "enforcement": "SUBACK rejected" if explicitly_rejected else "delivery suppressed"}
            else:
                checks["device_wrong_topic_read_denied"] = {"passed": False, "detail": "No provisioned device account; run provision-device.ps1 first."}
            retained_probe = uuid4().hex
            try:
                # This deliberate negative test is the only retained telemetry
                # publication. The normal simulator always uses retain=False.
                retained_ack = simulator.publish(TELEMETRY, synthetic_payload(probe_id=retained_probe), retain=True, timeout=timeout)
                barrier_probe = uuid4().hex
                barrier_ack = simulator.publish(TELEMETRY, synthetic_payload(probe_id=barrier_probe), timeout=timeout)
                barrier_row = wait_sqlite_probe(barrier_probe, db_path, timeout)
                retained_row = wait_sqlite_probe(retained_probe, db_path, min(2, timeout))
                checks["retained_telemetry_rejected_by_ingestion"] = {
                    "passed": retained_ack < 128 and barrier_ack < 128 and barrier_row is not None and retained_row is None,
                    "retained_puback": retained_ack, "later_nonretained_sqlite_row_id": barrier_row,
                    "retained_sqlite_row_id": retained_row}
            finally:
                simulator.publish(TELEMETRY, "", retain=True, timeout=timeout)
            if reconnect:
                collector.interrupt_socket(timeout + 5)
                probe = uuid4().hex
                reason = simulator.publish(TELEMETRY, synthetic_payload(probe_id=probe), timeout=timeout)
                received = reason < 128 and collector.wait_probe(probe, timeout)
                checks["automatic_reconnect_and_resubscribe"] = {"passed": received and collector.connection_count >= 2,
                    "successful_connections": collector.connection_count, "collector_received_after_interruption": received}
            if hardware_dummy_probe is not None:
                # Subsequent valid probes prove the ingestion pipeline advanced.
                # The permission-only packet must never become a hardware reading.
                with closing(sqlite3.connect(db_path, timeout=2)) as connection:
                    rows = connection.execute("SELECT COUNT(*) FROM observations WHERE instr(raw_json,?)>0",
                        (hardware_dummy_probe,)).fetchone()[0]
                checks["hardware_permission_dummy_not_ingested"] = {"passed": rows == 0, "sqlite_rows": rows}
    except (OSError, RuntimeError, TimeoutError, ValueError, sqlite3.Error) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # This field reports delivery only; the full security report is printed separately.
        try:
            write_delivery_status(delivered, status_path)
        except OSError:
            report["status_summary_warning"] = "The public status file could not be updated; delivery and security results remain separate."
    report["passed"] = bool(checks) and "error" not in report and all(check.get("passed") is True for check in checks.values())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("simulate", "check"):
        command = commands.add_parser(action)
        command.add_argument("--tls", action="store_true", help="Verify LAN TLS on port 8883 using the local CA.")
        command.add_argument("--host", help="Default: loopback; with --tls: configured LAN host.")
        command.add_argument("--port", type=int)
        command.add_argument("--timeout", type=float, default=10)
        if action == "simulate":
            command.add_argument("--count", type=int, default=1, help="0 publishes continuously until Ctrl+C.")
            command.add_argument("--interval", type=float, default=5)
        else:
            command.add_argument("--no-reconnect", action="store_true", help="Skip only the owned-client socket interruption check.")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive")
    try:
        credentials = load_credentials()
        settings = BrokerSettings(host=args.host or (credentials["lan_host"] if args.tls else "127.0.0.1"),
            port=args.port or (8883 if args.tls else 1883), tls=args.tls,
            username="astra-simulator", password=credentials["simulator_password"])
        if not 1 <= settings.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if args.action == "simulate":
            simulate(settings, args.count, args.interval, args.timeout)
            return 0
        report = run_checks(settings, credentials, timeout=args.timeout, reconnect=not args.no_reconnect)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1
    except KeyboardInterrupt:
        print("Synthetic MQTT publisher stopped; no actuator commands were sent.")
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"MQTT operation failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
