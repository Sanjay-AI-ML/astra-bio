"""Measured tray-cycle capture and deliberately guarded endpoint response fitting.

This optional research pipeline never replaces the planner's reference model.
Experiment groups, not correlated tray rows, supply independent replication.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "measurements" / "crop_cycles.csv"
DEFAULT_REPORT = ROOT / "data" / "reports" / "crop-response.json"
SCHEMA_VERSION = "astra-bio.crop-response.v1"
FEATURES = (
    "grow_days", "daily_light_integral_mol_m2_day", "mean_temperature_c",
    "mean_relative_humidity_pct", "mean_co2_ppm", "net_makeup_water_l_per_m2_day",
    "lighting_kwh_per_m2_day", "nutrient_ec_ms_cm", "nutrient_ph", "plants_per_m2",
)
CSV_FIELDS = (
    "cycle_id", "independent_group_id", "shared_resource_group_id", "tray_id",
    "crop_species", "cultivar", "environment_id", "cultivation_system",
    "evidence_setting", "start_basis", "start_date", "harvest_date", "area_m2",
    "fresh_edible_harvest_kg", "mass_basis", "observation_type", "source_reference",
    "environment_coverage_pct", "mean_ppfd_umol_m2_s", "photoperiod_hours",
    "mean_temperature_c", "mean_relative_humidity_pct", "mean_co2_ppm",
    "net_makeup_water_l_per_m2_day", "lighting_kwh_per_m2_day", "nutrient_ec_ms_cm",
    "nutrient_ph", "plants_per_m2", "notes",
)
LIMITATIONS = [
    "Observational endpoint association; coefficients do not establish causal stress responses.",
    "Independent group IDs and measurement provenance must be reviewed by the experimenter.",
    "Predictions are restricted to the same cultivar, environment, cultivation system and age basis.",
    "No daily growth curve, untested crop, new-facility or spaceflight transfer is established.",
    "The planner and hardware control never use this optional fitted research artifact automatically.",
]


def _numeric(value: object, field: str, *, optional: bool = False) -> float | None:
    if optional and (value is None or str(value).strip() == ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite measured number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite measured number.") from exc
    if not isfinite(number):
        raise ValueError(f"{field} must be a finite measured number.")
    return number


@dataclass(frozen=True)
class CropTrial:
    cycle_id: str
    independent_group_id: str
    shared_resource_group_id: str
    tray_id: str
    crop_species: str
    cultivar: str
    environment_id: str
    cultivation_system: str
    evidence_setting: str
    start_basis: str
    start_date: str
    harvest_date: str
    area_m2: float
    fresh_edible_harvest_kg: float
    source_reference: str
    environment_coverage_pct: float
    measured_features: dict[str, float | None]
    notes: str

    @property
    def profile(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in (
            "crop_species", "cultivar", "environment_id", "cultivation_system",
            "evidence_setting", "start_basis",
        )}

    @property
    def yield_kg_per_m2(self) -> float:
        return self.fresh_edible_harvest_kg / self.area_m2


def validate_crop_trials(rows: Iterable[Mapping[str, object]]) -> list[CropTrial]:
    """Validate raw measured records without converting summaries into replicates.

    One row represents ONE final fresh edible harvest of one tray-cycle. Repeated
    cuts and plant images belong in other datasets, not duplicate cycle rows.
    """
    records: list[CropTrial] = []
    ids: set[str] = set()
    physical_cycles: set[tuple[str, str, str, str]] = set()
    shared_groups: dict[tuple[str, str], str] = {}
    for row in rows:
        text = {key: str(row.get(key, "")).strip() for key in CSV_FIELDS}
        mandatory = CSV_FIELDS[:12] + ("source_reference",)
        if any(not text[key] or row.get(key) is None for key in mandatory):
            raise ValueError("Every cycle needs identity, independent/shared-resource groups, profile, dates and source provenance.")
        if text["observation_type"] != "crop_cycle" or text["mass_basis"] != "fresh_edible":
            raise ValueError("Only measured crop_cycle records with fresh_edible mass are accepted; no published summaries or synthetic rows.")
        if text["evidence_setting"] not in ("terrestrial_controlled", "spaceflight"):
            raise ValueError("evidence_setting must be terrestrial_controlled or spaceflight.")
        if text["start_basis"] not in ("sowing", "transplant"):
            raise ValueError("start_basis must distinguish sowing from transplant.")
        try:
            start, end = date.fromisoformat(text["start_date"]), date.fromisoformat(text["harvest_date"])
        except ValueError as exc:
            raise ValueError("Cycle dates must be ISO YYYY-MM-DD dates.") from exc
        grow_days = (end - start).days
        if grow_days <= 0:
            raise ValueError("Harvest must be after the measured cycle start.")
        physical_key = (text["environment_id"], text["tray_id"], text["start_date"], text["harvest_date"])
        if text["cycle_id"] in ids or physical_key in physical_cycles:
            raise ValueError("Duplicate tray-cycle measurements would inflate sample count and leak validation.")
        ids.add(text["cycle_id"])
        physical_cycles.add(physical_key)
        shared_key = (text["environment_id"], text["shared_resource_group_id"])
        prior_group = shared_groups.setdefault(shared_key, text["independent_group_id"])
        if prior_group != text["independent_group_id"]:
            raise ValueError("Trays sharing a resource/experimental run must share an independent group; otherwise holdouts leak.")
        area = _numeric(row.get("area_m2"), "area_m2")
        mass = _numeric(row.get("fresh_edible_harvest_kg"), "fresh_edible_harvest_kg")
        coverage = _numeric(row.get("environment_coverage_pct"), "environment_coverage_pct")
        if area <= 0 or mass < 0 or not 0 <= coverage <= 100:
            raise ValueError("Area must be positive, mass nonnegative, and measured coverage between 0 and 100 percent.")
        values = {key: _numeric(row.get(key), key, optional=True) for key in (
            "mean_ppfd_umol_m2_s", "photoperiod_hours", "mean_temperature_c",
            "mean_relative_humidity_pct", "mean_co2_ppm", "net_makeup_water_l_per_m2_day",
            "lighting_kwh_per_m2_day", "nutrient_ec_ms_cm", "nutrient_ph", "plants_per_m2",
        )}
        nonnegative = set(values) - {"mean_temperature_c"}
        if any(values[key] is not None and values[key] < 0 for key in nonnegative):
            raise ValueError("Measured light, humidity, CO2, water, energy, EC, pH and density must be nonnegative.")
        for field, ceiling in (("photoperiod_hours", 24), ("mean_relative_humidity_pct", 100), ("nutrient_ph", 14)):
            if values[field] is not None and values[field] > ceiling:
                raise ValueError(f"{field} exceeds its physical range.")
        ppfd, light_hours = values.pop("mean_ppfd_umol_m2_s"), values.pop("photoperiod_hours")
        values["daily_light_integral_mol_m2_day"] = None if ppfd is None or light_hours is None else ppfd * light_hours * .0036
        values["grow_days"] = float(grow_days)
        records.append(CropTrial(
            **{key: text[key] for key in mandatory if key != "source_reference"},
            area_m2=area, fresh_edible_harvest_kg=mass, source_reference=text["source_reference"],
            environment_coverage_pct=coverage, measured_features=values, notes=text["notes"],
        ))
    return records


def load_crop_trials(path: str | Path = DEFAULT_CSV) -> list[CropTrial]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(CSV_FIELDS) <= set(reader.fieldnames):
            raise ValueError("Crop-cycle CSV is missing required schema columns; use the blank capture template.")
        return validate_crop_trials(reader)


def _fingerprint(records: list[CropTrial]) -> str:
    raw = json.dumps([asdict(row) for row in sorted(records, key=lambda row: row.cycle_id)], sort_keys=True, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _inside_support(training: np.ndarray, query: np.ndarray) -> bool:
    """Require joint convex-hull support, not merely separate coordinate ranges.

    A HiGHS feasibility problem asks whether query = sum(w_i * training_i),
    w_i >= 0, sum(w_i) = 1. Solver failures refuse prediction.
    """
    if np.any(query < training.min(axis=0) - 1e-8) or np.any(query > training.max(axis=0) + 1e-8):
        return False
    import highspy  # Already a project dependency; no extra training dependency.
    matrix = np.vstack((np.ones(len(training)), training.T))
    target = np.concatenate(([1.0], query))
    nrows, ncols = matrix.shape
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = ncols, nrows
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = [0.] * ncols, [0.] * ncols, [highspy.kHighsInf] * ncols
    lp.row_lower_, lp.row_upper_ = target.tolist(), target.tolist()
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = list(range(0, (ncols + 1) * nrows, nrows))
    lp.a_matrix_.index_ = np.tile(np.arange(nrows), ncols).tolist()
    lp.a_matrix_.value_ = matrix.flatten(order="F").tolist()
    solver = highspy.Highs()
    # HiGHS uses a process-global scheduler; match the existing planner's setting.
    solver.setOptionValue("threads", 1)
    solver.setOptionValue("output_flag", False)
    solver.setOptionValue("time_limit", 2.)
    solver.setOptionValue("primal_feasibility_tolerance", 1e-8)
    solver.passModel(lp)
    solver.run()
    return solver.getModelStatus() == highspy.HighsModelStatus.kOptimal


def _metrics(errors: list[tuple[str, float]]) -> dict:
    # Every independent experiment gets equal influence regardless of tray count.
    groups = sorted({group for group, _ in errors})
    if not groups:
        return {"independent_group_count": 0, "mae_kg_per_m2": None, "rmse_kg_per_m2": None, "bias_kg_per_m2": None}
    grouped = [np.asarray([error for item, error in errors if item == group]) for group in groups]
    return {
        "independent_group_count": len(groups),
        "mae_kg_per_m2": float(np.mean([np.mean(np.abs(values)) for values in grouped])),
        "rmse_kg_per_m2": float(np.sqrt(np.mean([np.mean(values ** 2) for values in grouped]))),
        "bias_kg_per_m2": float(np.mean([np.mean(values) for values in grouped])),
    }


def fit_crop_response(
    trials: Iterable[CropTrial], *, holdout_groups: Iterable[str],
    features: Iterable[str] = ("daily_light_integral_mol_m2_day", "mean_temperature_c", "net_makeup_water_l_per_m2_day"),
    alpha: float = 1.,
) -> dict:
    """Fit one optional ridge endpoint model with explicit independent holdouts.

    Minimum group/coverage gates are conservative project design choices, not a
    universal scientific sample-size rule. Alpha is prespecified, never optimized
    on holdout results. Retain the holdout unchanged when iterating the model.
    """
    records, chosen, held = list(trials), list(features), set(holdout_groups)
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= set(FEATURES):
        raise ValueError("Choose unique supported measured response features.")
    if isinstance(alpha, bool) or not isfinite(alpha) or alpha <= 0:
        raise ValueError("Ridge alpha must be finite and positive, specified before evaluating holdouts.")
    groups = {row.independent_group_id for row in records}
    if held - groups:
        raise ValueError("Holdout IDs must refer to actual independent experiment groups.")
    train = [row for row in records if row.independent_group_id not in held]
    test = [row for row in records if row.independent_group_id in held]
    train_groups = sorted(groups - held)
    report = {
        "schema_version": SCHEMA_VERSION, "status": "insufficient_data" if records else "awaiting_measurements",
        "model_kind": "group-weighted standardized ridge fresh-edible endpoint association",
        "active_in_planner": False, "ready_for_hardware_control": False,
        "source_sha256": _fingerprint(records), "record_count": len(records), "features": chosen,
        "training_group_ids": train_groups, "holdout_group_ids": sorted(held),
        "training_record_count": len(train), "holdout_record_count": len(test),
        "minimum_training_groups": max(12, 4 * (len(chosen) + 1)), "minimum_holdout_groups": 3,
        "minimum_measured_coverage_pct": 80., "alpha": alpha,
        "source_references": sorted({row.source_reference for row in records}),
        "issues": [], "validation": None, "parameters": None, "limitations": list(LIMITATIONS),
    }
    if len({tuple(row.profile.values()) for row in records}) > 1:
        report["issues"].append("Mixed cultivar/environment/system/age-basis profiles cannot be pooled; fit one profile at a time.")
    if len(train_groups) < report["minimum_training_groups"] or len(held) < 3:
        report["issues"].append("Insufficient independent training/held-out experiments; correlated trays are not independent cycles.")
    missing = sorted({name for row in records for name in chosen if row.measured_features.get(name) is None})
    if missing:
        report["issues"].append("Missing measured features: " + ", ".join(missing) + ". No imputation or resource-budget substitution.")
    if any(row.environment_coverage_pct < 80 for row in records):
        report["issues"].append("At least one cycle has less than 80% measured environmental coverage.")
    if "grow_days" not in chosen and len({row.measured_features["grow_days"] for row in records}) > 1:
        report["issues"].append("Harvest age varies; include grow_days as a measured predictor or restrict to one age.")
    if report["issues"]:
        return report
    x = np.asarray([[row.measured_features[name] for name in chosen] for row in train], dtype=float)
    y = np.asarray([row.yield_kg_per_m2 for row in train])
    counts = Counter(row.independent_group_id for row in train)
    weights = np.asarray([1. / counts[row.independent_group_id] for row in train])
    means = np.average(x, axis=0, weights=weights)
    scales = np.sqrt(np.average((x - means) ** 2, axis=0, weights=weights))
    if np.any(scales < 1e-9):
        report["issues"].append("Selected exposures have no measured variation; a stress response cannot be identified.")
        return report
    z = (x - means) / scales
    if np.linalg.matrix_rank(z) != len(chosen) or np.linalg.cond(z) > 1e6:
        report["issues"].append("Selected exposures are collinear or ill-conditioned; separate water, light and temperature effects cannot be identified.")
        return report
    design = np.column_stack((np.ones(len(x)), z))
    penalty = np.diag([0.] + [alpha] * len(chosen))
    beta = np.linalg.solve(design.T @ (weights[:, None] * design) + penalty, design.T @ (weights * y))
    baseline = float(np.average(y, weights=weights))
    report["profile"] = train[0].profile
    report["parameters"] = {
        "intercept_kg_per_m2": float(beta[0]), "standardized_coefficients": beta[1:].tolist(),
        "training_feature_means": means.tolist(), "training_feature_scales": scales.tolist(),
        "joint_support_standardized": np.unique(z, axis=0).tolist(),
        "fixed_harvest_age_days": None if "grow_days" in chosen else train[0].measured_features["grow_days"],
        "training_mean_yield_kg_per_m2": baseline,
    }
    errors, baseline_errors, predictions = [], [], []
    for row in test:
        query = (np.asarray([row.measured_features[name] for name in chosen]) - means) / scales
        supported = _inside_support(z, query)
        predicted = float(beta[0] + query @ beta[1:]) if supported else None
        if predicted is not None and predicted < 0:
            predicted, supported = None, False
        if supported:
            errors.append((row.independent_group_id, predicted - row.yield_kg_per_m2))
            baseline_errors.append((row.independent_group_id, baseline - row.yield_kg_per_m2))
        predictions.append({"cycle_id": row.cycle_id, "independent_group_id": row.independent_group_id,
                            "observed_yield_kg_per_m2": row.yield_kg_per_m2, "predicted_yield_kg_per_m2": predicted,
                            "supported": supported})
    model_metrics, base_metrics = _metrics(errors), _metrics(baseline_errors)
    report["validation"] = {"kind": "explicit held-out whole-experiment groups; equal group weighting",
                            "response_model": model_metrics, "training_mean_baseline": base_metrics,
                            "unsupported_holdout_record_count": sum(not row["supported"] for row in predictions),
                            "records": predictions}
    adequate = model_metrics["independent_group_count"] >= 3 and all(row["supported"] for row in predictions)
    improved = adequate and model_metrics["mae_kg_per_m2"] < base_metrics["mae_kg_per_m2"]
    report["status"] = "experimental_fitted" if improved else "failed_validation"
    if not adequate:
        report["issues"].append("Held-out measurements include unsupported joint conditions or fewer than three supported independent experiments.")
    elif not improved:
        report["issues"].append("Held-out MAE does not improve on the training-mean endpoint baseline; keep the reference model.")
    return report


def predict_crop_response(report: Mapping, trial: CropTrial) -> dict:
    """Return unknown when evidence, profile, harvest age or joint support fails."""
    result = {"status": "unavailable", "predicted_yield_kg_per_m2": None, "expected_harvest_kg": None,
              "ready_for_hardware_control": False}
    if report.get("schema_version") != SCHEMA_VERSION or report.get("status") != "experimental_fitted":
        return {**result, "reason": "No eligible independently held-out experimental response model."}
    if trial.profile != report.get("profile"):
        return {**result, "status": "unsupported_profile", "reason": "Cultivar/environment/system/age basis differs from measured training profile."}
    params, chosen = report["parameters"], report["features"]
    if trial.environment_coverage_pct < 80 or any(trial.measured_features.get(key) is None for key in chosen):
        return {**result, "reason": "Measured exposures are missing or coverage is insufficient."}
    fixed_age = params["fixed_harvest_age_days"]
    if fixed_age is not None and trial.measured_features.get("grow_days") != fixed_age:
        return {**result, "status": "unsupported_age", "reason": "The model does not fit a harvest-age response."}
    query = (np.asarray([trial.measured_features[key] for key in chosen]) - np.asarray(params["training_feature_means"])) / np.asarray(params["training_feature_scales"])
    if not _inside_support(np.asarray(params["joint_support_standardized"]), query):
        return {**result, "status": "unsupported_conditions", "reason": "Conditions are outside joint measured training support; extrapolation is refused."}
    value = float(params["intercept_kg_per_m2"] + query @ np.asarray(params["standardized_coefficients"]))
    if not isfinite(value) or value < 0:
        return {**result, "reason": "The fitted association gives an invalid yield; it is not clipped to a reassuring number."}
    return {**result, "status": "experimental_estimate", "predicted_yield_kg_per_m2": value,
            "expected_harvest_kg": value * trial.area_m2, "reason": "Within measured profile and joint support; observational research estimate."}


def current_crop_response_status(csv_path: str | Path = DEFAULT_CSV, report_path: str | Path = DEFAULT_REPORT) -> dict:
    """Read-only API-friendly status; stale evidence never becomes an active model."""
    status = {"schema_version": SCHEMA_VERSION, "status": "awaiting_measurements", "record_count": 0,
              "independent_group_count": 0, "active_in_planner": False, "ready_for_hardware_control": False,
              "validation": None, "issues": [], "limitations": list(LIMITATIONS)}
    if not Path(csv_path).exists():
        return status
    try:
        records = load_crop_trials(csv_path)
        status.update(record_count=len(records), independent_group_count=len({row.independent_group_id for row in records}))
        if not records:
            return status
        if not Path(report_path).exists():
            return {**status, "status": "measurements_pending_fit"}
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if report.get("schema_version") != SCHEMA_VERSION or report.get("source_sha256") != _fingerprint(records):
            return {**status, "status": "stale_report", "issues": ["Fit report does not match current measured records."]}
        return {**status, **{key: report.get(key) for key in (
            "status", "features", "profile", "training_group_ids", "holdout_group_ids", "validation", "issues",
            "source_references", "minimum_training_groups", "minimum_holdout_groups",
        )}}
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return {**status, "status": "invalid_measurements", "issues": [str(exc)]}
