"""Provisioning uses private files; verify identity, TLS trust and stable secrets."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
import ipaddress
import pytest

from astra_bio import mqtt_runtime as runtime


@pytest.mark.parametrize("name", ["../bad", "tray/01", "UPPER", "demo-tray-01", "astra-collector", "", "1tray", "a"*41])
def test_unsafe_and_reserved_device_ids_rejected(name):
    with pytest.raises(ValueError):
        runtime.device_id(name)


def test_generated_tls_certificate_trust_and_ip_san(tmp_path):
    with patch.object(runtime, "RUNTIME", tmp_path):
        runtime.ensure_certificates("192.168.1.8")
        tls = tmp_path / "tls"
        original_ca = (tls / "ca.crt").read_bytes()
        original_server = (tls / "server.crt").read_bytes()
        ca = x509.load_pem_x509_certificate(original_ca)
        cert = x509.load_pem_x509_certificate(original_server)
        ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
        assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert ipaddress.ip_address("192.168.1.8") in sans.get_values_for_type(x509.IPAddress)
        assert cert.not_valid_after_utc > datetime.now(timezone.utc)
        runtime.ensure_certificates("192.168.1.8")
        assert (tls / "server.crt").read_bytes() == original_server
        runtime.ensure_certificates("192.168.1.9")
        assert (tls / "ca.crt").read_bytes() == original_ca
        new_cert = x509.load_pem_x509_certificate((tls / "server.crt").read_bytes())
        assert ipaddress.ip_address("192.168.1.9") in new_cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)


def test_reprovision_preserves_wifi_and_device_namespace(tmp_path):
    mqtt = tmp_path / "runtime/mqtt"
    (mqtt / "tls").mkdir(parents=True)
    (mqtt / "tls/ca.crt").write_text("PUBLIC TEST CA")
    templates = tmp_path / "integration/esphome"
    templates.mkdir(parents=True)
    (templates / "tray.example.yaml").write_text(
        (runtime.ROOT / "integration/esphome/tray.example.yaml").read_text())
    private = {"lan_host": "192.168.1.8", "devices": {"tray-02": "test-secret"}}
    with patch.object(runtime, "ROOT", tmp_path), patch.object(runtime, "RUNTIME", mqtt):
        runtime.provision("tray-02", private)
        folder = tmp_path / "runtime/hardware/tray-02"
        secrets_file = folder / "secrets.yaml"
        secrets_file.write_text(secrets_file.read_text().replace('"YOUR_PRIVATE_2_4_GHZ_WIFI"', '"My bench Wi-Fi"'))
        private["lan_host"] = "192.168.1.9"
        runtime.provision("tray-02", private)
        assert 'wifi_ssid: "My bench Wi-Fi"' in secrets_file.read_text()
        assert 'mqtt_broker: "192.168.1.9"' in secrets_file.read_text()
        connection = json.loads((folder / "connection.json").read_text())
        assert connection["telemetry_topic"] == "astra-bio/devices/tray-02/telemetry"
        assert connection["port"] == 8883 and connection["tls"]
        assert "device_id: tray-02" in (folder / "tray.yaml").read_text()


def test_status_write_survives_transient_windows_reader_lock(tmp_path):
    original = Path.replace
    attempts = []
    def reader_lock(path, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            raise PermissionError("Windows reader has no delete sharing")
        return original(path, destination)
    public = tmp_path / "mqtt-status.json"
    with patch.object(Path, "replace", reader_lock):
        runtime.atomic_json(public, {"running": True})
    assert json.loads(public.read_text()) == {"running": True}
    assert len(attempts) == 3
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("age, expected", [(0, True), (10, True), (30, False), (-30, False)])
def test_collector_connection_requires_recent_heartbeat(age, expected):
    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
    assert runtime.collector_is_fresh({"connected": True, "checked_at_utc": timestamp}) is expected
    assert runtime.collector_is_fresh({"connected": False, "checked_at_utc": timestamp}) is False
    assert runtime.collector_is_fresh({"connected": True, "checked_at_utc": "broken"}) is False
