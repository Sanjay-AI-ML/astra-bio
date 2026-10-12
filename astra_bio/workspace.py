"""Local, versioned configuration/run snapshots. No network or pickle deserialization."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .model import CropSpec, FoodSpec, HabitatConfig
from .planner import ComparisonResult, PlanResult

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "workspace.sqlite"
MAX_JSON_BYTES = 12 * 1024 * 1024


def _connection(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload TEXT NOT NULL)")
    return connection


def _decode(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError("Snapshot exceeds the 12 MB local import limit.")
        payload = json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Nonfinite number: {value}")))
    if not isinstance(payload, dict):
        raise ValueError("Snapshot must be a JSON object.")
    return payload


def _construct(kind, payload):
    if not isinstance(payload, dict):
        raise ValueError(f"{kind.__name__} must be an object.")
    unknown = set(payload) - {item.name for item in fields(kind)}
    if unknown:
        raise ValueError(f"Unknown {kind.__name__} fields: {', '.join(sorted(unknown))}.")
    try:
        return kind(**payload)
    except TypeError as error:
        raise ValueError(str(error)) from error


def configuration_json(config):
    config.validate()
    return json.dumps({"schema_version": 1, "config": asdict(config)}, indent=2, allow_nan=False)


def import_configuration(payload):
    record = _decode(payload)
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported configuration schema version.")
    if not isinstance(record.get("config"), dict):
        raise ValueError("Configuration must be a JSON object.")
    raw = dict(record["config"])
    if not isinstance(raw.get("foods", []), list) or not isinstance(raw.get("crops", []), list):
        raise ValueError("Food and crop catalogues must be arrays.")
    raw["foods"] = [_construct(FoodSpec, item) for item in raw.get("foods", [])]
    raw["crops"] = [_construct(CropSpec, item) for item in raw.get("crops", [])]
    config = _construct(HabitatConfig, raw)
    config.validate()
    return config


def _save(kind, name, payload, path):
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a snapshot name of 1–120 printable characters.")
    text = json.dumps(payload, allow_nan=False)
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Snapshot exceeds the 12 MB local import limit.")
    snapshot_id = uuid.uuid4().hex
    with _connection(path) as connection:
        connection.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, kind, name.strip(), datetime.now(timezone.utc).isoformat(), text))
    return snapshot_id


def save_configuration(name, config, path=DEFAULT_DB):
    return _save("config", name, json.loads(configuration_json(config)), path)


def save_nutrition_state(name, payload, path=DEFAULT_DB):
    payload = _decode(payload)
    from .nutrition import restore_state
    restore_state(payload)
    return _save("nutrition", name, payload, path)


def save_run(name, metadata, path=DEFAULT_DB):
    metadata = _decode(metadata)
    # Validate before saving: an unavailable solver must never become a result.
    restore_run(metadata)
    return _save("run", name, metadata, path)


def list_snapshots(kind, path=DEFAULT_DB, limit=100):
    if kind not in {"config", "run", "nutrition"}:
        raise ValueError("Unknown snapshot kind.")
    with _connection(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT id,kind,name,created_at_utc FROM snapshots WHERE kind=? ORDER BY created_at_utc DESC LIMIT ?", (kind, int(limit)))]


def load_snapshot(snapshot_id, kind, path=DEFAULT_DB):
    with _connection(path) as connection:
        row = connection.execute("SELECT payload FROM snapshots WHERE id=? AND kind=?", (snapshot_id, kind)).fetchone()
    if not row:
        raise ValueError("The selected snapshot was not found.")
    return _decode(row[0])


def restore_run(metadata):
    metadata = _decode(metadata)
    config = import_configuration(metadata)
    if not isinstance(metadata.get("scenario"), dict):
        raise ValueError("Run has no submitted scenario.")
    from .model import Scenario
    raw_scenario = dict(metadata["scenario"])
    raw_scenario["failed_crop_ids"] = tuple(raw_scenario.get("failed_crop_ids", ()))
    scenario = _construct(Scenario, raw_scenario)
    scenario.validate(config)
    plans = []
    for key in ("baseline", "adaptive"):
        raw = dict(metadata.get(key, {}))
        for field_name in ("consumption", "inventories"):
            raw[field_name] = {int(day): amounts for day, amounts in raw.get(field_name, {}).items()}
        plan = _construct(PlanResult, raw)
        if not plan.daily or plan.status in {"solver_error", "solver_unavailable"}:
            raise ValueError("This snapshot does not contain a completed model run.")
        if len(plan.daily) != config.days or [row.get("day") for row in plan.daily] != list(range(1, config.days + 1)):
            raise ValueError("Run daily records do not match the planning horizon.")
        plans.append(plan)
    delta = {key: plans[1].metrics[key] - plans[0].metrics[key]
        for key in set(plans[0].metrics) & set(plans[1].metrics)}
    return config, scenario, ComparisonResult(plans[0], plans[1], scenario.name, delta)
