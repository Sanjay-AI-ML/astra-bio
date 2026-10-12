"""Private Atlas/gateway configuration and device provisioning; no sensor claims."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import threading
import ssl
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .mqtt_runtime import atomic_json, default_lan_host, protect_directory

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runtime/mongodb"
SETTINGS = PRIVATE / "settings.json"
LAN_NETWORKS = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class MongoConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewaySettings:
    uri: str = field(repr=False)
    database: str = "astra_bio"
    collection: str = "observations"
    lan_host: str = "127.0.0.1"
    port: int = 8502
    devices: dict[str, str] = field(default_factory=dict, repr=False)

    def authenticated_device(self, token: str) -> str | None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        return next((device for device, expected in self.devices.items()
                     if secrets.compare_digest(digest, expected)), None)


def load_settings(path: Path = SETTINGS) -> GatewaySettings | None:
    """A malformed configured store never silently falls back to synthetic SQLite."""
    if not path.exists() and not os.environ.get("ASTRA_MONGODB_URI"):
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(raw, dict):
            raise ValueError()
        uri = os.environ.get("ASTRA_MONGODB_URI") or raw["uri"]
        database = raw.get("database", "astra_bio")
        collection = raw.get("collection", "observations")
        host = raw.get("lan_host", "127.0.0.1")
        port = raw.get("port", 8502)
        devices = raw.get("devices", {})
        if not isinstance(uri, str) or not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError()
        if not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,63}", name)
                   for name in (database, collection)):
            raise ValueError()
        address = ipaddress.ip_address(host)
        if address.version != 4 or not (address.is_loopback or any(address in network for network in LAN_NETWORKS)):
            raise ValueError()
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError()
        if not isinstance(devices, dict) or any(
            not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device)
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            for device, digest in devices.items()
        ):
            raise ValueError()
        return GatewaySettings(uri, database, collection, host, port, devices)
    except (ValueError, KeyError, TypeError, OSError):
        raise MongoConfigurationError("MongoDB configuration is invalid. Run setup-mongodb.ps1 again.") from None


_store_key = None
_store = None
_lock = threading.Lock()


def telemetry_reader():
    """Share a process-local pool; both gateway and dashboard use the same Atlas data."""
    global _store, _store_key
    settings = load_settings()
    if settings is None:
        return None
    from .mongo_telemetry import MongoTelemetryStore
    key = (settings.uri, settings.database, settings.collection)
    with _lock:
        if _store_key != key:
            if _store is not None:
                _store.close()
            _store = MongoTelemetryStore(*key)
            _store_key = key
        return _store


def ensure_tls(host: str, directory: Path = PRIVATE) -> None:
    """Use an independent CA so the existing MQTT certificate setup is untouched."""
    tls = directory / "tls"
    tls.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_file, key_file = tls / "ca.crt", tls / "ca.key"
    if ca_file.exists() and key_file.exists():
        ca = x509.load_pem_x509_certificate(ca_file.read_bytes())
        ca_key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ASTRA-BIO telemetry gateway CA")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
              .sign(ca_key, hashes.SHA256()))
        key_file.write_bytes(ca_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    addresses = {host, "127.0.0.1"}
    certificate = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(ca.subject).public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([
            *[x509.IPAddress(ipaddress.ip_address(value)) for value in sorted(addresses)],
            x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
    (tls / "server.key").write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (tls / "server.crt").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def setup(device: str, host: str | None = None, port: int = 8502) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", device) or device.startswith("demo-"):
        raise ValueError("Choose a physical device ID such as tray-01; demo-* is reserved.")
    try:
        previous = load_settings()
    except MongoConfigurationError:
        previous = None
        print("Saved MongoDB configuration is invalid. Setup will rebuild it from the details you enter.")
    uri = getpass.getpass("MongoDB Atlas connection URI (hidden; Enter keeps existing): ").strip()
    uri = uri or (previous.uri if previous else "")
    from .mongo_telemetry import MongoTelemetryStore
    # Validate connection settings locally; network check is a separate explicit command.
    store = MongoTelemetryStore(uri)
    store.close()
    host = host or (previous.lan_host if previous else default_lan_host())
    address = ipaddress.ip_address(host)
    if address.version != 4 or not any(address in network for network in LAN_NETWORKS):
        raise ValueError("Use the laptop's private Wi-Fi IPv4 address, such as 192.168.1.20.")
    if not 1024 <= port <= 65535:
        raise ValueError("Gateway port must be between 1024 and 65535.")
    protect_directory(PRIVATE)
    ensure_tls(host, PRIVATE)
    token = secrets.token_urlsafe(32)
    devices = dict(previous.devices) if previous else {}
    devices[device] = hashlib.sha256(token.encode()).hexdigest()
    settings = {"uri": uri, "database": previous.database if previous else "astra_bio",
        "collection": previous.collection if previous else "observations",
        "lan_host": host, "port": port, "devices": devices}
    atomic_json(SETTINGS, settings)
    ssid = input("Wi-Fi SSID (optional; can fill private header later): ").strip()
    password = getpass.getpass("Wi-Fi password (hidden; optional): ") if ssid else ""
    values = {"WIFI_SSID": ssid, "WIFI_PASSWORD": password,
        "GATEWAY_URL": f"https://{host}:{port}/v1/telemetry", "DEVICE_ID": device,
        "DEVICE_TOKEN": token, "ROOT_CA": (PRIVATE / "tls/ca.crt").read_text(encoding="utf-8")}
    header = "#pragma once\n// Private credentials: never share or commit this header.\n"
    header += "\n".join(f"#define {name} {json.dumps(value, ensure_ascii=False)}" for name, value in values.items())
    header += "\n#define TELEMETRY_SYNTHETIC_DEMO false\n"
    output = PRIVATE / f"device-{device}-config.h"
    output.write_text(header, encoding="utf-8")
    print(f"Atlas configuration saved privately. Device header: {output}")
    print(f"HTTPS telemetry endpoint: https://{host}:{port}/v1/telemetry")
    print("Copy the header to integration/esp32-mongodb/include/config.h; run run-gateway.ps1.")
    print("Provisioning this device again rotates its token. Database connection not yet checked.")
    print("Restart the gateway after changing its IP/port or TLS certificate. Device tokens reload on each request.")


def probe(device: str) -> dict:
    """An explicit synthetic test verifies TLS, Mongo receipt and duplicate handling."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", device):
        raise ValueError("Choose a provisioned device ID such as tray-01.")
    settings = load_settings()
    if settings is None or device not in settings.devices:
        raise MongoConfigurationError("Provision this device with setup-mongodb.ps1 first.")
    try:
        header = (PRIVATE / f"device-{device}-config.h").read_text(encoding="utf-8")
        match = re.search(r'^#define DEVICE_TOKEN (".*")$', header, re.MULTILINE)
        token = json.loads(match.group(1))
        if settings.authenticated_device(token) != device:
            raise ValueError()
    except (OSError, AttributeError, ValueError):
        raise MongoConfigurationError("The private device header is missing or outdated; provision it again.") from None
    sample = {"device_id": device, "sample_id": "check_" + secrets.token_hex(12),
        "source": "synthetic", "ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "air_temp_c": 23.5, "relative_humidity_pct": 60.0}
    body = json.dumps(sample).encode()
    context = ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.crt"))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    acknowledgements = []
    try:
        for expected_status in (201, 200):
            request = Request(f"https://{settings.lan_host}:{settings.port}/v1/telemetry", data=body,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            with urlopen(request, timeout=10, context=context) as response:
                result = json.load(response)
                if response.status != expected_status or result.get("duplicate") != (expected_status == 200):
                    raise ValueError()
                acknowledgements.append(result)
        if acknowledgements[0]["id"] != acknowledgements[1]["id"]:
            raise ValueError()
        store = telemetry_reader()
        saved = [row for row in store.recent_observations(device_id=device, source="synthetic", limit=10000)
                 if row.get("sample_id") == sample["sample_id"]]
        if len(saved) != 1:
            raise ValueError()
    except Exception:
        raise MongoConfigurationError("Synthetic delivery check failed. Verify Atlas access, gateway status and TLS configuration.") from None
    return {"passed": True, "transport": "verified HTTPS", "storage": "mongodb",
        "source": "synthetic", "device_id": device, "sample_id": sample["sample_id"],
        "duplicate_retry": "acknowledged without an extra record", "hardware_validated": False}


def main():
    parser = argparse.ArgumentParser(description="Private MongoDB/ESP32 telemetry setup")
    parser.add_argument("action", choices=("setup", "check", "probe", "run"))
    parser.add_argument("--device-id", default="tray-01")
    parser.add_argument("--lan-host")
    parser.add_argument("--port", type=int, default=8502)
    args = parser.parse_args()
    try:
        if args.action == "setup":
            setup(args.device_id, args.lan_host, args.port)
        elif args.action == "check":
            store = telemetry_reader()
            if store is None:
                raise MongoConfigurationError("Run setup-mongodb.ps1 first.")
            status = store.status()
            print(json.dumps(status, indent=2))
            if not status["connected"]:
                raise MongoConfigurationError("Atlas is unavailable. Check the URI, database user and IP access list.")
            store.ensure_indexes()
            print("MongoDB connection and required indexes verified. No readings inserted.")
        elif args.action == "probe":
            print(json.dumps(probe(args.device_id), indent=2))
        else:
            settings = load_settings()
            if settings is None or not settings.devices:
                raise MongoConfigurationError("Run setup-mongodb.ps1 first to configure Atlas and a device token.")
            import uvicorn
            uvicorn.run("astra_bio.telemetry_gateway:app", host=settings.lan_host, port=settings.port,
                ssl_certfile=str(PRIVATE / "tls/server.crt"), ssl_keyfile=str(PRIVATE / "tls/server.key"),
                proxy_headers=False, access_log=False)
    except (ValueError, MongoConfigurationError) as error:
        parser.exit(1, str(error) + "\n")
    except RuntimeError:
        parser.exit(1, "MongoDB telemetry setup failed. Check your private configuration and connectivity.\n")


if __name__ == "__main__":
    main()
