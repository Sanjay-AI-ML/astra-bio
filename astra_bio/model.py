"""Typed planning inputs. Provenance accompanies research presets; defaults are synthetic."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class FoodSpec:
    id: str
    name: str
    initial_kg: float
    nutrients_per_kg: dict[str, float]
    # Reserve eligibility is independent of storage/perishability. All FoodSpec
    # items are stored food; only CropSpec harvests are fresh in this demo.
    is_reserve: bool = True
    shelf_life_days: int | None = None
    initial_age_days: int = 0
    nutrient_half_life_days: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CropSpec:
    id: str
    name: str
    grow_days: int
    yield_kg_per_m2: float
    water_l_per_m2_day: float
    power_kwh_per_m2_day: float
    nutrients_per_kg: dict[str, float]


@dataclass(frozen=True)
class HabitatConfig:
    days: int = 90
    crew: int = 4
    area_m2: float = 12.5
    water_budget_l_per_day: float = 50.0
    power_budget_kwh_per_day: float = 8.0
    reserve_days: float = 7.0
    crew_water_l_per_day: float = 3.0
    foods: list[FoodSpec] = field(default_factory=list)
    crops: list[CropSpec] = field(default_factory=list)
    targets_per_crew: dict[str, float] = field(default_factory=dict)
    nutrient_units: dict[str, str] = field(default_factory=dict)
    max_fresh_kg_per_crew_day: float = 0.8
    planting_increment_m2: float = 0.0
    nutrient_upper_per_crew: dict[str, float] = field(default_factory=dict)
    max_total_food_kg_per_crew_day: float = 0.0
    input_provenance: dict[str, object] = field(default_factory=dict)
    # Initial named roster; later reviewed rosters belong to dated events.
    crew_profiles: list[dict[str, object]] = field(default_factory=list)
    # Absolute reviewed changes take effect on the specified mission day.
    # These preserve original conditions and already elapsed simulation rows.
    planning_events: list[dict[str, object]] = field(default_factory=list)
    # Optional finite, usable stores. Daily budgets remain delivery capacity;
    # an unspecified store does not imply an unlimited measured reservoir.
    initial_water_l: float | None = None
    initial_energy_kwh: float | None = None

    def validate(self) -> None:
        if isinstance(self.days, bool) or not isinstance(self.days, int) or self.days < 1:
            raise ValueError("Planning days must be a positive integer.")
        if isinstance(self.crew, bool) or not isinstance(self.crew, int) or self.crew < 1:
            raise ValueError("Crew must be a positive integer.")
        for name in (
            "area_m2", "water_budget_l_per_day", "power_budget_kwh_per_day",
            "reserve_days", "crew_water_l_per_day", "max_fresh_kg_per_crew_day",
            "planting_increment_m2", "max_total_food_kg_per_crew_day",
        ):
            _nonnegative(getattr(self, name), name)
        if not isinstance(self.targets_per_crew, dict) or not self.targets_per_crew:
            raise ValueError("At least one positive demonstration nutrient target is required.")
        for name in ("nutrient_units", "nutrient_upper_per_crew", "input_provenance"):
            if not isinstance(getattr(self, name), dict):
                raise ValueError(f"{name} must be an object.")
        if any(not isinstance(key, str) or not key for key in self.targets_per_crew):
            raise ValueError("Nutrient identifiers must be nonempty strings.")
        for nutrient, target in self.targets_per_crew.items():
            _nonnegative(target, f"Target {nutrient}")
            if target == 0:
                raise ValueError(f"Target {nutrient} must be positive.")
        for nutrient, upper in self.nutrient_upper_per_crew.items():
            if nutrient not in self.targets_per_crew:
                raise ValueError(f"Unknown nutrient upper bound: {nutrient}.")
            _nonnegative(upper, f"Upper bound {nutrient}")
            if upper < self.targets_per_crew[nutrient]:
                raise ValueError(f"Upper bound for {nutrient} must meet or exceed its target.")
        for name in ("initial_water_l", "initial_energy_kwh"):
            if getattr(self, name) is not None:
                _nonnegative(getattr(self, name), name)
        if not isinstance(self.planning_events, list):
            raise ValueError("Planning events must be a list.")
        for event in self.planning_events:
            _validate_planning_event(event, self)
        if not isinstance(self.crew_profiles, list):
            raise ValueError("Initial crew profiles must be a list.")
        if self.crew_profiles:
            _validate_planning_event({"day": 1, "crew": self.crew,
                "targets_per_crew": self.targets_per_crew, "crew_profiles": self.crew_profiles}, self)
        ids = [food.id for food in self.foods] + [crop.id for crop in self.crops]
        if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("Food and crop identifiers must be unique and nonempty.")
        if not ids:
            raise ValueError("Provide at least one food or crop.")
        for food in self.foods:
            if not isinstance(food.is_reserve, bool):
                raise ValueError("Reserve eligibility must be a boolean.")
            if not isinstance(food.nutrient_half_life_days, dict):
                raise ValueError("Nutrient half lives must be an object.")
            _nonnegative(food.initial_kg, f"Initial stock for {food.name}")
            _validate_profile(food.nutrients_per_kg, food.name)
            if isinstance(food.initial_age_days, bool) or not isinstance(food.initial_age_days, int) or food.initial_age_days < 0:
                raise ValueError("Food initial age must be a nonnegative integer.")
            if food.shelf_life_days is not None and (isinstance(food.shelf_life_days, bool) or not isinstance(food.shelf_life_days, int) or food.shelf_life_days < 1):
                raise ValueError("Shelf life must be a positive integer or unspecified.")
            for nutrient, half_life in food.nutrient_half_life_days.items():
                if nutrient not in food.nutrients_per_kg:
                    raise ValueError(f"Unknown retention nutrient: {nutrient}.")
                _nonnegative(half_life, f"Half life for {nutrient}")
                if half_life == 0:
                    raise ValueError("Nutrient half life must be positive.")
        for crop in self.crops:
            if isinstance(crop.grow_days, bool) or not isinstance(crop.grow_days, int) or crop.grow_days < 1:
                raise ValueError(f"Growth time for {crop.name} must be a positive integer.")
            for name in ("yield_kg_per_m2", "water_l_per_m2_day", "power_kwh_per_m2_day"):
                _nonnegative(getattr(crop, name), f"{crop.name}: {name}")
            _validate_profile(crop.nutrients_per_kg, crop.name)


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    event_day: int = 30
    water_factor: float = 1.0
    power_factor: float = 1.0
    extra_crew: int = 0
    target_factors: dict[str, float] = field(default_factory=dict)
    failed_crop_ids: tuple[str, ...] = ()
    crop_yield_factors: dict[str, float] = field(default_factory=dict)

    def validate(self, config: HabitatConfig) -> None:
        if isinstance(self.event_day, bool) or not isinstance(self.event_day, int) or self.event_day < 1:
            raise ValueError("The event day must be a positive integer.")
        if isinstance(self.extra_crew, bool) or not isinstance(self.extra_crew, int) or self.extra_crew < 0:
            raise ValueError("Additional crew must be a nonnegative integer.")
        _nonnegative(self.water_factor, "Water factor")
        _nonnegative(self.power_factor, "Power factor")
        if not isinstance(self.target_factors, dict) or not isinstance(self.crop_yield_factors, dict):
            raise ValueError("Scenario factors must be objects.")
        for nutrient, factor in self.target_factors.items():
            if nutrient not in config.targets_per_crew:
                raise ValueError(f"Unknown nutrient target: {nutrient}.")
            _nonnegative(factor, f"Target factor for {nutrient}")
            if factor == 0:
                raise ValueError("Target factors must be positive.")
        crop_ids = {crop.id for crop in config.crops}
        for crop_id in set(self.failed_crop_ids) | set(self.crop_yield_factors):
            if crop_id not in crop_ids:
                raise ValueError(f"Unknown affected crop: {crop_id}.")
        for crop_id, factor in self.crop_yield_factors.items():
            _nonnegative(factor, f"Crop yield factor for {crop_id}")
            if factor > 1:
                raise ValueError("Crop-loss yield factors must be between zero and one.")


def _nonnegative(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number.")


def _validate_profile(profile: dict[str, float], name: str) -> None:
    if not isinstance(profile, dict) or any(not isinstance(key, str) or not key for key in profile):
        raise ValueError(f"{name} needs a nutrient-to-number composition object.")
    for nutrient, amount in profile.items():
        _nonnegative(amount, f"{name}: {nutrient}")


def _validate_planning_event(event: dict, config: HabitatConfig) -> None:
    allowed = {"day", "crew", "targets_per_crew", "water_budget_l_per_day",
               "power_budget_kwh_per_day", "area_m2", "reason", "crew_profiles", "cancel_scenario_crew"}
    if not isinstance(event, dict) or set(event) - allowed:
        raise ValueError("Planning event contains unsupported fields.")
    day = event.get("day")
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= config.days:
        raise ValueError("Planning event day must be within the mission.")
    if "crew" in event and (isinstance(event["crew"], bool) or not isinstance(event["crew"], int) or event["crew"] < 1):
        raise ValueError("Planning event crew must be a positive integer.")
    if "cancel_scenario_crew" in event and not isinstance(event["cancel_scenario_crew"], bool):
        raise ValueError("Planning event crew cancellation must be a boolean.")
    for key in ("water_budget_l_per_day", "power_budget_kwh_per_day", "area_m2"):
        if key in event:
            _nonnegative(event[key], f"Planning event {key}")
    if "targets_per_crew" in event:
        targets = event["targets_per_crew"]
        if not isinstance(targets, dict) or set(targets) != set(config.targets_per_crew):
            raise ValueError("Planning event targets must include every tracked nutrient.")
        for nutrient, target in targets.items():
            _nonnegative(target, f"Planning event target {nutrient}")
            if target == 0:
                raise ValueError("Planning event targets must be positive.")
            if target > config.nutrient_upper_per_crew.get(nutrient, float("inf")):
                raise ValueError(f"Upper bound for {nutrient} must meet or exceed its target.")
    if "reason" in event and not isinstance(event["reason"], str):
        raise ValueError("Planning event reason must be text.")
    if "crew_profiles" in event:
        if not isinstance(event["crew_profiles"], list) or len(event["crew_profiles"]) != event.get("crew"):
            raise ValueError("Planning event profiles must match its crew count.")
        identifiers, totals = set(), {n: 0.0 for n in config.targets_per_crew}
        for profile in event["crew_profiles"]:
            if not isinstance(profile, dict) or not isinstance(profile.get("profile_id"), str) or not profile["profile_id"].strip() or profile["profile_id"] in identifiers:
                raise ValueError("Planning event profile identifiers must be unique and nonempty.")
            identifiers.add(profile["profile_id"])
            if not isinstance(profile.get("name"), str) or not profile["name"].strip():
                raise ValueError("Planning event profiles need names.")
            targets = profile.get("targets")
            if not isinstance(targets, dict) or not set(totals) <= set(targets):
                raise ValueError("Planning event profiles need every tracked target.")
            for nutrient in totals:
                _nonnegative(targets[nutrient], f"Planning event profile {nutrient}")
                if targets[nutrient] == 0 or targets[nutrient] > config.nutrient_upper_per_crew.get(nutrient, float("inf")):
                    raise ValueError("Planning event profile targets must be positive and within configured upper bounds.")
                totals[nutrient] += targets[nutrient]
        means = event.get("targets_per_crew", {})
        if any(abs(means.get(n, -1) * event["crew"] - amount) > 1e-6 * max(1.0, amount) for n, amount in totals.items()):
            raise ValueError("Planning event aggregate targets must match the reviewed crew roster.")


def default_config() -> HabitatConfig:
    """Return a fresh set of illustrative coefficients, never clinical guidance."""
    return HabitatConfig(
        foods=[
            FoodSpec("ration", "Stored mixed ration (synthetic)", 400.0,
                     {"energy": 2500.0, "protein": 100.0, "vitamin_c": 20.0}),
            FoodSpec("protein_pack", "Stored protein pack (synthetic)", 20.0,
                     {"energy": 3000.0, "protein": 400.0, "vitamin_c": 0.0}),
            FoodSpec("vitamin_blend", "Stored vitamin blend (synthetic)", 2.0,
                     {"energy": 1000.0, "protein": 0.0, "vitamin_c": 5000.0}),
        ],
        crops=[
            CropSpec("microgreens", "Microgreens (synthetic)", 14, 2.0, 3.0, 0.25,
                     {"energy": 250.0, "protein": 25.0, "vitamin_c": 350.0}),
            CropSpec("lettuce", "Lettuce (synthetic)", 28, 4.0, 1.5, 0.40,
                     {"energy": 150.0, "protein": 12.0, "vitamin_c": 180.0}),
            CropSpec("radish", "Radish (synthetic)", 23, 3.0, 2.0, 0.35,
                     {"energy": 180.0, "protein": 12.0, "vitamin_c": 240.0}),
            CropSpec("kale", "Kale (synthetic)", 30, 3.6, 1.4, 0.60,
                     {"energy": 350.0, "protein": 30.0, "vitamin_c": 400.0}),
            CropSpec("soy", "Soy crop (synthetic)", 60, 3.0, 2.0, 0.50,
                     {"energy": 1200.0, "protein": 150.0, "vitamin_c": 100.0}),
            CropSpec("tomato", "Tomato (synthetic)", 45, 8.0, 2.0, 0.40,
                     {"energy": 180.0, "protein": 15.0, "vitamin_c": 200.0}),
        ],
        targets_per_crew={"energy": 2200.0, "protein": 90.0, "vitamin_c": 100.0},
        nutrient_units={"energy": "kcal (demo)", "protein": "g (demo)", "vitamin_c": "mg (demo)"},
    )


def scenario_presets() -> dict[str, Scenario]:
    return {
        "nominal": Scenario("nominal", "Nominal operations"),
        "water": Scenario("water", "Water availability drops by 40%", water_factor=0.6),
        "crop_loss": Scenario("crop_loss", "Active kale batches lose 50% yield",
                              crop_yield_factors={"kale": 0.5}),
        "crew": Scenario("crew", "Two additional crew members", extra_crew=2),
        "targets": Scenario("targets", "Vitamin C demo target increases by 40%",
                            target_factors={"vitamin_c": 1.4}),
    }
