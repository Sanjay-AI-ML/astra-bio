"""Synthetic unit fixtures verify pipeline guards, not biological performance."""
import csv
import json
from dataclasses import replace

import numpy as np
import pytest

from astra_bio.crop_trials import (
    CSV_FIELDS, _inside_support, current_crop_response_status, fit_crop_response,
    load_crop_trials, predict_crop_response, validate_crop_trials,
)


def row(index, *, light=100., group=None):
    return {
        "cycle_id": f"cycle-{index}", "independent_group_id": group or f"run-{index}",
        "shared_resource_group_id": group or f"reservoir-run-{index}", "tray_id": f"tray-{index}",
        "crop_species": "Lactuca sativa", "cultivar": "unit-test-fixture", "environment_id": "test-lab",
        "cultivation_system": "NFT", "evidence_setting": "terrestrial_controlled", "start_basis": "transplant",
        "start_date": "2026-01-01", "harvest_date": "2026-01-31", "area_m2": "1",
        "fresh_edible_harvest_kg": str(1 + light * .01), "mass_basis": "fresh_edible",
        "observation_type": "crop_cycle", "source_reference": f"unit-test fixture only: {index}",
        "environment_coverage_pct": "95", "mean_ppfd_umol_m2_s": str(light), "photoperiod_hours": "16",
        "mean_temperature_c": "23", "mean_relative_humidity_pct": "65", "mean_co2_ppm": "800",
        "net_makeup_water_l_per_m2_day": "1.4", "lighting_kwh_per_m2_day": "2",
        "nutrient_ec_ms_cm": "1.6", "nutrient_ph": "5.8", "plants_per_m2": "20", "notes": "Synthetic unit-test fixture; never biological evidence.",
    }


def trials():
    values = [row(i, light=100 + i * 10) for i in range(12)]
    values += [row(12 + i, light=125 + 30 * i) for i in range(3)]
    return validate_crop_trials(values)


def fitted():
    return fit_crop_response(trials(), holdout_groups=["run-12", "run-13", "run-14"], features=["daily_light_integral_mol_m2_day"])


def test_csv_requires_real_single_cycle_fresh_edible_basis_and_provenance():
    for change in ({"observation_type": "published_summary"}, {"mass_basis": "dry_mass"}, {"source_reference": ""}):
        with pytest.raises(ValueError):
            validate_crop_trials([{**row(1), **change}])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_crop_trials([row(1), {**row(1), "cycle_id": "renamed-duplicate"}])
    with pytest.raises(ValueError, match="finite"):
        validate_crop_trials([{**row(1), "fresh_edible_harvest_kg": "nan"}])
    with pytest.raises(ValueError, match="after"):
        validate_crop_trials([{**row(1), "harvest_date": "2025-12-31"}])


def test_shared_reservoir_cannot_be_split_into_fake_independent_runs():
    with pytest.raises(ValueError, match="leak"):
        validate_crop_trials([row(1), {**row(2), "shared_resource_group_id": "reservoir-run-1"}])


def test_ridge_training_is_group_split_and_uses_training_only_scaling():
    report = fitted()
    assert report["status"] == "experimental_fitted"
    assert not set(report["training_group_ids"]) & set(report["holdout_group_ids"])
    train_light = np.array([100 + i * 10 for i in range(12)]) * 16 * .0036
    assert report["parameters"]["training_feature_means"] == pytest.approx([train_light.mean()])
    assert report["validation"]["response_model"]["independent_group_count"] == 3
    assert report["validation"]["response_model"]["mae_kg_per_m2"] < report["validation"]["training_mean_baseline"]["mae_kg_per_m2"]
    assert report["active_in_planner"] is False
    assert report["ready_for_hardware_control"] is False


def test_many_correlated_trays_do_not_pass_independent_cycle_gate():
    records = validate_crop_trials([row(i, light=100 + i, group="same-run") for i in range(100)])
    report = fit_crop_response(records, holdout_groups=[], features=["daily_light_integral_mol_m2_day"])
    assert report["status"] == "insufficient_data"
    assert report["parameters"] is None
    assert len(report["training_group_ids"]) == 1
    assert fit_crop_response([], holdout_groups=[])["status"] == "awaiting_measurements"


def test_missing_environment_features_and_constant_exposures_do_not_fit():
    records = trials()
    records[0] = replace(records[0], measured_features={**records[0].measured_features, "daily_light_integral_mol_m2_day": None})
    assert fit_crop_response(records, holdout_groups=["run-12", "run-13", "run-14"], features=["daily_light_integral_mol_m2_day"])["parameters"] is None
    records = trials()
    report = fit_crop_response(records, holdout_groups=["run-12", "run-13", "run-14"], features=["mean_temperature_c"])
    assert any("no measured variation" in issue for issue in report["issues"])
    records[0] = replace(records[0], environment_coverage_pct=30)
    assert fit_crop_response(records, holdout_groups=["run-12", "run-13", "run-14"], features=["daily_light_integral_mol_m2_day"])["parameters"] is None


def test_prediction_refuses_new_cultivar_age_and_unmeasured_resource_regime():
    report, sample = fitted(), trials()[-1]
    assert predict_crop_response(report, sample)["status"] == "experimental_estimate"
    assert predict_crop_response(report, replace(sample, cultivar="new-cultivar"))["status"] == "unsupported_profile"
    altered = replace(sample, measured_features={**sample.measured_features, "grow_days": 45})
    assert predict_crop_response(report, altered)["status"] == "unsupported_age"
    altered = replace(sample, measured_features={**sample.measured_features, "daily_light_integral_mol_m2_day": 50})
    result = predict_crop_response(report, altered)
    assert result["status"] == "unsupported_conditions"
    assert result["expected_harvest_kg"] is None


def test_joint_support_guard_refuses_unseen_combination_inside_scalar_ranges():
    measured = np.array([[0., 0.], [0., 1.], [1., 0.]])
    assert _inside_support(measured, np.array([.2, .2]))
    assert not _inside_support(measured, np.array([.8, .8]))
    assert not _inside_support(measured, np.array([1.1, .1]))


def test_unsupported_holdouts_fail_validation_without_fake_error_or_clipping():
    records = trials()
    records[-1] = replace(records[-1], measured_features={**records[-1].measured_features, "daily_light_integral_mol_m2_day": 100})
    report = fit_crop_response(records, holdout_groups=["run-12", "run-13", "run-14"], features=["daily_light_integral_mol_m2_day"])
    assert report["status"] == "failed_validation"
    assert report["validation"]["unsupported_holdout_record_count"] == 1
    assert report["validation"]["records"][-1]["predicted_yield_kg_per_m2"] is None


def test_status_detects_stale_data_and_blank_template(tmp_path):
    path, output = tmp_path / "cycles.csv", tmp_path / "model.json"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
    assert load_crop_trials(path) == []
    assert current_crop_response_status(path, output)["status"] == "awaiting_measurements"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(row(1))
    output.write_text(json.dumps(fitted()), encoding="utf-8")
    assert current_crop_response_status(path, output)["status"] == "stale_report"

