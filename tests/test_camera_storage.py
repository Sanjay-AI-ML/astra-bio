"""Camera contract and bounded storage checks, without contacting live Atlas."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

from bson import Binary, ObjectId
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from astra_bio import api, camera_storage, mongo_runtime
from astra_bio.camera_storage import MongoCameraStore, MAX_CAMERA_BYTES
from astra_bio.mongo_runtime import GatewaySettings
from astra_bio.mongo_telemetry import MongoTelemetryUnavailable
from astra_bio.telemetry_gateway import create_app

TOKEN = "test-camera-device-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "image/jpeg",
           "X-Device-Id": "tray-01", "X-Sample-Id": "boot01_0001", "X-Source": "hardware"}


class DuplicateKey(Exception):
    code = 11000


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.rows.sort(key=lambda row: row[field], reverse=direction == -1)
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    def __iter__(self):
        return iter(self.rows)


class Collection:
    def __init__(self):
        self.rows = []
        self.indexes = []
        self.projections = []

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    def insert_one(self, document):
        if any(all(row[key] == document[key] for key in ("device_id", "source", "sample_id")) for row in self.rows):
            raise DuplicateKey()
        row = deepcopy(document)
        row["_id"] = ObjectId()
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"], acknowledged=True)

    def _project(self, row, projection):
        if projection:
            self.projections.append(projection)
            if any(projection.values()):
                return deepcopy({key: value for key, value in row.items() if key == "_id" or projection.get(key) == 1})
            return deepcopy({key: value for key, value in row.items() if projection.get(key) != 0})
        return deepcopy(row)

    def find_one(self, query, projection=None):
        row = next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)
        return None if row is None else self._project(row, projection)

    def find(self, query, projection=None):
        return Cursor([self._project(row, projection) for row in self.rows
                       if all(row.get(key) == value for key, value in query.items())])


class Client:
    def __init__(self):
        self.collection = Collection()

    def __getitem__(self, key):
        assert key in {"astra_bio", "camera_images"}
        return self if key == "astra_bio" else self.collection


@pytest.fixture
def jpeg():
    output = BytesIO()
    Image.new("RGB", (32, 24), "green").save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def store():
    return MongoCameraStore("mongodb://localhost", client=Client())


@pytest.fixture
def gateway(store):
    settings = GatewaySettings("mongodb://localhost", devices={"tray-01": sha256(TOKEN.encode()).hexdigest()})
    return TestClient(create_app(settings, image_store=store), base_url="https://127.0.0.1"), store


def capture(store, jpeg, **changes):
    return store.ingest(jpeg, **({"device_id": "tray-01", "source": "hardware", "sample_id": "boot01_0001",
                                "received_at_utc": "2026-10-12T12:00:05Z"} | changes))


def test_original_jpeg_stored_as_bson_and_returned_byte_exact(store, jpeg):
    receipt = capture(store, jpeg, captured_at_utc="2026-10-12T17:30:00.987654+05:30")
    row = store._client.collection.rows[0]
    assert isinstance(row["image_data"], Binary)
    assert bytes(row["image_data"]) == jpeg
    assert row["received_at_utc"] == datetime(2026, 10, 12, 12, 0, 5, tzinfo=timezone.utc)
    assert receipt["image"]["captured_at_utc"] == "2026-10-12T12:00:00.987Z"
    assert receipt["image"]["width"] == 32 and receipt["image"]["height"] == 24
    assert receipt["image"]["bytes"] == len(jpeg) and receipt["image"]["sha256"] == sha256(jpeg).hexdigest()
    assert receipt["image"]["transport"] == "wifi_https"
    assert row["automatic_analysis"] is row["actuation_enabled"] is False
    assert store.image_content(receipt["id"]) == jpeg
    assert store._client.collection.indexes[0][1]["unique"] is True


def test_duplicate_preserves_receipt_and_transport_but_different_bytes_or_clock_rejected(store, jpeg):
    first = capture(store, jpeg)
    retry = capture(store, jpeg, received_at_utc="2026-10-12T12:05:00Z", transport="serial_bridge")
    assert retry == first | {"duplicate": True}
    assert len(store._client.collection.rows) == 1
    output = BytesIO()
    Image.new("RGB", (32, 24), "red").save(output, format="JPEG")
    with pytest.raises(ValueError, match="different image"):
        capture(store, output.getvalue())
    with pytest.raises(ValueError, match="capture time"):
        capture(store, jpeg, captured_at_utc="2026-10-12T12:00:00Z")
    assert store.image_content(first["id"]) == jpeg


def test_utc_equivalent_capture_time_is_idempotent(store, jpeg):
    first = capture(store, jpeg, captured_at_utc="2026-10-12T12:00:00Z")
    retry = capture(store, jpeg, captured_at_utc="2026-10-12T17:30:00+05:30")
    assert retry == first | {"duplicate": True}


def test_usb_retry_without_capture_clock_preserves_first_wifi_metadata(store, jpeg):
    first = capture(store, jpeg, captured_at_utc="2026-10-12T12:00:00Z", transport="wifi_https")
    replay = capture(store, jpeg, received_at_utc="2026-10-12T12:05:00Z", transport="serial_bridge")
    assert replay == first | {"duplicate": True}
    assert replay["image"]["captured_at_utc"] == "2026-10-12T12:00:00.000Z"
    assert replay["image"]["transport"] == "wifi_https"
    assert len(store._client.collection.rows) == 1
    with pytest.raises(ValueError, match="capture time"):
        capture(store, jpeg, captured_at_utc="2026-10-12T12:00:01Z", transport="serial_bridge")
    output = BytesIO()
    Image.new("RGB", (32, 24), "red").save(output, format="JPEG")
    with pytest.raises(ValueError, match="different image"):
        capture(store, output.getvalue(), transport="serial_bridge")


def test_source_device_filters_and_recent_window_keep_images_separate(store, jpeg):
    capture(store, jpeg)
    capture(store, jpeg, source="synthetic")
    capture(store, jpeg, device_id="tray-02", received_at_utc="2026-10-12T12:01:00Z", transport="serial_bridge")
    assert len(store.recent_images(source="hardware")) == 2
    assert len(store.recent_images(source="synthetic")) == 1
    assert len(store.recent_images(source="hardware", device_id="tray-01")) == 1
    assert store.recent_images(limit=1)[0]["device_id"] == "tray-02"
    assert store.recent_images(limit=1)[0]["transport"] == "serial_bridge"


def test_metadata_is_allowlisted_and_query_does_not_fetch_image_binary(store, jpeg):
    capture(store, jpeg)
    row = store._client.collection.rows[0]
    row.update(uri="mongodb://user:secret@private.example", device_token="private-token", arbitrary="not-public")
    items = store.recent_images()
    assert items[0]["content_url"] == f"/api/camera-images/{row['_id']}/content"
    assert set(items[0]) == {*camera_storage.PUBLIC_FIELDS, "id", "content_url"}
    assert "private" not in str(items) and "image_data" not in str(items)
    assert store._client.collection.projections[-1].get("image_data") is None


@pytest.mark.parametrize("changes", [
    {"source": "unknown"}, {"device_id": "../tray"}, {"device_id": "x" * 65},
    {"sample_id": ""}, {"sample_id": "x" * 97}, {"sample_id": "../frame"},
    {"captured_at_utc": "2026-10-12T12:00:00"}, {"captured_at_utc": ""},
    {"received_at_utc": "2026-10-12T12:00:00"}, {"received_at_utc": ""},
    {"transport": "mqtt"},
])
def test_invalid_metadata_never_enters_mongodb(store, jpeg, changes):
    with pytest.raises(ValueError):
        capture(store, jpeg, **changes)
    assert store._client.collection.rows == []


def test_nonjpeg_incomplete_oversize_and_pixel_bounds_rejected(store, jpeg, monkeypatch):
    png = BytesIO()
    Image.new("RGB", (32, 24)).save(png, format="PNG")
    for image in (b"", png.getvalue(), jpeg[:-2], jpeg[:100] + b"\xff\xd9", b"x" * (MAX_CAMERA_BYTES + 1)):
        with pytest.raises(ValueError):
            capture(store, image)
    monkeypatch.setattr(camera_storage, "MAX_CAMERA_PIXELS", 100)
    with pytest.raises(ValueError, match="20 megapixel"):
        capture(store, jpeg)
    assert store._client.collection.rows == []


@pytest.mark.parametrize("changes", [{"limit": True}, {"limit": 0}, {"limit": 101},
                                   {"source": "unknown"}, {"device_id": "../tray"}])
def test_invalid_read_filters_rejected(store, changes):
    with pytest.raises(ValueError):
        store.recent_images(**changes)


def test_missing_image_and_invalid_id(store):
    assert store.image_content(str(ObjectId())) is None
    with pytest.raises(ValueError, match="image ID"):
        store.image_content("../image")


def test_mongo_failures_redacted_before_http_and_tampering_not_served(store, jpeg, monkeypatch):
    receipt = capture(store, jpeg)
    store._client.collection.rows[0]["image_data"] = Binary(b"changed")
    with pytest.raises(MongoTelemetryUnavailable) as error:
        store.image_content(receipt["id"])
    assert "changed" not in str(error.value)
    def fail(*args, **kwargs):
        raise RuntimeError("mongodb://user:secret@private.example")
    monkeypatch.setattr(store._client.collection, "find", fail)
    with pytest.raises(MongoTelemetryUnavailable) as error:
        store.recent_images()
    assert "secret" not in str(error.value) and "private.example" not in str(error.value)


def test_reader_borrows_existing_pool_and_configuration_changes_replace_camera_store(monkeypatch):
    telemetry = SimpleNamespace(_uri="mongodb://localhost", database="astra_bio", _get_client=lambda: Client())
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: telemetry)
    first = camera_storage.camera_reader()
    assert first is camera_storage.camera_reader()
    assert first._client is None
    assert isinstance(first._get_client(), Client)
    telemetry = SimpleNamespace(_uri="mongodb://localhost", database="astra_bio", _get_client=lambda: Client())
    assert camera_storage.camera_reader() is not first
    monkeypatch.setattr(mongo_runtime, "telemetry_reader", lambda: None)
    assert camera_storage.camera_reader() is None


def test_gateway_accepts_real_jpeg_acknowledges_retry_and_has_no_actions(gateway, jpeg):
    client, store = gateway
    first = client.post("/v1/images", content=jpeg, headers=HEADERS)
    retry = client.post("/v1/images", content=jpeg, headers=HEADERS)
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json() == first.json() | {"duplicate": True}
    assert first.json()["storage"] == "mongodb"
    assert first.json()["automatic_analysis"] is first.json()["actuation_enabled"] is False
    assert first.headers["Cache-Control"] == "no-store"
    assert first.headers["X-Content-Type-Options"] == "nosniff"
    assert len(store._client.collection.rows) == 1


@pytest.mark.parametrize("changes,status", [
    ({"Authorization": "Bearer wrong"}, 401), ({"Authorization": "Basic wrong"}, 401),
    ({"X-Device-Id": "tray-02"}, 403), ({"Content-Type": "image/png"}, 415),
    ({"X-Source": ""}, 422), ({"X-Sample-Id": "../frame"}, 422),
    ({"X-Captured-At": "2026-10-12T12:00:00"}, 422), ({"X-Transport": "mqtt"}, 422),
    ({"Origin": "http://127.0.0.1:8501"}, 403),
])
def test_gateway_invalid_and_crossdevice_requests_write_nothing(gateway, jpeg, changes, status):
    client, store = gateway
    response = client.post("/v1/images", content=jpeg, headers=HEADERS | changes)
    assert response.status_code == status
    assert store._client.collection.rows == []


def test_gateway_missing_token_http_and_stream_bound_rejected(gateway, jpeg):
    client, store = gateway
    assert client.post("/v1/images", content=jpeg).status_code == 401
    assert client.post("http://127.0.0.1/v1/images", content=jpeg, headers=HEADERS).status_code == 403
    assert client.post("/v1/images", content=b"x" * (MAX_CAMERA_BYTES + 1),
                       headers=HEADERS | {"Content-Length": "1"}).status_code == 413
    assert client.post("/v1/images", content=jpeg, headers=HEADERS | {"Content-Length": "-1"}).status_code == 400
    assert client.post("/v1/images", content=jpeg, headers=HEADERS | {"Content-Length": str(MAX_CAMERA_BYTES + 1)}).status_code == 413
    assert client.post("/v1/images", content=jpeg[:-2], headers=HEADERS).status_code == 422
    assert store._client.collection.rows == []


def test_gateway_error_redacted_and_retryable(gateway, jpeg, monkeypatch):
    client, store = gateway
    def fail(*args, **kwargs):
        raise MongoTelemetryUnavailable("mongodb://user:secret@private.example")
    monkeypatch.setattr(store, "ingest", fail)
    response = client.post("/v1/images", content=jpeg, headers=HEADERS)
    assert response.status_code == 503 and response.headers["Retry-After"] == "10"
    assert "secret" not in response.text and "private.example" not in response.text


def test_local_dashboard_metadata_and_content_match_without_binary_json(monkeypatch, store, jpeg):
    receipt = capture(store, jpeg)
    monkeypatch.setattr(camera_storage, "camera_reader", lambda: store)
    client = TestClient(api.app, base_url="http://127.0.0.1")
    response = client.get("/api/camera-images?source=hardware&device_id=tray-01&limit=1")
    assert response.status_code == 200
    assert response.json()["items"] == [receipt["image"]]
    assert response.json()["storage"] == {"backend": "mongodb", "configured": True, "connected": True, "collection": "camera_images"}
    assert "image_data" not in response.text
    content = client.get(receipt["image"]["content_url"])
    assert content.content == jpeg and content.headers["content-type"] == "image/jpeg"
    assert content.headers["cache-control"] == "no-store"
    assert client.get(f"/api/camera-images/{ObjectId()}/content").status_code == 404
    assert client.get("/api/camera-images/invalid/content").status_code == 422
    assert client.get("/api/camera-images?source=all").status_code == 422
    assert client.get("/api/camera-images?limit=101").status_code == 422
    assert client.get("/api/camera-images?device_id=../tray").status_code == 422


def test_local_dashboard_unconfigured_and_outage_are_clear_and_redacted(monkeypatch):
    client = TestClient(api.app, base_url="http://127.0.0.1")
    monkeypatch.setattr(camera_storage, "camera_reader", lambda: None)
    response = client.get("/api/camera-images")
    assert response.status_code == 200 and response.json()["items"] == []
    assert response.json()["storage"]["configured"] is False
    assert client.get(f"/api/camera-images/{ObjectId()}/content").status_code == 503
    def fail():
        raise MongoTelemetryUnavailable("mongodb://user:secret@private.example")
    monkeypatch.setattr(camera_storage, "camera_reader", fail)
    response = client.get("/api/camera-images")
    assert response.status_code == 503 and "secret" not in response.text
