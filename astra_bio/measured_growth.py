"""A source-specific monotone age-to-fresh-mass curve from measured plants.

Holding out whole plants tests within-cycle curve transfer. It does not create
independent crop cycles or identify resource stress effects.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "research" / "growth" / "growth_observations.csv"
DEFAULT_REPORT = ROOT / "data" / "reports" / "measured-growth.json"
SCHEMA_VERSION = "astra-bio.measured-growth.v1"
FIELDS = ("observation_id", "plant_id", "independent_cycle_id", "crop_species", "cultivar",
          "environment_id", "days_after_transplant", "fresh_mass_g", "mass_basis", "source_reference", "source_url")
LIMITATIONS = [
    "Held-out plants share one growing cycle and environment with the training plants.",
    "Plant holdout results are a within-cycle diagnostic, not independent-cycle or habitat validation.",
    "The mass basis is retained from the source; unspecified fresh mass is not edible harvest yield.",
    "Age-to-mass interpolation has no fitted water, electricity, disease or temperature response.",
    "No predictions outside measured ages, cultivars or environments; no repeated-harvest assumption.",
    "This research curve is separate from the planner's batch endpoint and disabled for hardware control.",
]


@dataclass(frozen=True)
class GrowthObservation:
    observation_id: str
    plant_id: str
    independent_cycle_id: str
    crop_species: str
    cultivar: str
    environment_id: str
    days_after_transplant: float
    fresh_mass_g: float
    mass_basis: str
    source_reference: str
    source_url: str

    @property
    def profile(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in ("crop_species", "cultivar", "environment_id", "mass_basis")}


def validate_growth_observations(rows: Iterable[Mapping[str, object]]) -> list[GrowthObservation]:
    records, ids, plant_days = [], set(), set()
    for row in rows:
        values = {key: str(row.get(key, "")).strip() for key in FIELDS}
        if any(not values[key] or row.get(key) is None for key in FIELDS):
            raise ValueError("Every measured growth observation needs a plant, cycle, age, mass basis and source provenance.")
        for field in ("days_after_transplant", "fresh_mass_g"):
            if isinstance(row[field], bool):
                raise ValueError("Measured growth age and fresh mass must be finite nonnegative numbers.")
            try:
                values[field] = float(row[field])
            except (ValueError, TypeError) as exc:
                raise ValueError("Measured growth age and fresh mass must be finite nonnegative numbers.") from exc
            if not isfinite(values[field]) or values[field] < 0:
                raise ValueError("Measured growth age and fresh mass must be finite nonnegative numbers.")
        if values["mass_basis"] not in ("fresh_edible", "fresh_shoot", "whole_plant_fresh", "unspecified_fresh"):
            raise ValueError("Preserve a recognized fresh mass basis; dry mass cannot be relabeled fresh mass.")
        key = values["independent_cycle_id"], values["plant_id"], values["days_after_transplant"]
        if values["observation_id"] in ids or key in plant_days:
            raise ValueError("Duplicate plant/day observations would inflate data and leak validation.")
        ids.add(values["observation_id"])
        plant_days.add(key)
        records.append(GrowthObservation(**values))
    return records


def load_growth_observations(path: str | Path = DEFAULT_CSV) -> list[GrowthObservation]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(FIELDS) <= set(reader.fieldnames):
            raise ValueError("Measured growth CSV is missing required provenance/profile columns.")
        return validate_growth_observations(reader)


def _fingerprint(records: list[GrowthObservation]) -> str:
    raw = json.dumps([asdict(row) for row in sorted(records, key=lambda row: row.observation_id)], sort_keys=True, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _isotonic(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted pool-adjacent-violators fit, with no fitted mechanistic parameters."""
    blocks = []
    for i, (value, weight) in enumerate(zip(values, weights, strict=True)):
        blocks.append([i, i + 1, float(weight), float(value * weight)])
        while len(blocks) > 1 and blocks[-2][3] / blocks[-2][2] > blocks[-1][3] / blocks[-1][2]:
            right, left = blocks.pop(), blocks.pop()
            blocks.append([left[0], right[1], left[2] + right[2], left[3] + right[3]])
    result = np.empty(len(values))
    for start, end, weight, total in blocks:
        result[start:end] = total / weight
    return result


def _metrics(errors: list[tuple[str, float]]) -> dict:
    plants = sorted({plant for plant, _ in errors})
    if not plants:
        return {"plant_count": 0, "mae_g_per_plant": None, "rmse_g_per_plant": None, "bias_g_per_plant": None}
    grouped = [np.asarray([error for key, error in errors if key == plant]) for plant in plants]
    return {
        "plant_count": len(plants),
        "mae_g_per_plant": float(np.mean([np.mean(np.abs(group)) for group in grouped])),
        "rmse_g_per_plant": float(np.sqrt(np.mean([np.mean(group ** 2) for group in grouped]))),
        "bias_g_per_plant": float(np.mean([np.mean(group) for group in grouped])),
    }


def fit_measured_growth(observations: Iterable[GrowthObservation], *, holdout_plant_ids: Iterable[str]) -> dict:
    """Fit training-only age bins; complete plants are assigned to explicit holdout.

    Minimum counts are prototype safeguards, not a statistical power guarantee.
    The published source cycle remains the unit of external evidence.
    """
    records, held = list(observations), set(holdout_plant_ids)
    plants = {row.plant_id for row in records}
    if held - plants:
        raise ValueError("Holdout plant IDs must refer to actual complete plants.")
    train = [row for row in records if row.plant_id not in held]
    test = [row for row in records if row.plant_id in held]
    train_plants, cycles = sorted(plants - held), sorted({row.independent_cycle_id for row in records})
    report = {
        "schema_version": SCHEMA_VERSION, "status": "insufficient_data" if records else "awaiting_measurements",
        "model_kind": "training-plant age means with weighted monotone fit and linear interpolation",
        "source_sha256": _fingerprint(records), "record_count": len(records), "independent_cycle_count": len(cycles),
        "independent_cycle_ids": cycles, "training_plant_ids": train_plants, "holdout_plant_ids": sorted(held),
        "training_record_count": len(train), "holdout_record_count": len(test),
        "minimum_training_plants": 6, "minimum_holdout_plants": 3, "minimum_measured_ages": 4,
        "active_in_planner": False, "ready_for_hardware_control": False,
        "source_urls": sorted({row.source_url for row in records}),
        "issues": [], "validation": None, "parameters": None, "limitations": list(LIMITATIONS),
    }
    if len(cycles) != 1 or len({tuple(row.profile.values()) for row in records}) != 1:
        report["issues"].append("Fit one source cycle and exact crop/cultivar/environment/mass-basis profile at a time.")
    if len(train_plants) < 6 or len(held) < 3 or len({row.days_after_transplant for row in train}) < 4:
        report["issues"].append("Insufficient measured age coverage or complete training/held-out plants.")
    if report["issues"]:
        return report
    age_bins: dict[float, list[float]] = defaultdict(list)
    for row in train:
        age_bins[row.days_after_transplant].append(row.fresh_mass_g)
    ages = np.asarray(sorted(age_bins))
    means = np.asarray([np.mean(age_bins[age]) for age in ages])
    fitted = _isotonic(means, np.asarray([len(age_bins[age]) for age in ages], dtype=float))
    baseline = float(np.mean([np.mean([row.fresh_mass_g for row in train if row.plant_id == plant]) for plant in train_plants]))
    report["profile"] = train[0].profile
    report["parameters"] = {"ages_days_after_transplant": ages.tolist(), "fitted_fresh_mass_g": fitted.tolist(),
                            "training_mean_fresh_mass_g": baseline,
                            "training_plant_count_per_age": [len(age_bins[age]) for age in ages]}
    errors, baseline_errors, scored = [], [], []
    for row in test:
        supported = ages[0] <= row.days_after_transplant <= ages[-1]
        value = float(np.interp(row.days_after_transplant, ages, fitted)) if supported else None
        if supported:
            errors.append((row.plant_id, value - row.fresh_mass_g))
            baseline_errors.append((row.plant_id, baseline - row.fresh_mass_g))
        scored.append({"observation_id": row.observation_id, "plant_id": row.plant_id,
                       "days_after_transplant": row.days_after_transplant, "observed_fresh_mass_g": row.fresh_mass_g,
                       "predicted_fresh_mass_g": value, "supported": bool(supported)})
    fitted_metrics, baseline_metrics = _metrics(errors), _metrics(baseline_errors)
    report["validation"] = {"kind": "whole-plant held-out within ONE source cycle; equal plant weighting",
                            "independent_test_cycle_count": 0, "curve": fitted_metrics,
                            "training_mean_baseline": baseline_metrics,
                            "unsupported_holdout_record_count": sum(not row["supported"] for row in scored), "records": scored}
    improved = (fitted_metrics["plant_count"] >= 3 and all(row["supported"] for row in scored)
                and fitted_metrics["mae_g_per_plant"] < baseline_metrics["mae_g_per_plant"])
    report["status"] = "experimental_fitted" if improved else "failed_validation"
    if not improved:
        report["issues"].append("Held-out plants lack age support or the curve does not improve on the training-mean mass baseline.")
    return report


def predict_measured_growth(report: Mapping, days_after_transplant: float, *, profile: Mapping[str, str]) -> dict:
    result = {"status": "unavailable", "predicted_fresh_mass_g_per_plant": None,
              "mass_basis": report.get("profile", {}).get("mass_basis"), "ready_for_hardware_control": False}
    if report.get("schema_version") != SCHEMA_VERSION or report.get("status") != "experimental_fitted":
        return {**result, "reason": "No eligible source-specific measured growth curve."}
    if dict(profile) != report.get("profile"):
        return {**result, "status": "unsupported_profile", "reason": "Cultivar, environment or mass basis differs from measured source profile."}
    try:
        age = float(days_after_transplant)
    except (ValueError, TypeError) as exc:
        raise ValueError("Growth age must be a finite number of days after transplant.") from exc
    if isinstance(days_after_transplant, bool) or not isfinite(age):
        raise ValueError("Growth age must be a finite number of days after transplant.")
    ages, masses = report["parameters"]["ages_days_after_transplant"], report["parameters"]["fitted_fresh_mass_g"]
    if not ages[0] <= age <= ages[-1]:
        return {**result, "status": "unsupported_age", "reason": "Age is outside observed training ages; extrapolation is refused."}
    return {**result, "status": "source_specific_estimate", "predicted_fresh_mass_g_per_plant": float(np.interp(age, ages, masses)),
            "reason": "Interpolation of measured source plants; one-cycle diagnostic, with no fitted resource response."}


def current_measured_growth_status(csv_path: str | Path = DEFAULT_CSV, report_path: str | Path = DEFAULT_REPORT) -> dict:
    status = {"schema_version": SCHEMA_VERSION, "status": "awaiting_measurements", "record_count": 0,
              "independent_cycle_count": 0, "active_in_planner": False, "ready_for_hardware_control": False,
              "validation": None, "issues": [], "limitations": list(LIMITATIONS)}
    if not Path(csv_path).exists():
        return status
    try:
        records = load_growth_observations(csv_path)
        status.update(record_count=len(records), independent_cycle_count=len({row.independent_cycle_id for row in records}))
        if not Path(report_path).exists():
            return {**status, "status": "measurements_pending_fit" if records else "awaiting_measurements"}
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if report.get("schema_version") != SCHEMA_VERSION or report.get("source_sha256") != _fingerprint(records):
            return {**status, "status": "stale_report", "issues": ["Growth report does not match current measured source records."]}
        metrics = report.get("validation")
        # Browser status avoids all individual rows and potentially huge charts.
        validation = None if not metrics else {key: value for key, value in metrics.items() if key != "records"}
        return {**status, "status": report["status"], "profile": report.get("profile"), "validation": validation,
                "parameters": report.get("parameters"), "training_plant_ids": report.get("training_plant_ids"),
                "holdout_plant_ids": report.get("holdout_plant_ids"), "source_urls": report.get("source_urls"),
                "issues": report.get("issues", [])}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {**status, "status": "invalid_measurements", "issues": [str(exc)]}
