"""Validate real crop-cycle CSVs and fit optional guarded response associations."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astra_bio.crop_trials import DEFAULT_CSV, DEFAULT_REPORT, fit_crop_response, load_crop_trials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--holdout-group", action="append", default=[], help="Predeclared whole independent experiment group; repeat this option.")
    parser.add_argument("--features", nargs="+", default=["daily_light_integral_mol_m2_day", "mean_temperature_c", "net_makeup_water_l_per_m2_day"])
    parser.add_argument("--alpha", type=float, default=1.)
    args = parser.parse_args()
    try:
        report = fit_crop_response(load_crop_trials(args.csv), holdout_groups=args.holdout_group, features=args.features, alpha=args.alpha)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": report["status"], "record_count": report["record_count"], "issues": report["issues"], "output": str(args.output)}, indent=2))
    return 0 if report["status"] == "experimental_fitted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
