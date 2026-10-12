"""Validated local telemetry storage shared with the Node-RED flow."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
import sqlite3
from typing import Any, Iterator

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "telemetry.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ts_utc TEXT NOT NULL,
 device_id TEXT NOT NULL,
 source TEXT NOT NULL CHECK (source IN ('synthetic','hardware')),
 air_temp_c REAL, relative_humidity_pct REAL, solution_temp_c REAL,
 light_lux REAL, bus_voltage_v REAL, bus_current_a REAL, bus_power_w REAL,
 low_water INTEGER CHECK (low_water IN (0,1)),
 pump_on INTEGER CHECK (pump_on IN (0,1)),
 fan_on INTEGER CHECK (fan_on IN (0,1)),
 light_on INTEGER CHECK (light_on IN (0,1)),
 raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_time ON observations(ts_utc, id);
CREATE INDEX IF NOT EXISTS observations_stream ON observations(device_id, source, ts_utc, id);
CREATE TABLE IF NOT EXISTS device_status (
 device_id TEXT PRIMARY KEY,
 status TEXT NOT NULL CHECK(status IN ('online','offline')),
 source TEXT NOT NULL CHECK(source IN ('synthetic','hardware')),
 received_at_utc TEXT NOT NULL,
 raw_json TEXT NOT NULL
);
"""
FIELDS = (
    "ts_utc", "device_id", "source", "air_temp_c", "relative_humidity_pct",
    "solution_temp_c", "light_lux", "bus_voltage_v", "bus_current_a",
    "bus_power_w", "low_water", "pump_on", "fan_on", "light_on", "raw_json",
)
RANGES = {
    "air_temp_c": (-50, 80), "solution_temp_c": (-10, 60),
    "relative_humidity_pct": (0, 100), "light_lux": (0, 200_000),
    "bus_voltage_v": (0, 36), "bus_current_a": (0, 15),
    "bus_power_w": (0, 540),
}
FLAGS = ("low_water", "pump_on", "fan_on", "light_on")


@contextmanager
def _connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db(path: str | Path = DEFAULT_DB) -> None:
    with _connect(path) as connection:
        connection.executescript(SCHEMA)


def validate_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """Require provenance and normalize timestamps so lexical ordering is UTC."""
    if not isinstance(payload, dict):
        raise ValueError("observation must be a JSON object")
    if payload.get("source") not in ("synthetic", "hardware"):
        raise ValueError("source must explicitly be synthetic or hardware")
    device = payload.get("device_id")
    if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device):
        raise ValueError("device_id must contain 1-64 letters, digits, underscores or hyphens")
    timestamp = payload.get("ts_utc")
    if not isinstance(timestamp, str):
        raise ValueError("ts_utc must be an ISO timestamp with a timezone")
    try:
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ts_utc must be an ISO timestamp with a timezone") from exc
    if instant.tzinfo is None:
        raise ValueError("ts_utc requires a timezone")
    normalized = {field: payload.get(field) for field in FIELDS}
    normalized["device_id"] = device.strip()
    normalized["ts_utc"] = instant.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    readings = 0
    for field, (minimum, maximum) in RANGES.items():
        number = payload.get(field)
        if number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"{field} must be a number or null")
        if not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError(f"{field} is outside the accepted measurement range")
        normalized[field] = float(number)
        readings += 1
    if readings == 0:
        raise ValueError("at least one finite sensor reading is required")
    for field in FLAGS:
        flag = payload.get(field)
        if flag is None:
            continue
        if not isinstance(flag, (bool, int)) or flag not in (0, 1):
            raise ValueError(f"{field} must be 0, 1 or null")
        normalized[field] = int(flag)
    normalized["raw_json"] = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    if len(normalized["raw_json"]) > 16384:
        raise ValueError("telemetry exceeds 16 KiB")
    return normalized


def insert_observation(payload: dict[str, Any], path: str | Path = DEFAULT_DB) -> int:
    row = validate_observation(payload)
    init_db(path)
    with _connect(path) as connection:
        placeholders = ",".join("?" for _ in FIELDS)
        cursor = connection.execute(
            f"INSERT INTO observations ({','.join(FIELDS)}) VALUES ({placeholders})",
            [row[field] for field in FIELDS],
        )
        return int(cursor.lastrowid)


def recent_observations(limit: int = 240, path: str | Path = DEFAULT_DB,
                        device_id: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("limit must be an integer from 1 to 10000")
    if source is not None and source not in ('synthetic', 'hardware'):
        raise ValueError('invalid source')
    clauses, values = [], []
    for field, value in [('device_id', device_id), ('source', source)]:
        if value is not None:
            clauses.append(f'{field} = ?')
            values.append(value)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    init_db(path)
    with _connect(path) as connection:
        rows = connection.execute(
            'SELECT * FROM observations' + where + ' ORDER BY ts_utc DESC, id DESC LIMIT ?',
            [*values, limit],
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def latest_observation(path: str | Path = DEFAULT_DB, device_id: str | None = None,
                       source: str | None = None) -> dict[str, Any] | None:
    rows = recent_observations(limit=1, path=path, device_id=device_id, source=source)
    return rows[0] if rows else None


def list_devices(path: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    init_db(path)
    with _connect(path) as connection:
        rows = connection.execute('''SELECT device_id, source, MAX(ts_utc) AS latest_ts_utc,
            COUNT(*) AS observation_count FROM observations GROUP BY device_id, source
            ORDER BY source, device_id''').fetchall()
    return [dict(row) for row in rows]


list_observation_streams = list_devices


def device_states(path: str | Path = DEFAULT_DB) -> dict[str, dict[str, Any]]:
    init_db(path)
    with _connect(path) as connection:
        rows = connection.execute('SELECT * FROM device_status').fetchall()
    return {row['device_id']: dict(row) for row in rows}
