"""Manual dietary intake assessment backed by a reproducible USDA food subset.

Target gaps describe recorded intake, never nutritional status or deficiency.
No sensor, physiological prediction, diagnosis or automatic medical target is
required. Growth coefficients and pantry quantities remain separate inputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import copy
import json
from math import isfinite
from pathlib import Path
from typing import Iterable, Mapping

from astra_bio.model import FoodSpec, HabitatConfig

DATA_PATH = Path(__file__).resolve().parents[1] / "data/research/nutrition/compositions.json"
UNITS = {"energy": "kcal", "protein": "g", "vitamin_c": "mg"}
NIH_URL = "https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/"
PANTRY_KEYS = ("oats", "lentils", "peanut_butter")
# Explicit example edible masses, not clinical serving prescriptions or USDA
# portion definitions. Users can replace these portions in the intake workspace.
EXAMPLE_SERVINGS_G = {"lettuce": 75.0, "radish": 75.0, "kale": 75.0,
    "tomato": 120.0, "arugula": 25.0, "kohlrabi": 100.0}


def nonnegative(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative number.")
    return float(value)


@dataclass(frozen=True)
class FoodComposition:
    key: str
    fdc_id: int
    ndb_number: str
    name: str
    food_form: str
    nutrients_per_kg: dict[str, float | None]
    source_url: str
    publication_date: str


def load_compositions(path: Path = DATA_PATH) -> dict[str, FoodComposition]:
    source = json.loads(path.read_text(encoding="utf-8"))
    if source.get("schema_version") != 1:
        raise ValueError("Unsupported food-composition data format.")
    result = {}
    for key, item in source["foods"].items():
        profile = {nutrient: None if amount is None else nonnegative(amount, f"{key}: {nutrient}")
            for nutrient, amount in item["nutrients_per_kg"].items()}
        result[key] = FoodComposition(key, int(item["fdc_id"]), str(item["ndb_number"]),
            item["description"], item["food_form"], profile, item["source_url"], item["publication_date"])
    return result


def composition_for_species(species: str, compositions: Mapping[str, FoodComposition] | None = None) -> FoodComposition | None:
    catalog = compositions if compositions is not None else load_compositions()
    key = species.lower().strip()
    if key in catalog:
        return catalog[key]
    for canonical in EXAMPLE_SERVINGS_G:
        if key.startswith(canonical + "_"):
            return catalog.get(canonical)
    return None


def real_food_specs(initial_kg: Mapping[str, float] | None = None) -> list[FoodSpec]:
    """USDA composition, user-specified inventory; default inventory is zero."""
    catalog = load_compositions()
    quantities = dict(initial_kg or {})
    if set(quantities) - set(PANTRY_KEYS):
        raise ValueError("USDA pantry inventory supports oats, lentils and peanut_butter.")
    result = []
    for key in PANTRY_KEYS:
        food = catalog[key]
        if any(food.nutrients_per_kg.get(nutrient) is None for nutrient in UNITS):
            raise ValueError(f"{food.name} has a missing tracked nutrient; do not replace it with zero.")
        result.append(FoodSpec(key, food.name, nonnegative(quantities.get(key, 0), f"Stock {key}"),
            {nutrient: float(food.nutrients_per_kg[nutrient]) for nutrient in UNITS}, True))
    return result


def apply_usda_composition(config: HabitatConfig, initial_kg: Mapping[str, float] | None = None) -> HabitatConfig:
    """Explicit preset change; preserve crop operations and manual crew targets."""
    catalog = load_compositions()
    if initial_kg is None:
        initial_kg = {item.id: item.initial_kg for item in config.foods if item.id in PANTRY_KEYS}
    foods = real_food_specs(initial_kg)
    crops, mapped, unmatched = [], {}, []
    for crop in config.crops:
        reference = composition_for_species(crop.id, catalog)
        if reference is None or any(reference.nutrients_per_kg.get(nutrient) is None for nutrient in UNITS):
            crops.append(crop)
            unmatched.append(crop.id)
        else:
            crops.append(replace(crop, nutrients_per_kg={nutrient: float(reference.nutrients_per_kg[nutrient]) for nutrient in UNITS}))
            mapped[crop.id] = {"fdc_id": reference.fdc_id, "proxy_food": reference.name}
    provenance = copy.deepcopy(getattr(config, "input_provenance", {}))
    source = json.loads(DATA_PATH.read_text(encoding="utf-8"))["dataset"]
    provenance["food_composition"] = {"dataset": source["name"], "release": source["release"],
        "download_url": source["download_url"], "archive_sha256": source["download_sha256"],
        "pantry_fdc_ids": {food.id: catalog[food.id].fdc_id for food in foods},
        "crop_species_proxies": mapped, "unmatched_crop_ids_retaining_previous_composition": unmatched,
        "limitations": "Reference food-form composition; not a measured habitat harvest or aged/cooked meal."}
    provenance["food_inventory"] = {"status": "User-entered planning assumption, not USDA data",
        "initial_kg": {food.id: food.initial_kg for food in foods}}
    updated = replace(config, foods=foods, crops=crops, nutrient_units=UNITS.copy(), input_provenance=provenance)
    updated.validate()
    return updated


def apply_crop_composition(config: HabitatConfig) -> tuple[HabitatConfig, list[str], list[str]]:
    """Apply known edible-species proxies without replacing stocks or growth data."""
    config.validate()
    catalog = load_compositions()
    provenance = copy.deepcopy(config.input_provenance)
    crops, matched, unmatched = [], [], []
    for crop in config.crops:
        reference = composition_for_species(crop.id, catalog)
        if reference is None or any(reference.nutrients_per_kg.get(n) is None for n in UNITS):
            crops.append(crop)
            unmatched.append(crop.id)
            continue
        # Preserve any additional configured nutrients; USDA only supplies the
        # three explicitly extracted nutrients, not a complete composition.
        composition = {**crop.nutrients_per_kg, **{n: float(reference.nutrients_per_kg[n]) for n in UNITS}}
        crops.append(replace(crop, nutrients_per_kg=composition))
        matched.append(crop.id)
        provenance[f"crop:{crop.id}:composition"] = (
            f"{reference.source_url}; {reference.food_form}; USDA edible-species proxy, not a measured tray harvest."
        )
    provenance["crop_nutrition_update"] = {"matched_crop_ids": matched, "unmatched_crop_ids": unmatched,
        "scope": "Only matched energy/protein/vitamin C crop coefficients updated; unmatched crops retain configured values. Stored-food amounts/composition and crop growth/resources unchanged."}
    updated = replace(config, crops=crops, input_provenance=provenance)
    updated.validate()
    return updated, matched, unmatched


@dataclass(frozen=True)
class CrewProfile:
    profile_id: str
    name: str
    targets: dict[str, float]
    age: int | None = None
    sex: str = "unspecified"
    targets_reviewed: bool = False

    def validate(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("Each crew profile needs a nonempty stable ID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Each crew profile needs a label or alias.")
        if self.age is not None and (isinstance(self.age, bool) or not isinstance(self.age, int) or self.age < 0):
            raise ValueError("Age must be a nonnegative integer or omitted.")
        if self.sex not in {"unspecified", "male", "female"}:
            raise ValueError("Reference-table sex must be unspecified, male or female.")
        if set(self.targets) - set(UNITS):
            raise ValueError("Supported targets are energy, protein and vitamin_c.")
        for nutrient, target in self.targets.items():
            nonnegative(target, f"{self.name}: {nutrient} target")


@dataclass(frozen=True)
class FoodLogEntry:
    profile_id: str
    day: int
    food_key: str
    grams: float

    def validate(self, catalog: Mapping[str, FoodComposition]) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("Food logs need a crew-profile ID.")
        if isinstance(self.day, bool) or not isinstance(self.day, int) or self.day < 1:
            raise ValueError("Log day must be a positive integer.")
        if self.food_key not in catalog:
            raise ValueError(f"Unknown food-composition key: {self.food_key}.")
        nonnegative(self.grams, "Logged food mass")


def default_profiles(config: HabitatConfig) -> list[CrewProfile]:
    stored = getattr(config, "crew_profiles", [])
    if stored:
        return [CrewProfile(**{key: copy.deepcopy(row[key]) for key in CrewProfile.__dataclass_fields__ if key in row})
            for row in stored]
    return [CrewProfile(f"crew-{index + 1}", f"Crew {index + 1}", dict(config.targets_per_crew))
        for index in range(config.crew)]


def active_crew_context(config: HabitatConfig, day: int, daily_row: dict | None = None,
                        scenario=None) -> dict:
    """Resolve identities in mission order and match effective planning targets.

    The initial roster and dated reviewed rosters describe who is present. A
    count-only change cannot establish identities; unknown places remain
    explicitly unnamed. Relative or independent target adjustments are shared
    proportionally, preserving each member's reviewed target weights. These
    are planning targets, never blood-derived diagnoses or personal meals.
    """
    from .model import Scenario
    from .planner import _day_conditions
    if isinstance(day, bool) or not isinstance(day, int) or day < 1:
        raise ValueError("Crew context day must be a positive integer.")
    scenario = scenario or Scenario("crew-context", "Reviewed mission inputs", event_day=config.days + 1)
    roster = copy.deepcopy(getattr(config, "crew_profiles", []))
    count = config.crew
    source = "initial_reviewed_roster" if roster else "crew_count_only"
    effective_from = 1
    cancel_relative = any(event.get("cancel_scenario_crew") is True
        and event["day"] <= scenario.event_day for event in config.planning_events)
    timeline = [(scenario.event_day, -1, None)]
    timeline.extend((event["day"], index, event) for index, event in enumerate(config.planning_events))
    for effective_day, _, event in sorted(timeline):
        if effective_day > day:
            break
        if event is None:
            if not cancel_relative and scenario.extra_crew:
                count += scenario.extra_crew
                effective_from = effective_day
        elif "crew_profiles" in event:
            roster = copy.deepcopy(event["crew_profiles"])
            count = event["crew"]
            effective_from, source = effective_day, "dated_reviewed_roster"
        elif "crew" in event:
            if event["crew"] != count:
                # A numeric reduction cannot tell us which named person left;
                # an increase likewise does not establish a retained roster.
                roster = []
                effective_from, source = effective_day, "crew_count_only"
            count = event["crew"]
    reviewed_count, totals, _, _ = _day_conditions(config, scenario, day)
    row = daily_row or {}
    count = row.get("crew", reviewed_count)
    totals = {n: row.get(f"{n}_target", total * count / reviewed_count) for n, total in totals.items()}
    if len(roster) > count:
        roster = []
        source = "saved_count_without_matching_roster"
    named_count = len(roster)
    unnamed = max(0, count - named_count)
    denominators = {n: sum(p["targets"].get(n, 0) for p in roster) for n in totals}
    # An unnamed arrival receives the roster's average *planning* target for
    # proportional arithmetic; no label, clinical profile or observation is
    # invented for that person.
    original_mean = {n: denominators[n] / named_count if named_count else config.targets_per_crew[n] for n in totals}
    denominators = {n: amount + unnamed * original_mean[n] for n, amount in denominators.items()}
    members, adjusted = [], False
    for profile in roster:
        member = copy.deepcopy(profile)
        reviewed = copy.deepcopy(profile["targets"])
        member["reviewed_targets"] = reviewed
        member["targets"] = {n: reviewed.get(n, 0) * totals[n] / denominators[n]
            if denominators[n] else 0.0 for n in totals}
        adjusted |= any(abs(member["targets"][n] - reviewed.get(n, 0)) > 1e-6 for n in totals)
        members.append(member)
    return {"day": day, "crew_count": count, "members": members, "named_count": named_count,
        "unnamed_count": unnamed, "aggregate_daily_targets": totals,
        "effective_from_day": effective_from, "source": source, "targets_adjusted": adjusted,
        "unnamed_daily_targets": {n: max(0.0, total - sum(member["targets"][n] for member in members))
            for n, total in totals.items()},
        "scope": "Reviewed roster and effective simulated daily planning targets; aggregate supply does not establish individual intake or clinical status."}


def vitamin_c_reference(age: int | None, sex: str) -> dict | None:
    """Optional NIH adult reference; not auto-applied or a spaceflight prescription.

    The two values below apply to adults who are not pregnant/lactating and do
    not smoke. Those contexts need a separately reviewed target.
    """
    if age is None or age < 19 or sex not in {"male", "female"}:
        return None
    return {"rda_mg": 90.0 if sex == "male" else 75.0, "ul_mg": 2000.0,
        "source_url": NIH_URL, "scope": "NIH healthy-adult reference; nonpregnant, nonlactating, nonsmoking. Manual review required."}


def validate_profiles(profiles: Iterable[CrewProfile]) -> list[CrewProfile]:
    selected = list(profiles)
    ids = []
    for profile in selected:
        profile.validate()
        ids.append(profile.profile_id)
    if len(ids) != len(set(ids)):
        raise ValueError("Crew-profile IDs must be unique.")
    return selected


def assess_intake(profiles: Iterable[CrewProfile], entries: Iterable[FoodLogEntry], day: int,
                  complete: Mapping[str, bool] | None = None,
                  compositions: Mapping[str, FoodComposition] | None = None) -> list[dict]:
    """Estimate intake from logged masses; absence of a log is unknown intake."""
    if isinstance(day, bool) or not isinstance(day, int) or day < 1:
        raise ValueError("Assessment day must be a positive integer.")
    catalog = compositions if compositions is not None else load_compositions()
    profiles = validate_profiles(profiles)
    people = {profile.profile_id: profile for profile in profiles}
    logs = list(entries)
    for entry in logs:
        entry.validate(catalog)
        if entry.profile_id not in people:
            raise ValueError("A logged food references a missing crew profile.")
    rows = []
    for profile in profiles:
        selected = [entry for entry in logs if entry.profile_id == profile.profile_id and entry.day == day]
        is_complete = bool((complete or {}).get(profile.profile_id, False))
        reference = vitamin_c_reference(profile.age, profile.sex)
        for nutrient, unit in UNITS.items():
            target = profile.targets.get(nutrient)
            unknown = [entry.food_key for entry in selected if catalog[entry.food_key].nutrients_per_kg.get(nutrient) is None]
            known = sum(catalog[entry.food_key].nutrients_per_kg.get(nutrient, 0) * entry.grams / 1000
                for entry in selected if catalog[entry.food_key].nutrients_per_kg.get(nutrient) is not None)
            intake = None if unknown or (not selected and not is_complete) else known
            tracked = target is not None and target > 0
            gap = None if intake is None or not tracked else max(0.0, target - intake)
            coverage = None if intake is None or not tracked else 100 * intake / target
            status = "unknown_intake" if intake is None else "target_not_set" if not tracked else (
                "below_logged_target" if gap > 1e-9 else "logged_target_met")
            rows.append({"profile_id": profile.profile_id, "person": profile.name, "day": day, "nutrient": nutrient,
                "unit": unit, "intake": intake, "known_intake": known, "target": target, "gap": gap,
                "coverage_pct": coverage, "status": status, "log_complete": is_complete,
                "missing_composition_foods": sorted(set(unknown)), "targets_reviewed": profile.targets_reviewed,
                "above_adult_vitamin_c_ul": bool(nutrient == "vitamin_c" and reference and intake is not None and intake > reference["ul_mg"])})
    return rows


def aggregate_profile_targets(profiles: Iterable[CrewProfile]) -> dict[str, float]:
    profiles = validate_profiles(profiles)
    if not profiles:
        raise ValueError("At least one crew profile is required to aggregate targets.")
    if any(set(profile.targets) != set(UNITS) for profile in profiles):
        raise ValueError("Set all three manual targets before applying them to the planner.")
    return {nutrient: sum(profile.targets[nutrient] for profile in profiles) / len(profiles) for nutrient in UNITS}


def apply_profile_targets(config: HabitatConfig, profiles: Iterable[CrewProfile]) -> HabitatConfig:
    profiles = validate_profiles(profiles)
    if len(profiles) != config.crew:
        raise ValueError("The profile count must match the planner crew count before applying an aggregate.")
    targets = aggregate_profile_targets(profiles)
    provenance = copy.deepcopy(getattr(config, "input_provenance", {}))
    provenance["crew_targets"] = {"status": "Manual per-person targets explicitly aggregated by the user",
        "profiles": len(profiles), "all_targets_user_reviewed": all(profile.targets_reviewed for profile in profiles),
        "aggregation": "Arithmetic mean per crew member; planner still uses a shared daily target, not personal meal constraints.",
        "medical_validation": "Not established; no automatic astronaut energy/protein prescription."}
    updated = replace(config, targets_per_crew=targets, crew_profiles=[asdict(profile) for profile in profiles],
        nutrient_units=UNITS.copy(), input_provenance=provenance)
    updated.validate()
    return updated


def crop_contributions(gaps: Mapping[str, float], servings_g: Mapping[str, float] | None = None,
                       crop_ids: Iterable[str] | None = None) -> list[dict]:
    catalog = load_compositions()
    gaps = {nutrient: nonnegative(amount, f"Gap {nutrient}") for nutrient, amount in gaps.items() if nutrient in UNITS}
    servings = dict(EXAMPLE_SERVINGS_G)
    if servings_g is not None:
        for key, value in servings_g.items():
            servings[key] = nonnegative(value, f"Example serving {key}")
    rows = []
    for crop_id in list(crop_ids) if crop_ids is not None else EXAMPLE_SERVINGS_G:
        composition = composition_for_species(crop_id, catalog)
        if composition is None or composition.key not in EXAMPLE_SERVINGS_G:
            continue
        grams = servings.get(crop_id, servings[composition.key])
        amounts = {nutrient: None if composition.nutrients_per_kg.get(nutrient) is None else
            composition.nutrients_per_kg[nutrient] * grams / 1000 for nutrient in UNITS}
        coverage = {nutrient: None if gap == 0 or amounts[nutrient] is None else min(100.0, 100 * amounts[nutrient] / gap)
            for nutrient, gap in gaps.items()}
        rows.append({"crop_id": crop_id, "composition_key": composition.key, "food": composition.name,
            "serving_g": grams, "nutrients": amounts, "gap_coverage_pct": coverage, "fdc_id": composition.fdc_id,
            "source_url": composition.source_url, "available_now": "Not established; harvest timing and stock must be checked."})
    rows.sort(key=lambda row: row["gap_coverage_pct"].get("vitamin_c") or 0, reverse=True)
    return rows


def serialize_state(profiles: Iterable[CrewProfile], entries: Iterable[FoodLogEntry], complete_days: Mapping[str, bool]) -> dict:
    profiles = validate_profiles(profiles)
    entries = list(entries)
    for entry in entries:
        entry.validate(load_compositions())
        if entry.profile_id not in {profile.profile_id for profile in profiles}:
            raise ValueError("A logged food references a missing crew profile.")
    return {"schema_version": 1, "profiles": [asdict(profile) for profile in profiles],
        "entries": [asdict(entry) for entry in entries], "complete_days": dict(complete_days),
        "assessment_scope": "Manual dietary intake estimates; not clinical nutritional status or diagnosis.",
        "food_data": {"dataset": "USDA FoodData Central SR Legacy", "release": "2018-04"}}


def restore_state(payload: dict) -> tuple[list[CrewProfile], list[FoodLogEntry], dict[str, bool]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported nutrition snapshot format.")
    try:
        profiles = [CrewProfile(**row) for row in payload["profiles"]]
        entries = [FoodLogEntry(**row) for row in payload["entries"]]
        complete = payload.get("complete_days", {})
    except (KeyError, TypeError) as exc:
        raise ValueError("Nutrition snapshot structure is invalid.") from exc
    if not isinstance(complete, dict) or any(not isinstance(key, str) or not isinstance(value, bool) for key, value in complete.items()):
        raise ValueError("Snapshot completeness declarations are invalid.")
    serialize_state(profiles, entries, complete)
    return profiles, entries, complete
