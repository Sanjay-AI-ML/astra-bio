"""Conservation and evidence boundaries for additional production projections."""
from copy import deepcopy
from dataclasses import replace

import pytest

from astra_bio.bioproduction import bioproduction_catalog, simulate_bioproduction
from astra_bio.model import FoodSpec, HabitatConfig
from astra_bio.planner import PlanResult


def habitat(**changes):
    base = HabitatConfig(days=90, crew=1, area_m2=5,
        water_budget_l_per_day=100, power_budget_kwh_per_day=10,
        crew_water_l_per_day=3, targets_per_crew={"protein": 10},
        foods=[FoodSpec("stored", "Stored food", 100, {"protein": 20})])
    return replace(base, **changes)


def reactor(**changes):
    return {"id": "protein-reactor", "profile_id": "limnospira_pc8005",
        "size": 10, "size_unit": "L", "startup_days": 0,
        "water_l_per_unit_day": .6, "power_kwh_per_unit_day": .1,
        "commissioning_power_kwh": 0, **changes}


def aquatic(**changes):
    # All coefficients are explicit so this fixture does not transfer the
    # peak Wolffia reference to an unrelated fresh-to-dry fraction.
    return {"id": "aquatic-tray", "profile_id": "wolffia_globosa",
        "size": 2, "size_unit": "m2", "startup_days": 0,
        "biomass_g_per_unit_day": 40, "biomass_basis": "fresh",
        "dry_matter_fraction": .1, "protein_fraction": .4,
        "water_l_per_unit_day": .5, "power_kwh_per_unit_day": .2,
        "media_l_per_unit_day": .2, "commissioning_water_l": 0,
        "commissioning_power_kwh": 0, "commissioning_media_l": 0, **changes}


def wolffia_reference(**changes):
    # Biological coefficients remain the matched literature reference. The
    # operational/commissioning commitments are separately reviewed assumptions.
    return {"id": "wolffia-reference", "profile_id": "wolffia_globosa",
        "size": 2, "size_unit": "m2", "startup_days": 0,
        "water_l_per_unit_day": .5, "power_kwh_per_unit_day": .2,
        "media_l_per_unit_day": .2, "commissioning_water_l": 0,
        "commissioning_power_kwh": 0, "commissioning_media_l": 0, **changes}


def request(*modules, **changes):
    return {"start_day": 1, "horizon_days": 3, "focus_nutrient": "protein",
        "reviewed_inputs": True, "daily_media_budget_l": 100,
        "modules": list(modules or (reactor(),)), **changes}


def mission_row(day, **changes):
    return {"day": day, "crew": 1, "water_l": 3, "power_kwh": 0,
        "area_m2": 0, "water_available_l": 100,
        "power_available_kwh": 10, "protein_target": 10, **changes}


def test_limnospira_uses_matched_run_coefficients_and_charges_initial_fill_once():
    result = simulate_bioproduction(habitat(), None, request())
    module = result["modules"][0]
    assert module["coefficients"]["biomass_g_per_unit_day"] == .492
    assert module["coefficients"]["protein_fraction"] == .42
    assert module["provenance"]["biomass_g_per_unit_day"] == "literature_reference"
    assert result["daily"][0]["water_l"] == 16
    assert result["daily"][0]["media_l"] == 16
    assert result["daily"][1]["water_l"] == 6
    assert result["daily"][1]["modules"][0]["commissioning"]["water_l"] == 0
    assert result["totals"]["biomass_dry_g"] == pytest.approx(3 * 10 * .492)
    assert result["totals"]["protein_g"] == pytest.approx(3 * 10 * .492 * .42)
    assert result["totals"]["water_l"] == 28
    # Medium is a distinct supply commitment, already included in total water.
    assert result["totals"]["media_l"] == 28
    assert result["totals"]["protein_target_share"] == pytest.approx(6.1992 / 30)


def test_startup_requires_funded_operating_days_and_has_no_early_food_output():
    result = simulate_bioproduction(habitat(), None,
        request(reactor(startup_days=2), horizon_days=4))
    assert [r["modules"][0]["status"] for r in result["daily"]] == [
        "startup", "startup", "projected_production", "projected_production"]
    assert [r["protein_g"] for r in result["daily"]] == pytest.approx([0, 0, 2.0664, 2.0664])
    assert result["totals"]["water_l"] == 34
    assert result["totals"]["production_days"] == 2


def test_initial_fill_shortage_holds_everything_without_free_output_or_partial_draw():
    result = simulate_bioproduction(habitat(), None,
        request(daily_water_budget_l=15, daily_media_budget_l=15))
    assert all(r["modules"][0]["status"] == "resource_hold" for r in result["daily"])
    assert result["totals"]["water_l"] == 0
    assert result["totals"]["power_kwh"] == 0
    assert result["totals"]["media_l"] == 0
    assert result["totals"]["protein_g"] is None
    assert all(r["modules"][0]["funded_startup_days"] == 0 for r in result["daily"])


def test_resource_hold_does_not_advance_startup_or_erase_previous_funding():
    # Event factors deliberately cannot exceed one, so use a saved mission
    # row with an independently reviewed interruption and recovery instead.
    plan = PlanResult("Reviewed interruption", "simulated", daily=[
        mission_row(1), mission_row(2, water_available_l=3),
        mission_row(3), mission_row(4)])
    result = simulate_bioproduction(habitat(), plan,
        request(reactor(startup_days=2), horizon_days=4))
    assert [r["modules"][0]["status"] for r in result["daily"]] == [
        "startup", "resource_hold", "startup", "projected_production"]
    assert [r["modules"][0]["funded_startup_days"] for r in result["daily"]] == [1, 1, 2, 2]
    assert result["daily"][1]["water_l"] == 0
    assert result["daily"][3]["protein_g"] == pytest.approx(2.0664)


def test_production_loss_does_not_discount_resources_and_resource_events_persist():
    result = simulate_bioproduction(habitat(), None,
        request(events=[{"day": 2, "production_factor": .5},
                        {"day": 3, "production_factor": .5}]))
    assert [r["protein_g"] for r in result["daily"]] == pytest.approx([2.0664, 1.0332, .5166])
    assert [r["water_l"] for r in result["daily"]] == [16, 6, 6]
    held = simulate_bioproduction(habitat(), None,
        request(events=[{"day": 2, "water_factor": 0}]))
    assert [r["modules"][0]["status"] for r in held["daily"]] == [
        "projected_production", "resource_hold", "resource_hold"]


def test_explicit_fresh_and_dry_coefficients_keep_nutrient_units_distinct():
    # Iron focus lets the intentionally unknown protein concentration remain
    # unknown while an independently reviewed final mineral concentration runs.
    module = aquatic(protein_fraction=None, nutrients_mg_per_g_dry={"iron": 2})
    result = simulate_bioproduction(habitat(), None,
        request(module, focus_nutrient="iron", horizon_days=7))
    row = result["daily"][6]["modules"][0]
    assert all(r["focus_nutrient_output"] == 0 for r in result["daily"][:6])
    assert row["biomass_fresh_g"] == 560
    assert row["biomass_dry_g"] == 56
    assert row["protein_g"] is None
    assert row["nutrients"]["iron"] == 112  # mg, not g.
    assert row["nutrients"]["vitamin_c"] is None
    assert result["totals"]["protein_g"] is None
    assert result["totals"]["focus_nutrient_output"] == 112
    assert result["nutrient_units"]["iron"] == "mg"


def test_fresh_yield_without_dry_fraction_is_excluded_not_treated_as_dry_mass():
    result = simulate_bioproduction(habitat(), None,
        request(aquatic(dry_matter_fraction=None)))
    assert not result["modules"][0]["simulatable"]
    assert result["totals"]["protein_g"] is None
    assert any("dry_matter_fraction" in x for x in result["modules"][0]["exclusion_reasons"])


def test_unknown_target_nutrient_does_not_become_zero_or_relative_enrichment_credit():
    result = simulate_bioproduction(habitat(), None, request(focus_nutrient="iron"))
    assert result["totals"]["nutrients"]["iron"] is None
    assert result["totals"]["focus_nutrient_output"] is None
    assert result["totals"]["water_l"] == 0
    assert any("relative enrichment" in x for x in result["modules"][0]["exclusion_reasons"])


@pytest.mark.parametrize("profile_id", ["bionutrients_yeast", "electrocatalytic_acetate_microbes",
    "acetate_assisted_seedlings", "nanozyme_cucumber_research"])
def test_arbitrary_user_coefficients_cannot_qualify_research_only_profiles(profile_id):
    catalog = {p["id"]: p for p in bioproduction_catalog()["profiles"]}
    module = aquatic(profile_id=profile_id, size_unit=catalog[profile_id]["capacity_unit"])
    result = simulate_bioproduction(habitat(), None, request(module))
    assert not result["modules"][0]["simulatable"]
    assert "Research-only" in result["modules"][0]["exclusion_reasons"][0]
    assert result["totals"]["protein_g"] is None
    assert result["totals"]["water_l"] == 0


def test_changing_only_one_matched_literature_coefficient_excludes_cross_run_pair():
    result = simulate_bioproduction(habitat(), None,
        request(reactor(protein_fraction=.7)))
    assert not result["modules"][0]["simulatable"]
    assert result["totals"]["protein_g"] is None
    assert any("both coefficients" in x for x in result["modules"][0]["exclusion_reasons"])


def test_reviewing_both_changed_coefficients_drops_matched_literature_claim():
    result = simulate_bioproduction(habitat(), None,
        request(reactor(protein_fraction=.7, biomass_g_per_unit_day=.2)))
    assert result["totals"]["protein_g"] == pytest.approx(4.2)
    assert "no longer matched" in result["modules"][0]["provenance"]["protein_fraction"]


def test_saved_closing_stores_limit_additional_production_without_reusing_committed_water():
    config = habitat(initial_water_l=100, initial_energy_kwh=50)
    plan = PlanResult("Committed mission", "simulated", daily=[
        mission_row(1, water_remaining_l=97, energy_remaining_kwh=49),
        mission_row(90, water_remaining_l=20, energy_remaining_kwh=10)])
    original_config, original_plan = deepcopy(config), deepcopy(plan)
    result = simulate_bioproduction(config, plan, request())
    assert result["daily"][0]["finite_stores_remaining"]["water_l"] == 4
    assert result["daily"][1]["modules"][0]["status"] == "resource_hold"
    assert result["totals"]["water_l"] == 16
    assert result["totals"]["protein_g"] == pytest.approx(2.0664)
    assert config == original_config
    assert plan == original_plan
    with pytest.raises(ValueError, match="unallocated closing store"):
        simulate_bioproduction(config, plan, request(initial_water_l=21))


def test_missing_finite_store_forecast_cannot_resurrect_initial_supply():
    config = habitat(initial_water_l=100)
    with pytest.raises(ValueError, match="closing saved forecast"):
        simulate_bioproduction(config, PlanResult("Incomplete", "simulated"), request())


def test_prospective_boundary_and_mission_deadline_are_enforced():
    with pytest.raises(ValueError, match="Start day"):
        simulate_bioproduction(habitat(), None, request(start_day=17), earliest_start_day=18)
    with pytest.raises(ValueError, match="Horizon days"):
        simulate_bioproduction(habitat(), None, request(start_day=89, horizon_days=3))
    result = simulate_bioproduction(habitat(), None,
        request(start_day=18, horizon_days=2), earliest_start_day=18)
    assert [r["day"] for r in result["daily"]] == [18, 19]


def test_reviewed_crew_changes_are_reflected_in_prospective_nutrient_targets():
    config = habitat(planning_events=[{"day": 2, "crew": 3,
        "targets_per_crew": {"protein": 12}, "reason": "Reviewed crew arrival"}])
    result = simulate_bioproduction(config, None, request())
    assert [r["crew_protein_target_g"] for r in result["daily"]] == [10, 36, 36]
    assert result["totals"]["crew_protein_target_g"] == 82
    assert result["daily"][1]["protein_target_share"] == pytest.approx(2.0664 / 36)


def test_module_order_allocates_shared_budget_once_and_defers_second_commissioning():
    result = simulate_bioproduction(habitat(), None,
        request(reactor(id="first"), reactor(id="second"),
            daily_water_budget_l=25, daily_media_budget_l=25, horizon_days=2))
    assert [m["status"] for m in result["daily"][0]["modules"]] == [
        "projected_production", "resource_hold"]
    assert result["daily"][0]["water_l"] == 16
    assert [m["status"] for m in result["daily"][1]["modules"]] == [
        "projected_production", "projected_production"]
    assert result["daily"][1]["water_l"] == 22
    assert result["daily"][1]["modules"][1]["commissioning"]["water_l"] == 10


def test_shared_area_prevents_overlapping_additional_trays():
    result = simulate_bioproduction(habitat(), None,
        request(aquatic(id="first", size=3), aquatic(id="second", size=3),
            aquatic(id="third", size=2), horizon_days=1))
    assert [m["status"] for m in result["daily"][0]["modules"]] == [
        "growing_until_harvest", "resource_hold", "growing_until_harvest"]
    assert result["daily"][0]["area_remaining_m2"] == 0
    assert result["daily"][0]["water_l"] == 2.5


def test_existing_crop_area_and_resource_commitments_are_retained():
    plan = PlanResult("Occupied", "simulated", daily=[
        mission_row(1, area_m2=4, power_kwh=9.9, water_l=99)])
    result = simulate_bioproduction(habitat(), plan,
        request(aquatic(size=2), horizon_days=1))
    assert result["daily"][0]["modules"][0]["status"] == "resource_hold"
    assert any("area_m2" in x for x in result["resource_hold_reasons"])
    assert any("power_kwh" in x for x in result["resource_hold_reasons"])
    assert result["totals"]["water_l"] == 0


def test_catalog_returns_independent_copies():
    original = bioproduction_catalog()
    mutated = bioproduction_catalog()
    mutated["profiles"][0]["literature_defaults"]["protein_fraction"] = 1
    mutated["profiles"][0]["references"].clear()
    assert bioproduction_catalog() == original


def test_wolffia_reference_harvests_net_gain_weekly_and_excludes_retained_starter():
    result = simulate_bioproduction(habitat(), None,
        request(wolffia_reference(), horizon_days=14))
    module = result["modules"][0]
    assert module["coefficients"]["dry_matter_fraction"] == pytest.approx(4.83 / 42.14)
    assert module["coefficients"]["protein_fraction"] == .461
    assert module["weekly_net_fresh_g_per_m2_day"] == [
        42.14, 30.57, 34.16, 33.72, 40.58, 26.68, 23.90, 24.79]
    assert all(row["protein_g"] == 0 for row in result["daily"][:6])
    first = result["daily"][6]["modules"][0]
    # Each rate already subtracts the study's 40 g weekly starter. Counting
    # that starter again as an edible yield would create food from input stock.
    assert first["biomass_fresh_g"] == pytest.approx(2 * 42.14 * 7)
    assert first["biomass_dry_g"] == pytest.approx(2 * 4.83 * 7)
    assert first["protein_g"] == pytest.approx(2 * 4.83 * 7 * .461)
    assert first["unharvested_biomass_g"] == 0
    assert result["daily"][7]["modules"][0]["unharvested_biomass_g"] == pytest.approx(2 * 30.57)
    second = result["daily"][13]["modules"][0]
    assert second["biomass_fresh_g"] == pytest.approx(2 * 30.57 * 7)
    assert result["totals"]["protein_g"] == pytest.approx(
        2 * 7 * (42.14 + 30.57) * (4.83 / 42.14) * .461)
    assert result["totals"]["production_days"] == 2


def test_wolffia_deadline_does_not_turn_unharvested_growth_into_edible_output():
    result = simulate_bioproduction(habitat(), None,
        request(wolffia_reference(), horizon_days=6))
    assert result["totals"]["protein_g"] == 0
    assert result["totals"]["biomass_dry_g"] == 0
    assert result["totals"]["water_l"] == 6
    assert result["daily"][-1]["modules"][0]["unharvested_biomass_g"] == pytest.approx(2 * 42.14 * 6)
    assert result["daily"][-1]["modules"][0]["status"] == "growing_until_harvest"


def test_wolffia_harvest_timing_tracks_funded_growth_after_startup_and_interruptions():
    plan = PlanResult("Paused growing interval", "simulated", daily=[
        mission_row(day, water_available_l=3 if day == 23 else 100)
        for day in range(18, 29)])
    result = simulate_bioproduction(habitat(), plan,
        request(wolffia_reference(startup_days=2), start_day=18, horizon_days=11),
        earliest_start_day=18)
    daily = {row["day"]: row for row in result["daily"]}
    assert daily[18]["modules"][0]["status"] == "startup"
    assert daily[19]["modules"][0]["status"] == "startup"
    assert daily[23]["modules"][0]["status"] == "resource_hold"
    assert daily[23]["modules"][0]["production_age_days"] == 3
    assert daily[23]["water_l"] == 0
    assert daily[26]["protein_g"] == 0
    assert daily[27]["modules"][0]["status"] == "projected_production"
    assert daily[27]["protein_g"] == pytest.approx(2 * 4.83 * 7 * .461)
    assert daily[28]["protein_g"] == 0
    # A short interruption pauses the accounting clock; it does not mean a
    # biological trial has established survival or regrowth after interruption.
    assert result["totals"]["production_days"] == 1


def test_wolffia_reference_stops_at_observed_eight_week_boundary():
    result = simulate_bioproduction(habitat(), None,
        request(wolffia_reference(), horizon_days=63))
    assert result["daily"][55]["modules"][0]["status"] == "projected_production"
    assert all(row["modules"][0]["status"] == "resource_hold" for row in result["daily"][56:])
    assert all(row["water_l"] == 0 for row in result["daily"][56:])
    assert any("Eight-week reference exhausted" in reason for reason in result["resource_hold_reasons"])
    assert result["totals"]["water_l"] == 56
    assert result["totals"]["production_days"] == 8
    assert result["totals"]["protein_g"] == pytest.approx(
        2 * 7 * sum([42.14, 30.57, 34.16, 33.72, 40.58, 26.68, 23.90, 24.79])
        * (4.83 / 42.14) * .461)


def test_changed_dry_fraction_alone_does_not_enable_indefinite_peak_extrapolation():
    result = simulate_bioproduction(habitat(), None,
        request(wolffia_reference(dry_matter_fraction=.1), horizon_days=63))
    assert result["daily"][13]["modules"][0]["biomass_fresh_g"] == pytest.approx(2 * 30.57 * 7)
    assert result["daily"][56]["modules"][0]["status"] == "resource_hold"


def test_explicit_reviewed_wolffia_pair_is_a_separate_unvalidated_longer_duration_assumption():
    result = simulate_bioproduction(habitat(), None,
        request(aquatic(), horizon_days=63))
    assert result["modules"][0]["weekly_net_fresh_g_per_m2_day"] is None
    assert "no longer matched literature" in result["modules"][0]["provenance"]["protein_fraction"]
    assert result["daily"][62]["modules"][0]["status"] == "projected_production"
    assert result["totals"]["protein_g"] == pytest.approx(2 * 40 * .1 * .4 * 63)


def test_commissioned_tray_keeps_its_footprint_during_resource_hold():
    plan = PlanResult("One-day power interruption", "simulated", daily=[
        mission_row(1), mission_row(2, power_available_kwh=0)])
    result = simulate_bioproduction(habitat(), plan,
        request(aquatic(size=3), horizon_days=2))
    assert result["daily"][1]["modules"][0]["status"] == "resource_hold"
    assert result["daily"][1]["area_remaining_m2"] == 2
    assert result["daily"][1]["water_l"] == 0


@pytest.mark.parametrize("changes", [
    {"reviewed_inputs": False}, {"start_day": True}, {"horizon_days": 0},
    {"daily_media_budget_l": None}, {"daily_water_budget_l": float("nan")},
    {"initial_power_kwh": -1}, {"modules": []}, {"unknown": 1},
    {"focus_nutrient": "active_b12"},
    {"events": [{"day": 1, "production_factor": 2}]},
    {"events": [{"day": 1}, {"day": 1}]}, {"events": [{"day": 4}]},
])
def test_invalid_top_level_inputs_are_rejected(changes):
    with pytest.raises(ValueError):
        simulate_bioproduction(habitat(), None, request(**changes))


@pytest.mark.parametrize("changes", [
    {"size": True}, {"size": 0}, {"size": float("inf")}, {"startup_days": -1},
    {"size_unit": "m2"}, {"profile_id": "unknown"}, {"id": ""},
    {"protein_fraction": 1.1}, {"media_l_per_unit_day": .7},
    {"commissioning_water_l": 5}, {"biomass_basis": "wet"},
    {"nutrients_mg_per_g_dry": {"iron": -1}},
    {"nutrients_mg_per_g_dry": {"active_b12": 1}}, {"plant_photo": "anything"},
])
def test_invalid_module_inputs_are_rejected(changes):
    with pytest.raises(ValueError):
        simulate_bioproduction(habitat(), None, request(reactor(**changes)))


def test_duplicate_module_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        simulate_bioproduction(habitat(), None, request(reactor(), reactor()))


@pytest.mark.parametrize("field", ["protein_fraction", "biomass_g_per_unit_day"])
def test_explicit_null_literature_coefficient_is_unknown_instead_of_type_error(field):
    result = simulate_bioproduction(habitat(), None, request(reactor(**{field: None})))
    assert not result["modules"][0]["simulatable"]
    assert result["totals"]["protein_g"] is None


@pytest.mark.parametrize("value", [[], {}, None])
def test_non_string_nutrient_focus_is_rejected_as_invalid_input(value):
    with pytest.raises(ValueError):
        simulate_bioproduction(habitat(), None, request(focus_nutrient=value))
