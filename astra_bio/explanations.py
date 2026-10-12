"""Explanations assembled from saved solver facts, with optional local selection.

Generative output may select known fact IDs; it cannot supply visible advice or
numbers, change a scenario, or mutate an allocation. No network by default.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .model import HabitatConfig, Scenario
from .planner import ComparisonResult, PlanResult


def _finite(value, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Nonfinite plan evidence: {name}")
    return result


def _fact(identifier: str, text: str, value, unit: str, references: list[str]) -> dict:
    return {"id": identifier, "text": text, "value": value, "unit": unit, "references": references}


def _observed(plan: PlanResult) -> dict:
    rows = plan.daily
    return {
        "days": len(rows),
        "shortfall_days": sum(_finite(r.get("shortfall_normalized", 0), "shortfall") > 1e-5 for r in rows),
        "reserve_gap_days": sum(_finite(r.get("reserve_gap_days", 0), "reserve gap") > 1e-5 for r in rows),
        "capacity_gap_days": sum(bool(r.get("capacity_gap", False)) for r in rows),
        "min_coverage_pct": min((_finite(r["nutrient_coverage_pct"], "coverage") for r in rows), default=0),
        "total_water_l": sum(_finite(r["water_l"], "water") for r in rows),
        "total_power_kwh": sum(_finite(r["power_kwh"], "power") for r in rows),
        "total_harvest_kg": sum(_finite(r["harvest_kg"], "harvest") for r in rows),
        "total_waste_kg": sum(_finite(r.get("waste_kg", 0), "waste") for r in rows),
    }


def explain_plan(plan: PlanResult, config: HabitatConfig) -> dict:
    """Recompute reported quantities from daily rows, rather than trusting deltas."""
    limitations = ["Coverage refers only to the nutrient targets and input coefficients in this saved model run.",
        "This model output does not establish astronaut health, dietary safety or habitat-scale biological performance.",
        "Fresh crop harvest is consumed or discarded on its harvest day; menu preference and cooking are not modeled."]
    if not config.input_provenance:
        limitations.append("The default input coefficients and crew targets are synthetic demonstration values.")
    else:
        limitations.append("Research preset provenance belongs to its individual inputs; simulation results are not measurements.")
    if not plan.daily:
        return {"headline": "No solved daily plan is available to explain.", "facts": [], "verified": True,
            "status": plan.status, "warnings": list(plan.warnings), "limitations": limitations, "source": "saved daily solver result"}
    actual = _observed(plan)
    facts = [
        _fact("plan.days", f"{plan.label} contains {actual['days']} simulated days.", actual["days"], "days", ["daily[].day"]),
        _fact("plan.shortfalls", f"Tracked nutrient targets are unmet on {actual['shortfall_days']} simulated days.", actual["shortfall_days"], "days", ["daily[].shortfall_normalized"]),
        _fact("plan.coverage", f"The lowest daily coverage of any tracked nutrient target is {actual['min_coverage_pct']:.1f}%.", actual["min_coverage_pct"], "%", ["daily[].nutrient_coverage_pct"]),
        _fact("plan.reserve", f"The configured stored-food reserve target is unmet on {actual['reserve_gap_days']} simulated days.", actual["reserve_gap_days"], "days", ["daily[].reserve_gap_days"]),
        _fact("plan.capacity", f"Requested water or crop power exceeds available capacity on {actual['capacity_gap_days']} simulated days.", actual["capacity_gap_days"], "days", ["daily[].capacity_gap"]),
        _fact("plan.water", f"Modeled crew and crop water use totals {actual['total_water_l']:.1f} L.", actual["total_water_l"], "L", ["daily[].water_l"]),
        _fact("plan.power", f"Modeled crop power use totals {actual['total_power_kwh']:.1f} kWh; this excludes laptop and unmodeled habitat loads.", actual["total_power_kwh"], "kWh", ["daily[].power_kwh"]),
        _fact("plan.harvest", f"Modeled harvest totals {actual['total_harvest_kg']:.2f} kg.", actual["total_harvest_kg"], "kg", ["daily[].harvest_kg"]),
    ]
    for nutrient in config.targets_per_crew:
        gaps = [(int(r["day"]), _finite(r.get(f"{nutrient}_shortfall", 0), f"{nutrient} gap")) for r in plan.daily]
        worst = max(gaps, key=lambda item: item[1])
        if worst[1] > 1e-6:
            unit = config.nutrient_units.get(nutrient, "configured units")
            facts.append(_fact(f"nutrient.{nutrient}.worst_gap", f"Largest recorded {nutrient.replace('_', ' ')} shortfall: {worst[1]:.2f} {unit} on day {worst[0]} for the whole crew.",
                {"day": worst[0], "shortfall": worst[1]}, unit, [f"daily[day={worst[0]}].{nutrient}_shortfall"]))
    mismatches = []
    for name, value in actual.items():
        if name in plan.metrics and not math.isclose(_finite(plan.metrics[name], name), value, rel_tol=1e-6, abs_tol=1e-5):
            mismatches.append(f"Saved metric {name} differs from daily rows; this explanation uses the daily evidence.")
    return {"headline": "Explanation from the saved daily plan.", "facts": facts, "verified": True,
        "status": plan.status, "warnings": list(dict.fromkeys([*plan.warnings, *mismatches])),
        "limitations": limitations, "source": "saved daily solver result", "observed_metrics": actual}


def explain_comparison(comparison: ComparisonResult, config: HabitatConfig, scenario: Scenario) -> dict:
    adaptive = explain_plan(comparison.adaptive, config)
    fixed = explain_plan(comparison.baseline, config)
    if not comparison.adaptive.daily or not comparison.baseline.daily:
        return {**adaptive, "headline": "Comparison has no complete daily evidence; solver status must be reviewed."}
    before, after = fixed["observed_metrics"], adaptive["observed_metrics"]
    facts = []
    daily_references = {"shortfall_days": "shortfall_normalized", "reserve_gap_days": "reserve_gap_days",
        "capacity_gap_days": "capacity_gap", "total_water_l": "water_l", "total_power_kwh": "power_kwh", "total_harvest_kg": "harvest_kg"}
    for key, name, unit in [("shortfall_days", "days with a tracked nutrient shortfall", "days"),
        ("reserve_gap_days", "days below the reserve target", "days"),
        ("capacity_gap_days", "days with a requested resource gap", "days"),
        ("total_water_l", "modeled water use", "L"), ("total_power_kwh", "modeled crop power use", "kWh"),
        ("total_harvest_kg", "modeled harvest", "kg")]:
        delta = after[key] - before[key]
        facts.append(_fact(f"comparison.{key}", f"Fixed versus adaptive {name}: {before[key]:.2f} → {after[key]:.2f} {unit} (change {delta:+.2f} {unit}).",
            {"fixed": before[key], "adaptive": after[key], "change": delta}, unit, [f"baseline.daily[].{daily_references[key]}", f"adaptive.daily[].{daily_references[key]}"]))
    earlier_fixed = [r for r in comparison.baseline.daily if r["day"] < scenario.event_day]
    earlier_adaptive = [r for r in comparison.adaptive.daily if r["day"] < scenario.event_day]
    shared = earlier_fixed == earlier_adaptive
    facts.append(_fact("comparison.history", f"Saved daily history before event day {scenario.event_day} {'matches' if shared else 'differs between'} the two policies.", shared,
        "boolean", ["baseline.daily[day<event_day]", "adaptive.daily[day<event_day]", "scenario.event_day"]))
    # Savings never imply nutritional adequacy; both directions are shown verbatim.
    return {**adaptive, "headline": "Fixed and adaptive policies compared using saved daily evidence.",
        "facts": facts + adaptive["facts"], "scenario_name": comparison.scenario_name,
        "warnings": list(dict.fromkeys([*fixed["warnings"], *adaptive["warnings"]]))}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local explanation requests cannot redirect to another endpoint.")


def _local_request(request: Request, timeout: float):
    # Bypass environment proxies and reject redirects to preserve local-only data.
    return build_opener(ProxyHandler({}), _NoRedirects()).open(request, timeout=timeout)


def explain_with_ollama(evidence: dict, *, enabled: bool = False, model: str = "llama3.2:3b",
                        base_url: str = "http://127.0.0.1:11434", timeout: float = 8) -> dict:
    """Optionally select known fact IDs locally; never expose invented LLM prose.

No daemon/model is installed or pulled. Invalid or unavailable responses use
the deterministic explanation. A remote host is rejected even when enabled.
"""
    facts = deepcopy(evidence.get("facts", []))
    fallback = {"mode": "deterministic", "verified": True,
        "narrative": "\n".join(f["text"] for f in facts[:8]), "selected_fact_ids": [f["id"] for f in facts[:8]]}
    if not enabled:
        return fallback
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return {**fallback, "fallback_reason": "Only a local loopback Ollama endpoint is permitted."}
    if not math.isfinite(timeout) or not 0 < timeout <= 15 or not re.fullmatch(r"[A-Za-z0-9./:_-]{1,100}", model):
        return {**fallback, "fallback_reason": "Invalid local model name or timeout."}
    if not facts:
        return fallback
    prompt = "Select the most useful 4-8 fact IDs from this verified evidence. Return JSON only: {\"selected_fact_ids\":[...]}. Do not invent IDs, numbers, advice or text. Evidence:\n" + json.dumps(facts, allow_nan=False)
    body = json.dumps({"model": model, "stream": False, "format": "json", "prompt": prompt,
        "options": {"temperature": 0, "num_predict": 160}}).encode()
    try:
        request = Request(base_url.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with _local_request(request, timeout=timeout) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError("Local model response exceeds the bounded response size.")
        raw = json.loads(payload)
        chosen = json.loads(raw["response"])["selected_fact_ids"]
        known = {fact["id"]: fact for fact in facts}
        if not isinstance(chosen, list) or not 1 <= len(chosen) <= 8 or any(not isinstance(identifier, str) or identifier not in known for identifier in chosen) or len(set(chosen)) != len(chosen):
            raise ValueError("Local model selected invalid fact IDs.")
        return {"mode": "ollama_fact_selection", "verified": True, "model": model,
            "narrative": "\n".join(known[identifier]["text"] for identifier in chosen), "selected_fact_ids": chosen,
            "note": "Ollama chose fact order; visible statements come from verified saved evidence."}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {**fallback, "fallback_reason": f"Local Ollama unavailable or invalid ({type(exc).__name__}); verified explanation retained."}
