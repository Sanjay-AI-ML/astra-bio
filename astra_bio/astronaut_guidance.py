"""Per-person recorded-intake guidance, with explicit reference and stock scope.

No nutrient target is inferred from a vital sign or laboratory result. Food
examples describe reference contributions, not a prescribed meal or a shared
inventory allocation. This function is read-only.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from math import isclose

from .crew_response import build_response_plan
from .nutrition import (
    CrewProfile, EXAMPLE_SERVINGS_G, FoodLogEntry, UNITS, active_crew_context,
    assess_intake, composition_for_species, load_compositions, validate_profiles,
)

LABELS = {"energy": "Energy", "protein": "Protein", "vitamin_c": "Vitamin C"}
FOCUS_CHOICES = ("auto", *UNITS)


def _rows(state, key):
    values = state.get(key, [])
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise ValueError(f"{key} must be a list of objects.")
    return values


def _state_profiles(state):
    try:
        profiles = [CrewProfile(**{key: row[key] for key in CrewProfile.__dataclass_fields__ if key in row})
            for row in _rows(state, "profiles")]
    except (TypeError, KeyError) as exc:
        raise ValueError("Crew profiles need stable IDs, names and manual nutrient targets.") from exc
    for profile in profiles:
        if not isinstance(profile.targets, dict) or not isinstance(profile.targets_reviewed, bool):
            raise ValueError("Profile targets must be an object and targets_reviewed must be a boolean.")
    return validate_profiles(profiles)


def _selected_profiles(config, plan, profiles, day, scenario):
    daily = next((row for row in plan.daily if row.get("day") == day), None) if plan else None
    context = active_crew_context(config, day, daily, scenario)
    accepted = {person["profile_id"]: person for person in context["members"]}
    selected, origins = [], {}
    for profile in profiles:
        previous = accepted.get(profile.profile_id)
        pending = bool(previous and profile.targets != previous.get("reviewed_targets", previous["targets"]))
        # The individual workspace can analyze explicitly edited draft targets;
        # it never applies those edits to the mission or changes accepted totals.
        chosen = asdict(profile)
        if previous is not None and not pending:
            chosen["targets"] = {n: value for n, value in previous["targets"].items() if n in UNITS}
            chosen["targets_reviewed"] = previous.get("targets_reviewed", False)
        selected.append(CrewProfile(**chosen))
        origins[profile.profile_id] = {
            "target_source": "accepted_mission" if previous is not None and not pending else "provided_profile",
            "pending_target_change": pending,
            "in_accepted_roster": previous is not None,
            "mission_membership": "active" if previous is not None else "not_matched",
        }
    return selected, origins, context


def _stock(config, plan, day):
    if day == 1:
        return {food.id: food.initial_kg for food in config.foods}, "Configured initial stock"
    if plan is None or day - 1 not in plan.inventories:
        return None, f"No saved closing inventory for day {day - 1}"
    return plan.inventories[day - 1], f"Saved plan closing inventory on day {day - 1}"


def _food_candidates(config, plan, day, catalog):
    stocks, stock_source = _stock(config, plan, day)
    result, excluded = [], []
    seen = set()
    for item, is_food in [(food, True) for food in config.foods] + [(crop, False) for crop in config.crops]:
        reference = composition_for_species(item.id, catalog)
        if reference is None:
            excluded.append(item.id)
            continue
        # A fictional configured nutrient mixture with a familiar food ID does
        # not become a USDA-backed stored food merely by sharing its name.
        matched = all(reference.nutrients_per_kg.get(n) is not None
            and n in item.nutrients_per_kg
            and isclose(item.nutrients_per_kg[n], reference.nutrients_per_kg[n], rel_tol=1e-9, abs_tol=1e-6)
            for n in UNITS)
        if is_food and not matched:
            excluded.append(item.id)
            continue
        if reference.key in seen:
            continue
        seen.add(reference.key)
        mass = EXAMPLE_SERVINGS_G.get(reference.key, 100.0)
        age = item.initial_age_days + day - 1 if is_food else None
        expired = bool(is_food and item.shelf_life_days is not None and age >= item.shelf_life_days)
        quantity = stocks.get(item.id, 0.0) * 1000 if is_food and stocks is not None else None
        availability = ("expired" if expired else "unknown_inventory" if is_food and stocks is None
            else "available" if is_food and quantity is not None and quantity >= mass
            else "insufficient" if is_food and quantity is not None and quantity > 0
            else "not_in_saved_inventory")
        result.append({"food_key": reference.key, "food_id": item.id, "name": reference.name,
            "food_form": reference.food_form, "reference_grams": mass,
            "nutrients": {n: reference.nutrients_per_kg[n] * mass / 1000
                if reference.nutrients_per_kg.get(n) is not None else None for n in UNITS},
            "available_grams": 0.0 if expired else quantity,
            "availability": availability, "status": "reference_example",
            "source_url": reference.source_url, "fdc_id": reference.fdc_id,
            "stock_source": stock_source if is_food else "Crop harvest is not saved edible stock",
            "is_reserve": item.is_reserve if is_food else False,
            "modeled_retention_applied": False,
            "reference_only_warning": "Saved stock has nutrient-retention assumptions; these example amounts use unaged USDA reference composition."
                if is_food and item.nutrient_half_life_days and age else None,
            "reason": "Single-food reference contribution; check its food form, preparation, allergies and shared inventory before use."})
    return result, excluded


def _fact(member_token, key, text):
    return {"id": f"astronaut-{member_token}-{key}", "text": text}


def build_astronaut_guidance(config, plan, crew_state, *, day=1, focus_nutrient="auto", scenario=None):
    """Analyze current workspace profiles without editing the saved mission.

    Missing/partial logs do not establish a daily shortage. ``focus_nutrient``
    is an educational food-comparison focus, never an inferred diagnosis.
    """
    config.validate()
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= config.days:
        raise ValueError("Analysis day must be an integer within the mission.")
    if focus_nutrient not in FOCUS_CHOICES:
        raise ValueError("Nutrient focus must be auto, energy, protein or vitamin_c.")
    if not isinstance(crew_state, dict):
        raise ValueError("Crew state must be an object.")
    if crew_state.get("sample_only") is not None and not isinstance(crew_state["sample_only"], bool):
        raise ValueError("Sample provenance must be a boolean.")
    state = deepcopy(crew_state)
    profiles = _state_profiles(state)
    if len(profiles) > 12 or any(len(p.profile_id) > 200 or len(p.name) > 120 for p in profiles):
        raise ValueError("Personal guidance supports up to 12 profiles with short IDs and names.")
    if len(_rows(state, "entries")) > 50000:
        raise ValueError("Personal guidance supports up to 50,000 food-log entries.")
    selected, origins, mission_context = _selected_profiles(config, plan, profiles, day, scenario)
    complete = state.get("complete_days", {})
    if not isinstance(complete, dict) or any(not isinstance(key, str) or not isinstance(value, bool)
            for key, value in complete.items()):
        raise ValueError("Daily completeness declarations must map profile/day keys to booleans.")
    try:
        entries = [FoodLogEntry(**{key: row[key] for key in FoodLogEntry.__dataclass_fields__ if key in row})
            for row in _rows(state, "entries")]
    except (TypeError, KeyError) as exc:
        raise ValueError("Food logs need a profile ID, mission day, food key and grams.") from exc
    catalog = load_compositions()
    assessments = assess_intake(selected, entries, day,
        {p.profile_id: complete.get(f"{p.profile_id}:{day}", False) for p in selected}, catalog)
    foods, excluded = _food_candidates(config, plan, day, catalog)
    sample_only = state.get("sample_only") is True
    members = []
    for profile in selected:
        nutrients, facts, actions = [], [], []
        token = sha256(profile.profile_id.encode("utf-8")).hexdigest()[:16]
        logged_today = any(entry.profile_id == profile.profile_id and entry.day == day for entry in entries)
        completed = complete.get(f"{profile.profile_id}:{day}", False)
        log_status = "complete" if completed else "partial" if logged_today else "missing"
        for assessment in [row for row in assessments if row["profile_id"] == profile.profile_id]:
            nutrient = assessment["nutrient"]
            usable = completed and assessment["intake"] is not None and profile.targets_reviewed
            status = assessment["status"]
            if assessment["intake"] is not None and not completed:
                status = "incomplete_log"
            elif assessment["intake"] is not None and assessment["target"] and not profile.targets_reviewed:
                status = "target_not_reviewed"
            row = {key: assessment[key] for key in (
                "nutrient", "unit", "target", "intake", "status", "log_complete")}
            row.update(label=LABELS[nutrient], status=status,
                gap=assessment["gap"] if usable else None,
                coverage_pct=assessment["coverage_pct"] if usable else None,
                usable_for_guidance=usable,
                above_adult_vitamin_c_ul=assessment["above_adult_vitamin_c_ul"])
            nutrients.append(row)
            target = "unset" if row["target"] is None else f"{row['target']:g} {row['unit']}"
            intake = "unknown" if row["intake"] is None else f"{row['intake']:g} {row['unit']}"
            facts.append(_fact(token, nutrient,
                f"{row['label']}: recorded intake {intake}; manual target {target}; "
                f"log status {log_status}; target reviewed {profile.targets_reviewed}. "
                + (f"Logged target gap {row['gap']:g} {row['unit']}." if row["gap"] is not None
                   else "A daily shortage has not been established.")))
        gap_rows = [row for row in nutrients if row["gap"] is not None and row["gap"] > 1e-9
            and row["target"] and row["target"] > 0]
        chosen_focus = focus_nutrient if focus_nutrient != "auto" else (
            max(gap_rows, key=lambda row: row["gap"] / row["target"])["nutrient"] if gap_rows else "auto")
        options = deepcopy(foods)
        if chosen_focus != "auto":
            options.sort(key=lambda food: (food["availability"] not in {"available", "insufficient"},
                -(food["nutrients"].get(chosen_focus) or 0), food["food_key"]))
            for food in options:
                food["reason"] = f"Reference contribution to {LABELS[chosen_focus].lower()}; one example food, not a complete meal prescription."
        else:
            options.sort(key=lambda food: (food["availability"] not in {"available", "insufficient"}, food["food_key"]))
        options = options[:4]
        for food in options:
            contribution = "; ".join(f"{LABELS[n]} {amount:g} {UNITS[n]}"
                for n, amount in food["nutrients"].items() if amount is not None)
            facts.append(_fact(token, f"food-{food['food_key']}",
                f"USDA reference food {food['food_key']}, form {food['food_form']}: "
                f"{food['reference_grams']:g} g gives {contribution}. Saved inventory status: {food['availability']}. "
                "This is a single-food comparison, not a prescribed meal or guaranteed dietary intake."))
        if log_status != "complete":
            actions.append({"id": "complete_log", "kind": "data_review", "title": "Complete today's food log",
                "message": "Record all consumed food and confirm the day is complete before interpreting a daily intake gap."})
        if not profile.targets_reviewed:
            actions.append({"id": "review_targets", "kind": "target_review", "title": "Review individual targets",
                "message": "These manually provided planning targets have not been reviewed. No personal nutrient requirement is inferred."})
        if origins[profile.profile_id]["pending_target_change"] or not origins[profile.profile_id]["in_accepted_roster"]:
            actions.append({"id": "draft_profile", "kind": "mission_review", "title": "Profile differs from the saved mission",
                "message": "This personal analysis uses the current profile. Apply reviewed crew changes separately to update mission resource planning."})
        if gap_rows:
            focus = next(row for row in gap_rows if row["nutrient"] == chosen_focus) if any(
                row["nutrient"] == chosen_focus for row in gap_rows) else max(gap_rows, key=lambda row: row["gap"] / row["target"])
            actions.append({"id": "recorded_gap", "kind": "intake_review", "title": f"Review the logged {focus['label'].lower()} gap",
                "message": f"The complete log is {focus['gap']:g} {focus['unit']} below the reviewed planning target. "
                "Compare available food and the existing meal plan; this does not diagnose a deficiency."})
        elif completed and profile.targets_reviewed and all(row["gap"] == 0 for row in nutrients):
            actions.append({"id": "tracked_targets_met", "kind": "intake_review", "title": "Tracked intake targets met",
                "message": "The complete log meets these three planning targets. Other nutrients and clinical status are not assessed."})
        for row in nutrients:
            if row["above_adult_vitamin_c_ul"]:
                actions.append({"id": "vitamin_c_reference_review", "kind": "medical_review", "title": "Review vitamin C intake",
                    "message": "The recorded amount exceeds the limited NIH healthy-adult reference used by this app. Request review before adding supplements."})
        report = {"day": day, "crew_context": {"members": [asdict(profile)]},
            "forecast": {"nutrients": [{"nutrient": row["nutrient"], "current_shortfall": row["gap"]}
                for row in nutrients if row["gap"] is not None]}, "bridge_foods": []}
        response = build_response_plan(config, plan, report, state, None, scenario)
        alerts = response["health_alerts"]
        for index, support in enumerate(response["immediate_support"]):
            actions.append({"id": f"health_support_{index}", "kind": support["kind"],
                "title": support["title"], "message": support["message"]})
        if not alerts:
            facts.append(_fact(token, "health_scope", "No alert was generated from available observations; missing or historical data does not establish current health."))
        else:
            facts.append(_fact(token, "health_scope", "A recorded observation needs crew medical review. No nutrient cause, diagnosis or supplement dose is inferred."))
        facts.append(_fact(token, "food_scope", "Food examples use USDA reference edible forms and do not prescribe a meal, reserve stock or allocate shared inventory."))
        members.append({"profile_id": profile.profile_id, "name": profile.name, **origins[profile.profile_id],
            "targets_reviewed": profile.targets_reviewed, "log_status": log_status,
            "nutrients": nutrients, "focus_nutrient": chosen_focus, "food_options": options,
            "actions": actions, "health_alerts": alerts, "facts": facts,
            "missing_metrics": response["scope"]["missing_metrics"],
            "measurement_context_missing": response["scope"]["reference_context_missing"]})
    return {"schema_version": 1, "day": day, "focus_nutrient": focus_nutrient,
        "sample_only": sample_only, "members": members,
        "scope": {"method": "Deterministic per-person USDA food-log comparison with manually entered targets.",
            "analyzed_profile_count": len(members), "mission_crew_count": mission_context["crew_count"],
            "matched_active_profile_count": sum(member["mission_membership"] == "active" for member in members),
            "unmatched_mission_count": max(0, mission_context["crew_count"] - sum(
                member["mission_membership"] == "active" for member in members)),
            "roster_basis": "Current provided personal profiles; unmatched profiles do not establish membership in the accepted mission.",
            "tracked_nutrients": list(UNITS), "food_dataset": "USDA FoodData Central SR Legacy, 2018-04",
            "excluded_configured_food_ids": excluded,
            "limitations": ["Only energy, protein and vitamin C intake are calculated; iron and complete dietary adequacy are not modeled.",
                "Missing or incomplete logs do not establish a daily nutrient shortage.",
                "Heart rate, blood pressure, hemoglobin and ferritin do not automatically set nutrient targets or treatment.",
                "Reference food examples are not complete meals. Dry ingredients require appropriate preparation; cooking and absorption are not modeled.",
                "Current stock is shared, simulated and unallocated here. Reference nutrient amounts do not establish aged or prepared-food composition.",
                "Sample profiles and measurements remain fictional. No clinical recovery, mission change, inventory consumption or hardware command is generated."]},
        "ai": {"available": False, "status": "not_configured", "basis": "Verified calculations remain available without external AI."}}
