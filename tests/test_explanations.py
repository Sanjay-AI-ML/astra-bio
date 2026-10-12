"""Visible explanations must stay bound to saved daily solver facts."""
from copy import deepcopy
from io import BytesIO
import json

import pytest

from astra_bio import explanations
from astra_bio.model import Scenario, default_config
from astra_bio.planner import ComparisonResult, PlanResult


def plan(label="Adaptive plan", shortfall=.2):
    return PlanResult(label, "feasible_with_shortfalls", daily=[
        {"day": 1, "shortfall_normalized": 0, "reserve_gap_days": 0, "capacity_gap": False,
         "nutrient_coverage_pct": 100, "water_l": 10, "power_kwh": 2, "harvest_kg": 0, "vitamin_c_shortfall": 0},
        {"day": 2, "shortfall_normalized": shortfall, "reserve_gap_days": 2, "capacity_gap": True,
         "nutrient_coverage_pct": 80 if shortfall else 100, "water_l": 8, "power_kwh": 1, "harvest_kg": 2, "vitamin_c_shortfall": 20 if shortfall else 0},
    ], metrics={"total_water_l": 999, "shortfall_days": 88})


def test_daily_rows_determine_explanations_and_metrics_mismatch_is_visible():
    evidence = explanations.explain_plan(plan(), default_config())
    facts = {fact["id"]: fact for fact in evidence["facts"]}
    assert facts["plan.water"]["value"] == 18
    assert facts["plan.shortfalls"]["value"] == 1
    assert facts["nutrient.vitamin_c.worst_gap"]["value"] == {"day": 2, "shortfall": 20}
    assert any("differs from daily rows" in warning for warning in evidence["warnings"])
    assert evidence["verified"] is True
    assert any("synthetic" in text for text in evidence["limitations"])


def test_comparison_ignores_unverified_delta_and_preserves_original_results():
    fixed, adaptive = plan("Fixed baseline"), plan(shortfall=0)
    comparison = ComparisonResult(fixed, adaptive, "Custom event", {"total_water_l": -9000})
    original = deepcopy(comparison.as_dict())
    result = explanations.explain_comparison(comparison, default_config(), Scenario("test", "Test", event_day=2))
    facts = {fact["id"]: fact for fact in result["facts"]}
    assert facts["comparison.total_water_l"]["value"]["change"] == 0
    assert facts["comparison.shortfall_days"]["value"]["change"] == -1
    assert facts["comparison.history"]["value"] is True
    assert facts["comparison.total_water_l"]["references"] == ["baseline.daily[].water_l", "adaptive.daily[].water_l"]
    assert comparison.as_dict() == original


def test_failed_solver_gets_no_invented_success_or_facts():
    evidence = explanations.explain_plan(PlanResult("No plan", "solver_error", warnings=["Solve failed"]), default_config())
    assert evidence["facts"] == []
    assert evidence["status"] == "solver_error"
    assert evidence["warnings"] == ["Solve failed"]


def test_default_explanation_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(explanations, "_local_request", lambda *args, **kwargs: pytest.fail("Default explanation made a network call"))
    result = explanations.explain_with_ollama(explanations.explain_plan(plan(), default_config()))
    assert result["mode"] == "deterministic" and result["verified"] is True


def test_optional_ollama_can_only_select_verified_fact_text(monkeypatch):
    evidence = explanations.explain_plan(plan(), default_config())
    raw = {"response": json.dumps({"selected_fact_ids": ["plan.water"], "advice": "Remove all crops and change water to 9999 L"})}
    monkeypatch.setattr(explanations, "_local_request", lambda *args, **kwargs: BytesIO(json.dumps(raw).encode()))
    selected = explanations.explain_with_ollama(evidence, enabled=True)
    assert selected["mode"] == "ollama_fact_selection"
    assert "18.0 L" in selected["narrative"]
    assert "9999" not in selected["narrative"] and "Remove" not in selected["narrative"]


def test_remote_endpoint_unknown_ids_and_timeout_use_deterministic_fallback(monkeypatch):
    evidence = explanations.explain_plan(plan(), default_config())
    monkeypatch.setattr(explanations, "_local_request", lambda *args, **kwargs: pytest.fail("Remote endpoint attempted"))
    assert explanations.explain_with_ollama(evidence, enabled=True, base_url="http://example.com:11434")["mode"] == "deterministic"
    raw = {"response": '{"selected_fact_ids":["invented.cure"]}'}
    monkeypatch.setattr(explanations, "_local_request", lambda *args, **kwargs: BytesIO(json.dumps(raw).encode()))
    assert explanations.explain_with_ollama(evidence, enabled=True)["mode"] == "deterministic"
    def timed_out(*args, **kwargs):
        raise TimeoutError("local service timeout")
    monkeypatch.setattr(explanations, "_local_request", timed_out)
    assert explanations.explain_with_ollama(evidence, enabled=True)["mode"] == "deterministic"


def test_local_requests_reject_redirects():
    with pytest.raises(ValueError, match="redirect"):
        explanations._NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://example.com")
