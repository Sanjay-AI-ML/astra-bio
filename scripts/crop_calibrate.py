"""Reproduce the small NASA held-out endpoint diagnostic from pinned source data."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astra_bio.crop_growth import load_observations, calibrate_harvests

if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "data" / "reports" / "crop-calibration.json"
    report = calibrate_harvests(load_observations(), holdout_ids=["nasa_rlss_1992_cycle_2"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "validation": report["validation"]}, indent=2))
