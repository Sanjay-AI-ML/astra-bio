"""Join local leaf and visible-fruit evidence without asserting a diagnosis."""
from __future__ import annotations

from collections import OrderedDict
import copy
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_CONFIG = ROOT / "runtime" / "gemini" / "plant-summary.json"
CARE_SOURCE = "https://extension.umn.edu/garden-and-home/yard-and-garden/gardening-in-minnesota/yard-and-garden-problems/tomato-leaf-spot-diseases"
_CACHE = OrderedDict()
_LOCK = threading.Lock()
_AI_SLOT = threading.BoundedSemaphore(1)
TTL_SECONDS = 900


def build_overview(crop_species: str, leaf: dict | None, fruit: dict | None, *, single_photo: bool = False) -> dict:
    facts = []
    def add(identifier, category, text):
        facts.append({"id": identifier, "category": category, "text": text})
    leaf = leaf or {}
    fruit = fruit or {}
    predictions = leaf.get("predictions") or []
    leaf_status = leaf.get("status", "missing")
    if leaf_status == "tentative" and predictions:
        top = predictions[0]
        condition = str(top.get("condition", "unspecified class"))[:120]
        if top.get("healthy_label") is True:
            add("leaf.match", "overview", "The leaf photograph tentatively matches a healthy-leaf class; this does not establish whole-plant health.")
        else:
            add("leaf.match", "overview", f"The leaf photograph tentatively resembles {condition}; the cause has not been confirmed.")
            add("care.review", "next_steps", "Inspect both leaf surfaces and the stem, record where symptoms appear, and request a crop specialist's review before treatment or removal.")
    else:
        closeup = leaf.get("input_source") == "leaf_closeup"
        add("leaf.match", "overview", "Leaf condition could not be resolved from this photograph." if single_photo else "Leaf condition is unresolved in the supplied close-up." if closeup else "Leaf condition is unresolved: a leaf image is missing, ambiguous, rejected or unavailable.")
        add("care.retake", "next_steps", "Add a sharp, well-lit close-up of one leaf from this same plant; the leaf should fill most of the image. The original plant photo can still be used for fruit observations." if single_photo else "Take a sharp, well-lit close-up of one leaf, including a second view of its underside, then repeat leaf screening.")
    if fruit.get("status") == "observed":
        count = fruit.get("visible_count", 0)
        count = count if type(count) is int and count >= 0 else 0
        add("fruit.count", "overview", f"The fruit model reports {count} visible produce detection(s); hidden produce and duplicate views are not counted reliably.")
        stages = fruit.get("counts_by_stage") or {}
        stage_text = "; ".join(f"{str(stage).replace('_', ' ')}: {count}" for stage, count in stages.items() if type(count) is int and count > 0)[:400]
        if stage_text:
            add("fruit.stages", "overview", f"Model-supported visual stages in this view: {stage_text}.")
        ripe = sum(count for stage, count in stages.items() if stage in {"fully ripe", "ripe"} and type(count) is int)
        if ripe:
            add("use.harvest", "possible_use", "Some detections have ripe-stage labels. Inspect the actual produce for maturity and damage before deciding whether to harvest; visual labels do not certify food safety.")
        else:
            add("use.follow", "possible_use", "Use the visible counts and stage labels for follow-up observation; a harvest decision still needs physical inspection.")
    else:
        add("fruit.count", "overview", "Fruit condition or maturity is unresolved: no fruit view, usable detection or compatible model result is available.")
        add("use.none", "possible_use", "A missing detection does not mean there is no fruit. Capture an unobstructed fruit view before making a harvest plan.")
    add("care.monitor", "next_steps", "Compare repeat photographs of this same labeled plant and check the recorded growing conditions before changing the plan.")
    if crop_species == "tomato":
        add("care.tomato", "next_steps", "For tomato leaf-spot prevention, avoid wetting the foliage and handling plants while leaves are wet; this is general care, not a diagnosis-specific cure.")
    limits = ["A leaf and fruit photograph describe parts of a plant, not a complete health examination.",
        "Model scores are not calibrated probabilities; images cannot confirm bacteria, nutrient content or food safety.",
        "No pesticide, fertilizer dose, crop removal, food-inventory credit or hardware action is generated automatically."]
    if single_photo:
        limits[0] = "Both models analyze the same photograph. Only visible detail can support an observation; this is not a complete plant-health examination."
        limits.append("The leaf classifier processes the whole photo and does not locate individual leaves. Small, obscured leaves or a fruit-dominated view can give unreliable leaf-class matches.")
    elif leaf.get("input_source") == "leaf_closeup":
        limits.append("Leaf classification uses the supplied close-up; fruit detection uses the original plant photograph. Neither model verifies that the photographs show the same plant.")
    return {"mode": "local_evidence", "crop_species": crop_species,
        "headline": "One photograph, leaf and fruit observations" if single_photo else "Leaf and fruit observations combined",
        "brief_overview": " ".join(f["text"] for f in facts if f["category"] == "overview"),
        "next_steps": [f["text"] for f in facts if f["category"] == "next_steps"],
        "possible_use": [f["text"] for f in facts if f["category"] == "possible_use"],
        "limitations": limits, "facts": facts,
        "references": [{"title": "University of Minnesota Extension: tomato leaf spots", "url": CARE_SOURCE}] if crop_species == "tomato" else [],
        "automatic_action": False, "inventory_updated": False}


def remember(overview):
    token = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _LOCK:
        for key in list(_CACHE):
            if now - _CACHE[key][0] > TTL_SECONDS:
                del _CACHE[key]
        _CACHE[token] = (now, copy.deepcopy(overview))
        while len(_CACHE) > 32:
            _CACHE.popitem(last=False)
    return token


def recalled(token):
    if not isinstance(token, str) or len(token) > 80:
        raise ValueError("Choose a valid plant overview evidence identifier.")
    with _LOCK:
        record = _CACHE.get(token)
        if record is None or time.monotonic() - record[0] > TTL_SECONDS:
            raise ValueError("This overview expired. Screen the plant again before requesting an AI summary.")
        return copy.deepcopy(record[1])


def gemini_config():
    private = {}
    if PRIVATE_CONFIG.is_file():
        try:
            private = json.loads(PRIVATE_CONFIG.read_text(encoding="utf-8-sig"))
            if not isinstance(private, dict):
                private = {}
        except (OSError, ValueError):
            private = {}
    key = os.environ.get("GEMINI_API_KEY") or private.get("api_key", "")
    model = os.environ.get("GEMINI_MODEL") or private.get("model", "gemini-3.5-flash-lite")
    if not isinstance(model, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", model) is None:
        model = "gemini-3.5-flash-lite"
    return key if isinstance(key, str) else "", model


def gemini_status():
    key, _ = gemini_config()
    return {"configured": bool(key and not key.startswith("REPLACE_")),
        "provider": "gemini",
        "transmission": "Only the local overview's text facts are sent to Gemini after explicit submission; photographs are not sent.",
        "key_location": "Server GEMINI_API_KEY or ignored runtime/gemini/plant-summary.json; never browser storage."}


def curate_with_gemini(overview):
    """AI selects existing fact IDs; it cannot invent a cure or a finding."""
    key, model = gemini_config()
    if not gemini_status()["configured"]:
        return {**overview, "fallback_reason": "No Gemini API key is configured; the complete local overview is shown."}
    if not _AI_SLOT.acquire(blocking=False):
        return {**overview, "fallback_reason": "AI summary is busy; the local overview remains available."}
    try:
        facts = overview["facts"]
        allowed = {fact["id"]: fact for fact in facts}
        payload = {"systemInstruction": {"parts": [{"text": "Choose existing fact IDs for a brief plant overview and useful next steps. Return only IDs from the schema. Do not add findings, diagnoses, treatment doses or claims of food safety."}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps({"facts": facts}, ensure_ascii=False)}]}],
            "generationConfig": {"maxOutputTokens": 800, "responseFormat": {"text": {"mimeType": "APPLICATION_JSON",
                "schema": {"type": "object", "additionalProperties": False, "properties": {
                    "selected_fact_ids": {"type": "array", "items": {"type": "string", "enum": list(allowed)}}},
                    "required": ["selected_fact_ids"]}}}}}
        request = Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
        with urlopen(request, timeout=20) as response:
            output = json.loads(response.read(100000))
        candidates = output.get("candidates", [])
        content = "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", [])) if candidates else ""
        ids = json.loads(content).get("selected_fact_ids")
        if not isinstance(ids, list) or not ids or len(ids) > len(facts) or any(not isinstance(i, str) or i not in allowed for i in ids):
            raise ValueError("AI response did not match the evidence.")
        # The core leaf/fruit result and possible-use boundary always remain.
        chosen = list(dict.fromkeys(["leaf.match", "fruit.count", *ids]))
        for fact in facts:
            if fact["category"] == "possible_use" and fact["id"] not in chosen:
                chosen.append(fact["id"])
        if not any(allowed[i]["category"] == "next_steps" for i in chosen):
            chosen.append("care.monitor")
        selected = [allowed[i] for i in chosen]
        return {**overview, "mode": "gemini_fact_selection", "selected_fact_ids": chosen,
            "brief_overview": " ".join(f["text"] for f in selected if f["category"] == "overview"),
            "next_steps": [f["text"] for f in selected if f["category"] == "next_steps"]}
    except Exception:
        # Never expose provider messages, credentials, billing details or headers.
        return {**overview, "fallback_reason": "Gemini summary was unavailable or failed evidence validation; the local overview is retained."}
    finally:
        _AI_SLOT.release()
