"""Exercise the Wi-Fi API contract; fake repository does not establish live Atlas delivery."""
from datetime import datetime, timezone
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from astra_bio import api, mongo_runtime
from astra_bio.mongo_runtime import GatewaySettings
from astra_bio.mongo_telemetry import MongoTelemetryUnavailable
from astra_bio.telemetry_gateway import create_app


TOKEN = "test-device-token-32-bytes-minimum"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class Repository:
    def __init__(self):
        self.records = []
        self.connected = True

    def ingest(self, payload):
        if not self.connected:
            raise MongoTelemetryUnavailable("private URI must never appear")
        self.records.append(payload)
        return {"id": "saved-row", "duplicate": False}

    def status(self):
        return {"backend": "mongodb", "connected": self.connected}


@pytest.fixture
def gateway():
    settings = GatewaySettings("mongodb://localhost", devices={
        "tray-01": hashlib.sha256(TOKEN.encode()).hexdigest()})
    repository = Repository()
    return TestClient(create_app(settings, repository), base_url="https://127.0.0.1"), repository


def packet(**changes):
    return {"device_id": "tray-01", "sample_id": "boot1_1", "source": "synthetic",
        "air_temp_c": 24.1, **changes}


def test_gateway_records_verified_provenance_missing_clock_and_absent_sensors(gateway):
    client, store = gateway
    response = client.post("/v1/telemetry", json=packet(), headers=HEADERS)
    assert response.status_code == 201
    assert response.json() == {"id": "saved-row", "duplicate": False,
        "storage": "mongodb", "actuation_enabled": False}
    record = store.records[0]
    assert record["transport"] == "https" and record["timestamp_origin"] == "gateway"
    assert record["device_ts_utc"] is None
    assert "relative_humidity_pct" not in record
    assert "bus_power_w" not in record
    assert datetime.fromisoformat(record["ts_utc"].replace("Z", "+00:00")).tzinfo == timezone.utc


def test_device_clock_preserved_and_duplicate_acknowledged(gateway):
    client, store = gateway
    store.ingest = lambda payload: {"id": "existing-row", "duplicate": True}
    response = client.post("/v1/telemetry", json=packet(ts_utc="2026-10-12T12:30:00+05:30"), headers=HEADERS)
    assert response.status_code == 200 and response.json()["duplicate"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic wrong"}])
def test_bad_device_authentication_writes_nothing(gateway, headers):
    client, store = gateway
    assert client.post("/v1/telemetry", json=packet(), headers=headers).status_code == 401
    assert client.get("/v1/health", headers=headers).status_code == 401
    assert store.records == []


def test_token_cannot_claim_other_device(gateway):
    client, store = gateway
    assert client.post("/v1/telemetry", json=packet(device_id="tray-02"), headers=HEADERS).status_code == 403
    assert store.records == []


@pytest.mark.parametrize("changes", [{"air_temp_c": 81}, {"air_temp_c": True}, {"air_temp_c": None},
    {"source": "unknown"}, {"relative_humidity_pct": 101}, {"pump_on": 2},
    {"received_at_utc": "forged"}, {"transport": "mqtt"}, {"ts_utc": "2026-10-12"},
    {"timestamp_origin": "gateway"}, {"actuation_enabled": True}])
def test_invalid_or_forged_readings_rejected(gateway, changes):
    client, store = gateway
    assert client.post("/v1/telemetry", json=packet(**changes), headers=HEADERS).status_code == 422
    assert store.records == []


def test_bad_json_large_packet_browser_origin_and_http_rejected(gateway):
    client, store = gateway
    assert client.post("/v1/telemetry", content=b'{"air_temp_c":NaN}',
        headers={**HEADERS, "Content-Type": "application/json"}).status_code == 422
    assert client.post("/v1/telemetry", content=b"x" * 16385,
        headers={**HEADERS, "Content-Type": "application/json"}).status_code == 413
    assert client.post("/v1/telemetry", json=packet(), headers={**HEADERS, "Origin": "https://other.site"}).status_code == 403
    assert client.post("http://127.0.0.1/v1/telemetry", json=packet(), headers=HEADERS).status_code == 403
    assert client.post("/v1/telemetry", content="{}", headers=HEADERS).status_code == 415
    assert store.records == []


def test_outage_never_acknowledged_or_exposes_credentials(gateway):
    client, store = gateway
    store.connected = False
    response = client.post("/v1/telemetry", json=packet(), headers=HEADERS)
    assert response.status_code == 503 and response.headers["Retry-After"] == "10"
    assert "private URI" not in response.text
    assert client.get("/v1/health", headers=HEADERS).status_code == 503
    assert store.records == []


def test_dashboard_uses_mongodb_readings_without_raw_payload_leak(monkeypatch):
    class Reader:
        def list_devices(self):
            return [{"device_id": "tray-01", "source": "hardware"}]
        def recent_observations(self, **kwargs):
            assert kwargs == {"device_id": "tray-01", "source": "hardware"}
            return [{"id": "mongo-id", "device_id": "tray-01", "source": "hardware",
                "ts_utc": "2026-10-12T12:00:00Z", "air_temp_c": 24,
                "raw_json": json.dumps({"transport": "https", "received_at_utc": "2026-10-12T12:00:00Z", "private": "secret"})}]
        def latest_observation(self, **kwargs):
            return self.recent_observations(**kwargs)[0]
        def device_states(self):
            return {}
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: Reader())
    client = TestClient(api.app, base_url="http://127.0.0.1")
    response = client.get("/api/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert data["storage"] == {"backend": "mongodb", "connected": True}
    assert data["latest"]["id"] == "mongo-id" and data["metadata"]["transport"] == "https"
    assert "secret" not in response.text and "raw_json" not in response.text


def test_dashboard_reports_atlas_failure_without_sqlite_fallback(monkeypatch):
    def failed():
        raise MongoTelemetryUnavailable("private URI must not leak")
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", failed)
    client = TestClient(api.app, base_url="http://127.0.0.1")
    response = client.get("/api/telemetry")
    assert response.status_code == 503 and "private URI" not in response.text


def test_private_configuration_validation_and_secret_repr(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"uri": "mongodb+srv://user:password@cluster.example/",
        "devices": {"tray-01": hashlib.sha256(TOKEN.encode()).hexdigest()}}))
    settings = mongo_runtime.load_settings(settings_path)
    assert "password" not in repr(settings) and TOKEN not in repr(settings)
    assert settings.authenticated_device(TOKEN) == "tray-01"
    assert settings.authenticated_device("wrong") is None
    settings_path.write_text('{"uri":"secret-bad-config"}')
    with pytest.raises(mongo_runtime.MongoConfigurationError, match="configuration is invalid") as error:
        mongo_runtime.load_settings(settings_path)
    assert "secret-bad-config" not in str(error.value)


def test_gateway_certificate_matches_lan_ip(tmp_path):
    from cryptography import x509
    import ipaddress
    mongo_runtime.ensure_tls("192.168.1.20", tmp_path)
    certificate = x509.load_pem_x509_certificate((tmp_path / "tls/server.crt").read_bytes())
    sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(sans.get_values_for_type(x509.IPAddress)) == {
        ipaddress.ip_address("192.168.1.20"), ipaddress.ip_address("127.0.0.1")}
    assert set(sans.get_values_for_type(x509.DNSName)) == {"192.168.1.20", "127.0.0.1", "localhost"}
    assert len(sans) == 5
    assert certificate.not_valid_after_utc > datetime.now(timezone.utc)


def test_gateway_certificate_regeneration_preserves_ca_and_exact_host_scope(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import padding
    import ipaddress
    mongo_runtime.ensure_tls("192.168.1.20", tmp_path)
    ca_bytes = (tmp_path / "tls/ca.crt").read_bytes()
    ca_key_bytes = (tmp_path / "tls/ca.key").read_bytes()
    first_server = (tmp_path / "tls/server.crt").read_bytes()
    mongo_runtime.ensure_tls("172.16.58.241", tmp_path)
    assert (tmp_path / "tls/ca.crt").read_bytes() == ca_bytes
    assert (tmp_path / "tls/ca.key").read_bytes() == ca_key_bytes
    assert (tmp_path / "tls/server.crt").read_bytes() != first_server
    server = x509.load_pem_x509_certificate((tmp_path / "tls/server.crt").read_bytes())
    ca = x509.load_pem_x509_certificate(ca_bytes)
    assert server.issuer == ca.subject
    ca.public_key().verify(server.signature, server.tbs_certificate_bytes,
                           padding.PKCS1v15(), server.signature_hash_algorithm)
    sans = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(sans.get_values_for_type(x509.IPAddress)) == {
        ipaddress.ip_address("172.16.58.241"), ipaddress.ip_address("127.0.0.1")}
    assert set(sans.get_values_for_type(x509.DNSName)) == {"172.16.58.241", "127.0.0.1", "localhost"}
    assert len(sans) == 5


def test_software_probe_sends_identical_synthetic_packet_and_confirms_one_record(tmp_path, monkeypatch):
    from io import StringIO
    settings = GatewaySettings("mongodb://localhost", lan_host="192.168.1.20", devices={
        "tray-01": hashlib.sha256(TOKEN.encode()).hexdigest()})
    mongo_runtime.ensure_tls(settings.lan_host, tmp_path)
    (tmp_path / "device-tray-01-config.h").write_text('#define DEVICE_TOKEN ' + json.dumps(TOKEN) + '\n')
    monkeypatch.setattr(mongo_runtime, "PRIVATE", tmp_path)
    monkeypatch.setattr(mongo_runtime, "load_settings", lambda: settings)
    sent = []
    def receive(request, timeout, context):
        assert request.full_url == "https://192.168.1.20:8502/v1/telemetry"
        assert context.check_hostname and context.verify_mode != 0
        assert request.get_header("Authorization") == "Bearer " + TOKEN
        sent.append(request.data)
        response = StringIO(json.dumps({"id": "one-record", "duplicate": len(sent) == 2}))
        response.status = 201 if len(sent) == 1 else 200
        return response
    monkeypatch.setattr(mongo_runtime, "urlopen", receive)
    class Reader:
        def recent_observations(self, **kwargs):
            assert kwargs["source"] == "synthetic"
            return [json.loads(sent[0])]
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: Reader())
    result = mongo_runtime.probe("tray-01")
    assert len(sent) == 2 and sent[0] == sent[1]
    assert result["passed"] and not result["hardware_validated"]
    assert json.loads(sent[0])["source"] == "synthetic"


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "169.254.1.20", "192.0.2.20"])
def test_config_does_not_accept_wildcard_public_or_nonlan_hosts(tmp_path, host):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"uri": "mongodb://localhost", "lan_host": host}))
    with pytest.raises(mongo_runtime.MongoConfigurationError):
        mongo_runtime.load_settings(settings_path)


@pytest.mark.parametrize("raw", [[], None, "bad"])
def test_environment_uri_does_not_bypass_saved_config_object_validation(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("ASTRA_MONGODB_URI", "mongodb://localhost")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(mongo_runtime.MongoConfigurationError):
        mongo_runtime.load_settings(path)


def test_device_token_rotation_invalidates_old_token_without_restart(monkeypatch):
    from astra_bio import telemetry_gateway
    current = GatewaySettings("mongodb://localhost", devices={
        "tray-01": hashlib.sha256(TOKEN.encode()).hexdigest()})
    monkeypatch.setattr(telemetry_gateway, "load_settings", lambda: current)
    client = TestClient(create_app(store=Repository()), base_url="https://127.0.0.1")
    assert client.get("/v1/health", headers=HEADERS).status_code == 200
    new_token = "new-device-token-32-bytes-minimum"
    current = GatewaySettings("mongodb://localhost", devices={
        "tray-01": hashlib.sha256(new_token.encode()).hexdigest()})
    assert client.get("/v1/health", headers=HEADERS).status_code == 401
    assert client.get("/v1/health", headers={"Authorization": "Bearer " + new_token}).status_code == 200


def test_setup_can_rebuild_corrupt_config_privately(tmp_path, monkeypatch):
    def corrupt():
        raise mongo_runtime.MongoConfigurationError("invalid config")
    monkeypatch.setattr(mongo_runtime, "load_settings", corrupt)
    monkeypatch.setattr(mongo_runtime, "PRIVATE", tmp_path)
    monkeypatch.setattr(mongo_runtime, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(mongo_runtime, "protect_directory", lambda directory: directory.mkdir(exist_ok=True))
    monkeypatch.setattr(mongo_runtime.getpass, "getpass", lambda prompt: "mongodb://localhost")
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    mongo_runtime.setup("tray-01", "192.168.1.20")
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["uri"] == "mongodb://localhost"
    assert len(settings["devices"]["tray-01"]) == 64
    header = (tmp_path / "device-tray-01-config.h").read_text()
    assert "#define TELEMETRY_SYNTHETIC_DEMO false" in header
    assert "mongodb://localhost" not in header
