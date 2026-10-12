"""Workspace-owned MQTT setup and foreground supervisor; no actuator commands."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

from astra_bio.storage import DEFAULT_DB, init_db

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime/mqtt"
PRIVATE = RUNTIME / "credentials.json"
STATUS = ROOT / "runtime/mqtt-status.json"
COLLECTOR_STATUS = RUNTIME / "collector-status.json"
STOP_PATH = RUNTIME / "stop-request"
SIMULATOR_ID = "demo-tray-01"
BROKER = RUNTIME / "bin/mosquitto.exe"
DEVICE_RE = re.compile(r"[a-z][a-z0-9-]{0,39}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def atomic_json(path: Path, content: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        # Windows readers may hold the destination briefly without delete sharing.
        for attempt in range(100):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(.02)
    finally:
        temporary.unlink(missing_ok=True)


def protect_directory(path: Path) -> None:
    """Limit private runtime files to this user, Administrators and SYSTEM."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        user = subprocess.check_output(["whoami"], text=True).strip()
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r",
             user + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError("Could not restrict private runtime directory permissions.")
    else:
        path.chmod(0o700)


def default_lan_host() -> str:
    # UDP connect selects a local interface address without sending a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(("192.0.2.1", 9))
        return connection.getsockname()[0]


def load_private() -> dict:
    if not PRIVATE.exists():
        raise RuntimeError("Run setup-mqtt.ps1 first.")
    return json.loads(PRIVATE.read_text(encoding="utf-8"))


def ensure_certificates(host: str) -> None:
    tls = RUNTIME / "tls"
    tls.mkdir(exist_ok=True)
    ca_path, key_path = tls / "ca.crt", tls / "ca.key"
    if ca_path.exists() and key_path.exists():
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        ca_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ASTRA-BIO local development CA")])
        now = datetime.now(timezone.utc)
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
              .sign(ca_key, hashes.SHA256()))
        key_path.write_bytes(ca_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    certificate_path, server_key_path = tls / "server.crt", tls / "server.key"
    if certificate_path.exists() and server_key_path.exists():
        existing = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        sans = existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if ipaddress.ip_address(host) in sans.get_values_for_type(x509.IPAddress) and \
                existing.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=7):
            return
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    server = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(ca.subject).public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address(host)), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
    server_key_path.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    certificate_path.write_bytes(server.public_bytes(serialization.Encoding.PEM))


def device_id(value: str) -> str:
    if not DEVICE_RE.fullmatch(value) or value == SIMULATOR_ID or value.startswith("astra-"):
        raise ValueError("Device ID must start with a lowercase letter, contain lowercase letters/digits/hyphens, "
                         "and be at most 40 characters; demo-tray-01/astra-* are reserved.")
    return value


def render_configuration(private: dict) -> None:
    # Explicit user ACLs: own telemetry/availability writes and own command reads.
    acl = [
        "user astra-collector",
        "topic read astra-bio/devices/+/telemetry",
        "topic read astra-bio/devices/+/availability",
        "", "user astra-simulator",
        f"topic write astra-bio/devices/{SIMULATOR_ID}/telemetry",
        f"topic write astra-bio/devices/{SIMULATOR_ID}/availability",
    ]
    for name in sorted(private["devices"]):
        acl.extend(["", f"user {name}", f"topic write astra-bio/devices/{name}/telemetry",
                    f"topic write astra-bio/devices/{name}/availability",
                    f"topic read astra-bio/devices/{name}/command"])
    (RUNTIME / "acl").write_text("\n".join(acl) + "\n", encoding="utf-8")
    users = {"astra-collector": private["collector_password"],
             "astra-simulator": private["simulator_password"], **private["devices"]}
    password_path = RUNTIME / "passwords"
    # Transient plaintext is in the restricted directory, converted in place.
    # Passwords never appear in command arguments.
    password_path.write_text("".join(f"{name}:{password}\n" for name, password in users.items()), encoding="utf-8")
    result = subprocess.run([str(RUNTIME / "bin/mosquitto_passwd.exe"), "-U", str(password_path)],
                            capture_output=True, text=True)
    if result.returncode:
        password_path.unlink(missing_ok=True)
        raise RuntimeError("Mosquitto password hashing failed.")
    posix = lambda file: str(file).replace("\\", "/")
    config = "\n".join([
        "allow_anonymous false",
        "password_file " + posix(password_path), "acl_file " + posix(RUNTIME / "acl"),
        "persistence false", "log_dest stdout", "log_type error", "log_type warning", "log_type notice",
        "max_packet_size 17408", "max_inflight_messages 20",
        "listener 1883 127.0.0.1", "protocol mqtt",
        f"listener 8883 {private['lan_host']}", "protocol mqtt",
        "cafile " + posix(RUNTIME / "tls/ca.crt"),
        "certfile " + posix(RUNTIME / "tls/server.crt"),
        "keyfile " + posix(RUNTIME / "tls/server.key"),
        "tls_version tlsv1.2", "",
    ])
    (RUNTIME / "broker.conf").write_text(config, encoding="utf-8")
    checked = subprocess.run([str(BROKER), "-c", str(RUNTIME / "broker.conf"), "--test-config"],
                             capture_output=True, text=True)
    if checked.returncode:
        raise RuntimeError("Broker configuration invalid: " + checked.stderr.strip())
    init_db()
    flow = json.loads((ROOT / "integration/node-red-flow.json").read_text())
    for node in flow:
        if node["id"] == "astra-mqtt-broker":
            node.update(broker="127.0.0.1", port="1883")
        elif node["id"] == "astra-sqlite-db":
            node["db"] = posix(DEFAULT_DB)
        elif node["id"] == "astra-collector-status-file":
            node["filename"] = posix(COLLECTOR_STATUS)
    node_dir = ROOT / "runtime/node-red"
    atomic_json(node_dir / "flows.json", flow)
    atomic_json(node_dir / "flows_cred.json", {
        "astra-mqtt-broker": {"user": "astra-collector", "password": private["collector_password"]},
    })
    protect_directory(node_dir / "userdir")


def provision(name: str, private: dict) -> None:
    name = device_id(name)
    destination = ROOT / "runtime/hardware" / name
    protect_directory(ROOT / "runtime/hardware")
    destination.mkdir(parents=True, exist_ok=True)
    template = (ROOT / "integration/esphome/tray.example.yaml").read_text()
    template = template.replace("device_name: astra-tray-01", f"device_name: astra-{name}")
    template = template.replace("device_id: tray-01", f"device_id: {name}")
    template = template.replace("friendly_name: ASTRA BIO Tray 01", f"friendly_name: ASTRA BIO {name}")
    (destination / "tray.yaml").write_text(template, encoding="utf-8")
    secrets_path = destination / "secrets.yaml"
    # Preserve user-entered Wi-Fi details on repeat provisioning.
    wifi_lines = ['wifi_ssid: "YOUR_PRIVATE_2_4_GHZ_WIFI"', 'wifi_password: "REPLACE_LOCALLY"']
    if secrets_path.exists():
        old = secrets_path.read_text()
        for i, key in enumerate(("wifi_ssid:", "wifi_password:")):
            matching = [line for line in old.splitlines() if line.startswith(key)]
            if matching:
                wifi_lines[i] = matching[0]
    ca_lines = (RUNTIME / "tls/ca.crt").read_text().strip().splitlines()
    content = "\n".join([
        "# Private generated credentials. Enter Wi-Fi details; never commit this file.",
        *wifi_lines, f'mqtt_broker: "{private["lan_host"]}"', f'mqtt_username: "{name}"',
        f'mqtt_password: "{private["devices"][name]}"',
        "mqtt_ca_certificate: |-", *["  " + line for line in ca_lines],
        'ntp_server: "pool.ntp.org"', "",
    ])
    secrets_path.write_text(content, encoding="utf-8")
    atomic_json(destination / "connection.json", {
        "device_id": name, "host": private["lan_host"], "port": 8883, "tls": True,
        "username": name, "password": private["devices"][name],
        "ca_certificate": str(RUNTIME / "tls/ca.crt"),
        "telemetry_topic": f"astra-bio/devices/{name}/telemetry",
        "availability_topic": f"astra-bio/devices/{name}/availability",
        "command_topic": f"astra-bio/devices/{name}/command",
    })
    print("Generated device files:", destination)


def setup(host: str | None, name: str) -> None:
    if not BROKER.exists():
        raise RuntimeError("Run scripts/install_mqtt.ps1 before setup.")
    protect_directory(RUNTIME)
    protect_directory(ROOT / "runtime/node-red")
    private = load_private() if PRIVATE.exists() else {
        "collector_password": secrets.token_urlsafe(32),
        "simulator_password": secrets.token_urlsafe(32), "devices": {},
    }
    host = host or private.get("lan_host") or default_lan_host()
    address = ipaddress.ip_address(host)
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
        raise ValueError("LanHost must be the laptop's reachable private IPv4 address.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
        try:
            check.bind((host, 0))
        except OSError as exc:
            raise ValueError("LanHost must belong to this laptop's active network interface.") from exc
    private["lan_host"] = host
    name = device_id(name)
    private["devices"].setdefault(name, secrets.token_urlsafe(32))
    atomic_json(PRIVATE, private)
    ensure_certificates(host)
    render_configuration(private)
    for existing in private["devices"]:
        provision(existing, private)
    print(f"Configured authenticated localhost:1883 and TLS {host}:8883. Restart run-stack after provisioning.")


def health_open() -> bool:
    try:
        with urlopen("http://127.0.0.1:8501/api/health", timeout=1) as response:
            payload = json.load(response)
            return response.status == 200 and payload.get("service") == "astra-bio-api"
    except OSError:
        return False


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.3):
            return True
    except OSError:
        return False


def collector_is_fresh(report: dict) -> bool:
    """A connected event needs a recent Node-RED heartbeat, not just a live PID."""
    if not isinstance(report, dict) or report.get("connected") is not True:
        return False
    try:
        instant = datetime.fromisoformat(report["checked_at_utc"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - instant).total_seconds()
        return -5 <= age <= 15
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def run_stack(with_app: bool = True) -> None:
    private = load_private()
    node = shutil.which("node.exe") or shutil.which("node")
    entry = ROOT / "runtime/node-red/node_modules/node-red/red.js"
    if not node or not entry.exists():
        raise RuntimeError("Install Node 24 and run npm ci --prefix runtime/node-red.")
    if port_open(1883) or port_open(1880):
        raise RuntimeError("Port 1883/1880 already in use. Stop the earlier stack before starting this one.")
    COLLECTOR_STATUS.unlink(missing_ok=True)
    STOP_PATH.unlink(missing_ok=True)
    log_dir = RUNTIME / "logs"
    log_dir.mkdir(exist_ok=True)
    children, logs = [], []
    original_status = {}
    try:
        original_status = json.loads(STATUS.read_text())
        if not isinstance(original_status, dict):
            original_status = {}
    except (OSError, ValueError):
        pass
    public = {
        "broker_host": "127.0.0.1", "broker_port": 1883,
        "lan_host": private["lan_host"], "profile": "authenticated local + LAN TLS",
        "config_path": str(RUNTIME / "broker.conf"),
        "topic": f"astra-bio/devices/{SIMULATOR_ID}/telemetry",
        "running": False, "checked_at_utc": utc_now(),
    }
    if original_status.get("latest_delivery_check"):
        public["latest_delivery_check"] = original_status["latest_delivery_check"]
    try:
        for name, command in [
            ("mosquitto", [str(BROKER), "-c", str(RUNTIME / "broker.conf")]),
            ("node-red", [node, str(entry), "--userDir", str(ROOT / "runtime/node-red/userdir"),
                          "--settings", str(ROOT / "runtime/node-red/settings.js")]),
        ]:
            log = (log_dir / (name + ".log")).open("w", encoding="utf-8")
            logs.append(log)
            children.append((name, subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)))
        if with_app and not health_open():
            if not (ROOT / "frontend/dist/index.html").exists():
                raise RuntimeError("Build the React frontend with npm run build --prefix frontend before starting the stack.")
            log = (log_dir / "api.log").open("w", encoding="utf-8")
            logs.append(log)
            children.append(("api", subprocess.Popen([
                sys.executable, "-m", "uvicorn", "astra_bio.api:app",
                "--host=127.0.0.1", "--port=8501"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)))
        print("Stack running in this terminal; Ctrl+C stops its owned processes.", flush=True)
        print("Dashboard http://127.0.0.1:8501 | Node-RED http://127.0.0.1:1880", flush=True)
        print(f"Device TLS endpoint {private['lan_host']}:8883", flush=True)
        while not STOP_PATH.exists():
            for name, child in children:
                if child.poll() is not None:
                    raise RuntimeError(f"{name} exited ({child.returncode}); inspect runtime/mqtt/logs/{name}.log.")
            try:
                collector = json.loads(COLLECTOR_STATUS.read_text())
                connected = collector_is_fresh(collector)
            except (OSError, ValueError):
                connected = False
            public.update(running=connected, checked_at_utc=utc_now())
            try:
                latest = json.loads(STATUS.read_text()).get("latest_delivery_check")
                if latest:
                    public["latest_delivery_check"] = latest
            except (OSError, ValueError):
                pass
            try:
                atomic_json(STATUS, public)
            except OSError:
                # A public health-file lock must not stop the data collector.
                # The dashboard expires the older snapshot if writes stay blocked.
                print("Public health update unavailable; telemetry collection continues.", flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping stack.")
    finally:
        public.update(running=False, checked_at_utc=utc_now())
        try:
            atomic_json(STATUS, public)
        except OSError:
            pass
        for _, child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for _, child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for log in logs:
            log.close()
        STOP_PATH.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    initialize = commands.add_parser("setup")
    initialize.add_argument("--lan-host")
    initialize.add_argument("--device-id", default="tray-01")
    register = commands.add_parser("provision")
    register.add_argument("device_id")
    run = commands.add_parser("run")
    run.add_argument("--no-app", action="store_true")
    commands.add_parser("stop")
    args = parser.parse_args()
    if args.action == "setup":
        setup(args.lan_host, args.device_id)
    elif args.action == "provision":
        setup(None, args.device_id)
    elif args.action == "run":
        run_stack(not args.no_app)
    else:
        load_private()
        STOP_PATH.touch()
        print("Requested graceful shutdown of the managed stack.")


if __name__ == "__main__":
    main()
