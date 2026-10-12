from copy import deepcopy
from dataclasses import asdict, replace

from fastapi.testclient import TestClient
import pytest

from astra_bio import api, workspace
from astra_bio.continuation import continue_plan
from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, Scenario
from astra_bio.planner import run_comparison, _solve_lp
from astra_bio.model import default_config
from astra_bio.nutrition import load_compositions


def habitat():
    return HabitatConfig(days=9, crew=1, area_m2=2, reserve_days=0,
        water_budget_l_per_day=20, power_budget_kwh_per_day=20,
        foods=[FoodSpec("pantry", "Stored food", 3, {"protein": 1})],
        crops=[CropSpec("test", "Test crop", 2, 1, 1, 1, {"protein": 1})],
        targets_per_crew={"protein": 1}, nutrient_units={"protein": "g"}, max_fresh_kg_per_crew_day=2)


def test_continuation_preserves_stock_history_and_carries_real_cohorts():
    config, scenario = habitat(), Scenario("none", "Nominal", event_day=10)
    source = run_comparison(config, scenario).adaptive
    original = deepcopy(source.as_dict())
    assert source.daily and any(b["day"] <= 2 < b["harvest_day"] for b in source.planting)
    updated, result, details = continue_plan(config, scenario, source, 2, {"protein": 1.2})
    assert updated.targets_per_crew["protein"] == 1  # Base conditions stay historical.
    assert updated.planning_events[-1]["targets_per_crew"]["protein"] == pytest.approx(1.2)
    assert details["opening_stocks_kg"] == source.inventories[2]
    assert details["growing_cohorts_at_boundary"]
    assert result.adaptive.daily[:2] == result.baseline.daily[:2] == source.daily[:2]
    assert result.adaptive.consumption[2] == source.consumption[2]
    assert result.adaptive.inventories[2] == source.inventories[2]
    assert result.baseline.daily[2]["protein_target"] == pytest.approx(1.2)
    assert result.adaptive.daily[2]["protein_target"] == pytest.approx(1.2)
    assert source.as_dict() == original
    # Continuation cannot restock the original pantry. Future consumption uses
    # boundary stock plus crop harvest, rather than the original three kg.
    remaining = details["opening_stocks_kg"]["pantry"]
    assert sum(v["pantry"] for d, v in result.adaptive.consumption.items() if d > 2) <= remaining + 1e-6
    assert len(result.adaptive.daily) == config.days


@pytest.mark.parametrize("day,factors", [(0, {}), (9, {}), (True, {}), (2, {"protein": 0}),
    (2, {"protein": float("nan")}), (2, {"protein": True}), (2, {"iron": 1}), (2, [])])
def test_invalid_continuation_is_rejected(day, factors):
    config, scenario = habitat(), Scenario("none", "Nominal")
    source = run_comparison(config, scenario).adaptive
    with pytest.raises(ValueError):
        continue_plan(config, scenario, source, day, factors)


def test_missing_stock_and_upper_bound_are_not_silently_relaxed():
    config, scenario = habitat(), Scenario("none", "Nominal")
    source = run_comparison(config, scenario).adaptive
    broken = deepcopy(source)
    del broken.inventories[2]["pantry"]
    with pytest.raises(ValueError, match="inventory"):
        continue_plan(config, scenario, broken, 2)
    with pytest.raises(ValueError, match="Upper bound"):
        continue_plan(replace(config, nutrient_upper_per_crew={"protein": 1.1}), scenario, source, 2, {"protein": 1.2})


def test_new_plantings_crossing_a_known_future_crop_loss_keep_loss_factor():
    config = replace(habitat(), foods=[FoodSpec("pantry", "Stored food", 0, {"protein": 1})])
    scenario = Scenario("loss", "Known upcoming loss", event_day=4, crop_yield_factors={"test": .5})
    result = _solve_lp(config, scenario, 2, {"pantry": 0, "test": 0}, [], "Future")
    assert result.daily
    affected = [b for b in result.planting if b["day"] < 4 <= b["harvest_day"]]
    assert affected
    for batch in affected:
        assert batch["predicted_harvest_kg"] == pytest.approx(batch["area_m2"] * .5)


def test_http_continuation_saves_restorable_state_and_serializes_lock(tmp_path, monkeypatch):
    database = tmp_path / "workspace.sqlite"
    saver = workspace.save_run
    monkeypatch.setattr(workspace, "save_run", lambda name, metadata: saver(name, metadata, database))
    client = TestClient(api.app, base_url="http://127.0.0.1")
    config, scenario = habitat(), Scenario("none", "Nominal")
    source = client.post("/api/plans", json={"config": asdict(config), "scenario": asdict(scenario)}).json()
    payload = {"metadata": source["metadata"], "through_day": 2, "target_factors": {"protein": 1.1}}
    response = client.post("/api/plans/continue", json=payload)
    assert response.status_code == 200, response.text
    continued = response.json()
    assert continued["history_id"] != source["history_id"]
    saved = workspace.load_snapshot(continued["history_id"], "run", database)
    restored = workspace.restore_run(saved)
    assert restored[2].adaptive.daily[:2] == source["metadata"]["adaptive"]["daily"][:2]
    assert saved["continuation"]["simulation_only"] is True
    second = client.post("/api/plans/continue", json={"metadata": saved, "through_day": 4}).json()
    assert second["metadata"]["adaptive"]["daily"][:4] == saved["adaptive"]["daily"][:4]
    assert len(second["metadata"]["continuation"]["previous_boundaries"]) == 1
    assert client.post("/api/plans/continue", json={"metadata": second["metadata"], "through_day": 2}).status_code == 422
    recovery = client.post("/api/recovery", json={"metadata": saved, "options": {"lower_yield_factor": 1, "harvest_delay_days": 0}})
    assert recovery.status_code == 200, recovery.text
    assert recovery.json()["event_day"] == 3
    assert all(c["plan"]["daily"][:2] == saved["adaptive"]["daily"][:2] for c in recovery.json()["candidates"] if c["plan"])
    api.SOLVER_LOCK.acquire()
    try:
        assert client.post("/api/plans/continue", json=payload).status_code == 409
    finally:
        api.SOLVER_LOCK.release()


def test_crop_advisor_api_uses_saved_inputs_and_reports_reference_limits(tmp_path, monkeypatch):
    saver = workspace.save_run
    monkeypatch.setattr(workspace, "save_run", lambda name, metadata: saver(name, metadata, tmp_path / "history.sqlite"))
    client = TestClient(api.app, base_url="http://127.0.0.1")
    config = default_config()
    response = client.post("/api/crop-advisor", json={"config": asdict(config), "priority": "protein", "day": 1})
    assert response.status_code == 200, response.text
    report = response.json()
    soy = next(c for c in report["recommendations"] if c["crop_id"] == "soy")
    assert soy["provenance"]["composition"]["status"] == "configured_assumption"
    assert soy["provenance"]["composition"]["source_url"] is None
    assert client.post("/api/crop-advisor", json={"config": asdict(config), "priority": "iron"}).status_code == 422
    reference = client.post("/api/config/crop-nutrition", json={"config": asdict(config)}).json()
    assert reference["config"]["foods"] == asdict(config)["foods"]
    assert "soy" in reference["unmatched_crop_ids"]
    kale = next(c for c in reference["config"]["crops"] if c["id"] == "kale")
    assert kale["nutrients_per_kg"] == load_compositions()["kale"].nutrients_per_kg
    assert kale["grow_days"] == 30
    source = client.post("/api/plans", json={"config": asdict(habitat()), "scenario": asdict(Scenario("none", "Nominal"))}).json()
    saved_report = client.post("/api/crop-advisor", json={"metadata": source["metadata"], "config": asdict(config), "priority": "protein", "day": 2}).json()
    assert [c["crop_id"] for c in saved_report["recommendations"]] == ["test"]
