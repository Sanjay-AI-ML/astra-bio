"""Optional AI ordering of verified, anonymous nutrition facts.

The provider never supplies visible free-text medical advice or new quantities.
No request is made until the operator submits a server-generated evidence ID.
"""
from collections import OrderedDict
from copy import deepcopy
import json
import secrets
import threading
import time
from urllib.request import Request, urlopen

from .plant_overview import gemini_config

_CACHE = OrderedDict()
_LOCK = threading.Lock()
_SLOT = threading.BoundedSemaphore(1)
TTL_SECONDS = 900
MAX_REPORTS = 32
SCOPE = "AI can order verified nutrition facts; it cannot diagnose illness, set clinical targets, prescribe supplements or change the mission."


def guidance_ai_status():
    key, _ = gemini_config()
    return {"available": bool(key and not key.startswith("REPLACE_")), "provider": "gemini",
        "transmission": "Only anonymous computed nutrition facts are submitted after clicking Explain with Gemini; names and raw laboratory or vital readings are excluded."}


def remember_guidance(report):
    token = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _LOCK:
        for key in list(_CACHE):
            if now - _CACHE[key][0] > TTL_SECONDS:
                del _CACHE[key]
        _CACHE[token] = (now, deepcopy(report))
        while len(_CACHE) > MAX_REPORTS:
            _CACHE.popitem(last=False)
    return token


def _recall(token, profile_id):
    if not isinstance(token, str) or not 16 <= len(token) <= 100:
        raise ValueError("Refresh the astronaut analysis before requesting AI explanation.")
    if not isinstance(profile_id, str) or not profile_id or len(profile_id) > 200:
        raise ValueError("Choose a valid astronaut from this analysis.")
    with _LOCK:
        record = _CACHE.get(token)
        if not record or time.monotonic() - record[0] > TTL_SECONDS:
            _CACHE.pop(token, None)
            raise ValueError("Analysis expired or the backend restarted. Refresh the analysis and try again.")
        report = deepcopy(record[1])
    member = next((m for m in report["members"] if m["profile_id"] == profile_id), None)
    if member is None:
        raise ValueError("This astronaut does not belong to the submitted analysis.")
    return report, member


def _anonymous_facts(report, member):
    # Rebuild from typed quantities and pinned food names rather than accepting
    # user narrative, names, labels, identifiers or raw measurement values.
    from .nutrition import UNITS, load_compositions
    labels = {"energy": "Energy", "protein": "Protein", "vitamin_c": "Vitamin C"}
    facts = [{"id": "scope", "text": "Only energy, protein and vitamin C intake are tracked; this comparison does not establish nutritional deficiency."},
        {"id": "logs", "text": "Recorded intake is " + ("complete for this day." if member["log_status"] == "complete" else "incomplete or missing; a daily intake shortage is not established.")},
        {"id": "targets", "text": "Targets are " + ("operator-reviewed planning inputs." if member["targets_reviewed"] else "unreviewed provided inputs; review them before using this as intake guidance.")}]
    if report.get("sample_only"):
        facts.append({"id": "sample", "text": "This is a fictional crew demonstration, not measured astronaut health data."})
    if report.get("demo_intake"):
        next(f for f in facts if f["id"] == "targets")["text"] = "Targets are illustrative inputs for this dummy intake comparison; no clinical requirement or prescription is established."
    if member.get("health_alerts"):
        # Keep medical review mandatory, without sharing the measurement or its
        # identity. Actual urgent message remains independently on the local UI.
        facts.append({"id": "health_review", "text": "A separate recorded health comparison needs crew medical review; nutrition calculations do not set its treatment."})
    for row in member["nutrients"]:
        nutrient = row["nutrient"]
        if nutrient not in UNITS:
            continue
        target, intake, gap = row.get("target"), row.get("intake"), row.get("gap")
        text = f"{labels[nutrient]} target: {target:g} {UNITS[nutrient]}." if isinstance(target, (int, float)) else f"{labels[nutrient]} target is unknown."
        if isinstance(intake, (int, float)):
            text += f" Logged intake: {intake:.2f} {UNITS[nutrient]}."
        else:
            text += " Logged intake is unknown."
        if isinstance(gap, (int, float)):
            text += f" Remaining recorded daily gap: {gap:.2f} {UNITS[nutrient]}."
        facts.append({"id": f"nutrient.{nutrient}", "text": text})
    catalog = load_compositions()
    for index, food in enumerate(member.get("food_options", [])[:3]):
        reference = catalog.get(food.get("food_key"))
        if not reference:
            continue
        grams = food.get("reference_grams")
        if not isinstance(grams, (int, float)):
            continue
        parts = [f"{amount:.2f} {UNITS[n]} {labels[n].lower()}" for n, amount in food.get("nutrients", {}).items()
            if n in UNITS and isinstance(amount, (int, float))]
        text = f"Example only: {grams:g} g of {reference.name} ({reference.food_form}) contributes " + ", ".join(parts) + "."
        text += " This is a single-food comparison, not an allocated meal or instruction to consume it."
        facts.append({"id": f"food.{index}", "text": text})
    return facts


def explain_guidance(token, profile_id):
    report, member = _recall(token, profile_id)
    facts = _anonymous_facts(report, member)
    allowed = {f["id"]: f for f in facts}
    mandatory = [f["id"] for f in facts if f["id"] in {"scope", "logs", "targets", "sample", "health_review"}]
    local = {"mode": "local_evidence", "summary": [f["text"] for f in facts], "scope": SCOPE,
        "provider": None, "submitted_to_provider": False}
    key, model = gemini_config()
    if not guidance_ai_status()["available"]:
        return {**local, "reason": "Gemini is not configured; the calculated local guidance remains available."}
    if not _SLOT.acquire(blocking=False):
        return {**local, "reason": "AI explanation is busy; the calculated local guidance remains available."}
    try:
        payload = {"model": model, "store": False,
            "system_instruction": "Select existing fact IDs for a concise personal nutrition explanation. Only return selected_fact_ids. Never invent diagnoses, targets, doses, food quantities, availability or new advice. Prioritize the given nutrient focus. The mandatory boundaries are retained by the server.",
            "input": json.dumps({"nutrient_focus": member.get("focus_nutrient", "auto"), "facts": facts}),
            "response_format": {"type": "text", "mime_type": "application/json", "schema": {
                "type": "object", "additionalProperties": False,
                "properties": {"selected_fact_ids": {"type": "array", "items": {"type": "string", "enum": list(allowed)}}},
                "required": ["selected_fact_ids"]}}}
        request = Request("https://generativelanguage.googleapis.com/v1beta/interactions",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
        with urlopen(request, timeout=20) as response:
            raw = response.read(100001)
        if len(raw) > 100000:
            raise ValueError("Provider response too large.")
        output = json.loads(raw)
        content = output.get("output_text")
        if not isinstance(content, str):
            content = "".join(item.get("text", "") for item in output.get("outputs", [])
                if isinstance(item, dict) and item.get("type") == "text")
        if not content:
            # The Interactions REST response also represents output as steps.
            # Read model_output text only; never expose thought/signature data.
            content = "".join(part.get("text", "") for step in output.get("steps", [])
                if isinstance(step, dict) and step.get("type") == "model_output"
                for part in step.get("content", []) if isinstance(part, dict) and part.get("type") == "text")
        parsed = json.loads(content)
        ids = parsed.get("selected_fact_ids")
        if not isinstance(ids, list) or not ids or len(ids) > len(facts) or any(not isinstance(i, str) or i not in allowed for i in ids):
            raise ValueError("Provider response does not match verified evidence.")
        chosen = list(dict.fromkeys([*mandatory, *ids]))
        return {"mode": "gemini_fact_selection", "summary": [allowed[i]["text"] for i in chosen],
            "selected_fact_ids": chosen, "scope": SCOPE, "provider": "gemini", "submitted_to_provider": True}
    except Exception:
        return {**local, "submitted_to_provider": True,
            "reason": "Gemini was unavailable or returned unsupported advice; the calculated local guidance is retained."}
    finally:
        _SLOT.release()
