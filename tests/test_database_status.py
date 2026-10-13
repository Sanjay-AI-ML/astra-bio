from types import SimpleNamespace
import json

from fastapi.testclient import TestClient
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError
import pytest

from astra_bio import api, mongo_runtime
from astra_bio.mongo_telemetry import MongoTelemetryStore, connection_diagnosis


@pytest.mark.parametrize("error,code", [
    (OperationFailure("bad auth mongodb://user:secret@private.example", code=18), "authentication_failed"),
    (OperationFailure("user has no access", code=13), "permission_denied"),
    (ServerSelectionTimeoutError("certificate verify failed at private.example"), "tls_verification_failed"),
    (ConfigurationError("DNS lookup failed at private.example"), "dns_lookup_failed"),
    (ServerSelectionTimeoutError("Timeout connecting to mongodb://user:secret@private.example"), "network_unreachable"),
    (ConfigurationError("invalid mongodb://user:secret@private.example"), "invalid_configuration"),
    (RuntimeError("mongodb://user:secret@private.example"), "connection_failed"),
])
def test_connection_diagnosis_is_actionable_and_redacts_details(error, code):
    result = connection_diagnosis(error)
    assert result["error_code"] == code
    assert result["action"]
    assert "secret" not in json.dumps(result)
    assert "private.example" not in json.dumps(result)


def test_status_exposes_diagnosis_without_echoing_driver_error():
    def ping(command):
        raise ServerSelectionTimeoutError("Could not connect to mongodb://user:secret@private.example")
    client = SimpleNamespace(admin=SimpleNamespace(command=ping))
    status = MongoTelemetryStore("mongodb://localhost", client=client).status()
    assert not status["connected"]
    assert status["error_code"] == "network_unreachable"
    assert "secret" not in json.dumps(status)


def test_database_status_is_independent_of_api_health(monkeypatch):
    disconnected = {"configured":True, "connected":False, "error_code":"network_unreachable"}
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: SimpleNamespace(status=lambda: disconnected))
    client = TestClient(api.app, base_url="http://127.0.0.1")
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/database/status").json() == disconnected


def test_unconfigured_database_is_not_reported_as_connected(monkeypatch):
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: None)
    response = TestClient(api.app, base_url="http://127.0.0.1").get("/api/database/status")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["error_code"] == "not_configured"


def test_invalid_cloud_configuration_is_redacted(monkeypatch):
    def broken():
        raise mongo_runtime.MongoConfigurationError("Secret URI is invalid")
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", broken)
    result = TestClient(api.app, base_url="http://127.0.0.1").get("/api/database/status").json()
    assert result["error_code"] == "invalid_configuration"
    assert "Secret URI" not in json.dumps(result)


def test_environment_uri_whitespace_is_removed(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRA_MONGODB_URI", "  mongodb://localhost:27017  \n")
    settings = mongo_runtime.load_settings(tmp_path / "absent.json")
    assert settings.uri == "mongodb://localhost:27017"
