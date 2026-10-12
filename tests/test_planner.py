"""Behavioral tests of conservation, chronology, reserves and disruption handling."""

from dataclasses import replace

import pytest

from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, Scenario, default_config, scenario_presets
from astra_bio.planner import run_comparison


def small_config(**overrides):
    config = HabitatConfig(
        days=8, crew=1, area_m2=1.0, water_budget_l_per_day=5.0,
        power_budget_kwh_per_day=2.0, crew_water_l_per_day=0,
        reserve_days=0, max_fresh_kg_per_crew_day=2,
        foods=[FoodSpec("ration", "Demo ration", 0, {"n": 1})],
        crops=[CropSpec("crop", "Demo crop", 2, 1.0, 1.0, 0.5, {"n": 1})],
        targets_per_crew={"n": 1.0}, nutrient_units={"n": "demo units"},
    )
    return replace(config, **overrides)


def require_solver(result):
    assert result.adaptive.status not in {"solver_unavailable", "solver_error"}, result.adaptive.warnings
    assert result.baseline.daily


def test_harvest_delay_and_inventory_conservation():
    result = run_comparison(small_config(), Scenario("none", "No event", event_day=99))
    require_solver(result)
    rows = result.adaptive.daily
    assert rows[0]["harvest_kg"] == 0
    assert rows[1]["harvest_kg"] == 0
    assert rows[0]["n_supply"] == 0
    assert rows[1]["n_supply"] == 0
    assert any(row["harvest_kg"] > 0 for row in rows[2:])
    for stocks in result.adaptive.inventories.values():
        assert all(amount >= -1e-6 for amount in stocks.values())
    total_eaten = sum(eats["crop"] for eats in result.adaptive.consumption.values())
    total_harvest = sum(row["harvest_kg"] for row in rows)
    assert total_eaten <= total_harvest + 1e-6
    assert total_harvest == pytest.approx(total_eaten + result.adaptive.metrics["total_waste_kg"])


def test_crew_event_replans_future_without_changing_past():
    config = small_config(foods=[FoodSpec("ration", "Demo ration", 30, {"n": 1})], crops=[])
    event = Scenario("crew", "Extra crew", event_day=4, extra_crew=1)
    result = run_comparison(config, event)
    require_solver(result)
    assert result.baseline.daily[:3] == result.adaptive.daily[:3]
    assert result.baseline.metrics["shortfall_days"] == 5
    assert result.adaptive.metrics["shortfall_days"] == 0
    assert result.adaptive.food_totals_kg["ration"] == pytest.approx(13)
    assert all(row["crew"] == 2 for row in result.adaptive.daily[3:])


def test_no_water_yields_explicit_capacity_and_nutrition_gaps():
    config = small_config(crew_water_l_per_day=1.0)
    result = run_comparison(config, Scenario("dry", "No water", event_day=1, water_factor=0))
    require_solver(result)
    assert result.adaptive.metrics["total_harvest_kg"] == 0
    assert result.adaptive.metrics["shortfall_days"] == config.days
    assert result.adaptive.metrics["capacity_gap_days"] == config.days
    assert all(row["water_l"] == 0 and row["water_gap_l"] >= 1 for row in result.adaptive.daily)
    assert result.adaptive.status == "feasible_with_shortfalls"


def test_active_crop_batch_loses_half_yield_not_future_batches():
    config = small_config(crops=[CropSpec("crop", "Demo crop", 3, 1, 1, 0.5, {"n": 1})])
    nominal = run_comparison(config, Scenario("none", "None", event_day=99))
    event_day = min(batch["day"] for batch in nominal.baseline.planting) + 1
    affected = run_comparison(config, Scenario("loss", "Half batch", event_day=event_day,
                                             crop_yield_factors={"crop": 0.5}))
    require_solver(nominal)
    require_solver(affected)
    first_harvest_day = min(batch["harvest_day"] for batch in nominal.baseline.planting)
    normal_harvest = nominal.baseline.daily[first_harvest_day - 1]["harvest_kg"]
    reduced_harvest = affected.baseline.daily[first_harvest_day - 1]["harvest_kg"]
    assert normal_harvest > 0
    assert reduced_harvest == pytest.approx(normal_harvest * 0.5)
    for batch in affected.adaptive.planting:
        if batch["day"] >= event_day:
            assert batch["predicted_harvest_kg"] == pytest.approx(batch["area_m2"])


def test_reserves_are_kept_when_possible_and_gaps_reported_when_not():
    rich = small_config(days=5, reserve_days=2, crops=[],
                        foods=[FoodSpec("ration", "Demo ration", 10, {"n": 1})])
    result = run_comparison(rich, Scenario("none", "None", event_day=99))
    require_solver(result)
    assert result.adaptive.metrics["shortfall_days"] == 0
    assert result.adaptive.metrics["min_reserve_days"] >= 2 - 1e-6
    poor = replace(rich, foods=[FoodSpec("ration", "Demo ration", 3, {"n": 1})])
    scarce = run_comparison(poor, Scenario("none", "None", event_day=99))
    require_solver(scarce)
    assert scarce.adaptive.metrics["shortfall_days"] > 0
    assert scarce.adaptive.metrics["reserve_gap_days"] > 0
    assert scarce.adaptive.metrics["final_reserve_kg"] >= 0


def test_changed_targets_and_units_are_preserved():
    config = small_config(foods=[FoodSpec("ration", "Demo ration", 30, {"n": 1})], crops=[])
    result = run_comparison(config, Scenario("targets", "Target change", event_day=3,
                                             target_factors={"n": 1.5}))
    require_solver(result)
    assert result.adaptive.daily[1]["n_target"] == 1
    assert result.adaptive.daily[2]["n_target"] == 1.5
    assert result.baseline.metrics["shortfall_days"] == 6
    assert result.adaptive.metrics["shortfall_days"] == 0
    assert isinstance(result.adaptive.daily[2]["shortfall_units"], dict)


def test_nonreserve_stored_food_persists_without_reserve_credit():
    config = small_config(
        days=4, reserve_days=2, crops=[],
        foods=[FoodSpec("ration", "Stored food excluded from buffer", 10, {"n": 1}, is_reserve=False)],
    )
    result = run_comparison(config, Scenario("crew", "Extra crew", event_day=3, extra_crew=1))
    require_solver(result)
    assert result.baseline.inventories[2]["ration"] == pytest.approx(8)
    assert result.adaptive.inventories[4]["ration"] == pytest.approx(4)
    assert result.adaptive.food_totals_kg["ration"] == pytest.approx(6)
    assert result.adaptive.metrics["shortfall_days"] == 0
    assert result.adaptive.metrics["total_waste_kg"] == 0
    assert result.baseline.metrics["total_waste_kg"] == 0
    assert result.adaptive.metrics["min_reserve_days"] == 0
    assert result.adaptive.metrics["final_reserve_kg"] == 0
    assert result.adaptive.metrics["reserve_gap_days"] == 4


def test_default_ninety_day_demo_has_bounded_resources():
    config = default_config()
    result = run_comparison(config, scenario_presets()["water"])
    require_solver(result)
    assert len(result.adaptive.daily) == 90
    for row in result.adaptive.daily:
        assert row["water_l"] <= row["water_available_l"] + 1e-5
        assert row["power_kwh"] <= row["power_available_kwh"] + 1e-5
        assert row["area_m2"] <= config.area_m2 + 1e-5
    assert result.baseline.daily[:29] == result.adaptive.daily[:29]


def test_invalid_negative_inputs_are_rejected():
    with pytest.raises(ValueError, match="Water factor"):
        run_comparison(small_config(), Scenario("bad", "Invalid", water_factor=-1))
    with pytest.raises(ValueError, match="unique"):
        run_comparison(small_config(foods=[FoodSpec("crop", "Duplicate", 1, {"n": 1})]),
                       Scenario("none", "None"))
