"""Local FastAPI service for the React workspace; observations never actuate hardware."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from math import ceil
import csv
from io import StringIO
from pathlib import Path
import sqlite3
import threading

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .crop_growth import calibrate_harvests, load_observations, load_reference_crops, predict_growth
from .explanations import explain_comparison, explain_with_ollama
from .model import Scenario, default_config, scenario_presets
from .nutrition import CrewProfile, FoodLogEntry, apply_profile_targets, apply_usda_composition, assess_intake, crop_contributions, default_profiles, load_compositions, restore_state, serialize_state
from .planner import run_comparison
from .plant_vision import MAX_IMAGE_BYTES, assess_image, model_status
from .plant_registry import registry_status, select_model
from .crop_trials import CSV_FIELDS, current_crop_response_status
from .measured_growth import current_measured_growth_status
from .presets import input_status, research_preset
from . import storage, workspace, mongo_runtime
from .mongo_telemetry import MongoTelemetryUnavailable

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
SOLVER_LOCK = threading.Lock()
app = FastAPI(title="ASTRA-BIO", version="1.0.0", description="Local food, crop and resource planning research prototype.")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


@app.middleware("http")
async def local_requests(request: Request, call_next):
    if request.url.path.startswith("/api") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:8501", "http://localhost:8501", "http://127.0.0.1:5173", "http://localhost:5173"}:
            return JSONResponse({"detail": "This local API accepts changes only from its own workspace."}, status_code=403)
    try:
        if int(request.headers.get("content-length", "0")) > 12 * 1024 * 1024:
            return JSONResponse({"detail": "Request exceeds the 12 MB local limit."}, status_code=413)
    except ValueError:
        return JSONResponse({"detail": "Invalid content length."}, status_code=400)
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(ValueError)
async def invalid_value(request, error):
    return JSONResponse({"detail": str(error)}, status_code=422)


@app.exception_handler(TypeError)
async def invalid_type(request, error):
    return JSONResponse({"detail": "Input structure is invalid. Review the submitted fields."}, status_code=422)


@app.exception_handler(KeyError)
async def missing_field(request, error):
    return JSONResponse({"detail": f"Missing required input: {str(error)}."}, status_code=422)


@app.exception_handler(MongoTelemetryUnavailable)
@app.exception_handler(mongo_runtime.MongoConfigurationError)
async def telemetry_unavailable(request, error):
    return JSONResponse({"detail": "MongoDB telemetry is unavailable. Check the Atlas connection and refresh."}, status_code=503)


def configuration(raw):
    config = workspace.import_configuration({"schema_version": 1, "config": raw})
    if config.days > 180 or config.crew > 12 or len(config.foods) > 100 or len(config.crops) > 30:
        raise ValueError("Local planning limit: 180 days, 12 crew, 100 food lots and 30 crop profiles.")
    return config


def scenario_value(raw, config):
    raw = dict(raw)
    raw["failed_crop_ids"] = tuple(raw.get("failed_crop_ids", ()))
    scenario = Scenario(**raw)
    scenario.validate(config)
    return scenario


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "astra-bio-api", "frontend": "react", "frontend_built": (DIST / "index.html").exists()}


@app.get("/api/bootstrap")
def bootstrap():
    config = default_config()
    last_run = None
    try:
        records = workspace.list_snapshots("run")
        if records:
            metadata = workspace.load_snapshot(records[0]["id"], "run")
            config, scenario, comparison = workspace.restore_run(metadata)
            last_run = {"metadata": metadata, "delta": comparison.delta,
                "explanation": explain_comparison(comparison, config, scenario), "history_id": records[0]["id"]}
    except (ValueError, OSError, sqlite3.Error):
        # A damaged history record cannot prevent a new planning session.
        config = default_config()
    return {"config": asdict(config), "demo_config": asdict(default_config()), "input_status": input_status(config),
        "presets": {key: asdict(value) for key, value in scenario_presets().items()},
        "references": {key: value.as_dict() for key, value in load_reference_crops().items()},
        "compositions": {key: asdict(value) for key, value in load_compositions().items()},
        "observations": load_observations(), "profiles": [asdict(p) for p in default_profiles(config)],
        "plant_model": model_status(), "last_run": last_run}


@app.post("/api/config/validate")
def validate_config(payload: dict = Body(...)):
    config = configuration(payload["config"])
    return {"config": asdict(config), "input_status": input_status(config)}


@app.post("/api/config/research")
def apply_research(payload: dict = Body(...)):
    config = configuration(payload["config"])
    config = research_preset(config, payload["ids"], water_l_per_m2_day=payload.get("water", 1.5),
        efficacy=payload.get("efficacy", 2.5), photon_delivery=payload.get("delivery", .8),
        overhead_kwh_per_m2_day=payload.get("overhead", .15), conservative=payload.get("conservative", False))
    return {"config": asdict(config), "input_status": input_status(config)}


@app.post("/api/config/usda")
def apply_usda(payload: dict = Body(...)):
    config = apply_usda_composition(configuration(payload["config"]), payload.get("inventory"))
    return {"config": asdict(config), "input_status": input_status(config)}


@app.post("/api/plans")
def plan(payload: dict = Body(...)):
    config = configuration(payload["config"])
    scenario = scenario_value(payload["scenario"], config)
    if not SOLVER_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A planning run is already in progress. Wait for it to finish.")
    try:
        comparison = run_comparison(config, scenario)
    finally:
        SOLVER_LOCK.release()
    metadata = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_status": input_status(config), "config": asdict(config), "scenario": asdict(scenario),
        "baseline": comparison.baseline.as_dict(), "adaptive": comparison.adaptive.as_dict()}
    history_id, history_warning = None, None
    if comparison.adaptive.daily and comparison.baseline.daily:
        try:
            history_id = workspace.save_run(scenario.name, metadata)
        except (ValueError, OSError, sqlite3.Error) as error:
            history_warning = f"Run completed; local history save failed ({type(error).__name__})."
    return {"metadata": metadata, "delta": comparison.delta, "explanation": explain_comparison(comparison, config, scenario),
        "history_id": history_id, "history_warning": history_warning}


@app.post("/api/explain")
def explain(payload: dict = Body(...)):
    config, scenario, comparison = workspace.restore_run(payload["metadata"])
    evidence = explain_comparison(comparison, config, scenario)
    return explain_with_ollama(evidence, enabled=payload.get("ollama", False), model=payload.get("model", "llama3.2:3b"))


@app.post("/api/growth")
def growth(payload: dict = Body(...)):
    return predict_growth(payload["crop_id"], payload["age_days"], payload["area_m2"], conservative=payload.get("conservative", False)).as_dict()


@app.post("/api/calibrate")
def calibrate(payload: dict = Body(...)):
    if len(payload["observations"]) > 5000:
        raise ValueError("Keep calibration below 5,000 independently identified observations.")
    return calibrate_harvests(payload["observations"], holdout_ids=payload.get("holdout_ids", []))


@app.post("/api/calibrate/csv")
async def calibration_csv(file: UploadFile = File(...)):
    raw = await file.read(2_000_001)
    await file.close()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "Keep calibration CSV below 2 MB.")
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeError, csv.Error) as error:
        raise ValueError("Could not decode the calibration CSV.") from error
    if len(rows) > 5000:
        raise ValueError("Keep calibration below 5,000 observations.")
    calibrate_harvests(rows)
    return {"observations": rows}


@app.post("/api/calibrate/apply")
def apply_calibration(payload: dict = Body(...)):
    config = configuration(payload["config"])
    report = calibrate(payload)
    provenance = dict(config.input_provenance)
    crops = []
    matches = 0
    for crop in config.crops:
        params = report["fit_parameters"].get(crop.id)
        if params:
            matches += 1
            crops.append(replace(crop, grow_days=ceil(params["grow_days"]), yield_kg_per_m2=params["yield_kg_per_m2"]))
            provenance[f"crop:{crop.id}:harvest"] = {"local_calibration": params, "validation": report["validation"]}
        else:
            crops.append(crop)
    if not matches:
        raise ValueError("No fitted crop IDs match the current planner. Apply the matching measured profiles first.")
    candidate = replace(config, crops=crops, input_provenance=provenance)
    candidate.validate()
    return {"config": asdict(candidate), "input_status": input_status(candidate)}


@app.post("/api/sensitivity")
def sensitivity(payload: dict = Body(...)):
    config = configuration(payload["config"])
    references = load_reference_crops()
    if not any(c.id in references for c in config.crops):
        raise ValueError("Apply measured crop references before checking their observed yield ranges.")
    if not SOLVER_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A planning run is already in progress.")
    results = []
    try:
        for label, field in [("Observed minimum", "observed_min_kg_per_m2"), ("Published mean", "yield_kg_per_m2"), ("Observed maximum", "observed_max_kg_per_m2")]:
            candidate = replace(config, crops=[replace(c, yield_kg_per_m2=getattr(references[c.id], field)) if c.id in references else c for c in config.crops])
            plan = run_comparison(candidate, Scenario("none", "Harvest sensitivity", event_day=config.days + 1)).adaptive
            results.append({"case": label, "status": plan.status, **plan.metrics})
    finally:
        SOLVER_LOCK.release()
    return {"cases": results, "scope": "Deterministic sensitivity to observed experimental bounds; no probability or prediction interval."}


@app.post("/api/nutrition/assess")
def nutrition_assess(payload: dict = Body(...)):
    profiles = [CrewProfile(**row) for row in payload["profiles"]]
    logs = [FoodLogEntry(**row) for row in payload.get("entries", [])]
    day = payload.get("day", 1)
    complete = {p.profile_id: payload.get("complete_days", {}).get(f"{p.profile_id}:{day}", False) for p in profiles}
    rows = assess_intake(profiles, logs, day, complete=complete)
    gaps = {n: sum(row["gap"] or 0 for row in rows if row["nutrient"] == n) for n in ("energy", "protein", "vitamin_c")}
    return {"rows": rows, "contributions": crop_contributions(gaps), "scope": "Recorded intake estimate; missing or incomplete logs do not diagnose nutritional deficiency."}


@app.post("/api/nutrition/apply-targets")
def nutrition_targets(payload: dict = Body(...)):
    config = apply_profile_targets(configuration(payload["config"]), [CrewProfile(**row) for row in payload["profiles"]])
    return {"config": asdict(config), "input_status": input_status(config)}


@app.post("/api/nutrition/save")
def nutrition_save(payload: dict = Body(...)):
    profiles, logs, complete = restore_state(payload["state"])
    record = serialize_state(profiles, logs, complete)
    return {"id": workspace.save_nutrition_state(payload["name"], record, workspace.DEFAULT_DB)}


@app.post("/api/plant-image")
async def plant_image(crop_species: str = Query(...), file: UploadFile = File(...)):
    data = await file.read(MAX_IMAGE_BYTES + 1)
    await file.close()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Keep the image below 10 MiB.")
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(assess_image, data, crop_species)


@app.get("/api/models")
def models_status():
    return {"plant": registry_status(), "growth": current_measured_growth_status(),
        "crop_response": current_crop_response_status(), "automatic_action": False}


@app.post("/api/models/plant/select")
def select_plant_model(payload: dict = Body(...)):
    select_model(payload["candidate_id"])
    return {"plant_model": model_status(), "registry": registry_status()}


@app.get("/api/models/crop-trial-template")
def crop_trial_template():
    return Response(",".join(CSV_FIELDS)+"\n",media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=astra-bio-crop-trials.csv"})


def _age(value):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(value.replace("Z", "+00:00"))).total_seconds()
    except (ValueError, TypeError, AttributeError):
        return None


def mqtt_status():
    try:
        raw = json.loads((ROOT / "runtime/mqtt-status.json").read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid public health record.")
        public = {key: raw[key] for key in ("running", "checked_at_utc", "broker_host", "broker_port", "lan_host", "profile") if key in raw}
        age = _age(public.get("checked_at_utc"))
        public["fresh"] = age is not None and -5 <= age <= 120
        public["connected"] = public["fresh"] and public.get("running") is True
        check = raw.get("latest_delivery_check", {})
        if not isinstance(check, dict):
            check = {}
        public["latest_delivery_check"] = {key: check[key] for key in ("status", "source", "device_id", "checked_at_utc", "checks_passed") if key in check}
        return public
    except (OSError, ValueError, TypeError):
        return {"connected": False, "fresh": False, "running": None}


@app.get("/api/telemetry")
def telemetry(device_id: str | None = None, source: str = Query("hardware", pattern="^(hardware|synthetic)$")):
    mongo = mongo_runtime.telemetry_reader()
    reader = mongo if mongo is not None else storage
    streams = reader.list_devices()
    if device_id is None:
        device_id = next((row["device_id"] for row in streams if row["source"] == source), None)
    rows = reader.recent_observations(device_id=device_id, source=source) if device_id else []
    record = reader.latest_observation(device_id=device_id, source=source) if device_id else None
    safe = lambda row: {key: value for key, value in row.items() if key != "raw_json"}
    metadata = {}
    if record:
        try:
            raw = json.loads(record.get("raw_json", "{}"))
            metadata = {key: raw[key] for key in ("transport", "received_at_utc", "device_ts_utc", "timestamp_origin") if key in raw}
        except (ValueError, TypeError):
            pass
    age = _age(metadata.get("received_at_utc") or (record or {}).get("ts_utc"))
    states = reader.device_states()
    state = states.get(device_id)
    if state and state.get("source") != source:
        state = None
    return {"streams": streams, "device_id": device_id, "source": source, "latest": safe(record) if record else None,
        "history": [safe(row) for row in rows], "availability": safe(state) if state else None,
        "age_seconds": age, "metadata": metadata, "mqtt": mqtt_status(), "actuation_enabled": False,
        "storage": {"backend": "mongodb" if mongo is not None else "sqlite", "connected": True}}


@app.get("/api/snapshots/{kind}")
def snapshots(kind: str):
    return workspace.list_snapshots(kind)


@app.get("/api/snapshots/{kind}/{identifier}")
def snapshot(kind: str, identifier: str):
    return workspace.load_snapshot(identifier, kind)


@app.post("/api/snapshots/config")
def save_config(payload: dict = Body(...)):
    return {"id": workspace.save_configuration(payload["name"], configuration(payload["config"]))}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def frontend():
    if not (DIST / "index.html").exists():
        raise HTTPException(503, "Build the React frontend: npm ci --prefix frontend; npm run build --prefix frontend.")
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
