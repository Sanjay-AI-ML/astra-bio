"""Validated MongoDB telemetry storage for the ESP32 ingestion gateway.

MongoDB credentials remain on the server. The optional driver and connection are
created only when this backend is used; local SQLite workflows do not need them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import threading
from typing import Any
from urllib.parse import parse_qsl

from .storage import validate_observation


class MongoTelemetryUnavailable(RuntimeError):
    """A redacted connection/storage failure suitable for an API response."""


UNAVAILABLE = "MongoDB telemetry is unavailable. Check the server database configuration and connection."
SAMPLE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,96}")


def _connection_options(uri: str) -> dict[str, Any]:
    """Require authenticated TLS verification away from a loopback database."""
    if not isinstance(uri, str) or not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise ValueError("MongoDB URI must use mongodb:// or mongodb+srv://.")
    scheme, rest = uri.split("://", 1)
    authority = rest.split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1]
    if not authority:
        raise ValueError("MongoDB URI must specify a database host.")
    hosts = []
    for entry in authority.split(","):
        if entry.startswith("["):
            end = entry.find("]")
            if end < 0:
                raise ValueError("MongoDB URI contains an invalid database host.")
            hosts.append(entry[1:end].lower())
        else:
            hosts.append(entry.split(":", 1)[0].lower())
    if not all(hosts):
        raise ValueError("MongoDB URI must specify a database host.")
    remote = scheme == "mongodb+srv" or any(host not in {"localhost", "127.0.0.1", "::1"} for host in hosts)
    query = dict((key.lower(), value.lower()) for key, value in parse_qsl(uri.partition("?")[2]))
    if remote:
        if any(query.get(key) in {"false", "0"} for key in ("tls", "ssl")):
            raise ValueError("Remote MongoDB connections require TLS.")
        if any(query.get(key) in {"true", "1"} for key in (
            "tlsinsecure", "tlsallowinvalidcertificates", "tlsallowinvalidhostnames",
        )):
            raise ValueError("Remote MongoDB connections require certificate and hostname verification.")
    # A verified Atlas connection can exceed three seconds before the pool is
    # warm. Allow its initial handshake/authentication with a bounded cloud
    # operation deadline; this is not a compound HTTP request or DNS deadline.
    operation_timeout_ms = 8000 if remote else 3000
    options = {
        "serverSelectionTimeoutMS": operation_timeout_ms,
        "connectTimeoutMS": operation_timeout_ms,
        "socketTimeoutMS": operation_timeout_ms,
        "timeoutMS": operation_timeout_ms,
        "tz_aware": True,
        "connect": False,
    }
    if remote:
        options["tls"] = True
    return options


def _utc_date(value: Any, field: str) -> datetime:
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError
        instant = instant.astimezone(timezone.utc)
        # BSON dates retain milliseconds, matching the existing SQLite contract.
        return instant.replace(microsecond=(instant.microsecond // 1000) * 1000)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be an ISO timestamp with a timezone.") from None


def _api_timestamp(value: datetime) -> str:
    # MongoDB's default naive datetime reads are UTC; injected clients may use it.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _api_row(document: dict[str, Any]) -> dict[str, Any]:
    row = dict(document)
    row["id"] = str(row.pop("_id"))
    row.pop("payload_fingerprint", None)
    for field in ("ts_utc", "received_at_utc"):
        if isinstance(row.get(field), datetime):
            row[field] = _api_timestamp(row[field])
    return row


class MongoTelemetryStore:
    def __init__(self, uri: str, database: str = "astra_bio", collection: str = "observations", client=None):
        self._options = _connection_options(uri)
        if not isinstance(database, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", database):
            raise ValueError("MongoDB database name must contain 1-64 letters, digits, underscores or hyphens.")
        if not isinstance(collection, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", collection):
            raise ValueError("MongoDB collection name must contain 1-64 letters, digits, underscores or hyphens.")
        self.database = database
        self.collection = collection
        self._uri = uri
        self._client = client
        self._indexes_ready = False
        self._index_lock = threading.Lock()
        self._client_lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    try:
                        from pymongo import MongoClient
                        self._client = MongoClient(self._uri, **self._options)
                    except Exception:
                        raise MongoTelemetryUnavailable(UNAVAILABLE) from None
        return self._client

    def _get_collection(self):
        return self._get_client()[self.database][self.collection]

    def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        with self._index_lock:
            if self._indexes_ready:
                return
            try:
                collection = self._get_collection()
                collection.create_index(
                    [("device_id", 1), ("source", 1), ("sample_id", 1)],
                    unique=True, name="observation_sample_unique",
                )
                collection.create_index(
                    [("device_id", 1), ("source", 1), ("ts_utc", -1), ("_id", -1)],
                    name="observation_stream_time",
                )
                collection.create_index([("ts_utc", -1), ("_id", -1)], name="observation_time")
            except Exception:
                raise MongoTelemetryUnavailable(UNAVAILABLE) from None
            self._indexes_ready = True

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = validate_observation(payload)
        sample_id = payload.get("sample_id")
        if not isinstance(sample_id, str) or not SAMPLE_ID_PATTERN.fullmatch(sample_id):
            raise ValueError("sample_id must contain 1-96 letters, digits, underscores or hyphens.")
        received_at = _utc_date(payload.get("received_at_utc", datetime.now(timezone.utc)), "received_at_utc")
        content = dict(payload)
        content.pop("received_at_utc", None)
        content.pop("transport", None)
        if content.get("timestamp_origin") == "gateway":
            # A device without a synchronized clock resends the same sample;
            # the gateway's assigned observation time changes on that retry.
            content.pop("ts_utc", None)
        else:
            content["ts_utc"] = row["ts_utc"]
        if isinstance(content.get("device_ts_utc"), str):
            content["device_ts_utc"] = _api_timestamp(_utc_date(content["device_ts_utc"], "device_ts_utc"))
        fingerprint = sha256(json.dumps(content, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        row.update(sample_id=sample_id, ts_utc=_utc_date(row["ts_utc"], "ts_utc"),
                   received_at_utc=received_at, payload_fingerprint=fingerprint)
        identity = {key: row[key] for key in ("device_id", "source", "sample_id")}
        self.ensure_indexes()
        try:
            collection = self._get_collection()
            inserted = collection.insert_one(row)
            if not inserted.acknowledged:
                raise MongoTelemetryUnavailable(UNAVAILABLE)
            return {"id": str(inserted.inserted_id), "duplicate": False}
        except Exception as error:
            if getattr(error, "code", None) != 11000:
                raise MongoTelemetryUnavailable(UNAVAILABLE) from None
        try:
            previous = collection.find_one(identity)
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None
        if previous is None:
            raise MongoTelemetryUnavailable(UNAVAILABLE)
        if previous.get("payload_fingerprint") != fingerprint:
            raise ValueError("sample_id already exists with different telemetry. Use a new sample_id for each measurement.")
        return {"id": str(previous["_id"]), "duplicate": True}

    def recent_observations(self, limit: int = 240, device_id: str | None = None,
                            source: str | None = None) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise ValueError("limit must be an integer from 1 to 10000")
        if source is not None and source not in ("synthetic", "hardware"):
            raise ValueError("invalid source")
        if device_id is not None and (not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id)):
            raise ValueError("invalid device_id")
        query = {key: value for key, value in (("device_id", device_id), ("source", source)) if value is not None}
        try:
            rows = list(self._get_collection().find(query).sort([("ts_utc", -1), ("_id", -1)]).limit(limit))
            return [_api_row(row) for row in reversed(rows)]
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None

    def latest_observation(self, device_id: str | None = None, source: str | None = None) -> dict[str, Any] | None:
        rows = self.recent_observations(limit=1, device_id=device_id, source=source)
        return rows[0] if rows else None

    def list_devices(self) -> list[dict[str, Any]]:
        try:
            rows = self._get_collection().aggregate([
                {"$group": {"_id": {"device_id": "$device_id", "source": "$source"},
                            "latest_ts_utc": {"$max": "$ts_utc"}, "observation_count": {"$sum": 1}}},
                {"$sort": {"_id.source": 1, "_id.device_id": 1}},
            ])
            return [{**row["_id"], "latest_ts_utc": _api_timestamp(row["latest_ts_utc"]),
                     "observation_count": row["observation_count"]} for row in rows]
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None

    def device_states(self) -> dict[str, dict[str, Any]]:
        # MQTT availability messages are not implied by HTTP sensor samples.
        return {}

    def status(self) -> dict[str, Any]:
        result = {"backend": "mongodb", "configured": True, "connected": False,
                  "database": self.database, "collection": self.collection}
        try:
            self._get_client().admin.command("ping")
            result["connected"] = True
        except Exception:
            result["error"] = UNAVAILABLE
        return result

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                raise MongoTelemetryUnavailable(UNAVAILABLE) from None
            finally:
                self._client = None
                self._indexes_ready = False
