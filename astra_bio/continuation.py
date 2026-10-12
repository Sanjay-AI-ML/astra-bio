"""Reviewed rolling replans from saved food, resource and growing-cohort state.

Elapsed mission rows are frozen. Camera or blood values never become nutrient
targets, food mass or crop loss automatically.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import isfinite

from .model import HabitatConfig, Scenario, _nonnegative
from .planner import (ComparisonResult, PlanResult, _day_conditions, _finish,
                      _remaining_resource_stocks, _replay_fixed_plan, _solve_lp)


def _reviewed_profiles(profiles, config):
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Provide the complete reviewed crew roster, including retained crew members.")
    seen = set()
    totals = {nutrient: 0.0 for nutrient in config.targets_per_crew}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Each reviewed crew profile must be an object.")
        if profile.get("targets_reviewed") is not True:
            raise ValueError("Review each crew member's planning targets before applying a mission change.")
        identifier, name, targets = profile.get("profile_id"), profile.get("name"), profile.get("targets")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ValueError("Reviewed crew identifiers must be nonempty and unique.")
        seen.add(identifier)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each reviewed crew member needs a name.")
        if not isinstance(targets, dict) or any(nutrient not in targets for nutrient in totals):
            raise ValueError("Every reviewed member needs all tracked nutrient targets.")
        for nutrient in totals:
            target = targets[nutrient]
            _nonnegative(target, f"Reviewed target {nutrient}")
            if target == 0:
                raise ValueError("Reviewed nutrient targets must be positive.")
            if target > config.nutrient_upper_per_crew.get(nutrient, float("inf")):
                raise ValueError(f"Upper bound for {nutrient} must meet or exceed each reviewed target.")
            totals[nutrient] += target
    return copy.deepcopy(profiles), {n: total / len(profiles) for n, total in totals.items()}


def continue_plan(config: HabitatConfig, scenario: Scenario, source: PlanResult,
                  through_day: int, target_factors: dict[str, float] | None = None,
                  *, mission_change: dict | None = None
                  ) -> tuple[HabitatConfig, ComparisonResult, dict]:
    """Replan tomorrow onward without restoring initial stock or growing time.

    Mission change accepts a complete reviewed crew_profiles roster OR
    crew_count, and optional absolute water/power delivery budgets, area and
    reason. replace_future_crew_changes explicitly supersedes pending roster
    changes without cancelling unrelated events. Individual targets are summed
    for the crew. Aggregate optimization
    does not promise those nutrients were distributed to each individual.
    """
    config.validate()
    scenario.validate(config)
    if isinstance(through_day, bool) or not isinstance(through_day, int) or not 1 <= through_day < config.days:
        raise ValueError("Continue after a completed simulation day before the mission's final day.")
    if not source.daily or [row.get("day") for row in source.daily] != list(range(1, config.days + 1)):
        raise ValueError("Continuation requires a complete saved simulation.")
    if source.status in {"solver_unavailable", "solver_error", "infeasible"}:
        raise ValueError("Continuation requires a completed feasible simulation.")
    factors = {} if target_factors is None else target_factors
    if not isinstance(factors, dict):
        raise ValueError("Future nutrient target factors must be an object.")
    for nutrient, factor in factors.items():
        if nutrient not in config.targets_per_crew:
            raise ValueError(f"Unknown nutrient target: {nutrient}.")
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not isfinite(factor) or not 0 < factor <= 5:
            raise ValueError("Future nutrient target factors must be positive and at most five.")
    change = {} if mission_change is None else mission_change
    allowed = {"crew_profiles", "crew_count", "water_budget_l_per_day", "power_budget_kwh_per_day", "area_m2", "reason",
               "replace_future_crew_changes"}
    if not isinstance(change, dict) or set(change) - allowed:
        raise ValueError("Mission change must contain only reviewed crew, resource capacity, area or reason fields.")
    if "crew_profiles" in change and "crew_count" in change:
        raise ValueError("Provide a full crew roster or a crew count, not both.")
    if "crew_profiles" in change and factors:
        raise ValueError("Use reviewed individual targets or target multipliers, not both.")
    replace_future_crew = change.get("replace_future_crew_changes", False)
    if not isinstance(replace_future_crew, bool):
        raise ValueError("Replacing pending crew changes must be a boolean.")
    if "replace_future_crew_changes" in change and not {"crew_profiles", "crew_count"} & set(change):
        raise ValueError("Replacing pending crew changes requires a reviewed roster or crew count.")
    start = through_day + 1
    event = {"day": start}
    profiles = None
    if "crew_profiles" in change:
        if isinstance(change["crew_profiles"], list) and len(change["crew_profiles"]) > 12:
            raise ValueError("Local planning limit: at most 12 crew.")
        profiles, mean_targets = _reviewed_profiles(change["crew_profiles"], config)
        event.update(crew=len(profiles), targets_per_crew=mean_targets, crew_profiles=profiles)
    elif "crew_count" in change:
        count = change["crew_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 12:
            raise ValueError("Reviewed crew count must be a whole number between one and twelve.")
        event["crew"] = count
    for key in ("water_budget_l_per_day", "power_budget_kwh_per_day", "area_m2", "reason"):
        if key in change:
            event[key] = copy.deepcopy(change[key])
    pending_scenario_crew_cancelled = bool(replace_future_crew and scenario.extra_crew
                                           and scenario.event_day >= start)
    if pending_scenario_crew_cancelled:
        event["cancel_scenario_crew"] = True
    events = copy.deepcopy(config.planning_events)
    superseded_crew_event_days = []
    if replace_future_crew:
        retained = []
        for pending in events:
            if pending["day"] >= start:
                if "crew" in pending or "crew_profiles" in pending:
                    superseded_crew_event_days.append(pending["day"])
                # Mean targets attached to a superseded roster no longer
                # describe the replacement crew. Independent target changes,
                # resource capacity and cancellation markers remain intact.
                if "crew_profiles" in pending:
                    pending.pop("targets_per_crew", None)
                pending.pop("crew", None)
                pending.pop("crew_profiles", None)
                if not set(pending) - {"day", "reason"}:
                    continue
            retained.append(pending)
        events = retained
    if factors:
        # Derive multipliers from retained conditions, so a cancelled future
        # roster's mean requirements cannot leak into a count-only reset.
        factor_config = replace(config, planning_events=events + [event])
        crew, totals, _, _ = _day_conditions(factor_config, scenario, start)
        event["targets_per_crew"] = {n: total / crew * factors.get(n, 1.0) for n, total in totals.items()}
    provenance = copy.deepcopy(config.input_provenance)
    provenance["simulation_continuation"] = {
        "through_day": through_day, "target_factors": dict(factors), "mission_change": copy.deepcopy(event),
        "replace_future_crew_changes": replace_future_crew,
        "scope": "Reviewed future inputs; saved simulated inventories/cohorts. No automatic camera/blood-to-target conversion.",
    }
    if len(event) > 1:
        events.append(event)
    updated = replace(config, planning_events=events, input_provenance=provenance)
    updated.validate()
    if any(_day_conditions(updated, scenario, d)[0] > 12 for d in range(start, config.days + 1)):
        raise ValueError("Local planning limit: at most 12 crew on any mission day, including announced future arrivals.")
    food_ids = {f.id for f in config.foods} | {c.id for c in config.crops}
    opening = source.inventories.get(through_day)
    if not isinstance(opening, dict) or set(opening) != food_ids:
        raise ValueError("Saved end-of-day inventory is missing or does not match the food catalogue.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0 for v in opening.values()):
        raise ValueError("Saved inventory must contain finite nonnegative quantities.")
    resource_opening = _remaining_resource_stocks(updated, source.daily[:through_day])
    carry = [copy.deepcopy(b) for b in source.planting if b["day"] < start <= b["harvest_day"]]
    adaptive = _solve_lp(updated, scenario, start, dict(opening), carry, "Continued adaptive plan", resource_stocks=resource_opening)
    baseline = _replay_fixed_plan(updated, scenario, source, start_day=start)
    baseline.label = "Previous schedule at reviewed future conditions"
    if adaptive.daily:
        adaptive.daily = copy.deepcopy(source.daily[:through_day]) + adaptive.daily
        adaptive.consumption = {**{d: copy.deepcopy(v) for d, v in source.consumption.items() if d <= through_day}, **adaptive.consumption}
        adaptive.inventories = {**{d: copy.deepcopy(v) for d, v in source.inventories.items() if d <= through_day}, **adaptive.inventories}
        historical = [copy.deepcopy(b) for b in source.planting if b["harvest_day"] < start]
        adaptive.planting = historical + adaptive.planting
        _finish(updated, scenario, adaptive)
    delta = {key: adaptive.metrics[key] - baseline.metrics[key] for key in set(adaptive.metrics) & set(baseline.metrics)}
    details = {"through_day": through_day, "next_day": start, "target_factors": dict(factors),
        "mission_change": copy.deepcopy(event), "planning_events": copy.deepcopy(events),
        "replace_future_crew_changes": replace_future_crew,
        "superseded_crew_event_days": sorted(set(superseded_crew_event_days)),
        "pending_scenario_crew_cancelled": pending_scenario_crew_cancelled,
        "opening_stocks_kg": dict(opening), "remaining_resource_stocks": resource_opening,
        "growing_cohorts_at_boundary": carry, "historical_targets_preserved": True,
        "historical_source_plantings": copy.deepcopy(source.planting),
        "comparison_scope": "Previous future schedule versus a new schedule with identical boundary inventories/cohorts and reviewed future inputs; elapsed days frozen.",
        "resource_scope": "Finite usable stores only when configured; daily flow capacity is not a reservoir. No water recycling, energy regeneration or implicit resupply is modeled.",
        "crew_target_scope": "Summed reviewed targets constrain crew totals; individual meal allocation and iron treatment are not modeled.",
        "simulation_only": True}
    if profiles is not None:
        details["crew_profiles"] = profiles
    if "crew_count" in change:
        details["crew_target_scope"] = "Count-only change uses existing average planning targets; added individuals' requirements remain unspecified."
    return updated, ComparisonResult(baseline, adaptive, scenario.name, delta), details
