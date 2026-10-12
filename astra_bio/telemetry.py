"""Deterministic, explicitly synthetic observations for the offline demonstration."""

from datetime import datetime, timedelta, timezone
import math
from pathlib import Path

from astra_bio.storage import DEFAULT_DB, init_db, insert_observation, latest_observation


def seed_demo(path: str | Path = DEFAULT_DB, samples: int = 120) -> int:
    """Only populate an empty database; never overwrite real observations."""
    init_db(path)
    if latest_observation(path) is not None:
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for index in range(samples):
        phase = index / 13
        payload = {
            "ts_utc": (now - timedelta(minutes=samples - 1 - index)).isoformat(),
            "device_id": "demo-tray-01", "source": "synthetic",
            "air_temp_c": round(23.5 + 0.5 * math.sin(phase), 2),
            "relative_humidity_pct": round(62 + 3 * math.sin(phase / 2), 2),
            "solution_temp_c": round(21 + 0.25 * math.cos(phase), 2),
            "light_lux": round(11500 + 500 * math.sin(phase), 2),
            "bus_voltage_v": 12.0, "bus_current_a": 1.5,
            "bus_power_w": 18.0, "low_water": 0,
            "pump_on": 0, "fan_on": 1, "light_on": 1,
            "note": "Generated demo series; no hardware connected.",
        }
        insert_observation(payload, path=path)
    return samples


if __name__ == "__main__":
    print(f"Added {seed_demo()} synthetic observations to {DEFAULT_DB}")
