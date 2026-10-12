"""Exercise the actual API contracts used by the React workspace."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from astra_bio import api, storage, workspace
from astra_bio.model import Scenario, default_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "DEFAULT_DB", tmp_path / "workspace.sqlite")
    # API fixtures use their seeded SQLite store even on a configured laptop.
    # These tests must never query the user's live Atlas database.
    monkeypatch.setattr(api.mongo_runtime, "telemetry_reader", lambda: None)
    # Default arguments bind their initial values; redirect saving explicitly.
    save_run, save_config = workspace.save_run, workspace.save_configuration
    monkeypatch.setattr(workspace, "save_run", lambda name, data: save_run(name, data, tmp_path / "workspace.sqlite"))
    monkeypatch.setattr(workspace, "save_configuration", lambda name, config: save_config(name, config, tmp_path / "workspace.sqlite"))
    list_snapshots, load_snapshot = workspace.list_snapshots, workspace.load_snapshot
    monkeypatch.setattr(workspace, "list_snapshots", lambda kind: list_snapshots(kind, tmp_path / "workspace.sqlite"))
    monkeypatch.setattr(workspace, "load_snapshot", lambda identifier, kind: load_snapshot(identifier, kind, tmp_path / "workspace.sqlite"))
    return TestClient(api.app, base_url="http://127.0.0.1")


def test_bootstrap_serves_real_reference_and_private_config_never_appears(client):
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    data = response.json()
    assert len(data["references"]) == 10
    assert data["compositions"]["oats"]["fdc_id"] == 169705
    assert data["config"]["crew"] == 4
    assert client.get("/api/health").json()["frontend"] == "react"


def test_real_plan_saved_with_actual_scenario_and_restorable_inputs(client):
    config = replace(default_config(), days=8)
    scenario = Scenario("crew", "Additional crew", event_day=4, extra_crew=1)
    response = client.post("/api/plans", json={"config": asdict(config), "scenario": asdict(scenario)})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["metadata"]["baseline"]["daily"][:3] == run["metadata"]["adaptive"]["daily"][:3]
    assert run["metadata"]["adaptive"]["daily"][3]["crew"] == 5
    assert run["history_id"]
    saved = client.get("/api/snapshots/run/" + run["history_id"]).json()
    assert saved == run["metadata"]
    reopened = client.get("/api/bootstrap").json()
    assert reopened["last_run"]["metadata"] == saved
    assert reopened["config"]["days"] == 8
    assert reopened["demo_config"]["days"] == 90
    assert client.post("/api/explain", json={"metadata": saved}).json()["verified"] is True


def test_research_calibration_connected_to_growth_and_planner(client):
    result = client.post("/api/config/research", json={"config": asdict(default_config()), "ids": ["lettuce_waldmann_nasa"], "water": 1.5}).json()
    assert result["config"]["crops"][0]["grow_days"] == 30
    observations = client.get("/api/bootstrap").json()["observations"]
    result = client.post("/api/calibrate", json={"observations": observations, "holdout_ids": ["nasa_rlss_1992_cycle_2"]}).json()
    assert result["validation"]["mape_pct"] == pytest.approx(46.9387755)
    response = client.post("/api/growth", json={"crop_id": "lettuce_waldmann_nasa", "age_days": 12, "area_m2": 1})
    assert response.json()["available_harvest_kg"] == 0
    assert response.json()["illustrative_biomass_kg"] is None


def test_bad_inputs_external_origin_and_dns_rebinding_are_rejected(client):
    for raw in [{"crew": True}, {"foods": "invalid"}, {"unexpected": 1}, {"input_provenance": None}, {"nutrient_upper_per_crew": []}]:
        config = {**asdict(default_config()), **raw}
        assert client.post("/api/config/validate", json={"config": config}).status_code == 422
    assert client.post("/api/config/validate", json={}).status_code == 422
    assert client.post("/api/config/validate", json={"config": asdict(default_config())}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400


def test_unknown_intake_is_not_a_zero_intake_diagnosis(client):
    profiles = client.get("/api/bootstrap").json()["profiles"]
    response = client.post("/api/nutrition/assess", json={"profiles": profiles, "entries": [], "day": 1})
    rows = response.json()["rows"]
    assert all(row["intake"] is None and row["gap"] is None for row in rows)
    payload = {"profiles": profiles, "entries": [{"profile_id": "crew-1", "day": 1, "food_key": "kale", "grams": 75}], "day": 1}
    rows = client.post("/api/nutrition/assess", json=payload).json()["rows"]
    vitamin = next(row for row in rows if row["profile_id"] == "crew-1" and row["nutrient"] == "vitamin_c")
    assert vitamin["intake"] > 0
    assert vitamin["log_complete"] is False


def test_local_image_path_rejects_unsupported_or_invalid_photos(client):
    image = BytesIO()
    Image.new("RGB", (224, 224), "green").save(image, format="PNG")
    response = client.post("/api/plant-image?crop_species=lettuce", files={"file": ("leaf.png", image.getvalue(), "image/png")})
    assert response.json()["status"] == "rejected"
    assert response.json()["automatic_action"] is False
    response = client.post("/api/plant-image?crop_species=tomato", files={"file": ("leaf.png", b"not-an-image", "image/png")})
    assert response.json()["status"] == "rejected"


def test_telemetry_filters_independent_stream_and_hides_raw_secrets(client, tmp_path, monkeypatch):
    database = tmp_path / "telemetry.sqlite"
    now = datetime.now(timezone.utc)
    storage.insert_observation({"source": "hardware", "device_id": "tray-a", "ts_utc": (now - timedelta(minutes=5)).isoformat(), "air_temp_c": 22, "note": "SECRET"}, database)
    storage.insert_observation({"source": "synthetic", "device_id": "demo", "ts_utc": now.isoformat(), "air_temp_c": 33}, database)
    for name in ("list_devices", "recent_observations", "latest_observation", "device_states"):
        original = getattr(storage, name)
        monkeypatch.setattr(storage, name, lambda *args, _original=original, **kwargs: _original(*args, **{**kwargs, "path": database}))
    response = client.get("/api/telemetry?source=hardware&device_id=tray-a")
    data = response.json()
    assert data["latest"]["air_temp_c"] == 22
    assert all(row["device_id"] == "tray-a" for row in data["history"])
    assert data["age_seconds"] > 240
    assert "SECRET" not in response.text
    assert "raw_json" not in response.text
    assert data["actuation_enabled"] is False
