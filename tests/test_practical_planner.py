"""Safety/operability constraints change allocations rather than only labelling them."""
from dataclasses import replace

import pytest

from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, Scenario
from astra_bio.planner import run_comparison


def config(**changes):
    base = HabitatConfig(days=8, crew=1, area_m2=1, water_budget_l_per_day=5,
        power_budget_kwh_per_day=2, crew_water_l_per_day=0, reserve_days=0,
        max_fresh_kg_per_crew_day=2, foods=[FoodSpec("food", "Stored food", 20, {"n": 1, "v": 10})],
        crops=[], targets_per_crew={"n": 1, "v": 1})
    return replace(base, **changes)


def test_upper_bound_and_portion_cap_leave_shortfall_explicit():
    model = config(nutrient_upper_per_crew={"v": 5}, max_total_food_kg_per_crew_day=.25)
    result = run_comparison(model, Scenario("none", "None", event_day=99)).adaptive
    assert result.status == "feasible_with_shortfalls"
    for row in result.daily:
        assert row["food_mass_kg"] <= .25 + 1e-6
        assert row["v_supply"] <= 5 + 1e-6
        assert row["n_shortfall"] >= .75 - 1e-6


def test_expiring_food_not_eaten_or_credited_to_buffer():
    model = config(foods=[FoodSpec("food", "Expiring food", 20, {"n": 1, "v": 10}, shelf_life_days=2)], reserve_days=1)
    result = run_comparison(model, Scenario("none", "None", event_day=99)).adaptive
    assert result.inventories[3]["food"] == 0
    assert result.consumption[3]["food"] == 0
    assert result.daily[1]["reserve_days_available"] == 0
    assert sum(result.food_totals_kg.values()) + result.metrics["total_waste_kg"] == pytest.approx(20)


def test_nutrient_retention_uses_explicit_age_and_unit_consistent_supply():
    model = config(foods=[FoodSpec("food", "Retention assumption", 20, {"n": 1, "v": 10}, nutrient_half_life_days={"v": 1})])
    result = run_comparison(model, Scenario("none", "None", event_day=99)).adaptive
    for row in result.daily:
        eaten = result.consumption[row["day"]]["food"]
        assert row["v_supply"] == pytest.approx(eaten * 10 * 2 ** (-(row["day"] - 1)))


def test_plantings_are_whole_tray_increments():
    model = config(foods=[FoodSpec("food", "Empty", 0, {"n": 1, "v": 1})],
        crops=[CropSpec("crop", "Tray crop", 2, 1, 1, .5, {"n": 1, "v": 1})],
        area_m2=.9, planting_increment_m2=.25)
    result = run_comparison(model, Scenario("water", "Water change", event_day=4, water_factor=.4)).adaptive
    assert result.status != "solver_error", result.warnings
    assert result.planting
    for batch in result.planting:
        assert batch["area_m2"] / .25 == pytest.approx(round(batch["area_m2"] / .25))
    assert all(row["area_m2"] <= .9 + 1e-6 for row in result.daily)


def test_fixed_replay_reports_expired_stock_and_does_not_replan_past():
    model = config(foods=[FoodSpec("food", "Expiring food", 20, {"n": 1, "v": 10}, shelf_life_days=5)])
    result = run_comparison(model, Scenario("crew", "Crew change", event_day=3, extra_crew=1))
    assert result.adaptive.daily[:2] == result.baseline.daily[:2]
    for plan in [result.baseline, result.adaptive]:
        assert plan.consumption[6]["food"] == 0
        assert plan.inventories[6]["food"] == 0
        assert plan.metrics["total_waste_kg"] > 0
