"""Resource-constrained, harvest-aware planning with a fixed-plan comparison.

The nutrient constraints adapt the educational Pyomo Gallery diet formulation:
https://github.com/Pyomo/pyomo-gallery/tree/main/diet
Copyright (c) 2015-2025 National Technology and Engineering Solutions of
Sandia, LLC; Contract DE-NA0003525; BSD-3-Clause. The ASTRA-BIO
extensions model daily inventory, crop cohorts, resources, reserve gaps and
disruptions. See THIRD_PARTY_NOTICES.md for the complete upstream notice.

All outputs are simulations with the input coefficients, not medical advice.
Fresh crops must be consumed or discarded on harvest day. Stored-food expiry
and exponential nutrient retention use explicitly supplied assumptions; no
oxygen/CO2 loop or medical diagnosis is modelled.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from math import ceil, isfinite
from typing import Any

from .model import HabitatConfig, Scenario

EPS = 1e-6


@dataclass
class PlanResult:
    label: str
    status: str
    daily: list[dict[str, Any]] = field(default_factory=list)
    planting: list[dict[str, Any]] = field(default_factory=list)
    food_totals_kg: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    resource_additions: dict[str, Any] = field(default_factory=dict)
    # Kept for exact state reconstruction, so comparison never replans the past.
    consumption: dict[int, dict[str, float]] = field(default_factory=dict, repr=False)
    inventories: dict[int, dict[str, float]] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonResult:
    baseline: PlanResult
    adaptive: PlanResult
    scenario_name: str
    delta: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_comparison(config: HabitatConfig, scenario: Scenario) -> ComparisonResult:
    """Compare one fixed nominal plan with a replan from the event-day state.

Both strategies share the same days before the event, starting inventory and
crop cohorts. The baseline keeps its planned meals and plantings; resource
shortages reduce realized yield. The adaptive strategy can change future meals,
plantings and retained crop area. Nutritional/reserve slack records shortages.
"""
    config.validate()
    scenario.validate(config)
    nominal = _solve_lp(config, Scenario("nominal", "Nominal operations"), 1, {}, [], "Nominal plan")
    if not nominal.daily:
        failed = replace(nominal, label="Adaptive plan")
        return ComparisonResult(replace(nominal, label="Fixed baseline"), failed, scenario.name, {})
    baseline = _replay_fixed_plan(config, scenario, nominal)
    start = min(scenario.event_day, config.days + 1)
    if start > config.days or not _has_change(scenario):
        adaptive = replace(nominal, label="Adaptive plan")
    else:
        stocks = nominal.inventories.get(start - 1, {})
        carry = [dict(batch) for batch in nominal.planting
                 if batch["day"] < start <= batch["harvest_day"]]
        adaptive = _solve_lp(config, scenario, start, stocks, carry, "Adaptive plan",
                             resource_stocks=_remaining_resource_stocks(config, nominal.daily[:start - 1]))
        if adaptive.daily:
            adaptive.daily = [dict(row) for row in nominal.daily if row["day"] < start] + adaptive.daily
            adaptive.consumption = {
                **{d: dict(v) for d, v in nominal.consumption.items() if d < start},
                **adaptive.consumption,
            }
            adaptive.inventories = {
                **{d: dict(v) for d, v in nominal.inventories.items() if d < start},
                **adaptive.inventories,
            }
            historical = [dict(batch) for batch in nominal.planting
                          if batch["day"] < start and batch["harvest_day"] < start]
            adaptive.planting = historical + adaptive.planting
            _finish(config, scenario, adaptive)
    delta = {}
    for key in set(baseline.metrics) & set(adaptive.metrics):
        delta[key] = adaptive.metrics[key] - baseline.metrics[key]
    affected_ids = set(scenario.failed_crop_ids) | set(scenario.crop_yield_factors)
    if affected_ids and not any(
        batch["crop_id"] in affected_ids and batch["day"] < scenario.event_day <= batch["harvest_day"]
        for batch in nominal.planting
    ):
        warning = f"No specified crop batch was active at day {scenario.event_day}; this crop-loss event affected no harvest."
        baseline.warnings.append(warning)
        adaptive.warnings.append(warning)
    return ComparisonResult(baseline, adaptive, scenario.name, delta)


def _has_change(scenario: Scenario) -> bool:
    return bool(scenario.water_factor != 1 or scenario.power_factor != 1
                or scenario.extra_crew or scenario.target_factors
                or scenario.failed_crop_ids or scenario.crop_yield_factors)


def _day_conditions(config: HabitatConfig, scenario: Scenario, day: int, relief=None):
    crew = config.crew
    per_crew = dict(config.targets_per_crew)
    water = config.water_budget_l_per_day
    power = config.power_budget_kwh_per_day
    # Relative scenarios and reviewed absolute changes are applied in mission
    # order. Only an explicit roster reset may cancel pending relative arrivals;
    # its water, power, target and crop effects remain scheduled.
    cancel_scenario_crew = any(event.get("cancel_scenario_crew") is True
                               and event["day"] <= scenario.event_day
                               for event in config.planning_events)
    timeline = [(scenario.event_day, -1, None)]
    timeline.extend((event["day"], index, event) for index, event in enumerate(config.planning_events))
    for effective_day, _, event in sorted(timeline):
        if effective_day > day:
            break
        if event is None:
            if not cancel_scenario_crew:
                crew += scenario.extra_crew
            per_crew = {n: target * scenario.target_factors.get(n, 1.0) for n, target in per_crew.items()}
            water *= scenario.water_factor
            power *= scenario.power_factor
        else:
            crew = event.get("crew", crew)
            per_crew = dict(event.get("targets_per_crew", per_crew))
            water = event.get("water_budget_l_per_day", water)
            power = event.get("power_budget_kwh_per_day", power)
    targets = {n: target * crew for n, target in per_crew.items()}
    if relief and day >= relief.get("arrival_day", scenario.event_day):
        water += relief.get("water_l_per_day", 0)
        power += relief.get("power_kwh_per_day", 0)
    return crew, targets, water, power


def _day_area_capacity(config: HabitatConfig, scenario: Scenario, day: int) -> float:
    area = config.area_m2
    for event in sorted(config.planning_events, key=lambda item: item["day"]):
        if event["day"] > day:
            break
        area = event.get("area_m2", area)
    return area


def _remaining_resource_stocks(config: HabitatConfig, rows: list[dict]) -> dict[str, float | None]:
    """Usable store less actual simulated delivery, never a reset on replan."""
    result = {}
    for key, configured, used in (("water_l", config.initial_water_l, "water_l"),
                                 ("energy_kwh", config.initial_energy_kwh, "power_kwh")):
        if configured is None:
            result[key] = None
            continue
        remaining_key = "water_remaining_l" if key == "water_l" else "energy_remaining_kwh"
        if rows and remaining_key in rows[-1]:
            value = rows[-1][remaining_key]
        else:
            value = configured - sum(row[used] for row in rows)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < -1e-5:
            raise ValueError("Saved simulated resource consumption exceeds its configured finite store.")
        result[key] = _clean(value)
    return result


def _carried_batch_factor(scenario, crop, batch, start):
    """Preserve already realized/predicted losses, apply pending losses once."""
    expected = crop.yield_kg_per_m2 * batch["area_m2"]
    saved_factor = batch.get("predicted_harvest_kg", expected) / expected if expected > EPS else 0.0
    if scenario.event_day >= start:
        # The saved schedule can already include the same announced loss.
        # Taking the bound applies this single scenario once, not twice.
        saved_factor = min(saved_factor, _batch_factor(scenario, crop.id, batch["day"], batch["harvest_day"]))
    return min(1.0, max(0.0, saved_factor))


def _batch_factor(scenario: Scenario, crop_id: str, sow: int, harvest: int) -> float:
    # The loss concerns batches active when the event happens, not all future crops.
    if sow < scenario.event_day <= harvest:
        if crop_id in scenario.failed_crop_ids:
            return 0.0
        return scenario.crop_yield_factors.get(crop_id, 1.0)
    return 1.0


def _catalogue(config: HabitatConfig):
    profiles = {food.id: food.nutrients_per_kg for food in config.foods}
    profiles.update({crop.id: crop.nutrients_per_kg for crop in config.crops})
    initial = {food.id: food.initial_kg for food in config.foods}
    initial.update({crop.id: 0.0 for crop in config.crops})
    reserve = {food.id for food in config.foods if food.is_reserve}
    return profiles, initial, reserve


def _expired(food, day):
    return food.shelf_life_days is not None and food.initial_age_days + day - 1 >= food.shelf_life_days


def _profiles_for_day(config, day):
    """User-supplied first-order retention assumptions; never inferred kinetics."""
    profiles, _, _ = _catalogue(config)
    for food in config.foods:
        age = food.initial_age_days + day - 1
        profiles[food.id] = {n: amount * (2 ** (-age / food.nutrient_half_life_days[n])
            if n in food.nutrient_half_life_days else 1.0)
            for n, amount in food.nutrients_per_kg.items()}
    return profiles


def _reserve_profiles(config, day):
    # Conservative credit at the end of the requested buffer; food expiring
    # within that window gets no reserve credit, even if edible today.
    future_day = day + ceil(config.reserve_days)
    profiles = _profiles_for_day(config, future_day)
    return {f.id: profiles[f.id] for f in config.foods if f.is_reserve and not _expired(f, future_day)}


def _solve_lp(config, scenario, start, opening_stocks, carry, label, rescue=None, *, resource_stocks=None) -> PlanResult:
    result = PlanResult(label=label, status="solver_error")
    try:
        import pyomo.environ as pyo
        from pyomo.opt import TerminationCondition
    except ImportError:
        result.status = "solver_unavailable"
        result.warnings = ["Install pyomo and highspy to run the real planning engine."]
        return result
    try:
        solver = pyo.SolverFactory("appsi_highs")
        if not solver.available(exception_flag=False):
            result.status = "solver_unavailable"
            result.warnings = ["HiGHS is unavailable. Install highspy; no simulated solver result was substituted."]
            return result
        profiles, initial, reserve = _catalogue(config)
        stored_foods = {food.id for food in config.foods}
        stocks = initial if start == 1 else {f: opening_stocks.get(f, 0.0) for f in profiles}
        crops = {crop.id: crop for crop in config.crops}
        days = list(range(start, config.days + 1))
        conditions = {day: _day_conditions(config, scenario, day) for day in days}
        decisions = [(crop.id, day) for crop in config.crops for day in days
                     if day + crop.grow_days <= config.days]
        m = pyo.ConcreteModel("ASTRA-BIO harvest and inventory planning")
        m.days = pyo.Set(initialize=days, ordered=True)
        m.foods = pyo.Set(initialize=list(profiles))
        m.nutrients = pyo.Set(initialize=list(config.targets_per_crew))
        m.plantings = pyo.Set(initialize=decisions, dimen=2)
        m.carry_batches = pyo.Set(initialize=list(range(len(carry))))
        m.eat = pyo.Var(m.foods, m.days, domain=pyo.NonNegativeReals)
        m.stock = pyo.Var(m.foods, m.days, domain=pyo.NonNegativeReals)
        m.waste = pyo.Var(m.foods, m.days, domain=pyo.NonNegativeReals)
        m.sow = pyo.Var(m.plantings, domain=pyo.NonNegativeReals)
        if config.planting_increment_m2 > 0:
            m.tray_units = pyo.Var(m.plantings, domain=pyo.NonNegativeIntegers)
            m.tray_sizing = pyo.Constraint(m.plantings, rule=lambda model, c, day:
                model.sow[c, day] == config.planting_increment_m2 * model.tray_units[c, day])
        m.keep = pyo.Var(m.carry_batches, domain=pyo.NonNegativeReals,
                         bounds=lambda model, i: (0, carry[i]["area_m2"]))
        if config.planting_increment_m2 > 0:
            m.kept_trays = pyo.Var(m.carry_batches, domain=pyo.NonNegativeIntegers)
            m.kept_tray_sizing = pyo.Constraint(m.carry_batches, rule=lambda model, i:
                model.keep[i] == config.planting_increment_m2 * model.kept_trays[i])
        m.shortfall = pyo.Var(m.nutrients, m.days, domain=pyo.NonNegativeReals)
        m.reserve_gap = pyo.Var(m.nutrients, m.days, domain=pyo.NonNegativeReals)
        m.crew_water_gap = pyo.Var(m.days, domain=pyo.NonNegativeReals,
            bounds=lambda model, day: (0, conditions[day][0] * config.crew_water_l_per_day))
        usable_stores = resource_stocks or {"water_l": config.initial_water_l, "energy_kwh": config.initial_energy_kwh}
        water_used, power_used = {}, {}
        relief = {}
        if rescue:
            mode, limit = rescue["mode"], rescue["limit"]
            for n in m.nutrients:
                for day in days:
                    m.shortfall[n, day].fix(0)
                    if rescue.get("include_reserve"):
                        m.reserve_gap[n, day].fix(0)
            for day in days:
                m.crew_water_gap[day].fix(0)
            if mode == "food":
                m.add_food = pyo.Var(sorted(stored_foods), domain=pyo.NonNegativeReals)
                primary_resource = sum(m.add_food[f] for f in stored_foods)
                m.resource_limit = pyo.Constraint(expr=primary_resource <= limit)
            elif mode in {"water", "power"}:
                m.add_resource = pyo.Var(domain=pyo.NonNegativeReals, bounds=(0, limit))
                primary_resource = m.add_resource
                relief = {"water_l_per_day" if mode == "water" else "power_kwh_per_day": m.add_resource}
            else:
                raise ValueError("Unknown rescue resource mode.")
        active: dict[int, list[tuple[str, Any]]] = {day: [] for day in days}
        harvest: dict[tuple[str, int], Any] = {(crop_id, day): 0.0 for crop_id in crops for day in days}
        for crop_id, sow in decisions:
            crop = crops[crop_id]
            for day in range(sow, sow + crop.grow_days):
                active[day].append((crop_id, m.sow[crop_id, sow]))
            # Rolling continuation may start before an already-defined event.
            # New cohorts that cross that event retain its known loss factor.
            factor = _batch_factor(scenario, crop_id, sow, sow + crop.grow_days)
            harvest[crop_id, sow + crop.grow_days] += m.sow[crop_id, sow] * crop.yield_kg_per_m2 * factor
        retired_by_crop: dict[str, float] = {}
        for i, batch in enumerate(carry):
            crop_id = batch["crop_id"]
            factor = _carried_batch_factor(scenario, crops[crop_id], batch, start)
            if factor <= EPS:
                m.keep[i].fix(0)
            for day in range(start, batch["harvest_day"]):
                active[day].append((crop_id, m.keep[i]))
            if batch["harvest_day"] in days:
                harvest[crop_id, batch["harvest_day"]] += (
                    m.keep[i] * crops[crop_id].yield_kg_per_m2 * factor)
        m.balance = pyo.ConstraintList()
        m.capacity = pyo.ConstraintList()
        m.nutrition = pyo.ConstraintList()
        m.reserves = pyo.ConstraintList()
        for day in days:
            crew, targets, water, power = conditions[day]
            water += relief.get("water_l_per_day", 0)
            power += relief.get("power_kwh_per_day", 0)
            daily_profiles = _profiles_for_day(config, day)
            reserve_profiles = _reserve_profiles(config, day)
            for f in profiles:
                opening = stocks.get(f, 0.0) if day == start else m.stock[f, day - 1]
                if rescue and rescue["mode"] == "food" and day == start and f in stored_foods:
                    opening += m.add_food[f]
                incoming = harvest.get((f, day), 0.0)
                m.balance.add(m.stock[f, day] == opening + incoming - m.eat[f, day] - m.waste[f, day])
                if f in stored_foods:
                    food = next(item for item in config.foods if item.id == f)
                    if _expired(food, day):
                        m.stock[f, day].fix(0)
                        m.eat[f, day].fix(0)
                    else:
                        m.waste[f, day].fix(0)
                else:
                    # No unvalidated long-term storage of freshly harvested produce.
                    m.stock[f, day].fix(0)
            area = sum((area for _, area in active[day]), 0 * m.eat[next(iter(profiles)), day])
            crop_water = sum((crops[c].water_l_per_m2_day * a for c, a in active[day]), 0 * area)
            crop_power = sum((crops[c].power_kwh_per_m2_day * a for c, a in active[day]), 0 * area)
            m.capacity.add(area <= _day_area_capacity(config, scenario, day))
            water_used[day] = crop_water + crew * config.crew_water_l_per_day - m.crew_water_gap[day]
            power_used[day] = crop_power
            m.capacity.add(water_used[day] <= water)
            m.capacity.add(crop_power <= power)
            # Delivered crop water cannot be obtained by reducing crew service
            # when that day's drinking requirement can be met by its capacity.
            if usable_stores.get("water_l") is None:
                m.crew_water_gap[day].fix(max(0.0, crew * config.crew_water_l_per_day - conditions[day][2]) if not rescue else 0)
            m.capacity.add(sum((m.eat[f, day] for f in crops),
                               0 * m.eat[next(iter(profiles)), day])
                           <= crew * config.max_fresh_kg_per_crew_day)
            if config.max_total_food_kg_per_crew_day > 0:
                m.capacity.add(sum(m.eat[f, day] for f in profiles) <= crew * config.max_total_food_kg_per_crew_day)
            for n, target in targets.items():
                supply = sum(m.eat[f, day] * daily_profiles[f].get(n, 0.0) for f in profiles)
                m.nutrition.add(supply + m.shortfall[n, day] >= target)
                if n in config.nutrient_upper_per_crew:
                    m.nutrition.add(supply <= crew * config.nutrient_upper_per_crew[n])
                stored = sum((m.stock[f, day] * profile.get(n, 0.0) for f, profile in reserve_profiles.items()), 0 * m.eat[next(iter(profiles)), day])
                m.reserves.add(stored + m.reserve_gap[n, day] >= config.reserve_days * target)
        # Finite stores constrain actual cumulative delivery, independently of
        # daily flow capacity. Any rescue resource is an explicit daily addition.
        if usable_stores.get("water_l") is not None:
            water_extra = relief.get("water_l_per_day", 0)
            for index, day in enumerate(days):
                m.capacity.add(sum(water_used[d] for d in days[:index + 1]) <= usable_stores["water_l"] + (index + 1) * water_extra)
        if usable_stores.get("energy_kwh") is not None:
            power_extra = relief.get("power_kwh_per_day", 0)
            for index, day in enumerate(days):
                m.capacity.add(sum(power_used[d] for d in days[:index + 1]) <= usable_stores["energy_kwh"] + (index + 1) * power_extra)
        # Unit-normalized nutrient slack prevents adding kcal, grams and mg.
        # Soft reserves allow an honest gap report when stock is inadequate.
        nutrition_penalty = sum(m.shortfall[n, day] / conditions[day][1][n]
                                for n in m.nutrients for day in days)
        reserve_penalty = sum(m.reserve_gap[n, day] / conditions[day][1][n]
                              for n in m.nutrients for day in days)
        operating_cost = sum(m.eat[f, day] * 0.01 for f in stored_foods for day in days)
        operating_cost += sum(m.sow[c, day] * (0.005 + crops[c].power_kwh_per_m2_day * 0.005)
                              for c, day in decisions)
        operating_cost += sum(m.waste[f, day] * 0.001 for f in profiles for day in days)
        # Retain viable existing crops unless capacity or useful scheduling calls for retirement.
        operating_cost += sum((carry[i]["area_m2"] - m.keep[i]) * 0.0001 for i in m.carry_batches)
        water_penalty = sum(m.crew_water_gap[day] / max(EPS, conditions[day][0] * config.crew_water_l_per_day) for day in days)
        m.objective = pyo.Objective(expr=primary_resource if rescue else 10000000 * water_penalty + 100000 * nutrition_penalty + 1000 * reserve_penalty + operating_cost)
        solver.options["time_limit"] = 8.0 if rescue else 30.0
        solver.options["threads"] = 1
        outcome = solver.solve(m, load_solutions=not bool(rescue))
        term = outcome.solver.termination_condition
        if rescue and term == TerminationCondition.infeasible:
            result.status = "infeasible"
            result.warnings = ["Targets cannot all be met using only this resource within its entered limit and the current food/crop assumptions."]
            return result
        if term not in (TerminationCondition.optimal, TerminationCondition.feasible, TerminationCondition.maxTimeLimit):
            result.warnings = [f"Planner returned {term}; inspect the input coefficients."]
            return result
        if rescue:
            solver.load_vars()
            primary_minimum = float(pyo.value(primary_resource))
            minimum_proven = term == TerminationCondition.optimal
            if minimum_proven:
                m.minimum_resource = pyo.Constraint(expr=primary_resource <= primary_minimum + 1e-7)
                m.objective.set_value(1000 * reserve_penalty + operating_cost)
                secondary = solver.solve(m, load_solutions=False)
                if secondary.solver.termination_condition in (TerminationCondition.optimal, TerminationCondition.feasible, TerminationCondition.maxTimeLimit):
                    try:
                        solver.load_vars()
                    except RuntimeError:
                        pass  # The already loaded primary solution remains a valid fallback.
            result.resource_additions = {"arrival_day": start, "mode": rescue["mode"], "limit": rescue["limit"],
                "minimum_proven": minimum_proven, "primary_minimum": primary_minimum if minimum_proven else None,
                "feasible_resource_amount": _clean(pyo.value(primary_resource)),
                "include_reserve": bool(rescue.get("include_reserve")),
                "food_kg": {f: _clean(pyo.value(m.add_food[f])) for f in sorted(stored_foods)} if rescue["mode"] == "food" else {},
                "water_l_per_day": _clean(pyo.value(m.add_resource)) if rescue["mode"] == "water" else 0,
                "power_kwh_per_day": _clean(pyo.value(m.add_resource)) if rescue["mode"] == "power" else 0}
        value = lambda expression: _clean(pyo.value(expression))
        remaining_water = usable_stores.get("water_l")
        remaining_energy = usable_stores.get("energy_kwh")
        for day in days:
            eats = {f: value(m.eat[f, day]) for f in profiles}
            remaining = {f: value(m.stock[f, day]) for f in profiles}
            result.consumption[day] = eats
            result.inventories[day] = remaining
            crop_water = sum(crops[c].water_l_per_m2_day * value(a) for c, a in active[day])
            crop_power = sum(crops[c].power_kwh_per_m2_day * value(a) for c, a in active[day])
            crew, _, available_water, _ = conditions[day]
            applied_relief = {key: value(amount) for key, amount in relief.items()}
            if rescue:
                applied_relief["arrival_day"] = start
            available_water += applied_relief.get("water_l_per_day", 0)
            crew_water = crew * config.crew_water_l_per_day
            row = _daily_row(config, scenario, day, eats, remaining,
                             crew_water - value(m.crew_water_gap[day]) + crop_water, crop_power,
                             sum(value(harvest[c, day]) for c in crops),
                             value(m.crew_water_gap[day]), 0.0,
                             sum(value(m.waste[f, day]) for f in profiles), applied_relief)
            row["area_m2"] = sum(value(a) for _, a in active[day])
            row["area_available_m2"] = _day_area_capacity(config, scenario, day)
            if remaining_water is not None:
                remaining_water = _clean(remaining_water + applied_relief.get("water_l_per_day", 0) - row["water_l"])
                row["water_remaining_l"] = remaining_water
            if remaining_energy is not None:
                remaining_energy = _clean(remaining_energy + applied_relief.get("power_kwh_per_day", 0) - row["power_kwh"])
                row["energy_remaining_kwh"] = remaining_energy
            result.daily.append(row)
        for crop_id, day in decisions:
            area = value(m.sow[crop_id, day])
            if area > EPS:
                factor = _batch_factor(scenario, crop_id, day, day + crops[crop_id].grow_days)
                result.planting.append(_planting_row(crops[crop_id], day, area, factor))
        for i, batch in enumerate(carry):
            retained = value(m.keep[i])
            factor = _carried_batch_factor(scenario, crops[batch["crop_id"]], batch, start)
            if retained > EPS:
                row = _planting_row(crops[batch["crop_id"]], batch["day"], retained, factor)
                row["retained_from_nominal"] = True
                result.planting.append(row)
            retired = batch["area_m2"] - retained
            if retired > 1e-4:
                crop_id = batch["crop_id"]
                retired_by_crop[crop_id] = retired_by_crop.get(crop_id, 0.0) + retired
        for crop_id, retired in retired_by_crop.items():
            result.warnings.append(f"Retired {retired:.2f} m² of active {crops[crop_id].name} after the event.")
        result.status = "optimal" if term == TerminationCondition.optimal else "feasible"
        _finish(config, scenario, result)
        return result
    except Exception as exc:
        result.status = "solver_error"
        result.warnings = [f"The planning solver failed: {type(exc).__name__}: {exc}"]
        return result


def _planting_row(crop, day, area, factor=1.0):
    return {"day": day, "crop_id": crop.id, "crop": crop.name, "area_m2": area,
            "harvest_day": day + crop.grow_days,
            "predicted_harvest_kg": area * crop.yield_kg_per_m2 * factor}


def _replay_fixed_plan(config: HabitatConfig, scenario: Scenario, nominal: PlanResult,
        relief=None, yield_factor=1.0, harvest_delay_days=0, *, start_day=None) -> PlanResult:
    boundary = scenario.event_day if start_day is None else start_day
    if isinstance(boundary, bool) or not isinstance(boundary, int) or boundary < 1:
        raise ValueError("Replay start day must be a positive integer.")
    result = PlanResult(label="Fixed baseline", status="simulated", planting=[dict(x) for x in nominal.planting])
    profiles, stocks, reserve = _catalogue(config)
    crops = {crop.id: crop for crop in config.crops}
    batches = []
    for batch in nominal.planting:
        crop = crops[batch["crop_id"]]
        factor = _carried_batch_factor(scenario, crop, batch, boundary)
        batches.append(dict(batch, loss_factor=factor, stress_factor=1.0, realized_factor=factor))
    remaining_water, remaining_energy = config.initial_water_l, config.initial_energy_kwh
    for batch in batches:
        if batch["harvest_day"] >= boundary:
            batch["harvest_day"] += harvest_delay_days
    for day in range(1, config.days + 1):
        if day < boundary:
            stocks = dict(nominal.inventories[day])
            result.consumption[day] = dict(nominal.consumption[day])
            result.inventories[day] = dict(stocks)
            result.daily.append(dict(nominal.daily[day - 1]))
            if remaining_water is not None:
                remaining_water = _clean(remaining_water - nominal.daily[day - 1]["water_l"])
            if remaining_energy is not None:
                remaining_energy = _clean(remaining_energy - nominal.daily[day - 1]["power_kwh"])
            continue
        crew, _, water, power = _day_conditions(config, scenario, day, relief)
        delivered_water, delivered_power = water, power
        if remaining_water is not None:
            remaining_water += (relief or {}).get("water_l_per_day", 0) if day >= (relief or {}).get("arrival_day", scenario.event_day) else 0
            delivered_water = min(water, remaining_water)
        if remaining_energy is not None:
            remaining_energy += (relief or {}).get("power_kwh_per_day", 0) if day >= (relief or {}).get("arrival_day", scenario.event_day) else 0
            delivered_power = min(power, remaining_energy)
        if relief and day == relief.get("arrival_day", boundary):
            for food_id, amount in relief.get("food_kg", {}).items():
                stocks[food_id] += amount
        expired_waste = 0.0
        for food in config.foods:
            if _expired(food, day):
                expired_waste += stocks[food.id]
                stocks[food.id] = 0.0
        active = [batch for batch in batches if batch["day"] <= day < batch["harvest_day"]]
        if day == boundary:
            for batch in batches:
                # Crop loss is determined by the original event-day cohort state.
                batch["loss_factor"] *= yield_factor
                batch["realized_factor"] = batch["loss_factor"] * batch["stress_factor"]
        living = [batch for batch in active if batch["realized_factor"] > EPS]
        requested_water = sum(crops[b["crop_id"]].water_l_per_m2_day * b["area_m2"] for b in living)
        requested_power = sum(crops[b["crop_id"]].power_kwh_per_m2_day * b["area_m2"] for b in living)
        crew_water = crew * config.crew_water_l_per_day
        crop_budget = max(0.0, delivered_water - crew_water)
        water_ratio = min(1.0, crop_budget / requested_water) if requested_water > EPS else 1.0
        power_ratio = min(1.0, delivered_power / requested_power) if requested_power > EPS else 1.0
        # A transparent synthetic stress proxy: worst delivered-resource ratio
        # encountered during growth bounds that cohort's eventual yield.
        for batch in living:
            batch["stress_factor"] = min(batch["stress_factor"], water_ratio, power_ratio)
            batch["realized_factor"] = batch["loss_factor"] * batch["stress_factor"]
        harvested = 0.0
        for batch in batches:
            if batch["harvest_day"] == day:
                amount = batch["area_m2"] * crops[batch["crop_id"]].yield_kg_per_m2 * batch["realized_factor"]
                stocks[batch["crop_id"]] += amount
                harvested += amount
        eats = {f: min(max(0.0, nominal.consumption[day].get(f, 0.0)), stocks[f]) for f in profiles}
        for f, amount in eats.items():
            stocks[f] = _clean(stocks[f] - amount)
        waste = sum(stocks[f] for f in crops) + expired_waste
        for f in profiles:
            if f in crops:
                stocks[f] = 0.0
        result.consumption[day] = eats
        result.inventories[day] = dict(stocks)
        row = _daily_row(config, scenario, day, eats, stocks,
                         min(crew_water, delivered_water) + min(requested_water, crop_budget),
                         min(requested_power, delivered_power), harvested,
                         max(0.0, crew_water + requested_water - delivered_water),
                         max(0.0, requested_power - delivered_power), waste, relief)
        row["area_m2"] = sum(b["area_m2"] for b in living)
        row["area_available_m2"] = _day_area_capacity(config, scenario, day)
        row["area_gap_m2"] = max(0.0, row["area_m2"] - row["area_available_m2"])
        row["capacity_gap"] = row["capacity_gap"] or row["area_gap_m2"] > EPS
        if remaining_water is not None:
            remaining_water = _clean(remaining_water - row["water_l"])
            row["water_remaining_l"] = remaining_water
        if remaining_energy is not None:
            remaining_energy = _clean(remaining_energy - row["power_kwh"])
            row["energy_remaining_kwh"] = remaining_energy
        result.daily.append(row)
    for index, batch in enumerate(batches):
        if batch["harvest_day"] >= boundary:
            # Preserve actual modeled resource losses if this baseline is used
            # as a later continuation source instead of refilling its cohort.
            result.planting[index]["predicted_harvest_kg"] = batch["area_m2"] * crops[batch["crop_id"]].yield_kg_per_m2 * batch["realized_factor"]
            result.planting[index]["harvest_day"] = batch["harvest_day"]
    _finish(config, scenario, result)
    if result.metrics["capacity_gap_days"]:
        result.warnings.append("Fixed-plan yield under resource stress uses a synthetic worst-resource-ratio proxy, not a validated crop-response model.")
    return result


def _daily_row(config, scenario, day, eats, stocks, water, power, harvest, water_gap, power_gap, waste, relief=None):
    profiles = _profiles_for_day(config, day)
    _, _, reserve = _catalogue(config)
    crew, targets, available_water, available_power = _day_conditions(config, scenario, day, relief)
    supplies = {n: sum(eats.get(f, 0) * profiles[f].get(n, 0) for f in profiles) for n in targets}
    deficits = {n: max(0.0, targets[n] - supplies[n]) for n in targets}
    coverage = {n: min(100.0, 100 * supplies[n] / targets[n]) for n in targets}
    reserve_profiles = _reserve_profiles(config, day)
    reserve_days = min(sum(stocks.get(f, 0) * profile.get(n, 0) for f, profile in reserve_profiles.items()) / targets[n]
                       for n in targets)
    upper_excess = {n: max(0.0, supplies[n] - crew * upper) for n, upper in config.nutrient_upper_per_crew.items()}
    row = {
        "day": day, "crew": crew, "water_l": _clean(water), "power_kwh": _clean(power),
        "water_available_l": available_water, "power_available_kwh": available_power,
        "harvest_kg": _clean(harvest), "reserve_kg": sum(stocks.get(f, 0) for f in reserve),
        "reserve_days_available": max(0.0, reserve_days),
        "reserve_gap_days": max(0.0, config.reserve_days - reserve_days),
        "nutrient_coverage_pct": min(coverage.values()), "shortfall_units": deficits,
        "shortfall_normalized": sum(deficits[n] / targets[n] for n in targets),
        "water_gap_l": _clean(water_gap), "power_gap_kwh": _clean(power_gap),
        "capacity_gap": water_gap > EPS or power_gap > EPS, "waste_kg": _clean(waste),
        "upper_excess_units": upper_excess,
        "food_mass_kg": sum(eats.values()),
        "food_mass_excess_kg": max(0.0, sum(eats.values()) - crew * config.max_total_food_kg_per_crew_day) if config.max_total_food_kg_per_crew_day else 0.0,
    }
    for n in targets:
        row[f"{n}_supply"] = supplies[n]
        row[f"{n}_target"] = targets[n]
        row[f"{n}_coverage_pct"] = coverage[n]
        row[f"{n}_shortfall"] = deficits[n]
    return row


def _finish(config: HabitatConfig, scenario: Scenario, result: PlanResult) -> None:
    if not result.daily:
        return
    # Recomputed after the adaptive suffix is joined to the common history.
    result.warnings = [warning for warning in result.warnings if not (
        warning.startswith("Tracked demo nutrient targets are unmet")
        or warning.startswith(f"The {config.reserve_days:g}-day stored-food reserve target")
        or warning.startswith("Requested resources exceed available capacity"))]
    rows = result.daily
    result.metrics = {
        "shortfall_days": sum(row["shortfall_normalized"] > 1e-5 for row in rows),
        "mean_coverage_pct": sum(row["nutrient_coverage_pct"] for row in rows) / len(rows),
        "min_coverage_pct": min(row["nutrient_coverage_pct"] for row in rows),
        "total_water_l": sum(row["water_l"] for row in rows),
        "total_power_kwh": sum(row["power_kwh"] for row in rows),
        "total_harvest_kg": sum(row["harvest_kg"] for row in rows),
        "final_reserve_kg": rows[-1]["reserve_kg"],
        "min_reserve_days": min(row["reserve_days_available"] for row in rows),
        "reserve_gap_days": sum(row["reserve_gap_days"] > 1e-5 for row in rows),
        "capacity_gap_days": sum(bool(row["capacity_gap"]) for row in rows),
        "total_shortfall_normalized": sum(row["shortfall_normalized"] for row in rows),
        "total_waste_kg": sum(row["waste_kg"] for row in rows),
        "upper_bound_excess_days": sum(any(x > EPS for x in row["upper_excess_units"].values()) for row in rows),
        "food_mass_excess_days": sum(row["food_mass_excess_kg"] > EPS for row in rows),
    }
    result.food_totals_kg = {f: sum(eats.get(f, 0.0) for eats in result.consumption.values())
                            for f in _catalogue(config)[0]}
    if any(result.metrics[key] for key in ("shortfall_days", "reserve_gap_days", "capacity_gap_days", "upper_bound_excess_days", "food_mass_excess_days")):
        result.status = "feasible_with_shortfalls"
    if result.metrics["shortfall_days"]:
        result.warnings.append(f"Tracked demo nutrient targets are unmet on {int(result.metrics['shortfall_days'])} day(s); the model does not claim nutritional adequacy.")
    if result.metrics["reserve_gap_days"]:
        result.warnings.append(f"The {config.reserve_days:g}-day stored-food reserve target is unmet on {int(result.metrics['reserve_gap_days'])} day(s).")
    if result.metrics["capacity_gap_days"]:
        result.warnings.append(f"Requested resources exceed available capacity on {int(result.metrics['capacity_gap_days'])} day(s).")
    if result.metrics["upper_bound_excess_days"]:
        result.warnings.append("The fixed allocation exceeds a configured nutrient upper bound; review before using this plan.")
    if result.metrics["food_mass_excess_days"]:
        result.warnings.append("The fixed allocation exceeds the configured daily food-mass limit.")
    result.warnings = list(dict.fromkeys(result.warnings))


def _clean(value: float) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError("The solver returned a nonfinite quantity.")
    return 0.0 if abs(number) < EPS else max(0.0, number)
