"""Fit a monotone curve from source measurements with whole-plant holdouts."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astra_bio.measured_growth import DEFAULT_CSV, DEFAULT_REPORT, fit_measured_growth, load_growth_observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--holdout-plant", action="append", required=True, help="Hold out ALL days for this plant; repeat option.")
    args = parser.parse_args()
    try:
        report = fit_measured_growth(load_growth_observations(args.csv), holdout_plant_ids=args.holdout_plant)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    metrics = report["validation"]
    print(json.dumps({"status": report["status"], "independent_cycle_count": report["independent_cycle_count"],
                      "curve_metrics": metrics["curve"] if metrics else None,
                      "issues": report["issues"], "output": str(args.output)}, indent=2))
    return 0 if report["status"] == "experimental_fitted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
