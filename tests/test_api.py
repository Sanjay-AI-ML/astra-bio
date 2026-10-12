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


def test_reviewed_crew_event_saved_with_timely_advice_and_reloaded_roster(client):
    config=replace(default_config(),days=18,initial_water_l=300,initial_energy_kwh=80)
    source=client.post('/api/plans',json={'config':asdict(config),'scenario':asdict(Scenario('none','Nominal',event_day=18))}).json()
    profiles=[{'profile_id':f'crew-{i}','name':f'Sample Crew {i}',
        'targets':{'energy':2200,'protein':90+i,'vitamin_c':100},'targets_reviewed':True} for i in range(1,7)]
    response=client.post('/api/plans/continue',json={'run_id':source['history_id'],'through_day':6,
        'mission_change':{'crew_profiles':profiles,'reason':'Two arrivals'}})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['metadata']['adaptive']['daily'][:6]==source['metadata']['adaptive']['daily'][:6]
    assert result['metadata']['adaptive']['daily'][6]['crew']==6
    assert result['metadata']['adaptive']['daily'][6]['protein_target']==sum(p['targets']['protein'] for p in profiles)
    assert result['planning_advice']['day']==7
    assert 'selection_reason' in result['planning_advice']
    assert all(b['harvest_day']<=18 for b in result['planning_advice']['planned_crop_actions'])
    restored=client.get('/api/bootstrap').json()['last_run']['metadata']
    assert restored['crew_profiles']==profiles
    assert restored['planning_advice']==result['planning_advice']
    assert source['history_id']!=result['history_id']
    rejected=client.post('/api/plans/continue',json={'run_id':result['history_id'],'through_day':5})
    assert rejected.status_code==422


def test_manual_roster_reset_is_saved_and_pending_arrivals_do_not_return_on_reload(client):
    old_profiles = [{'profile_id':f'crew-{i}','name':f'Crew {i}',
        'targets':{'energy':2200,'protein':90,'vitamin_c':100},'targets_reviewed':True} for i in range(1,7)]
    config = replace(default_config(),days=18,initial_water_l=300,initial_energy_kwh=80,
        planning_events=[{'day':12,'crew':6,'crew_profiles':old_profiles,
            'targets_per_crew':{'energy':2200,'protein':90,'vitamin_c':100}}])
    scenario = Scenario('pending','Pending combined event',event_day=10,extra_crew=2,
                        water_factor=.5,target_factors={'protein':1.4})
    source = client.post('/api/plans',json={'config':asdict(config),'scenario':asdict(scenario)}).json()
    replacement = old_profiles[:3]
    response = client.post('/api/plans/continue',json={'run_id':source['history_id'],'through_day':4,
        'mission_change':{'crew_profiles':replacement,'replace_future_crew_changes':True}})
    assert response.status_code==200,response.text
    result = response.json()
    metadata = result['metadata']
    assert metadata['adaptive']['daily'][:4] == source['metadata']['adaptive']['daily'][:4]
    assert metadata['adaptive']['inventories']['4'] == source['metadata']['adaptive']['inventories']['4']
    assert all(row['crew']==3 for row in metadata['adaptive']['daily'][4:])
    assert metadata['adaptive']['daily'][9]['protein_target'] == pytest.approx(378)
    assert metadata['adaptive']['daily'][9]['water_available_l'] == 25
    assert metadata['config']['planning_events'] == [{'day':5,'crew':3,'crew_profiles':replacement,
        'targets_per_crew':{'energy':2200,'protein':90,'vitamin_c':100},'cancel_scenario_crew':True}]
    assert metadata['scenario'] == asdict(scenario) | {'failed_crop_ids':[]}
    assert metadata['continuation']['superseded_crew_event_days'] == [12]
    restored = client.get('/api/bootstrap').json()['last_run']['metadata']
    assert restored == metadata
    second = client.post('/api/plans/continue',json={'run_id':result['history_id'],'through_day':7})
    assert second.status_code==200,second.text
    continued = second.json()['metadata']
    assert continued['adaptive']['daily'][:7] == metadata['adaptive']['daily'][:7]
    assert all(row['crew']==3 for row in continued['adaptive']['daily'][7:])
    assert continued['crew_profiles'] == replacement


def test_crew_limit_validation_accounts_for_cancelled_relative_arrivals():
    config = replace(default_config(),days=18,crew=12,
        planning_events=[{'day':5,'crew':12,'cancel_scenario_crew':True}])
    scenario = Scenario('pending','Pending arrivals',event_day=10,extra_crew=2)
    assert api.scenario_value(asdict(scenario),config) == scenario
    with pytest.raises(ValueError,match='at most 12 crew'):
        api.scenario_value(asdict(scenario),replace(config,planning_events=[]))


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


def test_named_sample_crew_has_traceable_intake_separate_blood_and_bounded_count(client):
    sample = client.get("/api/nutrition/sample?count=4").json()
    assert sample["sample_only"] is True
    assert [p["name"] for p in sample["profiles"]] == ["Shree Ram Vishal", "Shamyuktha", "Sanjay", "Vamshika"]
    assert sample["references"]["hemoglobin"]["female_cutoff_g_dl"] == 12
    assessed = client.post("/api/nutrition/assess", json={**sample, "day": 1}).json()
    assert assessed["rows"] == [row for row in sample["assessments"] if row["day"] == 1]
    expanded = client.get("/api/nutrition/sample?count=6").json()
    assert [p["name"] for p in expanded["profiles"]][-2:] == ["Sample Crew 5", "Sample Crew 6"]
    assert not any(row["profile_id"] in {"crew-5", "crew-6"} for row in expanded["blood_samples"])
    assert client.get("/api/nutrition/sample?count=13").status_code == 422
    assert client.get("/api/nutrition/sample?count=0").status_code == 422
    assert "crew_sample" in client.get("/api/bootstrap").json()


def test_sample_marker_roundtrip_does_not_add_blood_measurements_to_food_logs(client):
    sample = client.get("/api/nutrition/sample").json()
    state = {**sample, "sample_context": {"sample_only": True, "fixture_version": 1}}
    saved = client.post("/api/nutrition/save", json={"name": "Fictional crew", "state": state})
    assert saved.status_code == 200, saved.text
    restored = client.get("/api/snapshots/nutrition/" + saved.json()["id"]).json()
    assert restored["sample_context"] == {"sample_only": True, "fixture_version": 1}
    assert "blood_samples" not in restored
    assert "hemoglobin_g_dl" not in restored["profiles"][0]
    assert len(restored["entries"]) == len(sample["entries"])


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
