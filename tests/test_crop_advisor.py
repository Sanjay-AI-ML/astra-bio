from copy import deepcopy
from dataclasses import replace

import pytest

from astra_bio.crop_advisor import recommend_crops
from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, default_config
from astra_bio.nutrition import apply_usda_composition
from astra_bio.planner import PlanResult


def habitat(**changes):
    base = HabitatConfig(days=100, crew=1, area_m2=5, water_budget_l_per_day=15,
        power_budget_kwh_per_day=8, crew_water_l_per_day=3,
        targets_per_crew={"energy": 100, "protein": 10, "vitamin_c": 50},
        foods=[FoodSpec("stored", "Stored food", 10, {"energy": 100, "protein": 20, "vitamin_c": 0})],
        crops=[CropSpec("quick", "Quick protein crop", 10, 2, 1, .2,
            {"energy": 50, "protein": 20, "vitamin_c": 25}),
            CropSpec("dense", "Protein dense slow crop", 80, 2, 1, .2,
            {"energy": 100, "protein": 100, "vitamin_c": 50})])
    return replace(base, **changes)


def daily(day, *, protein_gap=0, energy_gap=0, **extra):
    return {"day": day, "crew": 1, "water_l": 3, "power_kwh": 0, "area_m2": 0,
        "water_available_l": 15, "power_available_kwh": 8,
        "protein_target": 10, "energy_target": 100, "vitamin_c_target": 50,
        "shortfall_units": {"protein": protein_gap, "energy": energy_gap, "vitamin_c": 0}, **extra}


def candidate(report, crop_id):
    return next(row for row in report["recommendations"] if row["crop_id"] == crop_id)


def test_protein_priority_uses_cycle_output_and_keeps_preharvest_gap_visible():
    config = habitat()
    plan = PlanResult("Saved plan", "simulated", daily=[daily(1, protein_gap=5), daily(2)])
    report = recommend_crops(config, plan, priority="protein")
    # A denser food is not automatically better: the fast crop supplies more
    # protein per area and growing day, and neither supplies food on day one.
    assert report["top_choice_crop_id"] == "quick"
    quick, dense = candidate(report, "quick"), candidate(report, "dense")
    assert dense["nutrients_per_100g"]["protein"] > quick["nutrients_per_100g"]["protein"]
    assert quick["harvest_day"] == 11
    assert quick["nutrients_at_harvest"]["protein"] == 40
    assert quick["gaps_before_harvest"]["protein"] == 5
    assert report["forecast"]["nutrients"][1]["earliest_gap_day"] == 1
    assert all("guaranteed" in row["warnings"][0] for row in report["recommendations"])


def test_explicit_priority_still_selects_protein_with_zero_forecast_gaps():
    report = recommend_crops(habitat(), PlanResult("No gaps", "optimal", daily=[daily(1)]), priority="protein")
    assert report["weights"] == {"energy": 0, "protein": 1, "vitamin_c": 0}
    assert report["top_choice_crop_id"] == "quick"
    assert report["forecast"]["nutrients"][1]["earliest_gap_day"] is None


def test_balanced_priorities_compare_normalized_gaps_with_different_units():
    report = recommend_crops(habitat(), PlanResult("Gaps", "simulated", daily=[daily(1, protein_gap=5, energy_gap=10)]))
    assert report["weights"]["protein"] == pytest.approx(5 / 6)
    assert report["weights"]["energy"] == pytest.approx(1 / 6)
    assert report["weights"]["vitamin_c"] == 0


def test_blocked_high_score_is_not_top_actionable_choice():
    config = habitat()
    config = replace(config, crops=[replace(config.crops[0], water_l_per_m2_day=20), config.crops[1]])
    report = recommend_crops(config, priority="protein")
    assert report["recommendations"][0]["crop_id"] == "quick"
    assert report["top_choice_crop_id"] == "dense"
    assert not candidate(report, "quick")["actionable"]
    assert any("water" in reason for reason in candidate(report, "quick")["blocked_reasons"])


def test_future_water_drop_blocks_crop_even_when_today_has_water():
    plan = PlanResult("Water event", "simulated", daily=[daily(1), daily(4, water_available_l=3.5)])
    report = recommend_crops(habitat(), plan, priority="protein")
    quick = candidate(report, "quick")
    assert quick["resources"]["available_daily_water_l"] == 12
    assert quick["resources"]["min_available_water_l_in_cycle"] == .5
    assert not quick["actionable"]
    assert report["top_choice_crop_id"] is None


def test_crew_and_active_crop_allocations_leave_only_remaining_capacity():
    plan = PlanResult("Occupied", "simulated", daily=[daily(3, crew=2, water_l=14,
        power_kwh=7.9, area_m2=4.5)], inventories={2: {"stored": 4}})
    report = recommend_crops(habitat(), plan, day=3)
    quick = candidate(report, "quick")
    assert quick["resources"]["available_daily_water_l"] == 1
    assert quick["resources"]["available_daily_power_kwh"] == pytest.approx(.1)
    assert quick["resources"]["available_area_m2"] == .5
    assert not quick["actionable"]
    assert any("area" in reason for reason in quick["blocked_reasons"])
    assert any("power" in reason for reason in quick["blocked_reasons"])


def test_horizon_and_tray_increment_exclude_unavailable_choices():
    report = recommend_crops(habitat(days=10, planting_increment_m2=.3), area_m2=1)
    assert report["top_choice_crop_id"] is None
    assert any("horizon" in reason for reason in candidate(report, "quick")["blocked_reasons"])
    assert any("tray" in reason for reason in candidate(report, "quick")["blocked_reasons"])


def test_large_harvest_is_potential_output_not_edible_promise():
    config = habitat(max_fresh_kg_per_crew_day=.25)
    report = recommend_crops(config, area_m2=2)
    quick = candidate(report, "quick")
    assert quick["estimated_harvest_kg"] == 4
    assert quick["harvest_day_fresh_limit_kg"] == .25
    assert any("discarded" in text for text in quick["warnings"])


def test_usda_provenance_requires_matching_submitted_composition():
    synthetic = recommend_crops(default_config())
    assert candidate(synthetic, "soy")["provenance"]["composition"]["status"] == "configured_assumption"
    assert candidate(synthetic, "lettuce")["provenance"]["composition"]["source_url"] is None
    research = recommend_crops(apply_usda_composition(default_config()))
    source = candidate(research, "lettuce")["provenance"]["composition"]
    assert source["status"] == "usda_reference_proxy"
    assert source["source_url"].startswith("https://fdc.nal.usda.gov/")


def test_bridge_uses_previous_inventory_retention_and_expiry():
    config = habitat(foods=[FoodSpec("stored", "Stored food", 10,
        {"energy": 100, "protein": 20, "vitamin_c": 0}, nutrient_half_life_days={"protein": 2}),
        FoodSpec("expired", "Expired food", 5, {"protein": 40}, shelf_life_days=2)])
    plan = PlanResult("Saved", "simulated", daily=[daily(3)], inventories={2: {"stored": 2, "expired": 3}})
    report = recommend_crops(config, plan, day=3)
    bridge = {row["food_id"]: row for row in report["bridge_foods"]}
    assert bridge["stored"]["stock_kg"] == 2
    assert bridge["stored"]["protein_in_stock_g"] == pytest.approx(20)
    assert bridge["stored"]["current_nutrients_per_100g"]["protein"] == 1
    assert bridge["expired"]["stock_kg"] == 3
    assert bridge["expired"]["expired"]
    assert not bridge["expired"]["available"]


def test_missing_saved_inventory_does_not_resurrect_initial_stock():
    report = recommend_crops(habitat(), PlanResult("Saved", "simulated", daily=[daily(3)]), day=3)
    assert report["bridge_foods"][0]["stock_kg"] is None
    assert not report["bridge_foods"][0]["available"]


def test_no_plan_future_day_does_not_claim_initial_stock_is_still_available():
    report = recommend_crops(habitat(), day=3)
    assert report["bridge_foods"][0]["stock_kg"] is None
    assert report["bridge_foods"][0]["available_nutrients_in_stock"]["protein"] is None
    assert not report["bridge_foods"][0]["available"]


def test_bridge_rank_responds_to_priority_and_current_stock():
    config = habitat(foods=[FoodSpec("protein_food", "Protein", 1, {"protein": 50, "energy": 20, "vitamin_c": 0}),
        FoodSpec("vitamin_food", "Vitamin C", 1, {"protein": 0, "energy": 20, "vitamin_c": 100})])
    assert recommend_crops(config, priority="protein")["bridge_foods"][0]["food_id"] == "protein_food"
    report = recommend_crops(config, priority="vitamin_c")
    assert report["bridge_foods"][0]["food_id"] == "vitamin_food"
    assert report["bridge_foods"][0]["available_nutrients_in_stock"]["vitamin_c"] == 100


def test_score_uses_harvest_day_crew_target_when_future_crew_changes():
    config = habitat()
    plan = PlanResult("Crew changes", "simulated", daily=[daily(1), daily(11, protein_target=20, crew=2)])
    normal = recommend_crops(config, priority="protein")
    changed = recommend_crops(config, plan, priority="protein")
    assert candidate(changed, "quick")["score"] == pytest.approx(candidate(normal, "quick")["score"] / 2)
    assert candidate(changed, "quick")["score_daily_targets"]["protein"] == 20


def test_forecast_infers_targets_from_row_crew_when_explicit_target_absent():
    row = daily(3, crew=2)
    del row["protein_target"]
    report = recommend_crops(habitat(), PlanResult("Crew", "simulated", daily=[row]), day=3)
    assert next(n for n in report["forecast"]["nutrients"] if n["nutrient"] == "protein")["current_target"] == 20


def test_missing_composition_remains_unknown_and_cannot_win_selected_priority():
    config = habitat()
    config = replace(config, crops=[replace(config.crops[0], nutrients_per_kg={"energy": 50}), config.crops[1]])
    report = recommend_crops(config, priority="protein")
    assert candidate(report, "quick")["nutrients_per_100g"]["protein"] is None
    assert report["top_choice_crop_id"] == "dense"


def test_advisor_is_deterministic_and_does_not_modify_saved_inputs():
    config = habitat()
    plan = PlanResult("Saved", "simulated", daily=[daily(1, protein_gap=5)], inventories={1: {"stored": 5}})
    before_config, before_plan = deepcopy(config), deepcopy(plan)
    first = recommend_crops(config, plan)
    assert first == recommend_crops(config, plan)
    assert config == before_config
    assert plan == before_plan


def test_zero_production_is_not_actionable_and_past_rows_are_not_a_future_forecast():
    config = habitat()
    config = replace(config, crops=[replace(crop, yield_kg_per_m2=0) for crop in config.crops])
    report = recommend_crops(config, PlanResult("Past", "simulated", daily=[daily(1)]), day=2)
    assert report["top_choice_crop_id"] is None
    assert not report["forecast"]["available"]


def test_unknown_stored_protein_content_is_not_replaced_by_zero():
    config = habitat(foods=[FoodSpec("unknown", "Unknown protein", 10, {"energy": 100})])
    report = recommend_crops(config)
    assert report["bridge_foods"][0]["available"]
    assert report["bridge_foods"][0]["protein_in_stock_g"] is None


def test_urgent_known_gap_ranks_actual_harvest_help_above_slow_dense_output():
    config = habitat(days=90, max_fresh_kg_per_crew_day=2)
    config = replace(config, crops=[config.crops[0], replace(config.crops[1],
        nutrients_per_kg={"energy": 100, "protein": 1000, "vitamin_c": 50})])
    plan = PlanResult("Complete forecast", "simulated", daily=[daily(d, protein_gap=10 if d == 11 else 0)
        for d in range(1, 91)])
    report = recommend_crops(config, plan, priority="protein")
    quick, dense = candidate(report, "quick"), candidate(report, "dense")
    assert dense["production_score"] > quick["production_score"]
    assert report["score_mode"] == "harvest_day_gap_help"
    assert report["top_choice_crop_id"] == "quick"
    assert quick["credited_nutrient_gap_reduction"]["protein"] == 10
    assert quick["score"] == 1
    assert dense["score"] == 0
    assert dense["missed_gap_days_before_harvest"]["protein"] == 1


def test_single_harvest_gets_no_credit_for_gaps_on_other_days():
    config = habitat(days=25)
    plan = PlanResult("Daily gaps", "simulated", daily=[daily(d, protein_gap=10)
        for d in range(1, 26)])
    report = recommend_crops(config, plan, priority="protein")
    quick = candidate(report, "quick")
    assert report["forecast"]["nutrients"][1]["cumulative_future_shortfall"] == 250
    assert quick["credited_nutrient_gap_reduction"]["protein"] == 10
    assert quick["weighted_gap_help_at_harvest"] == 1
    assert quick["gaps_before_harvest"]["protein"] == 100
    assert quick["missed_gap_days_before_harvest"]["protein"] == 10


def test_existing_harvest_meal_uses_fresh_limit_before_additional_batch():
    config = habitat(days=25, max_fresh_kg_per_crew_day=.25)
    plan = PlanResult("Existing crop", "simulated", daily=[daily(d, protein_gap=10 if d == 11 else 0)
        for d in range(1, 26)], consumption={11: {"quick": .2, "stored": .1}})
    report = recommend_crops(config, plan, priority="protein")
    quick = candidate(report, "quick")
    assert quick["harvest_day_fresh_remaining_kg"] == pytest.approx(.05)
    assert quick["consumable_harvest_kg"] == pytest.approx(.05)
    assert quick["credited_nutrient_gap_reduction"]["protein"] == pytest.approx(1)
    plan.consumption[11]["quick"] = .25
    exhausted = recommend_crops(config, plan, priority="protein")
    assert candidate(exhausted, "quick")["credited_nutrient_gap_reduction"]["protein"] == 0
    assert exhausted["top_choice_crop_id"] is None
    assert exhausted["selection_reason"]["type"] == "no_timely_gap_help"


def test_all_known_shortages_before_any_new_harvest_show_bridge_need():
    config = habitat(days=25)
    plan = PlanResult("Urgent shortage", "simulated", daily=[daily(d, protein_gap=10 if d <= 5 else 0)
        for d in range(1, 26)])
    report = recommend_crops(config, plan, priority="protein")
    assert report["top_choice_crop_id"] is None
    assert report["selection_reason"]["type"] == "no_timely_gap_help"
    assert candidate(report, "quick")["actionable"]
    assert candidate(report, "quick")["score"] == 0
    assert any("Earlier shortages" in warning for warning in candidate(report, "quick")["warnings"])
    assert report["bridge_foods"][0]["available"]


def test_additional_nutrient_credit_respects_total_meal_and_upper_limits():
    config = habitat(days=25, max_fresh_kg_per_crew_day=2,
        max_total_food_kg_per_crew_day=.5, nutrient_upper_per_crew={"energy": 100})
    plan = PlanResult("Meal bound", "simulated", daily=[daily(d, protein_gap=10 if d == 11 else 0,
        food_mass_kg=.4, energy_supply=99) for d in range(1, 26)])
    report = recommend_crops(config, plan, priority="protein")
    # Only 1 kcal of energy room remains, limiting this crop to .02 kg even
    # though protein is short and the fresh-food cap has ample room.
    assert candidate(report, "quick")["consumable_harvest_kg"] == pytest.approx(.02)
    assert candidate(report, "quick")["credited_nutrient_gap_reduction"]["protein"] == pytest.approx(.4)


def test_saved_solver_crop_actions_remain_visible_when_additive_area_is_full():
    config = habitat(days=25)
    plan = PlanResult("Full crop schedule", "optimal", daily=[daily(d, area_m2=5)
        for d in range(1, 26)], planting=[
            {"crop_id": "quick", "day": 3, "harvest_day": 13, "area_m2": 1, "predicted_harvest_kg": .75},
            {"crop_id": "quick", "day": 1, "harvest_day": 11, "area_m2": 4, "predicted_harvest_kg": 8},
        ], consumption={13: {"quick": .6}}, inventories={2: {"stored": 1}})
    report = recommend_crops(config, plan, day=3)
    assert report["top_choice_crop_id"] is None
    assert len(report["planned_crop_actions"]) == 1
    assert report["selection_reason"]["type"] == "no_growing_capacity"
    action = report["planned_crop_actions"][0]
    assert action["planting_day"] == 3
    assert action["harvest_day"] == 13
    assert action["estimated_harvest_kg"] == .75
    assert action["planned_crop_day_consumption_kg"] == .6
    assert "Already allocated" in action["scope"]


def test_future_reviewed_area_loss_restricts_additional_crop_batch():
    plan = PlanResult("Tray retired", "simulated", daily=[daily(1), daily(4, area_available_m2=.5)])
    report = recommend_crops(habitat(), plan)
    quick = candidate(report, "quick")
    assert not quick["actionable"]
    assert quick["resources"]["min_available_area_m2_in_cycle"] == .5


def test_extra_batch_cannot_spend_finite_stock_reserved_for_later_saved_days():
    config = habitat(days=25, initial_water_l=300, initial_energy_kwh=100)
    plan = PlanResult("Finite mission", "simulated", daily=[daily(d,
        water_remaining_l=300 - 10 * d, energy_remaining_kwh=100 - 3.9 * d)
        for d in range(1, 26)])
    report = recommend_crops(config, plan, area_m2=1)
    quick = candidate(report, "quick")
    assert quick["resources"]["remaining_unallocated_water_l"] == 50
    assert quick["resources"]["remaining_unallocated_energy_kwh"] == pytest.approx(2.5)
    assert quick["actionable"]
    plan.daily[-1]["water_remaining_l"] = 2
    plan.daily[-1]["energy_remaining_kwh"] = .1
    blocked = candidate(recommend_crops(config, plan), "quick")
    assert not blocked["actionable"]
    assert any("finite water" in text for text in blocked["blocked_reasons"])
    assert any("finite energy" in text for text in blocked["blocked_reasons"])


def test_finite_initial_stock_without_complete_remaining_forecast_is_unknown():
    report = recommend_crops(habitat(initial_water_l=1000), priority="protein")
    quick = candidate(report, "quick")
    assert quick["resources"]["finite_water_configured"]
    assert quick["resources"]["remaining_unallocated_water_l"] is None
    assert not quick["actionable"]
    assert any("unknown" in text for text in quick["blocked_reasons"])


def test_reviewed_events_apply_to_candidate_cycle_even_without_saved_daily_rows():
    config = habitat(planning_events=[{"day": 4, "crew": 2, "area_m2": .5,
        "water_budget_l_per_day": 6.5,
        "targets_per_crew": {"energy": 100, "protein": 30, "vitamin_c": 50}}])
    report = recommend_crops(config, priority="protein")
    quick = candidate(report, "quick")
    assert quick["score_daily_targets"]["protein"] == 60
    assert quick["resources"]["min_available_water_l_in_cycle"] == .5
    assert quick["resources"]["min_available_area_m2_in_cycle"] == .5
    assert not quick["actionable"]


def test_selected_deadline_includes_on_time_harvest_and_blocks_late_production():
    report = recommend_crops(habitat(), day=3, deadline_day=13, priority="protein")
    quick, dense = candidate(report, "quick"), candidate(report, "dense")
    assert report["deadline_day"] == 13
    assert report["remaining_days"] == 11
    assert quick["fits_deadline"] and quick["latest_planting_day"] == 3
    assert quick["actionable"]
    assert not dense["fits_deadline"] and not dense["actionable"]
    assert any("deadline" in reason for reason in dense["blocked_reasons"])
    assert report["top_choice_crop_id"] == "quick"


def test_deadline_excludes_later_gaps_and_credits_only_on_time_harvest():
    plan = PlanResult("Full mission forecast", "simulated", daily=[daily(d,
        protein_gap=10 if d == 11 else 0,
        shortfall_units={"protein": 10 if d == 11 else 0,
            "energy": 0, "vitamin_c": 50 if d == 81 else 0}) for d in range(1, 101)])
    report = recommend_crops(habitat(), plan, deadline_day=20)
    assert report["weights"] == {"energy": 0, "protein": 1, "vitamin_c": 0}
    assert report["forecast"]["through_day"] == 20
    assert report["forecast"]["nutrients"][2]["cumulative_future_shortfall"] == 0
    assert candidate(report, "dense")["consumable_harvest_kg"] == 0
    assert candidate(report, "dense")["weighted_gap_help_at_harvest"] == 0


def test_advice_uses_named_roster_today_and_reviewed_roster_at_harvest():
    from astra_bio.nutrition import CrewProfile, apply_profile_targets
    config = apply_profile_targets(habitat(), [CrewProfile("sanjay", "Sanjay",
        {"energy": 100, "protein": 10, "vitamin_c": 50}, targets_reviewed=True)])
    profiles = [{"profile_id": "sanjay", "name": "Sanjay", "targets_reviewed": True,
        "targets": {"energy": 100, "protein": 20, "vitamin_c": 50}},
        {"profile_id": "vamshika", "name": "Vamshika", "targets_reviewed": True,
        "targets": {"energy": 100, "protein": 30, "vitamin_c": 50}}]
    config = replace(config, planning_events=[{"day": 5, "crew": 2,
        "crew_profiles": profiles, "targets_per_crew": {"energy": 100, "protein": 25, "vitamin_c": 50}}])
    report = recommend_crops(config, deadline_day=20, priority="protein")
    assert [p["name"] for p in report["crew_context"]["members"]] == ["Sanjay"]
    quick = candidate(report, "quick")
    assert [p["name"] for p in quick["crew_context_at_harvest"]["members"]] == ["Sanjay", "Vamshika"]
    assert quick["score_daily_targets"]["protein"] == 50
    assert quick["crew_context_at_harvest"]["aggregate_daily_targets"]["protein"] == 50


def test_scenario_loss_targets_and_resources_apply_without_saved_daily_rows():
    from astra_bio.model import Scenario
    scenario = Scenario("loss", "Known crop and resource loss", event_day=4,
        extra_crew=2, target_factors={"protein": 2},
        crop_yield_factors={"quick": .5}, water_factor=.5)
    report = recommend_crops(habitat(), scenario=scenario, priority="protein")
    quick = candidate(report, "quick")
    assert quick["estimated_harvest_kg"] == 1
    assert quick["yield_factor"] == .5
    assert quick["nutrients_at_harvest"]["protein"] == 20
    assert quick["score_daily_targets"]["protein"] == 60
    assert quick["crew_context_at_harvest"]["unnamed_count"] == 3
    assert quick["resources"]["min_available_water_l_in_cycle"] == 0
    assert not quick["actionable"]


def test_saved_solver_actions_show_deadline_and_harvest_roster_without_deleting_schedule():
    plan = PlanResult("Saved crop schedule", "optimal", daily=[daily(d) for d in range(1, 101)],
        planting=[{"crop_id": "quick", "day": 1, "harvest_day": 11, "area_m2": 1},
            {"crop_id": "dense", "day": 1, "harvest_day": 81, "area_m2": 1}])
    report = recommend_crops(habitat(), plan, deadline_day=20)
    actions = {row["crop_id"]: row for row in report["planned_crop_actions"]}
    assert len(actions) == 2
    assert actions["quick"]["fits_deadline"]
    assert not actions["dense"]["fits_deadline"]
    assert actions["quick"]["crew_context_at_harvest"]["crew_count"] == 1


@pytest.mark.parametrize("deadline", [True, 0, 1, 101, 10.5, float("nan")])
def test_invalid_harvest_deadline_is_rejected(deadline):
    with pytest.raises(ValueError, match="Harvest deadline"):
        recommend_crops(habitat(), day=2, deadline_day=deadline)



@pytest.mark.parametrize("changes", [{"day": True}, {"day": 0}, {"day": 101}, {"day": 1.5},
    {"priority": "iron"}, {"area_m2": True}, {"area_m2": -1}, {"area_m2": 0},
    {"area_m2": float("nan")}, {"area_m2": float("inf")}])
def test_invalid_advisor_requests_are_rejected(changes):
    with pytest.raises(ValueError):
        recommend_crops(habitat(), **changes)
