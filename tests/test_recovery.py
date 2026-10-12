from dataclasses import asdict, replace
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from astra_bio import api, workspace
from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, Scenario
from astra_bio.planner import ComparisonResult, run_comparison
from astra_bio.recovery import RecoveryOptions, analyze_recovery


def config(**changes):
    return replace(HabitatConfig(days=5, crew=1, area_m2=2, water_budget_l_per_day=4,
        power_budget_kwh_per_day=2, reserve_days=0, crew_water_l_per_day=0,
        foods=[FoodSpec("food", "Stored food", 5, {"n": 1})], crops=[],
        targets_per_crew={"n": 1}, max_fresh_kg_per_crew_day=2), **changes)


def candidate(report, identifier):
    return next(row for row in report["candidates"] if row["id"] == identifier)


def test_food_minimum_arrives_at_event_and_preserves_history_and_inputs():
    model = config()
    scenario = Scenario("crew", "Crew increase", event_day=3, extra_crew=1)
    comparison = run_comparison(model, scenario)
    original = deepcopy(comparison.as_dict())
    report = analyze_recovery(model, scenario, comparison=comparison)
    food = candidate(report, "food")
    assert food["summary"]["meets_targets"]
    assert food["resources"]["primary_minimum"] == pytest.approx(3)
    assert food["resources"]["food_kg"]["food"] == pytest.approx(3, abs=1e-6)
    assert food["resources"]["minimum_proven"] is True
    assert food["resources"]["arrival_day"] == 3
    assert food["plan"]["daily"][:2] == comparison.baseline.daily[:2]
    assert food["plan"]["inventories"][2] == comparison.baseline.inventories[2]
    assert comparison.as_dict() == original
    assert model.foods[0].initial_kg == 5
    assert candidate(report, "water")["status"] == "infeasible"
    assert candidate(report, "power")["status"] == "infeasible"
    assert report["automatic_action"] is False and report["inventory_updated"] is False


def test_zero_water_budget_needs_real_daily_crew_allowance():
    model = config(days=2, crew_water_l_per_day=1)
    report = analyze_recovery(model, Scenario("water", "No water", event_day=1, water_factor=0))
    water = candidate(report, "water")
    assert water["summary"]["meets_targets"]
    assert water["resources"]["primary_minimum"] == pytest.approx(1)
    assert all(row["water_available_l"] == pytest.approx(1, abs=1e-6) for row in water["plan"]["daily"])
    assert all(case["summary"]["resource_gap_days"] == 0 for case in water["stress_tests"])
    assert candidate(report, "food")["status"] == "infeasible"


def test_power_minimum_supports_a_required_crop_and_stress_exposes_delay():
    model = config(days=2, power_budget_kwh_per_day=0,
        foods=[FoodSpec("food", "Stored food", 1, {"n": 1})],
        crops=[CropSpec("crop", "Fast crop", 1, 1, 0, 2, {"n": 1})])
    report = analyze_recovery(model, Scenario("power", "No electricity", event_day=1))
    power = candidate(report, "power")
    assert power["resources"]["primary_minimum"] == pytest.approx(2)
    assert power["summary"]["target_gap_days"] == 0
    delayed = next(case for case in power["stress_tests"] if case["id"] == "delayed")
    assert delayed["summary"]["target_gap_days"] > 0
    assert power["cases_passed"] < power["cases_tested"]


def test_resource_limit_is_not_reported_as_a_minimum_when_infeasible():
    report = analyze_recovery(config(), Scenario("crew", "More crew", event_day=3, extra_crew=1),
        RecoveryOptions(food_limit_kg=.1))
    food = candidate(report, "food")
    assert food["status"] == "infeasible"
    assert not food["summary"]["available"]
    assert food["resources"] == {} and food["plan"] is None
    assert "within" in food["warnings"][0]


def test_reserve_requirement_is_an_explicit_separate_choice():
    model = config(days=2, foods=[FoodSpec("food", "Stored food", 2, {"n": 1})], reserve_days=1)
    scenario = Scenario("nominal", "Nominal", event_day=1)
    basic = analyze_recovery(model, scenario, RecoveryOptions(include_reserve=False))
    assert candidate(basic, "food")["resources"]["primary_minimum"] == 0
    protected = analyze_recovery(model, scenario, RecoveryOptions(include_reserve=True))
    food = candidate(protected, "food")
    assert food["resources"]["primary_minimum"] == pytest.approx(1)
    assert food["summary"]["reserve_gap_days"] == 0


def test_stress_test_holds_meals_and_plantings_fixed_and_checks_area():
    model = config(days=4, foods=[FoodSpec("food", "Stored food", 1, {"n": 1})], area_m2=1,
        crops=[CropSpec("crop", "Fast crop", 1, 1, 0, 0, {"n": 1})])
    report = analyze_recovery(model, Scenario("nominal", "Nominal", event_day=1))
    replan = candidate(report, "replan")
    assert replan["summary"]["target_gap_days"] == 0
    submitted = next(case for case in replan["stress_tests"] if case["id"] == "submitted")
    combined = next(case for case in replan["stress_tests"] if case["id"] == "combined")
    assert submitted["summary"]["meets_targets"]
    assert combined["summary"]["target_gap_days"] > 0
    assert combined["summary"]["resource_gap_days"] > 0  # delayed batches overlap the tray area


@pytest.mark.parametrize("options", [RecoveryOptions(food_limit_kg=True), RecoveryOptions(lower_yield_factor=float("nan")),
    RecoveryOptions(harvest_delay_days=1.5), RecoveryOptions(include_reserve=1), RecoveryOptions(power_limit_kwh_per_day=-1)])
def test_invalid_uncertainty_or_limit_values_are_rejected(options):
    with pytest.raises(ValueError):
        analyze_recovery(config(), Scenario("nominal", "Nominal", event_day=1), options)


def test_degenerate_stress_settings_do_not_invent_independent_cases():
    report = analyze_recovery(config(), Scenario("nominal", "Nominal", event_day=1),
        RecoveryOptions(lower_yield_factor=1, harvest_delay_days=0))
    assert candidate(report, "replan")["cases_tested"] == 1


def test_continued_recovery_starts_after_elapsed_history_and_stress_preserves_prefix(monkeypatch):
    from astra_bio import recovery

    model = config(days=6, foods=[FoodSpec("food", "Stored food", 0, {"n": 1})])
    scenario = Scenario("crew", "Earlier crew increase", event_day=2, extra_crew=1)
    source = run_comparison(model, scenario).adaptive
    continued = ComparisonResult(deepcopy(source), deepcopy(source), scenario.name, {})
    original = deepcopy(continued.as_dict())
    replay_original = recovery._replay_fixed_plan
    tested = []

    def preserve_prefix(*args, **kwargs):
        plan = args[2]
        replay = replay_original(*args, **kwargs)
        assert kwargs["start_day"] == 4
        assert replay.daily[:3] == plan.daily[:3]
        assert {d: rows for d, rows in replay.inventories.items() if d < 4} == {
            d: rows for d, rows in plan.inventories.items() if d < 4}
        assert {d: rows for d, rows in replay.consumption.items() if d < 4} == {
            d: rows for d, rows in plan.consumption.items() if d < 4}
        tested.append(replay)
        return replay

    monkeypatch.setattr(recovery, "_replay_fixed_plan", preserve_prefix)
    report = analyze_recovery(model, scenario, comparison=continued, start_day=4)
    food = candidate(report, "food")
    assert food["resources"]["primary_minimum"] == pytest.approx(6, abs=1e-6)
    assert food["resources"]["arrival_day"] == 4
    assert food["summary"]["days_evaluated"] == 3
    assert food["summary"]["meets_targets"]
    assert food["plan"]["daily"][:3] == source.daily[:3]
    assert report["event_day"] == 4 and report["remaining_days"] == 3
    assert report["inputs"]["start_day"] == 4
    assert report["inputs"]["scenario"]["event_day"] == 2
    assert all(case["summary"]["days_evaluated"] == 3 for case in food["stress_tests"])
    assert tested
    assert continued.as_dict() == original


def test_recovery_can_start_before_original_disruption_without_changing_scenario():
    model = config(days=5, foods=[FoodSpec("food", "Stored food", 0, {"n": 1})])
    scenario = Scenario("crew", "Future crew increase", event_day=4, extra_crew=1)
    comparison = run_comparison(model, scenario)
    report = analyze_recovery(model, scenario, comparison=comparison, start_day=2)
    food = candidate(report, "food")
    # Two single-crew days, followed by two days with two crew; the additional
    # food arrives on day two rather than waiting until the original event.
    assert food["resources"]["primary_minimum"] == pytest.approx(6, abs=1e-6)
    assert food["resources"]["arrival_day"] == 2
    assert food["plan"]["daily"][:1] == comparison.baseline.daily[:1]
    assert food["summary"]["meets_targets"]
    assert [row["crew"] for row in food["plan"]["daily"]] == [1, 1, 1, 2, 2]
    assert all(case["summary"]["target_gap_days"] == 0 for case in food["stress_tests"])
    assert scenario.event_day == 4


@pytest.mark.parametrize("start", [True, 0, 6, 2.5, float("nan")])
def test_invalid_recovery_start_boundary_is_rejected(start):
    with pytest.raises(ValueError):
        analyze_recovery(config(), Scenario("nominal", "Nominal", event_day=1), start_day=start)


def test_default_recovery_provenance_does_not_add_an_implicit_start_day():
    report = analyze_recovery(config(), Scenario("nominal", "Nominal", event_day=1))
    assert "start_day" not in report["inputs"]
    assert report["event_day"] == 1


def test_api_uses_saved_server_state_instead_of_forged_draft_and_does_not_save(tmp_path, monkeypatch):
    path = tmp_path / "workspace.sqlite"
    model = config()
    scenario = Scenario("crew", "More crew", event_day=3, extra_crew=1)
    comparison = run_comparison(model, scenario)
    metadata = {"schema_version": 1, "created_at_utc": "2026-10-12T00:00:00Z", "input_status": "demo",
        "config": asdict(model), "scenario": asdict(scenario), "baseline": comparison.baseline.as_dict(), "adaptive": comparison.adaptive.as_dict()}
    identifier = workspace.save_run("Test", metadata, path)
    load = workspace.load_snapshot
    monkeypatch.setattr(workspace, "load_snapshot", lambda ident, kind: load(ident, kind, path))
    with TestClient(api.app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/recovery", json={"run_id": identifier, "config": {"crew": 99}, "scenario": {}})
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["inputs"]["config"]["crew"] == 1
        assert report["source_run_id"] == identifier
        assert candidate(report, "food")["resources"]["primary_minimum"] == pytest.approx(3)
        assert len(workspace.list_snapshots("run", path)) == 1
        invalid = client.post("/api/recovery", json={"config": asdict(model), "scenario": asdict(scenario), "options": {"harvest_delay_days": 2.5}})
        assert invalid.status_code == 422
        assert api.SOLVER_LOCK.acquire(blocking=False)
        try:
            assert client.post("/api/recovery", json={"config": asdict(model), "scenario": asdict(scenario)}).status_code == 409
        finally:
            api.SOLVER_LOCK.release()
