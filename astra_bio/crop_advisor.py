"""Explainable crop comparisons using the submitted simulation's coefficients.

This is a deterministic planning aid, not a new biological model. Nutrient
amounts with different units are never added directly. A recommendation does
not change a planting, consume stored food, or infer nutrients from a photo.
"""
from __future__ import annotations

from math import floor, isclose

from .model import HabitatConfig, Scenario
from .nutrition import UNITS, active_crew_context, composition_for_species, load_compositions, nonnegative
from .planner import PlanResult, _batch_factor, _day_area_capacity, _day_conditions

PRIORITIES = ("balanced", "protein", "energy", "vitamin_c")
EPS = 1e-6


def _reviewed_conditions(config: HabitatConfig, day: int, scenario: Scenario | None = None):
    """Known reviewed changes also apply when no saved row is available."""
    neutral = Scenario("advisor", "Reviewed planning inputs", event_day=config.days + 1)
    return _day_conditions(config, scenario or neutral, day)


def _target_for_row(config: HabitatConfig, row: dict, day: int, nutrient: str, scenario=None) -> float:
    crew, targets, _, _ = _reviewed_conditions(config, day, scenario)
    return row.get(f"{nutrient}_target", targets.get(nutrient, 0.0) * row.get("crew", crew) / crew)


def _amounts(profile: dict, mass_kg: float) -> dict:
    # Unknown composition remains unknown, rather than becoming a measured zero.
    return {n: profile[n] * mass_kg if n in profile else None for n in UNITS}


def _composition_provenance(item, catalog) -> dict:
    reference = composition_for_species(item.id, catalog)
    matches = reference is not None and all(
        n in item.nutrients_per_kg
        and reference.nutrients_per_kg.get(n) is not None
        and isclose(item.nutrients_per_kg[n], reference.nutrients_per_kg[n], rel_tol=1e-9, abs_tol=1e-6)
        for n in UNITS
    )
    result = {
        "status": "usda_reference_proxy" if matches else "configured_assumption",
        "source_url": reference.source_url if matches else None,
        "fdc_id": reference.fdc_id if matches else None,
        "food_form": reference.food_form if matches else "Configured edible food form; verify before applying.",
        "detail": "Generic USDA edible-food composition; not a measured habitat harvest."
        if matches else "Current configuration coefficients; no matching measured composition is established.",
    }
    if reference is not None and not matches:
        result["comparison_reference"] = {"source_url": reference.source_url, "fdc_id": reference.fdc_id,
            "detail": "A reference exists, but its nutrient values differ from the submitted coefficients."}
    return result


def _forecast(config: HabitatConfig, rows: dict[int, dict], day: int, deadline: int, scenario=None) -> dict:
    result = []
    current = rows.get(day, {})
    for nutrient, unit in UNITS.items():
        target = _target_for_row(config, current, day, nutrient, scenario)
        gaps = []
        normalized_gap = 0.0
        for d, row in sorted(rows.items()):
            if d < day or d > deadline:
                continue
            gap = row.get("shortfall_units", {}).get(nutrient, row.get(f"{nutrient}_shortfall", 0.0))
            daily_target = _target_for_row(config, row, d, nutrient, scenario)
            if gap > EPS:
                gaps.append((d, gap))
                if daily_target > 0:
                    normalized_gap += gap / daily_target
        daily_forecast = []
        for d, row in sorted(rows.items()):
            if d < day or d > deadline:
                continue
            daily_forecast.append({"day": d,
                "target": _target_for_row(config, row, d, nutrient, scenario),
                "supply": row.get(f"{nutrient}_supply"),
                "shortfall": row.get("shortfall_units", {}).get(nutrient, row.get(f"{nutrient}_shortfall"))})
        result.append({"nutrient": nutrient, "unit": unit,
            "current_target": target,
            "current_supply": current.get(f"{nutrient}_supply"),
            "current_shortfall": current.get("shortfall_units", {}).get(nutrient, current.get(f"{nutrient}_shortfall")),
            "earliest_gap_day": gaps[0][0] if gaps else None,
            "cumulative_future_shortfall": sum(gap for _, gap in gaps),
            "normalized_future_gap": normalized_gap, "gap_days": len(gaps), "daily": daily_forecast})
    return {"available": any(day <= d <= deadline for d in rows), "nutrients": result,
        "through_day": deadline,
        "scope": "Forecast of the saved plan from the requested planting day; not observed dietary intake."}


def _headroom(config: HabitatConfig, plan: PlanResult | None, row: dict, day: int, scenario=None) -> dict:
    crops = {crop.id: crop for crop in config.crops}
    active = [batch for batch in plan.planting if batch["day"] <= day < batch["harvest_day"]] if plan else []
    reviewed_crew, _, available_water, available_power = _reviewed_conditions(config, day, scenario)
    crew = row.get("crew", reviewed_crew)
    crew_water = crew * config.crew_water_l_per_day
    inferred_water = crew_water + sum(crops[b["crop_id"]].water_l_per_m2_day * b["area_m2"]
        for b in active if b["crop_id"] in crops)
    inferred_power = sum(crops[b["crop_id"]].power_kwh_per_m2_day * b["area_m2"]
        for b in active if b["crop_id"] in crops)
    return {
        "water_l": max(0.0, row.get("water_available_l", available_water)
            - max(crew_water, row.get("water_l", inferred_water))),
        "power_kwh": max(0.0, row.get("power_available_kwh", available_power)
            - row.get("power_kwh", inferred_power)),
        "area_m2": max(0.0, row.get("area_available_m2", _day_area_capacity(config,
            scenario or Scenario("advisor", "Reviewed planning inputs", event_day=config.days + 1), day))
            - row.get("area_m2", sum(b["area_m2"] for b in active))),
    }


def _unallocated_stores(config: HabitatConfig, rows: dict[int, dict], day: int) -> dict:
    """Finite stores left after every allocation in the saved mission.

    Today's remaining tank is not free capacity: later saved meals and crops
    already depend on it. Missing finite-store forecasts remain unknown.
    """
    final = rows.get(config.days, {})
    result = {}
    for key, field in (("water_l", "initial_water_l"), ("energy_kwh", "initial_energy_kwh")):
        initial = getattr(config, field, None)
        remaining_field = "water_remaining_l" if key == "water_l" else "energy_remaining_kwh"
        result[key] = {
            "configured": initial is not None,
            "remaining": final.get(remaining_field) if initial is not None else None,
            "source": f"Saved plan closing finite store on day {config.days}"
                if remaining_field in final else "No complete closing finite-store forecast",
        }
    return result


def _harvest_help(config: HabitatConfig, plan: PlanResult | None, rows: dict[int, dict],
                  crop, harvest_day: int, mass_kg: float, targets: dict, weights: dict, scenario=None,
                  deadline: int | None = None) -> dict:
    """Credit a new batch only on its consumable harvest day.

    This is a marginal screening comparison, not a second nutrition solve. It
    preserves meals and harvests already allocated in the saved plan.
    """
    row = rows.get(harvest_day, {})
    crew = row.get("crew", _reviewed_conditions(config, harvest_day, scenario)[0])
    eaten = plan.consumption.get(harvest_day, {}) if plan else {}
    crop_ids = {item.id for item in config.crops}
    existing_fresh = sum(max(0.0, eaten.get(item, 0.0)) for item in crop_ids)
    fresh_limit = crew * config.max_fresh_kg_per_crew_day
    fresh_remaining = max(0.0, fresh_limit - existing_fresh)
    mass = min(mass_kg, fresh_remaining) if harvest_day <= (deadline or config.days) else 0.0
    if config.max_total_food_kg_per_crew_day:
        total_eaten = row.get("food_mass_kg", sum(eaten.values()))
        mass = min(mass, max(0.0, crew * config.max_total_food_kg_per_crew_day - total_eaten))
    for nutrient, upper in config.nutrient_upper_per_crew.items():
        amount = crop.nutrients_per_kg.get(nutrient, 0.0)
        supply = row.get(f"{nutrient}_supply")
        if amount > 0 and supply is not None:
            mass = min(mass, max(0.0, crew * upper - supply) / amount)
    gaps = {n: max(0.0, row.get("shortfall_units", {}).get(n, row.get(f"{n}_shortfall", 0.0)))
        if row else None for n in UNITS}
    consumed = _amounts(crop.nutrients_per_kg, mass)
    credit = {n: min(consumed[n], gaps[n]) if consumed[n] is not None and gaps[n] is not None
        else None for n in UNITS}
    components = {n: weights[n] * (credit[n] or 0.0) / targets[n]
        if targets[n] > 0 else 0.0 for n in UNITS}
    return {"harvest_day_shortfalls": gaps,
        "harvest_day_fresh_remaining_kg": fresh_remaining,
        "saved_fresh_consumption_kg": existing_fresh,
        "consumable_harvest_kg": mass,
        "consumable_nutrients_at_harvest": consumed,
        "credited_nutrient_gap_reduction": credit,
        "timing_score_components": components,
        "weighted_gap_help_at_harvest": sum(components.values())}


def _planned_actions(config: HabitatConfig, plan: PlanResult | None, rows: dict[int, dict],
                     day: int, deadline: int, scenario=None) -> list[dict]:
    """Explain the saved solver's future plantings separately from extra trays."""
    if plan is None:
        return []
    crops = {crop.id: crop for crop in config.crops}
    actions = []
    for batch in sorted(plan.planting, key=lambda b: (b["day"], b["harvest_day"], b["crop_id"])):
        if batch["day"] < day or batch["crop_id"] not in crops:
            continue
        crop = crops[batch["crop_id"]]
        harvest = batch["harvest_day"]
        mass = batch.get("predicted_harvest_kg", batch.get("yield_kg",
            batch.get("harvest_kg", batch["area_m2"] * crop.yield_kg_per_m2)))
        targets = {n: rows.get(harvest, {}).get(f"{n}_target") for n in UNITS}
        supply = _amounts(crop.nutrients_per_kg, mass)
        eaten_kg = plan.consumption.get(harvest, {}).get(crop.id, 0.0)
        planned_nutrients = _amounts(crop.nutrients_per_kg, eaten_kg)
        contributions = {n: planned_nutrients[n] / targets[n] if planned_nutrients[n] is not None
            and targets[n] is not None and targets[n] > 0 else None for n in UNITS}
        # Several batches may share a crop/harvest day; consumption below is the
        # crop/day total and is deliberately not attributed to each batch.
        actions.append({"crop_id": crop.id, "name": crop.name, "day": batch["day"],
            "planting_day": batch["day"], "harvest_day": harvest, "area_m2": batch["area_m2"],
            "harvest_deadline_day": deadline, "fits_deadline": harvest <= deadline,
            "latest_planting_day": deadline - crop.grow_days,
            "crew_context_at_harvest": active_crew_context(config, harvest, rows.get(harvest), scenario),
            "estimated_harvest_kg": mass, "predicted_harvest_kg": mass,
            "potential_nutrients_at_harvest": supply, "nutrients_at_harvest": supply,
            "forecast_daily_targets": targets, "planned_crop_day_consumption_kg": eaten_kg,
            "planned_crop_day_nutrients": planned_nutrients,
            "planned_crop_day_target_shares": contributions,
            "reason": "Selected in the saved resource-constrained planting and meal plan; harvest timing and daily crew nutrient targets are considered together.",
            "scope": "Already allocated in the saved plan; not an additional batch. Consumption is the crop/day total, shared by batches harvested together."})
    return actions


def _bridge_foods(config: HabitatConfig, plan: PlanResult | None, day: int, catalog,
                  weights: dict, targets: dict) -> list[dict]:
    if day == 1:
        stocks = {food.id: food.initial_kg for food in config.foods}
        stock_source = "Configured initial stock"
    else:
        stocks = plan.inventories.get(day - 1) if plan is not None else None
        stock_source = f"Saved plan closing inventory on day {day - 1}" if stocks is not None else "No saved inventory for the requested day"
    rows = []
    for food in config.foods:
        age = food.initial_age_days + day - 1
        expired = food.shelf_life_days is not None and age >= food.shelf_life_days
        stock = stocks.get(food.id, 0.0) if stocks is not None else None
        current_profile = {n: amount * (2 ** (-age / food.nutrient_half_life_days[n])
            if n in food.nutrient_half_life_days else 1.0) for n, amount in food.nutrients_per_kg.items()}
        available = stock is not None and stock > EPS and not expired
        stock_nutrients = _amounts(current_profile, stock if available else 0.0) if stock is not None else dict.fromkeys(UNITS)
        score = sum(weights[n] * (stock_nutrients[n] or 0.0) / targets[n]
            for n in UNITS if targets[n] > 0)
        warnings = ["Edible stock is a simulation input/result; it has not been physically verified."]
        if stocks is None:
            warnings.append("Previous-day saved inventory is missing; initial stock was not substituted.")
        if expired:
            warnings.append("Configured shelf life has elapsed; this stock is excluded from bridge options.")
        if food.is_reserve:
            warnings.append("Reserve stock: review the protected reserve before changing planned consumption.")
        rows.append({"food_id": food.id, "name": food.name, "stock_kg": stock,
            "available": available, "expired": expired, "is_reserve": food.is_reserve,
            "stock_source": stock_source, "nutrients_per_100g": _amounts(food.nutrients_per_kg, .1),
            "current_nutrients_per_100g": _amounts(current_profile, .1),
            "available_nutrients_in_stock": stock_nutrients, "score": score,
            "protein_in_stock_g": (stock * current_profile["protein"] if available else 0.0)
                if stock is not None and "protein" in current_profile else None,
            "provenance": _composition_provenance(food, catalog), "warnings": warnings})
    rows.sort(key=lambda row: (not row["available"], -row["score"], row["food_id"]))
    return rows


def recommend_crops(config: HabitatConfig, plan: PlanResult | None = None, *, day: int = 1,
                    priority: str = "balanced", area_m2: float = 1.0,
                    deadline_day: int | None = None, scenario: Scenario | None = None,
                    automatic: bool = False) -> dict:
    """Rank additive crop candidates without changing the submitted simulation.

    ``day`` is the planting day. A crop's first harvest is ``day + grow_days``.
    Resource feasibility checks the remaining daily capacity in the saved plan
    across the full growth window, including any future scenario changes.
    """
    config.validate()
    if not isinstance(automatic, bool):
        raise ValueError("Automatic crop selection must be true or false.")
    if automatic:
        priority = "balanced"
        deadline_day = config.days
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= config.days:
        raise ValueError("Crop planting day must be an integer within the planning horizon.")
    deadline = config.days if deadline_day is None else deadline_day
    if isinstance(deadline, bool) or not isinstance(deadline, int) or not day <= deadline <= config.days:
        raise ValueError("Harvest deadline must be an integer from the planting day through the mission's final day.")
    if scenario is not None:
        scenario.validate(config)
    if not isinstance(priority, str) or priority not in PRIORITIES:
        raise ValueError("Crop priority must be balanced, protein, energy or vitamin_c.")
    area_m2 = nonnegative(area_m2, "Requested growing area")
    if area_m2 == 0:
        raise ValueError("Requested growing area must be positive.")
    if priority != "balanced" and priority not in config.targets_per_crew:
        raise ValueError(f"Set a positive {priority} target before choosing that priority.")
    catalog = load_compositions()
    rows = {row["day"]: row for row in plan.daily if 1 <= row["day"] <= config.days} if plan else {}
    forecast = _forecast(config, rows, day, deadline, scenario)
    crew_context = active_crew_context(config, day, rows.get(day), scenario)
    targets = {row["nutrient"]: row["current_target"] for row in forecast["nutrients"]}
    if priority != "balanced":
        weights = {nutrient: float(nutrient == priority) for nutrient in UNITS}
        weight_basis = "Explicit selected nutrient priority, even when the saved plan has no shortfall."
    else:
        gaps = {row["nutrient"]: row["normalized_future_gap"] for row in forecast["nutrients"]}
        total = sum(gaps.values())
        tracked = sum(target > 0 for target in targets.values())
        weights = {n: gaps[n] / total if total > EPS else float(targets[n] > 0) / tracked if tracked else 0.0 for n in UNITS}
        weight_basis = "Shares of future shortfall divided by each day's crew target." if total > EPS else "Equal weights among configured nutrient targets; no future shortfalls are established."
    headrooms = {d: _headroom(config, plan, rows.get(d, {}), d, scenario) for d in range(day, config.days + 1)}
    today = headrooms[day]
    stores = _unallocated_stores(config, rows, day)
    complete_forecast = all(d in rows for d in range(day, deadline + 1))
    selected_gaps = sum(weights[n] * next(item["normalized_future_gap"]
        for item in forecast["nutrients"] if item["nutrient"] == n) for n in UNITS)
    use_gap_timing = complete_forecast and selected_gaps > EPS
    recommendations = []
    for crop in config.crops:
        harvest_day = day + crop.grow_days
        yield_factor = _batch_factor(scenario, crop.id, day, harvest_day) if scenario else 1.0
        harvest_row = rows.get(harvest_day, {})
        harvest_context = active_crew_context(config, harvest_day, harvest_row, scenario)
        harvest_crew = harvest_context["crew_count"]
        harvest_targets = {n: _target_for_row(config, harvest_row, harvest_day, n, scenario) for n in UNITS}
        growth_window = [headrooms[d] for d in range(day, min(harvest_day, config.days + 1))]
        minimum = {key: min(h[key] for h in growth_window) for key in today}
        batch_area = area_m2
        if automatic:
            # Evaluate alternatives without spending any saved commitments.
            caps = [minimum["area_m2"]]
            for rate, resource in ((crop.water_l_per_m2_day, "water_l"),
                    (crop.power_kwh_per_m2_day, "power_kwh")):
                if rate > EPS:
                    caps.append(minimum[resource] / rate)
            for rate, resource in ((crop.water_l_per_m2_day, "water_l"),
                    (crop.power_kwh_per_m2_day, "energy_kwh")):
                store = stores[resource]
                if rate > EPS and store["configured"]:
                    caps.append(max(0.0, store["remaining"] or 0.0) / (rate * crop.grow_days))
            batch_area = max(0.0, min(caps))
            yield_per_area = crop.yield_kg_per_m2 * yield_factor
            if yield_per_area > EPS:
                help_limit = _harvest_help(config, plan, rows, crop, harvest_day,
                    batch_area * yield_per_area, harvest_targets, weights, scenario, deadline)
                mass_limit = help_limit["consumable_harvest_kg"]
                if use_gap_timing:
                    gap_masses = [help_limit["harvest_day_shortfalls"][n] / crop.nutrients_per_kg[n]
                        for n in UNITS if weights[n] > EPS and crop.nutrients_per_kg.get(n, 0) > EPS
                        and help_limit["harvest_day_shortfalls"].get(n) is not None]
                    mass_limit = min(mass_limit, max(gap_masses, default=0.0))
                batch_area = min(batch_area, mass_limit / yield_per_area)
            if config.planting_increment_m2 > 0:
                batch_area = floor((batch_area + EPS) / config.planting_increment_m2) * config.planting_increment_m2
        kg = batch_area * crop.yield_kg_per_m2 * yield_factor
        nutrients = _amounts(crop.nutrients_per_kg, kg)
        outputs = _amounts(crop.nutrients_per_kg, crop.yield_kg_per_m2 * yield_factor / crop.grow_days)
        normalized = {n: (outputs[n] or 0.0) / harvest_targets[n] if harvest_targets[n] > 0 else 0.0 for n in UNITS}
        components = {n: weights[n] * normalized[n] for n in UNITS}
        water = batch_area * crop.water_l_per_m2_day
        power = batch_area * crop.power_kwh_per_m2_day
        help_at_harvest = _harvest_help(config, plan, rows, crop, harvest_day, kg,
            harvest_targets, weights, scenario, deadline)
        blocked = []
        if automatic and batch_area <= EPS:
            blocked.append("No useful additional batch fits unused growing resources and harvest-day meal capacity; keep or review the saved crop actions.")
        if harvest_day > config.days:
            blocked.append("First harvest is after the planning horizon.")
        elif harvest_day > deadline:
            blocked.append("First harvest is after the selected harvest deadline.")
        if batch_area > minimum["area_m2"] + EPS:
            blocked.append("Insufficient free growing area while keeping the saved plantings.")
        if water > minimum["water_l"] + EPS:
            blocked.append("Insufficient daily water after crew and saved crop allocations.")
        if power > minimum["power_kwh"] + EPS:
            blocked.append("Insufficient daily crop power after saved allocations.")
        for resource, required, description in (("water_l", water * crop.grow_days, "water"),
                ("energy_kwh", power * crop.grow_days, "energy")):
            store = stores[resource]
            if store["configured"] and required > EPS and store["remaining"] is None:
                blocked.append(f"Remaining finite {description} stock is unknown; an additional batch cannot be confirmed.")
            elif store["configured"] and store["remaining"] is not None and required > max(0.0, store["remaining"]) + EPS:
                blocked.append(f"Insufficient unallocated finite {description} stock after the saved mission's future allocations.")
        if config.planting_increment_m2 > 0 and not isclose(batch_area / config.planting_increment_m2,
                round(batch_area / config.planting_increment_m2), abs_tol=EPS, rel_tol=0):
            blocked.append("Requested area is not a multiple of the configured tray increment.")
        if any(weights[n] > 0 and outputs[n] is None for n in UNITS):
            blocked.append("Composition is missing a nutrient used by the selected priority.")
        if not any(weights[n] > 0 and (outputs[n] or 0.0) > 0 for n in UNITS):
            blocked.append("Configured crop supplies no nutrient used by the selected priority.")
        gaps_before = {n: sum(row.get("shortfall_units", {}).get(n, row.get(f"{n}_shortfall", 0.0))
            for d, row in rows.items() if day <= d < harvest_day and d <= deadline) for n in UNITS}
        gap_days_before = {n: sum(row.get("shortfall_units", {}).get(n, row.get(f"{n}_shortfall", 0.0)) > EPS
            for d, row in rows.items() if day <= d < harvest_day and d <= deadline) for n in UNITS}
        fresh_cap = harvest_crew * config.max_fresh_kg_per_crew_day
        warnings = ["Harvest nutrients are potential production, not guaranteed consumption or gap closure.",
            "A crop planted now supplies no food before its first harvest."]
        if kg > fresh_cap + EPS:
            warnings.append("This batch exceeds the total fresh-food limit on harvest day; other harvests share that limit and excess may be discarded.")
        if use_gap_timing and help_at_harvest["weighted_gap_help_at_harvest"] <= EPS:
            warnings.append("This extra batch cannot reduce the selected nutrient gaps on its harvest day while keeping the saved meals and harvests. Earlier shortages require stored-food or recovery decisions.")
        if not complete_forecast:
            warnings.append("The remaining daily forecast is incomplete; ranking uses production per area and growth day, without claiming timed gap closure.")
        recommendations.append({"crop_id": crop.id, "name": crop.name, "actionable": not blocked,
            "area_m2": batch_area,
            "blocked_reasons": blocked,
            "score": help_at_harvest["weighted_gap_help_at_harvest"] if use_gap_timing else sum(components.values()),
            "score_components": help_at_harvest["timing_score_components"] if use_gap_timing else components,
            "score_mode": "harvest_day_gap_help" if use_gap_timing else "production_per_area_day",
            "production_score": sum(components.values()),
            "normalized_output_per_m2_day": normalized, "nutrients_per_100g": _amounts(crop.nutrients_per_kg, .1),
            "score_daily_targets": harvest_targets,
            "nutrient_output_per_m2_day": outputs, "estimated_harvest_kg": kg, "nutrients_at_harvest": nutrients,
            "harvest_day": harvest_day, "grow_days": crop.grow_days, "gaps_before_harvest": gaps_before,
            "harvest_deadline_day": deadline, "latest_planting_day": deadline - crop.grow_days,
            "fits_deadline": harvest_day <= deadline, "yield_factor": yield_factor,
            "crew_context_at_harvest": harvest_context,
            "missed_gap_days_before_harvest": gap_days_before, **help_at_harvest,
            "harvest_day_fresh_limit_kg": fresh_cap,
            "resources": {"required_daily_water_l": water, "available_daily_water_l": today["water_l"],
                "required_daily_power_kwh": power, "available_daily_power_kwh": today["power_kwh"],
                "required_area_m2": batch_area, "available_area_m2": today["area_m2"],
                "cycle_water_l": water * crop.grow_days, "cycle_power_kwh": power * crop.grow_days,
                "min_available_water_l_in_cycle": minimum["water_l"],
                "min_available_power_kwh_in_cycle": minimum["power_kwh"],
                "min_available_area_m2_in_cycle": minimum["area_m2"],
                "remaining_unallocated_water_l": stores["water_l"]["remaining"],
                "remaining_unallocated_energy_kwh": stores["energy_kwh"]["remaining"],
                "finite_water_configured": stores["water_l"]["configured"],
                "finite_energy_configured": stores["energy_kwh"]["configured"]},
            "provenance": {"composition": _composition_provenance(crop, catalog),
                "growth": {"status": "configured_planning_coefficients", "detail": config.input_provenance.get(
                    f"crop:{crop.id}:harvest", "Configured growth duration and edible yield; not a locally validated crop cycle.")},
                "resources": {"status": "planning_assumptions", "detail": config.input_provenance.get(
                    f"crop:{crop.id}:resources", "Configured crop water/power rates and habitat budgets; not physical sensor observations.")}},
            "warnings": warnings})
    recommendations.sort(key=lambda row: (-row["score"], -row["production_score"], row["grow_days"], row["crop_id"]))
    for rank, row in enumerate(recommendations, start=1):
        row["rank"] = rank
    top = next((row["crop_id"] for row in recommendations if row["actionable"]
        and (not use_gap_timing or row["weighted_gap_help_at_harvest"] > EPS)), None)
    if top is not None:
        selection_reason = {"type": "selected", "text": "A resource-feasible additional batch can help the selected nutrient need on its harvest day."
            if use_gap_timing else "A resource-feasible additional batch ranks highest for nutrient production per growing area and day; timed gap closure is not established."}
    elif not recommendations:
        selection_reason = {"type": "no_crops", "text": "No crops are configured for comparison."}
    elif not any(row["actionable"] for row in recommendations):
        selection_reason = {"type": "no_growing_capacity", "text": "No additional batch fits the remaining horizon, tray space and resource allocations. Review the saved plan's selected crop actions."}
    else:
        selection_reason = {"type": "no_timely_gap_help", "text": "Additional growing capacity exists, but these extra batches cannot reduce the selected forecast gaps on their harvest days while preserving saved meals and harvests. Review stored food, recovery options or a replan."}
    return {"schema_version": 1, "day": day, "deadline_day": deadline,
        "crew_context": crew_context, "priority": priority, "area_m2": None if automatic else area_m2,
        "automatic": automatic,
        "area_basis": "Each crop uses only unallocated growth-window resources and unused harvest-day meal capacity; size is capped to weighted harvest-day gaps when established, then rounded down to the configured tray increment. Candidates are alternatives, not simultaneous allocations."
            if automatic else "User-entered comparison area, evaluated independently for each crop.",
        "units": dict(UNITS), "weights": weights, "weight_basis": weight_basis,
        "scoring_basis": "With a complete saved forecast and selected nutrient gaps, score credits only the consumable extra harvest against that harvest day's remaining gaps, divided by that day's crew nutrient targets. Earlier or later gaps receive no credit. Otherwise score compares normalized nutrient production per m²/growth day. Production score breaks timing ties; no nutrient quantities with different units are added directly.",
        "score_mode": "harvest_day_gap_help" if use_gap_timing else "production_per_area_day",
        "remaining_days": deadline - day + 1, "mission_remaining_days": config.days - day + 1,
        "planned_crop_actions": _planned_actions(config, plan, rows, day, deadline, scenario),
        "forecast": forecast, "recommendations": recommendations, "top_choice_crop_id": top,
        "selection_reason": selection_reason,
        "bridge_foods": _bridge_foods(config, plan, day, catalog, weights, targets),
        "limitations": ["Only energy, protein and vitamin C are compared; this is not a complete diet or a clinical assessment.",
            "Recommendations use submitted coefficients and a saved forecast; camera images do not measure nutrient content.",
            "Actionable means remaining area and resources can accommodate an additional batch in the saved schedule; no planting or inventory is changed.",
            "Growing time and yield still need calibration against the actual tray and cultivar.",
            "New crops cannot resolve shortages before harvest; review stored food or recovery options for those days.",
            "Fresh harvest is consumed or discarded on harvest day in the current planner; total batch nutrients are not guaranteed dietary intake."]}
