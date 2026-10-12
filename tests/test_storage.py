from datetime import datetime, timezone

import pytest

from astra_bio.storage import insert_observation, latest_observation, recent_observations
from astra_bio.telemetry import seed_demo


def observation(**changes):
    payload = {"ts_utc": "2026-10-10T12:00:00Z", "source": "synthetic", "device_id": "test", "air_temp_c": 23.5, "low_water": False}
    return payload | changes


def test_roundtrip_orders_by_instant_and_keeps_provenance(tmp_path):
    database = tmp_path / "observations.sqlite"
    insert_observation(observation(ts_utc="2026-10-10T18:00:00+05:30"), database)
    insert_observation(observation(ts_utc="2026-10-10T12:01:00Z", source="hardware"), database)
    assert latest_observation(database)["ts_utc"] == "2026-10-10T12:30:00.000Z"
    rows = recent_observations(path=database)
    assert [row["source"] for row in rows] == ["hardware", "synthetic"]
    assert rows[-1]["low_water"] == 0
    assert '"source":"hardware"' in rows[0]["raw_json"]


@pytest.mark.parametrize("changes", [
    {"source": None}, {"source": "live"}, {"device_id": ""},
    {"device_id": "../tray"}, {"air_temp_c": None},
    {"ts_utc": "2026-10-10T12:00:00"}, {"air_temp_c": float("nan")},
    {"relative_humidity_pct": 110}, {"light_lux": -1},
    {"low_water": 2}, {"pump_on": "false"},
])
def test_invalid_measurements_do_not_enter_db(tmp_path, changes):
    database = tmp_path / "observations.sqlite"
    with pytest.raises(ValueError):
        insert_observation(observation(**changes), database)
    assert latest_observation(database) is None


def test_seed_does_not_overwrite_existing_observation(tmp_path):
    database = tmp_path / "observations.sqlite"
    insert_observation(observation(source="hardware"), database)
    assert seed_demo(database, samples=5) == 0
    assert len(recent_observations(path=database)) == 1


def test_seed_is_explicitly_synthetic(tmp_path):
    database = tmp_path / "observations.sqlite"
    assert seed_demo(database, samples=5) == 5
    assert {row["source"] for row in recent_observations(path=database)} == {"synthetic"}
    assert datetime.fromisoformat(latest_observation(database)["ts_utc"].replace("Z", "+00:00")).tzinfo == timezone.utc
