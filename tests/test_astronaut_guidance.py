from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from astra_bio.astronaut_guidance import build_astronaut_guidance
from astra_bio.crew_samples import crew_sample
from astra_bio.model import default_config
from astra_bio.nutrition import CrewProfile, apply_profile_targets, apply_usda_composition, load_compositions
from astra_bio.planner import PlanResult


def fixture(reviewed=True):
    state = crew_sample()
    state["profiles"] = [{**profile, "targets_reviewed": reviewed} for profile in state["profiles"]]
    config = apply_usda_composition(replace(default_config(), planning_events=[]),
        {"oats": 1, "lentils": 2, "peanut_butter": 3})
    config = apply_profile_targets(config, [CrewProfile(**profile) for profile in state["profiles"]])
    return config, state


def member(report, index=0):
    return report["members"][index]


def nutrient(report, key="protein", index=0):
    return next(row for row in member(report, index)["nutrients"] if row["nutrient"] == key)


def test_complete_reviewed_log_uses_actual_usda_mass_and_target():
    config, state = fixture()
    state["entries"] = [{"profile_id": "crew-1", "day": 1, "food_key": "oats", "grams": 100}]
    report = build_astronaut_guidance(config, None, state)
    result = nutrient(report)
    assert result["intake"] == pytest.approx(16.89)
    assert result["target"] == 100
    assert result["gap"] == pytest.approx(83.11)
    assert result["coverage_pct"] == pytest.approx(16.89)
    assert result["status"] == "below_logged_target"
    assert member(report)["log_status"] == "complete"
    assert member(report)["target_source"] == "accepted_mission"
    assert member(report)["mission_membership"] == "active"
    assert report["scope"]["unmatched_mission_count"] == 0


def test_partial_log_records_intake_without_a_daily_shortage():
    config, state = fixture()
    state["entries"] = [{"profile_id": "crew-1", "day": 1, "food_key": "oats", "grams": 100}]
    state["complete_days"]["crew-1:1"] = False
    report = build_astronaut_guidance(config, None, state)
    result = nutrient(report)
    assert result["intake"] == pytest.approx(16.89)
    assert result["gap"] is None and result["coverage_pct"] is None
    assert result["status"] == "incomplete_log"
    assert member(report)["log_status"] == "partial"
    assert member(report)["focus_nutrient"] == "auto"
    assert not any(action["id"] == "recorded_gap" for action in member(report)["actions"])


def test_missing_log_is_unknown_but_explicit_complete_empty_log_is_zero():
    config, state = fixture()
    state["entries"] = []
    state["complete_days"] = {}
    report = build_astronaut_guidance(config, None, state)
    assert nutrient(report)["intake"] is None
    assert nutrient(report)["status"] == "unknown_intake"
    assert nutrient(report)["gap"] is None
    state["complete_days"]["crew-1:1"] = True
    report = build_astronaut_guidance(config, None, state)
    assert nutrient(report)["intake"] == 0
    assert nutrient(report)["gap"] == 100


def test_sample_targets_are_not_personal_requirements_and_blood_remains_fictional():
    config, state = fixture(reviewed=False)
    report = build_astronaut_guidance(config, None, state)
    assert report["sample_only"] is True
    assert all(row["gap"] is None for person in report["members"] for row in person["nutrients"])
    assert {alert["kind"] for alert in member(report, 3)["health_alerts"]} == {"low_hemoglobin", "low_ferritin"}
    assert all(alert["sample_only"] for alert in member(report, 3)["health_alerts"])
    assert not any(action["kind"] == "approved_supplement" for action in member(report, 3)["actions"])
    assert "iron" not in {row["nutrient"] for row in member(report, 3)["nutrients"]}


def test_named_personal_analysis_does_not_claim_an_unnamed_mission_roster():
    config, state = fixture()
    config = replace(config, crew=6, crew_profiles=[])
    report = build_astronaut_guidance(config, None, state)
    assert len(report["members"]) == 4
    assert all(person["target_source"] == "provided_profile" for person in report["members"])
    assert all(person["mission_membership"] == "not_matched" for person in report["members"])
    assert report["scope"]["mission_crew_count"] == 6
    assert report["scope"]["unmatched_mission_count"] == 6
    # A matching personal reading can still be reviewed independently of mission membership.
    assert member(report, 3)["health_alerts"]


def test_draft_target_is_explicit_and_never_overwrites_accepted_mission():
    config, state = fixture()
    state["profiles"][0]["targets"]["protein"] = 500
    report = build_astronaut_guidance(config, None, state)
    assert nutrient(report)["target"] == 500
    assert member(report)["target_source"] == "provided_profile"
    assert member(report)["pending_target_change"] is True
    assert config.crew_profiles[0]["targets"]["protein"] == 100
    assert any(action["id"] == "draft_profile" for action in member(report)["actions"])


def test_effective_mission_adjustment_uses_reviewed_base_to_detect_pending_edits():
    config, state = fixture()
    original_total = sum(profile["targets"]["protein"] for profile in state["profiles"])
    plan = PlanResult("test", "optimal", daily=[{"day": 1, "crew": 4, "protein_target": original_total * 2}])
    report = build_astronaut_guidance(config, plan, state)
    assert nutrient(report)["target"] == 200
    assert member(report)["target_source"] == "accepted_mission"
    assert member(report)["pending_target_change"] is False


def test_food_examples_have_source_form_reference_contribution_and_real_stock():
    config, state = fixture()
    report = build_astronaut_guidance(config, None, state, focus_nutrient="protein")
    option = next(food for food in member(report)["food_options"] if food["food_key"] == "lentils")
    assert option["reference_grams"] == 100
    assert option["nutrients"]["protein"] == pytest.approx(24.63)
    assert option["available_grams"] == 2000
    assert option["availability"] == "available"
    assert option["source_url"] == load_compositions()["lentils"].source_url
    assert "before cooking" in option["food_form"]
    assert option["status"] == "reference_example"


def test_future_inventory_never_falls_back_to_initial_and_expired_food_is_excluded():
    config, state = fixture()
    report = build_astronaut_guidance(config, None, state, day=2, focus_nutrient="energy")
    assert all(food["availability"] == "unknown_inventory" and food["available_grams"] is None
        for food in member(report)["food_options"] if food["food_key"] in {"oats", "lentils", "peanut_butter"})
    foods = [replace(food, shelf_life_days=1) if food.id == "oats" else food for food in config.foods]
    config = replace(config, foods=foods)
    plan = PlanResult("test", "optimal", inventories={1: {"oats": .5, "lentils": .2, "peanut_butter": .3}})
    report = build_astronaut_guidance(config, plan, state, day=2, focus_nutrient="energy")
    oat = next(food for food in member(report)["food_options"] if food["food_key"] == "oats")
    assert oat["availability"] == "expired" and oat["available_grams"] == 0
    lentil = next(food for food in member(report)["food_options"] if food["food_key"] == "lentils")
    assert lentil["available_grams"] == 200


def test_crop_reference_does_not_invent_current_edible_inventory():
    config, state = fixture()
    report = build_astronaut_guidance(config, None, state, focus_nutrient="vitamin_c")
    crop = next(food for food in member(report)["food_options"] if food["food_key"] not in {"oats", "lentils", "peanut_butter"})
    assert crop["availability"] == "not_in_saved_inventory"
    assert crop["available_grams"] is None


def test_retention_assumptions_are_not_misrepresented_as_reference_nutrients():
    config, state = fixture()
    foods = [replace(food, nutrient_half_life_days={"protein": 1}) if food.id == "lentils" else food
        for food in config.foods]
    config = replace(config, foods=foods)
    plan = PlanResult("test", "optimal", inventories={1: {"oats": .5, "lentils": .05, "peanut_butter": .3}})
    report = build_astronaut_guidance(config, plan, state, day=2, focus_nutrient="protein")
    lentil = next(food for food in member(report)["food_options"] if food["food_key"] == "lentils")
    assert lentil["availability"] == "insufficient"
    assert lentil["available_grams"] == 50
    assert lentil["nutrients"]["protein"] == pytest.approx(24.63)
    assert lentil["modeled_retention_applied"] is False
    assert lentil["reference_only_warning"]


def test_synthetic_configured_food_cannot_claim_a_real_usda_nutrient_amount():
    config, state = fixture()
    foods = [replace(food, nutrients_per_kg={"energy": 9999, "protein": 999, "vitamin_c": 999})
        if food.id == "lentils" else food for food in config.foods]
    config = replace(config, foods=foods)
    report = build_astronaut_guidance(config, None, state)
    assert "lentils" in report["scope"]["excluded_configured_food_ids"]
    assert not any(food["food_id"] == "lentils" for person in report["members"] for food in person["food_options"])


def test_current_urgent_real_symptoms_get_medical_response_not_nutrient_treatment():
    config, state = fixture()
    state["sample_only"] = False
    state["blood_samples"] = []
    state["health_observations"] = [{"profile_id": "crew-1", "day": 1,
        "heart_rate_bpm": 110, "symptoms": ["chest_pain", "breathlessness"]}]
    report = build_astronaut_guidance(config, None, state)
    person = member(report)
    assert person["health_alerts"][0]["severity"] == "urgent"
    assert any(action["kind"] == "crew_medical" for action in person["actions"])
    assert nutrient(report)["target"] == 100
    state["health_observations"][0]["day"] = 2
    assert not member(build_astronaut_guidance(config, None, state))["health_alerts"]


def test_supplement_requires_available_person_matched_approved_order():
    config, state = fixture()
    state["approved_supplements"] = [{"profile_id": "crew-4", "nutrient": "iron",
        "name": "Existing medical order", "clinician_approved": True, "available": True,
        "quantity_remaining": 2, "start_day": 1}]
    report = build_astronaut_guidance(config, None, state)
    assert any(action["kind"] == "approved_supplement" for action in member(report, 3)["actions"])
    assert not any(action["kind"] == "approved_supplement" for action in member(report)["actions"])
    state["approved_supplements"][0]["quantity_remaining"] = 0
    assert not any(action["kind"] == "approved_supplement"
        for action in member(build_astronaut_guidance(config, None, state), 3)["actions"])


def test_fact_ids_are_stable_unique_and_do_not_send_names_or_raw_blood_values():
    config, state = fixture()
    report = build_astronaut_guidance(config, None, state)
    facts = [fact for person in report["members"] for fact in person["facts"]]
    ids = [fact["id"] for fact in facts]
    assert len(ids) == len(set(ids))
    text = " ".join(fact["text"] for fact in facts)
    assert all(profile["name"] not in text for profile in state["profiles"])
    assert "hemoglobin" not in text.lower() and "ferritin" not in text.lower()
    assert [fact["id"] for person in build_astronaut_guidance(config, None, state)["members"]
        for fact in person["facts"]] == ids


@pytest.mark.parametrize("mutation", [
    lambda s: s["profiles"].append(deepcopy(s["profiles"][0])),
    lambda s: s["profiles"][0].update(targets={"iron": 100}),
    lambda s: s["complete_days"].update({"crew-1:1": "true"}),
    lambda s: s["entries"].append({"profile_id": "missing", "day": 1, "food_key": "oats", "grams": 10}),
    lambda s: s["entries"].append({"profile_id": "crew-1", "day": 1, "food_key": "unknown", "grams": 10}),
    lambda s: s["profiles"][0].update(targets_reviewed="true"),
])
def test_malformed_or_unsupported_input_is_rejected(mutation):
    config, state = fixture()
    mutation(state)
    with pytest.raises(ValueError):
        build_astronaut_guidance(config, None, state)


def test_read_only_analysis_preserves_inputs_and_rejects_unsupported_focus():
    config, state = fixture()
    plan = PlanResult("test", "optimal", inventories={1: {"oats": .5}})
    originals = asdict(config), deepcopy(state), plan.as_dict()
    build_astronaut_guidance(config, plan, state)
    assert (asdict(config), state, plan.as_dict()) == originals
    with pytest.raises(ValueError):
        build_astronaut_guidance(config, plan, state, focus_nutrient="iron")
