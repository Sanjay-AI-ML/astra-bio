"""Bounded original JPEG storage for authenticated ESP32 camera captures.

Images are kept as BSON Binary in a separate collection. They never enter the
telemetry payload or automatically run a model, change inventory or actuate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import re
import threading
from typing import Any

from PIL import Image, UnidentifiedImageError

from .mongo_telemetry import MongoTelemetryUnavailable, _api_timestamp, _connection_options, _utc_date

MAX_CAMERA_BYTES = 2 * 1024 * 1024
MAX_CAMERA_PIXELS = 20_000_000
CAMERA_COLLECTION = "camera_images"
UNAVAILABLE = "MongoDB camera storage is unavailable. Check the server database connection."
IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
SAMPLE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,96}")
PUBLIC_FIELDS = ("device_id", "source", "sample_id", "received_at_utc", "captured_at_utc",
                 "width", "height", "bytes", "sha256", "transport")


def validate_capture(image: bytes, *, device_id: str, source: str, sample_id: str,
                     captured_at_utc: str | None = None,
                     received_at_utc: datetime | str | None = None,
                     transport: str = "wifi_https") -> dict[str, Any]:
    """Validate bounded complete JPEG bytes before any MongoDB write."""
    if not isinstance(device_id, str) or not IDENTITY_PATTERN.fullmatch(device_id):
        raise ValueError("device_id must contain 1-64 letters, digits, underscores or hyphens.")
    if source not in {"hardware", "synthetic"}:
        raise ValueError("source must be hardware or synthetic.")
    if not isinstance(sample_id, str) or not SAMPLE_PATTERN.fullmatch(sample_id):
        raise ValueError("sample_id must contain 1-96 letters, digits, underscores or hyphens.")
    if transport not in {"wifi_https", "serial_bridge"}:
        raise ValueError("transport must be wifi_https or serial_bridge.")
    if not isinstance(image, bytes) or not 0 < len(image) <= MAX_CAMERA_BYTES:
        raise ValueError("Camera JPEG must contain 1 byte to 2 MiB.")
    # The camera driver returns one complete JPEG, with no trailing container.
    if not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
        raise ValueError("Send a complete JPEG image.")
    try:
        with Image.open(BytesIO(image)) as candidate:
            if candidate.format != "JPEG":
                raise ValueError("Send a JPEG image.")
            width, height = candidate.size
            if width < 1 or height < 1 or width * height > MAX_CAMERA_PIXELS:
                raise ValueError("Camera image exceeds the 20 megapixel limit.")
            candidate.verify()
        # verify() alone does not decode JPEG entropy data. load() also rejects
        # corrupt or truncated frames; never enable LOAD_TRUNCATED_IMAGES.
        with Image.open(BytesIO(image)) as decoded:
            decoded.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("JPEG image is invalid or incomplete.") from None
    received = _utc_date(datetime.now(timezone.utc) if received_at_utc is None else received_at_utc, "received_at_utc")
    captured = _utc_date(captured_at_utc, "captured_at_utc") if captured_at_utc is not None else None
    return {"device_id": device_id, "source": source, "sample_id": sample_id,
            "received_at_utc": received, "captured_at_utc": captured,
            "width": width, "height": height, "bytes": len(image), "sha256": sha256(image).hexdigest(),
            "transport": transport}


def public_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Allowlist metadata; neither BSON bytes nor private/internal fields escape."""
    result = {field: document.get(field) for field in PUBLIC_FIELDS}
    image_id = str(document["_id"])
    result["id"] = image_id
    for field in ("received_at_utc", "captured_at_utc"):
        if isinstance(result.get(field), datetime):
            result[field] = _api_timestamp(result[field])
    result["content_url"] = f"/api/camera-images/{image_id}/content"
    return result


class MongoCameraStore:
    def __init__(self, uri: str, database: str = "astra_bio", collection: str = CAMERA_COLLECTION,
                 client=None, client_provider=None):
        self._options = _connection_options(uri)
        if not isinstance(database, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", database):
            raise ValueError("Invalid MongoDB database name.")
        if not isinstance(collection, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", collection):
            raise ValueError("Invalid MongoDB camera collection name.")
        self.database = database
        self.collection = collection
        self._uri = uri
        self._client = client
        self._client_provider = client_provider
        self._client_lock = threading.Lock()
        self._index_lock = threading.Lock()
        self._indexes_ready = False

    def _get_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    try:
                        if self._client_provider is not None:
                            self._client = self._client_provider()
                        else:
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
                collection.create_index([("device_id", 1), ("source", 1), ("sample_id", 1)],
                                        unique=True, name="camera_sample_unique")
                collection.create_index([("source", 1), ("device_id", 1), ("received_at_utc", -1), ("_id", -1)],
                                        name="camera_stream_received")
                collection.create_index([("received_at_utc", -1), ("_id", -1)], name="camera_received")
            except Exception:
                raise MongoTelemetryUnavailable(UNAVAILABLE) from None
            self._indexes_ready = True

    def ingest(self, image: bytes, *, device_id: str, source: str, sample_id: str,
               captured_at_utc: str | None = None,
               received_at_utc: datetime | str | None = None,
               transport: str = "wifi_https") -> dict[str, Any]:
        metadata = validate_capture(image, device_id=device_id, source=source, sample_id=sample_id,
                                    captured_at_utc=captured_at_utc, received_at_utc=received_at_utc,
                                    transport=transport)
        identity = {key: metadata[key] for key in ("device_id", "source", "sample_id")}
        self.ensure_indexes()
        try:
            from bson import Binary
            collection = self._get_collection()
            document = {**metadata, "content_type": "image/jpeg", "image_data": Binary(image),
                        "automatic_analysis": False, "actuation_enabled": False}
            inserted = collection.insert_one(document)
            if not inserted.acknowledged:
                raise MongoTelemetryUnavailable(UNAVAILABLE)
            document["_id"] = inserted.inserted_id
            return {"id": str(inserted.inserted_id), "duplicate": False, "image": public_metadata(document)}
        except Exception as error:
            if getattr(error, "code", None) != 11000:
                raise MongoTelemetryUnavailable(UNAVAILABLE) from None
        try:
            previous = collection.find_one(identity, {"image_data": 0})
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None
        if previous is None:
            raise MongoTelemetryUnavailable(UNAVAILABLE)
        # A USB relay may replay the retained frame without the device's clock
        # field. Accept that exact image and preserve the first receipt metadata.
        # An explicitly supplied conflicting clock is still a different sample.
        clock_conflict = (metadata["captured_at_utc"] is not None
                          and previous.get("captured_at_utc") != metadata["captured_at_utc"])
        if previous.get("sha256") != metadata["sha256"] or clock_conflict:
            raise ValueError("sample_id already exists with different image or capture time. Use a new sample_id for each capture.")
        return {"id": str(previous["_id"]), "duplicate": True, "image": public_metadata(previous)}

    def recent_images(self, limit: int = 24, device_id: str | None = None,
                      source: str = "hardware") -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100.")
        if source not in {"hardware", "synthetic"}:
            raise ValueError("source must be hardware or synthetic.")
        if device_id is not None and (not isinstance(device_id, str) or not IDENTITY_PATTERN.fullmatch(device_id)):
            raise ValueError("Invalid device_id.")
        query = {"source": source}
        if device_id is not None:
            query["device_id"] = device_id
        try:
            # MongoDB excludes binary at the query itself, not only JSON output.
            projection = {field: 1 for field in PUBLIC_FIELDS}
            rows = self._get_collection().find(query, projection).sort([("received_at_utc", -1), ("_id", -1)]).limit(limit)
            return [public_metadata(row) for row in rows]
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None

    def image_content(self, image_id: str) -> bytes | None:
        if not isinstance(image_id, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", image_id):
            raise ValueError("Invalid camera image ID.")
        try:
            from bson import ObjectId
            document = self._get_collection().find_one({"_id": ObjectId(image_id)},
                {"image_data": 1, "sha256": 1, "bytes": 1, "content_type": 1})
            if document is None:
                return None
            image = bytes(document["image_data"])
            if (not 0 < len(image) <= MAX_CAMERA_BYTES or len(image) != document.get("bytes")
                    or document.get("content_type") != "image/jpeg" or sha256(image).hexdigest() != document.get("sha256")):
                raise ValueError()
            return image
        except Exception:
            raise MongoTelemetryUnavailable(UNAVAILABLE) from None


_reader_key = None
_reader = None
_reader_lock = threading.Lock()


def camera_reader() -> MongoCameraStore | None:
    """Borrow the existing process-local verified Atlas client; no new secrets."""
    global _reader_key, _reader
    from .mongo_runtime import telemetry_reader
    telemetry = telemetry_reader()
    if telemetry is None:
        return None
    key = (id(telemetry), telemetry.database, CAMERA_COLLECTION)
    with _reader_lock:
        if _reader_key != key:
            _reader = MongoCameraStore(telemetry._uri, telemetry.database, CAMERA_COLLECTION,
                                      client_provider=telemetry._get_client)
            _reader_key = key
        return _reader
