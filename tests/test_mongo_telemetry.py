from copy import deepcopy
from datetime import datetime, timezone
import sys
from types import SimpleNamespace

import pytest

from astra_bio.mongo_telemetry import MongoTelemetryStore, MongoTelemetryUnavailable


class DuplicateKey(Exception):
    code = 11000


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, ordering):
        for field, direction in reversed(ordering):
            self.rows.sort(key=lambda row: row[field], reverse=direction == -1)
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeCollection:
    def __init__(self):
        self.rows = []
        self.indexes = []

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    def insert_one(self, row):
        if any(all(previous[key] == row[key] for key in ("device_id", "source", "sample_id")) for previous in self.rows):
            raise DuplicateKey()
        row = deepcopy(row)
        row["_id"] = len(self.rows) + 1
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"], acknowledged=True)

    def find_one(self, query):
        return next((deepcopy(row) for row in self.rows if all(row[key] == value for key, value in query.items())), None)

    def find(self, query):
        return FakeCursor([deepcopy(row) for row in self.rows if all(row[key] == value for key, value in query.items())])

    def aggregate(self, pipeline):
        assert pipeline[0]["$group"]["_id"] == {"device_id": "$device_id", "source": "$source"}
        groups = {}
        for row in self.rows:
            identity = row["device_id"], row["source"]
            group = groups.setdefault(identity, {"_id": {"device_id": identity[0], "source": identity[1]},
                                                 "latest_ts_utc": row["ts_utc"], "observation_count": 0})
            group["observation_count"] += 1
            group["latest_ts_utc"] = max(group["latest_ts_utc"], row["ts_utc"])
        return sorted(groups.values(), key=lambda row: (row["_id"]["source"], row["_id"]["device_id"]))


class FakeClient:
    def __init__(self):
        self.collection = FakeCollection()
        self.admin = SimpleNamespace(command=lambda command: {"ok": 1})
        self.closed = False

    def __getitem__(self, key):
        return self if key == "astra_bio" else self.collection

    def close(self):
        self.closed = True


@pytest.fixture
def store():
    return MongoTelemetryStore("mongodb://localhost:27017", client=FakeClient())


def observation(**changes):
    return {"ts_utc": "2026-10-12T12:00:00Z", "received_at_utc": "2026-10-12T12:00:05Z",
            "source": "hardware", "device_id": "esp32-tray-01", "sample_id": "boot001_0001",
            "air_temp_c": 23.5, "low_water": False} | changes


def test_retry_is_idempotent_despite_new_server_received_timestamp(store):
    first = store.ingest(observation())
    retry = store.ingest(observation(received_at_utc="2026-10-12T12:00:20Z"))
    assert first == {"id": "1", "duplicate": False}
    assert retry == {"id": "1", "duplicate": True}
    assert len(store.recent_observations()) == 1
    assert store.latest_observation()["received_at_utc"] == "2026-10-12T12:00:05.000Z"
    assert len(store._client.collection.indexes) == 3
    assert store._client.collection.indexes[0][1]["unique"] is True


def test_retry_without_device_clock_preserves_original_gateway_observation_time(store):
    payload = observation(timestamp_origin="gateway", device_ts_utc=None, transport="https")
    first = store.ingest(payload)
    retry = store.ingest(payload | {"ts_utc": "2026-10-12T12:00:20Z", "received_at_utc": "2026-10-12T12:00:20Z",
                                   "transport": "https-retry"})
    assert retry == first | {"duplicate": True}
    assert store.latest_observation()["ts_utc"] == "2026-10-12T12:00:00.000Z"
    with pytest.raises(ValueError, match="different telemetry"):
        store.ingest(payload | {"air_temp_c": 28})


def test_device_clock_changes_conflict_but_equivalent_utc_instants_do_not(store):
    payload = observation(timestamp_origin="device", device_ts_utc="2026-10-12T12:00:00Z")
    store.ingest(payload)
    assert store.ingest(payload | {"ts_utc": "2026-10-12T17:30:00+05:30",
                                  "device_ts_utc": "2026-10-12T17:30:00+05:30"})["duplicate"] is True
    with pytest.raises(ValueError, match="different telemetry"):
        store.ingest(payload | {"ts_utc": "2026-10-12T12:00:01Z"})


def test_conflicting_sample_id_is_rejected_and_original_measurement_survives(store):
    store.ingest(observation())
    with pytest.raises(ValueError, match="different telemetry"):
        store.ingest(observation(air_temp_c=31))
    assert store.latest_observation()["air_temp_c"] == 23.5


def test_content_order_is_irrelevant_but_extra_metadata_collision_is_rejected(store):
    payload = observation(sensor="sht31")
    store.ingest(payload)
    assert store.ingest(dict(reversed(list(payload.items()))))["duplicate"] is True
    with pytest.raises(ValueError, match="different telemetry"):
        store.ingest(observation(sensor="dht22"))


def test_storage_uses_bson_utc_dates_and_returns_normalized_timestamps_and_raw_provenance(store):
    payload = observation(ts_utc="2026-10-12T18:00:00.987654+05:30", received_at_utc="2026-10-12T18:00:05+05:30")
    store.ingest(payload)
    document = store._client.collection.rows[0]
    assert document["ts_utc"] == datetime(2026, 10, 12, 12, 30, 0, 987000, tzinfo=timezone.utc)
    row = store.latest_observation()
    assert row["ts_utc"] == "2026-10-12T12:30:00.987Z"
    assert row["received_at_utc"] == "2026-10-12T12:30:05.000Z"
    assert row["low_water"] == 0
    assert '"source":"hardware"' in row["raw_json"]
    assert "payload_fingerprint" not in row
    assert "_id" not in row


def test_delayed_packets_order_by_measurement_time_with_latest_window(store):
    store.ingest(observation(sample_id="s1", ts_utc="2026-10-12T12:02:00Z"))
    store.ingest(observation(sample_id="s2", ts_utc="2026-10-12T12:00:00Z"))
    store.ingest(observation(sample_id="s3", ts_utc="2026-10-12T12:01:00Z"))
    assert [row["sample_id"] for row in store.recent_observations(limit=2)] == ["s3", "s1"]
    assert store.latest_observation()["sample_id"] == "s1"


def test_stream_identity_and_source_filter_keep_synthetic_separate(store):
    store.ingest(observation())
    store.ingest(observation(source="synthetic"))
    store.ingest(observation(device_id="esp32-tray-02"))
    assert len(store.recent_observations(source="hardware")) == 2
    assert len(store.recent_observations(device_id="esp32-tray-01", source="hardware")) == 1
    assert len(store.list_devices()) == 3
    assert all(row["observation_count"] == 1 for row in store.list_devices())
    assert all(row["latest_ts_utc"] == "2026-10-12T12:00:00.000Z" for row in store.list_devices())
    assert store.device_states() == {}


@pytest.mark.parametrize("changes", [
    {"sample_id": ""}, {"sample_id": "s" * 97}, {"sample_id": "../sample"}, {"sample_id": None},
    {"source": "live"}, {"air_temp_c": 81}, {"air_temp_c": float("nan")}, {"air_temp_c": True},
    {"relative_humidity_pct": 101}, {"bus_voltage_v": 37}, {"light_lux": -1},
    {"air_temp_c": None}, {"pump_on": 2}, {"device_id": "../tray"},
    {"ts_utc": "2026-10-12T12:00:00"}, {"received_at_utc": "2026-10-12T12:00:00"},
    {"extra": "x" * 16385},
])
def test_invalid_packet_does_not_enter_database(store, changes):
    with pytest.raises(ValueError):
        store.ingest(observation(**changes))
    assert store._client.collection.rows == []


@pytest.mark.parametrize("kwargs", [{"limit": True}, {"limit": 0}, {"limit": 10001}, {"source": "live"}, {"device_id": "../tray"}])
def test_invalid_reads_rejected(store, kwargs):
    with pytest.raises(ValueError):
        store.recent_observations(**kwargs)


@pytest.mark.parametrize("uri", [
    "mongodb://user:secret@db.example.com:27017/?tls=false",
    "mongodb+srv://user:secret@cluster.example.com/?ssl=false",
    "mongodb://db.example.com/?tlsInsecure=true",
    "mongodb://db.example.com/?tlsAllowInvalidCertificates=true",
    "mongodb://db.example.com/?tlsAllowInvalidHostnames=true",
    "https://user:secret@db.example.com", "mongodb://",
])
def test_unsafe_or_invalid_configuration_is_redacted(uri):
    with pytest.raises(ValueError) as error:
        MongoTelemetryStore(uri)
    assert uri not in str(error.value)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("uri, tls", [
    ("mongodb://localhost:27017", None), ("mongodb://127.0.0.1:27017", None),
    ("mongodb://[::1]:27017", None),
    ("mongodb://localhost:27017,db.example.com:27017", True),
    ("mongodb+srv://user:secret@cluster.example.com", True),
    ("mongodb://user:secret@db.example.com:27017", True),
])
def test_client_is_lazy_and_driver_timeouts_tls_are_bounded(monkeypatch, uri, tls):
    calls = []
    client = FakeClient()
    def mongo_client(*args, **kwargs):
        calls.append((args, kwargs))
        return client
    monkeypatch.setitem(sys.modules, "pymongo", SimpleNamespace(MongoClient=mongo_client))
    backend = MongoTelemetryStore(uri)
    assert calls == []
    assert backend.status()["connected"] is True
    options = calls[0][1]
    assert options.get("tls") is tls
    expected_timeout = 8000 if tls else 3000
    assert options["serverSelectionTimeoutMS"] == options["connectTimeoutMS"] == options["socketTimeoutMS"] == expected_timeout
    assert options["timeoutMS"] == expected_timeout
    backend.close()
    assert client.closed is True


def test_backend_failures_never_echo_credentials(monkeypatch):
    uri = "mongodb://alice:secret123@db.example.com"
    def fail(*args, **kwargs):
        raise RuntimeError(f"Unable to connect to {uri}")
    monkeypatch.setitem(sys.modules, "pymongo", SimpleNamespace(MongoClient=fail))
    backend = MongoTelemetryStore(uri)
    with pytest.raises(MongoTelemetryUnavailable) as error:
        backend.recent_observations()
    assert "secret123" not in str(error.value)
    assert "db.example.com" not in str(error.value)
    assert error.value.__suppress_context__ is True
    status = backend.status()
    assert status["connected"] is False
    assert "secret123" not in str(status)


def test_insert_and_index_errors_are_redacted(store, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("mongodb://user:secret123@private.example.com")
    monkeypatch.setattr(store._client.collection, "create_index", fail)
    with pytest.raises(MongoTelemetryUnavailable) as error:
        store.ingest(observation())
    assert "secret123" not in str(error.value)
    assert store._client.collection.rows == []


def test_naive_bson_read_is_treated_as_utc(store):
    store.ingest(observation())
    document = store._client.collection.rows[0]
    document["ts_utc"] = document["ts_utc"].replace(tzinfo=None)
    assert store.latest_observation()["ts_utc"] == "2026-10-12T12:00:00.000Z"
