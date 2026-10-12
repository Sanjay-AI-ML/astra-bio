from dataclasses import replace

import pytest

from astra_bio.model import default_config
from astra_bio.nutrition import (CrewProfile, FoodLogEntry, active_crew_context,
    apply_profile_targets, assess_intake, apply_usda_composition, default_profiles,
    load_compositions, restore_state, serialize_state, vitamin_c_reference)
from astra_bio.model import Scenario


def test_usda_composition_units_and_provenance_are_traceable():
    food = load_compositions()["oats"]
    assert food.fdc_id == 169705
    assert food.nutrients_per_kg["energy"] == 3890
    assert food.nutrients_per_kg["protein"] == pytest.approx(168.9)
    model = apply_usda_composition(default_config(), {"oats": 20, "lentils": 10, "peanut_butter": 5})
    assert model.foods[0].initial_kg == 20
    assert model.crops[1].grow_days == default_config().crops[1].grow_days
    assert model.input_provenance["food_composition"]["dataset"] == "USDA FoodData Central SR Legacy"


def test_incomplete_empty_log_and_missing_composition_remain_unknown():
    profile = CrewProfile("p", "Alias", {"energy": 2200, "protein": 90, "vitamin_c": 100})
    assert all(row["intake"] is None for row in assess_intake([profile], [], 1))
    assert all(row["intake"] == 0 for row in assess_intake([profile], [], 1, {"p": True}))
    foods = load_compositions()
    foods["oats"] = replace(foods["oats"], nutrients_per_kg={**foods["oats"].nutrients_per_kg, "vitamin_c": None})
    result = assess_intake([profile], [FoodLogEntry("p", 1, "oats", 100)], 1, compositions=foods)
    assert next(row for row in result if row["nutrient"] == "vitamin_c")["intake"] is None


def test_logged_food_form_mass_and_saved_state_roundtrip():
    profile = CrewProfile("p", "Alias", {"energy": 2200, "protein": 90, "vitamin_c": 100})
    entry = FoodLogEntry("p", 1, "oats", 100)
    rows = assess_intake([profile], [entry], 1)
    assert next(row for row in rows if row["nutrient"] == "energy")["intake"] == 389
    assert restore_state(serialize_state([profile], [entry], {"p:1": False})) == ([profile], [entry], {"p:1": False})
    assert vitamin_c_reference(20, "female")["rda_mg"] == 75
    assert vitamin_c_reference(None, "unspecified") is None


def named_profiles():
    return [CrewProfile("vishal", "Shree Ram Vishal", {"energy": 2400, "protein": 100, "vitamin_c": 100}, targets_reviewed=True),
        CrewProfile("shamyuktha", "Shamyuktha", {"energy": 2000, "protein": 75, "vitamin_c": 90}, targets_reviewed=True),
        CrewProfile("sanjay", "Sanjay", {"energy": 2300, "protein": 90, "vitamin_c": 100}, targets_reviewed=True),
        CrewProfile("vamshika", "Vamshika", {"energy": 2100, "protein": 85, "vitamin_c": 100}, targets_reviewed=True)]


def test_applying_nutrition_roster_preserves_names_and_individual_target_weights():
    config = apply_profile_targets(default_config(), named_profiles())
    assert default_profiles(config) == named_profiles()
    assert config.targets_per_crew == {"energy": 2200, "protein": 87.5, "vitamin_c": 97.5}
    current = active_crew_context(config, 17)
    assert [p["name"] for p in current["members"]] == [p.name for p in named_profiles()]
    assert current["aggregate_daily_targets"] == {"energy": 8800, "protein": 350, "vitamin_c": 390}
    assert current["unnamed_count"] == 0
    assert not current["targets_adjusted"]
    # The reviewed originals do not change when a future protein factor applies.
    changed = active_crew_context(config, 22, scenario=Scenario("protein", "Reviewed protein change",
        event_day=22, target_factors={"protein": 1.4}))
    assert changed["members"][0]["targets"]["protein"] == pytest.approx(140)
    assert changed["members"][0]["reviewed_targets"]["protein"] == 100
    assert changed["aggregate_daily_targets"]["protein"] == pytest.approx(490)
    assert changed["targets_adjusted"]


def test_dated_roster_changes_identity_only_at_reviewed_boundary():
    config = apply_profile_targets(default_config(), named_profiles())
    later = [{"profile_id": "new", "name": "Reviewed arrival", "targets": {"energy": 2500, "protein": 110, "vitamin_c": 120},
        "targets_reviewed": True}]
    config = replace(config, planning_events=[{"day": 18, "crew": 1,
        "crew_profiles": later, "targets_per_crew": later[0]["targets"]}])
    config.validate()
    assert active_crew_context(config, 17)["members"][0]["name"] == "Shree Ram Vishal"
    next_day = active_crew_context(config, 18)
    assert next_day["members"][0]["name"] == "Reviewed arrival"
    assert next_day["effective_from_day"] == 18
    assert next_day["aggregate_daily_targets"]["protein"] == 110
    assert len(config.crew_profiles) == 4


def test_count_only_and_relative_arrivals_leave_unestablished_identities_unnamed():
    config = apply_profile_targets(default_config(), named_profiles())
    relative = active_crew_context(config, 31, scenario=Scenario("arrivals", "Two arrivals", event_day=31, extra_crew=2))
    assert relative["named_count"] == 4
    assert relative["unnamed_count"] == 2
    assert relative["members"][0]["targets"]["protein"] == 100
    assert relative["effective_from_day"] == 31
    assert relative["unnamed_daily_targets"]["protein"] == 175
    count_only = active_crew_context(replace(config, planning_events=[{"day": 19, "crew": 3}]), 19)
    assert count_only["members"] == []
    assert count_only["unnamed_count"] == 3
    assert count_only["source"] == "crew_count_only"
    assert count_only["unnamed_daily_targets"] == count_only["aggregate_daily_targets"]


def test_saved_effective_row_targets_scale_proportionally_without_resetting_reviewed_profile():
    config = apply_profile_targets(default_config(), named_profiles())
    result = active_crew_context(config, 16, {"crew": 4, "protein_target": 420,
        "energy_target": 8800, "vitamin_c_target": 390})
    assert result["members"][0]["targets"]["protein"] == 120
    assert sum(p["targets"]["protein"] for p in result["members"]) == 420
    assert result["members"][1]["reviewed_targets"]["protein"] == 75


def test_cancelled_relative_arrival_retains_named_roster_and_other_scenario_targets():
    config = apply_profile_targets(default_config(), named_profiles())
    config = replace(config, planning_events=[{"day": 20, "cancel_scenario_crew": True}])
    scenario = Scenario("cancelled", "Arrival replaced", event_day=30, extra_crew=2,
        target_factors={"protein": 1.2}, water_factor=.5)
    context = active_crew_context(config, 30, scenario=scenario)
    assert context["crew_count"] == context["named_count"] == 4
    assert context["unnamed_count"] == 0
    assert context["members"][0]["targets"]["protein"] == 120
    assert context["aggregate_daily_targets"]["protein"] == 420


def test_independent_mean_target_update_scales_dated_roster_without_changing_identity():
    config = apply_profile_targets(default_config(), named_profiles())
    config = replace(config, planning_events=[{"day": 8, "targets_per_crew": {
        "energy": 2200, "protein": 105, "vitamin_c": 97.5}}])
    context = active_crew_context(config, 8)
    assert [p["name"] for p in context["members"]] == [p.name for p in named_profiles()]
    assert sum(p["targets"]["protein"] for p in context["members"]) == 420
    assert context["members"][0]["reviewed_targets"]["protein"] == 100
    assert context["targets_adjusted"]


def test_saved_count_mismatch_does_not_assign_wrong_named_people_or_change_inputs():
    config = apply_profile_targets(default_config(), named_profiles())
    previous = serialize_state(default_profiles(config), [], {})
    context = active_crew_context(config, 8, {"crew": 3, "protein_target": 300})
    assert context["members"] == []
    assert context["unnamed_count"] == 3
    assert context["source"] == "saved_count_without_matching_roster"
    assert context["aggregate_daily_targets"]["protein"] == 300
    assert serialize_state(default_profiles(config), [], {}) == previous


@pytest.mark.parametrize("day", [True, 0, -1, 1.5])
def test_crew_context_rejects_invalid_day(day):
    with pytest.raises(ValueError, match="positive integer"):
        active_crew_context(default_config(), day)
