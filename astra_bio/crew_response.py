"""Separate immediate crew review from prospective nutrient production.

Laboratory and vital observations are never converted into nutrient targets,
diagnoses, prescriptions, or edible inventory. Missing context remains unknown.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite

from .bioproduction import bioproduction_catalog, simulate_bioproduction
from .nutrition import CrewProfile, FoodLogEntry, active_crew_context, assess_intake

MEDICAL_SOURCE = "https://www.nhlbi.nih.gov/health/anemia/iron-deficiency-anemia"
URGENT_SOURCE = "https://www.nhs.uk/symptoms/chest-pain/"


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative number.")
    return float(value)


def _rows(state, key):
    rows = state.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{key} must be a list of observation objects.")
    return rows


def _timing(row, day, now):
    recorded = row.get("day")
    if recorded is not None and (isinstance(recorded, bool) or not isinstance(recorded, int) or recorded < 1):
        raise ValueError("Observation mission day must be a positive integer.")
    stamp = row.get("observed_at")
    temporal = "undated" if recorded is None else "current" if recorded == day else "historical" if recorded < day else "future"
    if stamp is not None:
        if not isinstance(stamp, str):
            raise ValueError("Observation timestamp must be an ISO timestamp with timezone.")
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Observation timestamp must be an ISO timestamp with timezone.") from exc
        if parsed.tzinfo is None:
            raise ValueError("Observation timestamp must include its timezone.")
        if parsed > now:
            temporal = "future"
        elif parsed.date() < now.date() and temporal == "current":
            temporal = "historical"
    return temporal


def _alert(person, row, sample_only, kind, message, *, severity="review", **evidence):
    return {"profile_id": person["profile_id"], "name": person["name"], "kind": kind,
        "severity": "demo" if sample_only and severity == "urgent" else severity,
        "message": message, "day": row.get("day"), "observed_at": row.get("observed_at"),
        "sample_only": sample_only, "measurement_status": evidence.pop("measurement_status", "unknown"),
        "evidence": evidence}


def _lab_alerts(people, state, day, now, sample_only):
    references = state.get("references", {})
    if not isinstance(references, dict):
        raise ValueError("Crew measurement references must be an object.")
    latest, records = {}, []
    for row in _rows(state, "blood_samples"):
        for key in ("hemoglobin_g_dl", "ferritin_ug_l"):
            if row.get(key) is not None:
                _number(row[key], key)
        status = _timing(row, day, now)
        records.append({"profile_id": row.get("profile_id"), "day": row.get("day"),
            "observed_at": row.get("observed_at"), "status": status})
        if row.get("profile_id") in people and status != "future":
            old = latest.get(row["profile_id"])
            if old is None or (row.get("day") or 0) >= (old[0].get("day") or 0):
                latest[row["profile_id"]] = row, status
    alerts, context_missing = [], []
    for profile_id, (row, status) in latest.items():
        person = people[profile_id]
        age = person.get("age")
        adult = isinstance(age, int) and not isinstance(age, bool) and 15 <= age <= 65
        context = row.get("reference_context", person.get("reference_context", {}))
        if not isinstance(context, dict):
            raise ValueError("Laboratory reference_context must be an object.")
        # Existing sample reference text explicitly declares these assumptions.
        # They apply only to invented demonstrations, never to real observations.
        fictional = sample_only and "invented" in str(state.get("scope", "")).lower()
        hb_context = fictional or (context.get("sea_level") is True and context.get("no_smoking") is True
            and (person.get("sex") == "male" or context.get("nonpregnant") is True))
        ferritin_context = fictional or (context.get("no_inflammation") is True and context.get("nonpregnant") is True)
        for key, reference_key, eligible, unit, label in (
            ("hemoglobin_g_dl", "hemoglobin", adult and hb_context, "g/dL", "Hemoglobin"),
            ("ferritin_ug_l", "ferritin", adult and ferritin_context, "µg/L", "Ferritin"),
        ):
            if row.get(key) is None:
                continue
            ref = references.get(reference_key, {})
            if not isinstance(ref, dict):
                raise ValueError("A laboratory reference must be an object.")
            cutoff_key = f"{person.get('sex')}_cutoff_g_dl" if key == "hemoglobin_g_dl" else "cutoff_ug_l"
            cutoff = ref.get(cutoff_key)
            if not eligible or cutoff is None:
                context_missing.append({"profile_id": profile_id, "metric": key,
                    "message": "Reference context or applicable adult cutoff is not established; clinician review required."})
                continue
            cutoff = _number(cutoff, "Laboratory reference cutoff")
            if row[key] < cutoff:
                prefix = "Fictional example: " if sample_only else ""
                alerts.append(_alert(person, row, sample_only, f"low_{reference_key}",
                    f"{prefix}{label} is below the applicable reference cutoff. Request crew medical review; the cause and treatment are not established.",
                    measurement_status=status, value=row[key], cutoff=cutoff, unit=unit,
                    source_url=ref.get("source_url"), reference_scope=ref.get("scope")))
    return alerts, records, context_missing


def _observation_alerts(people, state, day, now, sample_only):
    alerts, records, observed_heart_rate = [], [], set()
    for row in _rows(state, "health_observations"):
        status = _timing(row, day, now)
        records.append({"profile_id": row.get("profile_id"), "day": row.get("day"),
            "observed_at": row.get("observed_at"), "status": status})
        value = row.get("heart_rate_bpm")
        if value is not None:
            value = _number(value, "Heart rate")
        limits = row.get("reviewed_limits", {})
        if not isinstance(limits, dict):
            raise ValueError("Reviewed vital limits must be an object.")
        symptoms = row.get("symptoms", [])
        if not isinstance(symptoms, list) or any(not isinstance(item, str) for item in symptoms):
            raise ValueError("Reported symptoms must be a list of identifiers.")
        if row.get("resting") is not None and not isinstance(row["resting"], bool):
            raise ValueError("Resting context must be a boolean when supplied.")
        person = people.get(row.get("profile_id"))
        if person is None or status == "future":
            continue
        if value is not None:
            observed_heart_rate.add(person["profile_id"])
        urgent_symptoms = "fainting" in symptoms or (
            "chest_pain" in symptoms and ("breathlessness" in symptoms or "shortness_of_breath" in symptoms))
        if urgent_symptoms:
            live = status == "current"
            message = "Contact the crew medical officer immediately and follow the mission emergency protocol. Do not wait for new biological production."
            if sample_only:
                message = "Fictional emergency example: a real current report of these symptoms requires immediate crew medical response."
            elif not live:
                message = "Historical or undated symptom record: review its timing with the crew medical officer; current symptoms are not established."
            alerts.append(_alert(person, row, sample_only, "reported_urgent_symptoms", message,
                severity="urgent" if live else "review", measurement_status=status,
                symptoms=symptoms, source_url=URGENT_SOURCE))
        limit = limits.get("heart_rate_bpm")
        if value is not None and row.get("resting") is True and isinstance(limit, dict) and limit.get("reviewed") is True:
            low = _number(limit.get("min"), "Reviewed resting heart-rate lower limit")
            high = _number(limit.get("max"), "Reviewed resting heart-rate upper limit")
            if low >= high:
                raise ValueError("Reviewed heart-rate limits must have min smaller than max.")
            if value < low or value > high:
                alerts.append(_alert(person, row, sample_only, "heart_rate_outside_reviewed_limits",
                    "Resting heart rate is outside the operator-reviewed limits. Confirm the measurement and request crew medical review; no nutrient cause is inferred.",
                    measurement_status=status, value=value, unit="bpm", reviewed_min=low, reviewed_max=high))
    return alerts, records, observed_heart_rate


def _support(report, state, people, alerts, day, sample_only):
    result = []
    for alert in alerts:
        if alert["severity"] == "urgent":
            result.append({"kind": "crew_medical", "status": "urgent", "title": "Crew medical response now",
                "message": alert["message"], "profile_id": alert["profile_id"], "sample_only": False})
    lab_people = {alert["profile_id"] for alert in alerts if alert["kind"] in {"low_hemoglobin", "low_ferritin"}}
    if lab_people:
        result.append({"kind": "medical_review", "status": "demo" if sample_only else "review",
            "title": "Review blood results with crew medical", "profile_ids": sorted(lab_people),
            "message": "Confirm the cause and an existing treatment plan. Hemoglobin and ferritin do not set protein or iron intake targets.",
            "sample_only": sample_only, "source_url": MEDICAL_SOURCE})
    for food in report.get("bridge_foods", []):
        if food.get("available") is True and food.get("expired") is not True and food.get("stock_kg") is not None and _number(food["stock_kg"], "Available food stock") > 0:
            result.append({"kind": "stored_food", "status": "review", "title": food["name"],
                "message": "Available in the saved inventory; review the existing meal allocation before using it.",
                "food_id": food["food_id"], "stock_kg": food["stock_kg"],
                "nutrients": deepcopy(food.get("available_nutrients_in_stock", {})),
                "is_reserve": food.get("is_reserve", False), "stock_source": food.get("stock_source"),
                "sample_only": sample_only})
    for order in _rows(state, "approved_supplements"):
        profile_id, nutrient = order.get("profile_id"), order.get("nutrient")
        quantity = order.get("quantity_remaining")
        if quantity is not None:
            quantity = _number(quantity, "Supplement inventory")
        start, end = order.get("start_day", 1), order.get("end_day")
        if isinstance(start, bool) or not isinstance(start, int) or start < 1 or (end is not None and (isinstance(end, bool) or not isinstance(end, int) or end < start)):
            raise ValueError("Approved supplement order dates must be valid mission days.")
        indicated = (nutrient == "iron" and profile_id in lab_people) or any(
            row.get("nutrient") == nutrient and (row.get("current_shortfall") or 0) > 0
            for row in report.get("forecast", {}).get("nutrients", []))
        if profile_id in people and indicated and order.get("clinician_approved") is True and order.get("available") is True and quantity is not None and quantity > 0 and start <= day and (end is None or day <= end):
            result.append({"kind": "approved_supplement", "status": "demo" if sample_only else "review",
                "title": order.get("name", "Existing approved supplement"), "profile_id": profile_id,
                "nutrient": nutrient, "quantity_remaining": quantity,
                "message": "An available clinician-approved order is recorded for this person and nutrient. Follow that existing order; no dose is generated.",
                "sample_only": sample_only})
    if not any(row["kind"] == "approved_supplement" for row in result) and lab_people:
        result.append({"kind": "supplement_review", "status": "unknown", "title": "Supplement availability unconfirmed",
            "message": "No matching available clinician-approved order is recorded. Ask crew medical to review treatment and inventory.",
            "sample_only": sample_only})
    return result


def _production(config, plan, report, request, scenario, day):
    catalog = {profile["id"]: profile for profile in bioproduction_catalog()["profiles"]}
    if request is not None and not isinstance(request, dict):
        raise ValueError("Biological scenario must be an object.")
    if not request or request.get("reviewed_inputs") is not True:
        return [{"id": key, "profile_id": key, "name": catalog[key]["name"], "status": "needs_review",
            "first_harvest_day": None, "protein_g": None, "protein_target_share": None,
            "first_harvest_protein_g": None, "food_qualified": False,
            "reasons": ["No saved reviewed production scenario establishes startup, capacity and remaining resource commitments."],
            "references": deepcopy(catalog[key]["references"])} for key in ("limnospira_pc8005", "wolffia_globosa")]
    updated = deepcopy(request)
    for key in ("start_day", "horizon_days"):
        value = updated.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("Reviewed biological scenario needs positive integer start_day and horizon_days.")
    original_end = updated.get("start_day", day) + updated.get("horizon_days", 0) - 1
    start = max(day, updated.get("start_day", day))
    end = min(config.days, report.get("deadline_day", config.days), original_end)
    if end < start:
        return [{"id": "reviewed-scenario", "profile_id": None, "name": "Saved biological scenario",
            "status": "needs_review", "first_harvest_day": None, "protein_g": None,
            "protein_target_share": None, "first_harvest_protein_g": None, "food_qualified": False,
            "reasons": ["Saved scenario horizon has ended; review a prospective scenario for the remaining mission."]}]
    updated.update(start_day=start, horizon_days=end - start + 1)
    factors = {"water_factor": 1., "power_factor": 1., "media_factor": 1., "production_factor": 1.}
    events = []
    for event in updated.get("events", []):
        if event["day"] <= start:
            for key in factors:
                factors[key] *= event.get(key, 1.)
        elif event["day"] <= end:
            events.append(event)
    if any(value != 1. for value in factors.values()):
        events.insert(0, {"day": start, **factors})
    updated["events"] = events
    try:
        projected = simulate_bioproduction(config, plan, updated, scenario, earliest_start_day=day)
    except ValueError as exc:
        return [{"id": "reviewed-scenario", "profile_id": None, "name": "Saved biological scenario",
            "status": "needs_review", "first_harvest_day": None, "protein_g": None,
            "protein_target_share": None, "first_harvest_protein_g": None, "food_qualified": False,
            "reasons": [str(exc)]}]
    options = []
    for module in projected["modules"]:
        rows = [(row, next(item for item in row["modules"] if item["id"] == module["id"])) for row in projected["daily"]]
        harvests = [(row, item) for row, item in rows if item["biomass_dry_g"] > 0]
        first = harvests[0] if harvests else None
        protein = sum(item["protein_g"] or 0 for _, item in rows) if any(item["protein_g"] is not None for _, item in rows) else None
        target = projected["totals"]["crew_protein_target_g"]
        reasons = list(module["exclusion_reasons"])
        reasons.extend(reason for _, item in rows for reason in item["exclusion_reasons"] if reason not in reasons)
        if not first and not reasons:
            reasons.append("No supported harvest occurs within the remaining reviewed horizon.")
        options.append({"id": module["id"], "profile_id": module["profile_id"], "name": module["name"],
            "status": "projected" if first else "needs_review", "first_harvest_day": first[0]["day"] if first else None,
            "first_harvest_protein_g": first[1]["protein_g"] if first else None,
            "protein_g": protein, "protein_target_share": protein / target if protein is not None and target else None,
            "nutrients": {nutrient: sum(item["nutrients"][nutrient] or 0 for _, item in rows)
                if any(item["nutrients"][nutrient] is not None for _, item in rows) else None
                for nutrient in projected["nutrient_units"]}, "nutrient_units": projected["nutrient_units"],
            "start_day": start, "end_day": end, "food_qualified": False,
            "scope": "Prospective new-module projection; reviewed startup restarts here. Food qualification and actual intake are unestablished.",
            "reasons": reasons, "references": module["references"]})
    options.sort(key=lambda item: (item["first_harvest_day"] is None, item["first_harvest_day"] or config.days + 1))
    return options


def _crew_intake(people, state, day):
    """Current complete logs compared with accepted targets, never draft ones."""
    complete = state.get("complete_days", {})
    if not isinstance(complete, dict):
        raise ValueError("Crew log completeness must be an object.")
    profiles = [CrewProfile(**{key: person[key] for key in CrewProfile.__dataclass_fields__ if key in person})
        for person in people.values()]
    logs = [FoodLogEntry(**{key: row[key] for key in FoodLogEntry.__dataclass_fields__ if key in row})
        for row in _rows(state, "entries") if row.get("profile_id") in people and row.get("day") == day]
    rows = assess_intake(profiles, logs, day,
        {pid: complete.get(f"{pid}:{day}") is True for pid in people}) if profiles else []
    for row in rows:
        row["usable_for_response"] = row["log_complete"] and row["intake"] is not None
    return rows


def build_response_plan(config, plan, report, crew_state, biological_scenario, scenario=None):
    """Return immediate review, existing stock and prospective production separately.

    ``report`` is the existing crop-advisor report. Optional health_observations
    use profile_id, mission day, observed_at, symptoms and operator-reviewed
    resting heart-rate limits. Optional approved_supplements must explicitly
    identify the person, nutrient, approval and positive available inventory.
    """
    state = crew_state or {}
    if not isinstance(state, dict) or not isinstance(report, dict):
        raise ValueError("Crew state and recommendation report must be objects.")
    day = report.get("day", 1)
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= config.days:
        raise ValueError("Response mission day must fall within the mission.")
    sample_only = state.get("sample_only") is True
    context = report.get("crew_context") or active_crew_context(config, day, scenario=scenario)
    people = {person["profile_id"]: person for person in context.get("members", [])}
    # Explicit roster identities remain authoritative; sample measurements can
    # enrich only matching people and cannot add an absent crew member.
    for profile in _rows(state, "profiles"):
        if profile.get("profile_id") in people:
            people[profile["profile_id"]] = {**profile, **people[profile["profile_id"]]}
    now = datetime.now(timezone.utc)
    labs, lab_records, context_missing = _lab_alerts(people, state, day, now, sample_only)
    vitals, vital_records, heart_rate_known = _observation_alerts(people, state, day, now, sample_only)
    alerts = vitals + labs
    intake = _crew_intake(people, state, day)
    pending = [p["profile_id"] for p in _rows(state, "profiles") if p.get("profile_id") in people
        and p.get("targets") != people[p["profile_id"]].get("reviewed_targets", people[p["profile_id"]]["targets"])]
    return {"health_alerts": alerts, "immediate_support": _support(report, state, people, alerts, day, sample_only),
        "crew_intake": intake,
        "production_options": _production(config, plan, report, biological_scenario, scenario, day),
        "scope": {"day": day, "sample_only": sample_only,
            "measurement_records": lab_records + vital_records, "reference_context_missing": context_missing,
            "heart_rate_missing_profile_ids": sorted(set(people) - heart_rate_known),
            "pending_target_profile_ids": pending,
            "missing_metrics": ["Blood pressure"] + (["Heart rate for one or more crew members"] if set(people) - heart_rate_known else []),
            "blood_pressure_status": "unknown; no configured measurements or clinical limits",
            "targets_basis": "Existing reviewed crew planning targets; never inferred from hemoglobin, ferritin, heart rate or blood pressure.",
            "limitations": ["Sample blood values remain fictional and never trigger a real emergency instruction.",
                "Historical, future and undated observations do not establish a current emergency.",
                "No diagnosis, supplement dose, clinical recovery, new edible inventory or hardware command is generated.",
                "New crops and microorganisms cannot resolve an immediate illness before qualified harvest.",
                "NASA BioNutrients 48-hour engineered-yeast experiments do not establish an available emergency food or a universal supplement replacement."]}}
