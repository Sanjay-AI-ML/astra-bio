"""Explicit resource rescue and fixed-policy stress tests; never hardware control."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite

from .model import HabitatConfig, Scenario
from .planner import PlanResult, _finish, _remaining_resource_stocks, _replay_fixed_plan, _solve_lp, run_comparison


@dataclass(frozen=True)
class RecoveryOptions:
    food_limit_kg: float = 1000
    water_limit_l_per_day: float = 100
    power_limit_kwh_per_day: float = 20
    include_reserve: bool = False
    lower_yield_factor: float = .8
    harvest_delay_days: int = 3

    def validate(self):
        bounds = {"food_limit_kg": (0, 10000), "water_limit_l_per_day": (0, 1000),
            "power_limit_kwh_per_day": (0, 100), "lower_yield_factor": (0, 1)}
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or not low <= value <= high:
                raise ValueError(f"Recovery {key} must be a finite number between {low} and {high}.")
        if type(self.include_reserve) is not bool:
            raise ValueError("Recovery include_reserve must be a boolean.")
        if type(self.harvest_delay_days) is not int or not 0 <= self.harvest_delay_days <= 30:
            raise ValueError("Harvest delay must be a whole number between zero and 30 days.")


def summarize(plan: PlanResult, event_day: int, include_reserve=False) -> dict:
    rows = [row for row in plan.daily if row["day"] >= event_day]
    if not rows:
        return {"available": False, "meets_targets": False, "status": plan.status}
    target_gaps = [row for row in rows if row["shortfall_normalized"] > 1e-5]
    resource_gaps = [row for row in rows if row["capacity_gap"]]
    reserve_gaps = [row for row in rows if row["reserve_gap_days"] > 1e-5]
    upper_gaps = [row for row in rows if any(v > 1e-6 for v in row.get("upper_excess_units", {}).values())]
    mass_gaps = [row for row in rows if row.get("food_mass_excess_kg", 0) > 1e-6]
    return {"available": True, "status": plan.status, "days_evaluated": len(rows),
        "meets_targets": not (target_gaps or resource_gaps or upper_gaps or mass_gaps or (include_reserve and reserve_gaps)),
        "target_gap_days": len(target_gaps), "resource_gap_days": len(resource_gaps),
        "reserve_gap_days": len(reserve_gaps), "upper_bound_gap_days": len(upper_gaps), "food_mass_gap_days": len(mass_gaps),
        "first_target_gap_day": target_gaps[0]["day"] if target_gaps else None,
        "total_shortfall_normalized": sum(row["shortfall_normalized"] for row in rows),
        "minimum_coverage_pct": min(row["nutrient_coverage_pct"] for row in rows),
        "minimum_reserve_days": min(row["reserve_days_available"] for row in rows),
        "water_l": sum(row["water_l"] for row in rows), "power_kwh": sum(row["power_kwh"] for row in rows),
        "harvest_kg": sum(row["harvest_kg"] for row in rows),
        "nutrient_shortfall_units": {n: sum(row.get(n + "_shortfall", 0) for row in rows)
            for n in rows[0]["shortfall_units"]}}


def _join_history(config, scenario, reference, suffix, *, start_day=None):
    if not suffix.daily:
        return suffix
    start = scenario.event_day if start_day is None else start_day
    suffix.daily = [dict(row) for row in reference.daily if row["day"] < start] + suffix.daily
    suffix.consumption = {**{d: dict(v) for d, v in reference.consumption.items() if d < start}, **suffix.consumption}
    suffix.inventories = {**{d: dict(v) for d, v in reference.inventories.items() if d < start}, **suffix.inventories}
    suffix.planting = [dict(batch) for batch in reference.planting if batch["day"] < start and batch["harvest_day"] < start] + suffix.planting
    _finish(config, scenario, suffix)
    return suffix


def _stress_cases(options):
    cases = [{"id": "submitted", "name": "Submitted assumptions", "yield_factor": 1, "harvest_delay_days": 0}]
    if options.lower_yield_factor < 1:
        cases.append({"id": "lower_yield", "name": "Lower remaining harvest yields", "yield_factor": options.lower_yield_factor, "harvest_delay_days": 0})
    if options.harvest_delay_days:
        cases.append({"id": "delayed", "name": "Delayed remaining harvests", "yield_factor": 1, "harvest_delay_days": options.harvest_delay_days})
    if options.lower_yield_factor < 1 and options.harvest_delay_days:
        cases.append({"id": "combined", "name": "Lower yields and delayed harvests", "yield_factor": options.lower_yield_factor, "harvest_delay_days": options.harvest_delay_days})
    return cases


def _candidate(config, scenario, plan, identifier, title, options, *, start_day=None):
    start = scenario.event_day if start_day is None else start_day
    summary = summarize(plan, start, options.include_reserve)
    candidate = {"id": identifier, "title": title, "status": plan.status, "summary": summary,
        "resources": plan.resource_additions, "warnings": plan.warnings, "stress_tests": [],
        "plan": plan.as_dict() if plan.daily else None}
    if not summary["available"]:
        return candidate
    for case in _stress_cases(options):
        replay = _replay_fixed_plan(config, scenario, plan, plan.resource_additions,
            case["yield_factor"], case["harvest_delay_days"], start_day=start)
        candidate["stress_tests"].append({**case, "summary": summarize(replay, start, options.include_reserve)})
    candidate["cases_passed"] = sum(case["summary"]["meets_targets"] for case in candidate["stress_tests"])
    candidate["cases_tested"] = len(candidate["stress_tests"])
    candidate["worst_case_target_gap_days"] = max(case["summary"]["target_gap_days"] for case in candidate["stress_tests"])
    candidate["worst_case_shortfall_normalized"] = max(case["summary"]["total_shortfall_normalized"] for case in candidate["stress_tests"])
    return candidate


def analyze_recovery(config: HabitatConfig, scenario: Scenario, options=None, comparison=None, *, start_day=None) -> dict:
    options = options or RecoveryOptions()
    config.validate()
    scenario.validate(config)
    options.validate()
    if config.days > 120 or len(config.crops) > 12 or len(config.foods) > 20:
        raise ValueError("Recovery analysis supports up to 120 days, 12 crops and 20 stored food forms.")
    start = scenario.event_day if start_day is None else start_day
    if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= config.days:
        raise ValueError("Choose a disruption day within the mission before comparing recovery options.")
    comparison = comparison or run_comparison(config, scenario)
    reference = comparison.baseline
    inputs = {"config": asdict(config), "scenario": asdict(scenario), "options": asdict(options)}
    if start_day is not None:
        inputs["start_day"] = start_day
    report = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "inputs": inputs, "event_day": start, "remaining_days": config.days - start + 1,
        "tracked_nutrients": list(config.targets_per_crew), "include_reserve": options.include_reserve,
        "baseline": summarize(reference, start, options.include_reserve), "candidates": [],
        "automatic_action": False, "inventory_updated": False,
        "ranking_basis": "Remaining-mission nutrient/resource feasibility, then worst tested normalized nutrient shortage, then passed cases. Different resource units are not compared as costs.",
        "limitations": ["Results cover only the entered nutrient targets and coefficients; meeting them does not establish complete nutritional adequacy.",
            "Stress cases are user-entered assumptions, not probabilities, measured crop responses or confidence intervals. Crop resource-stress replay uses the existing synthetic ratio proxy.",
            "All options share history before the recovery start day. Each stress test holds planting and requested meals fixed; no reoptimization occurs inside the test.",
            "Extra food arrives on the recovery start day and inherits each stored form's declared composition, age, expiry and nutrient-retention assumptions; it is not a fresh-food resupply model.",
            "Extra water and power are uniform daily allowances from the recovery start day through mission end. Only one resource type is added per rescue option.",
            "A minimum is claimed only after an optimal solve; failure within a limit does not prove that no larger or combined resource intervention could work.",
            "These are proposed plans. Inventory, saved comparisons, sensors and equipment are not changed."]}
    if not reference.daily or not comparison.adaptive.daily:
        report["status"] = "unavailable"
        report["warnings"] = reference.warnings + comparison.adaptive.warnings
        return report
    opening = reference.inventories.get(start - 1, {})
    carry = [dict(batch) for batch in reference.planting if batch["day"] < start <= batch["harvest_day"]]
    adaptive = replace(comparison.adaptive, label="Replan with existing resources", resource_additions={})
    report["candidates"].append(_candidate(config, scenario, adaptive, "replan", adaptive.label, options, start_day=start))
    already_feasible = summarize(adaptive, start, options.include_reserve)["meets_targets"]
    for mode, limit, title in [("food", options.food_limit_kg, "Add stored food"),
            ("water", options.water_limit_l_per_day, "Add daily water"), ("power", options.power_limit_kwh_per_day, "Add daily electricity")]:
        if already_feasible:
            plan = replace(adaptive, label=title, resource_additions={"mode": mode, "arrival_day": start,
                "minimum_proven": True, "primary_minimum": 0, "feasible_resource_amount": 0, "food_kg": {}, "water_l_per_day": 0, "power_kwh_per_day": 0,
                "limit": limit, "include_reserve": options.include_reserve, "not_needed": True})
        elif mode == "food" and not config.foods:
            plan = PlanResult(label=title, status="unavailable", warnings=["No stored food forms are configured for an extra-food option."])
        else:
            plan = _solve_lp(config, scenario, start, opening, carry, title,
                rescue={"mode": mode, "limit": limit, "include_reserve": options.include_reserve},
                resource_stocks=_remaining_resource_stocks(config, reference.daily[:start - 1]))
            plan = _join_history(config, scenario, reference, plan, start_day=start)
        report["candidates"].append(_candidate(config, scenario, plan, mode, title, options, start_day=start))
    available = [candidate for candidate in report["candidates"] if candidate["summary"]["available"]]
    available.sort(key=lambda candidate: (not candidate["summary"]["meets_targets"],
        candidate.get("worst_case_shortfall_normalized", float("inf")), -candidate.get("cases_passed", 0),
        candidate["id"] != "replan"))
    for rank, candidate in enumerate(available, 1):
        candidate["rank"] = rank
    report["candidates"] = available + [c for c in report["candidates"] if not c["summary"]["available"]]
    report["status"] = "calculated"
    report["recommended_candidate_id"] = available[0]["id"] if available else None
    return report
