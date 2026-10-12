"""Synthetic fixtures test growth-curve leakage guards, not model accuracy."""
import csv
import json

import pytest

from astra_bio.measured_growth import (
    FIELDS, current_measured_growth_status, fit_measured_growth,
    predict_measured_growth, validate_growth_observations,
)


def rows():
    return [{"observation_id": f"plant-{plant}-day-{day}", "plant_id": f"plant-{plant}",
             "independent_cycle_id": "one-unit-test-cycle", "crop_species": "Lactuca sativa",
             "cultivar": "synthetic-test", "environment_id": "synthetic-test-lab",
             "days_after_transplant": day, "fresh_mass_g": day * 10 + plant,
             "mass_basis": "unspecified_fresh", "source_reference": "synthetic unit fixture only",
             "source_url": "https://example.invalid/unit-test-not-evidence"}
            for plant in range(9) for day in (1, 2, 3, 4)]


def fit():
    return fit_measured_growth(validate_growth_observations(rows()), holdout_plant_ids=["plant-6", "plant-7", "plant-8"])


def test_whole_plant_holdout_prevents_daily_row_leakage():
    report = fit()
    assert report["status"] == "experimental_fitted"
    assert report["training_record_count"] == 24
    assert report["holdout_record_count"] == 12
    assert not set(report["training_plant_ids"]) & set(report["holdout_plant_ids"])
    assert report["parameters"]["fitted_fresh_mass_g"] == pytest.approx([12.5, 22.5, 32.5, 42.5])
    assert report["validation"]["curve"]["plant_count"] == 3
    assert report["validation"]["curve"]["mae_g_per_plant"] == pytest.approx(4.5)
    assert report["validation"]["independent_test_cycle_count"] == 0
    assert report["active_in_planner"] is False


def test_no_growth_extrapolation_or_edible_mass_invention():
    report = fit()
    prediction = predict_measured_growth(report, 2.5, profile=report["profile"])
    assert prediction["predicted_fresh_mass_g_per_plant"] == pytest.approx(27.5)
    assert prediction["mass_basis"] == "unspecified_fresh"
    for age in (0, 5):
        result = predict_measured_growth(report, age, profile=report["profile"])
        assert result["status"] == "unsupported_age"
        assert result["predicted_fresh_mass_g_per_plant"] is None
    assert predict_measured_growth(report, 2, profile={**report["profile"], "cultivar": "new"})["status"] == "unsupported_profile"


def test_curve_fit_is_monotone_without_using_holdout_values():
    records = rows()
    for row in records:
        if row["plant_id"] in {f"plant-{i}" for i in range(6)} and row["days_after_transplant"] == 3:
            row["fresh_mass_g"] = 2
    report = fit_measured_growth(validate_growth_observations(records), holdout_plant_ids=["plant-6", "plant-7", "plant-8"])
    values = report["parameters"]["fitted_fresh_mass_g"]
    assert values == sorted(values)
    assert values[1] == values[2]


def test_duplicate_plants_unknown_holdout_and_pooled_cycles_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_growth_observations(rows() + [rows()[0]])
    with pytest.raises(ValueError, match="complete plants"):
        fit_measured_growth(validate_growth_observations(rows()), holdout_plant_ids=["unknown"])
    samples = rows()
    samples[0]["independent_cycle_id"] = "other-cycle"
    report = fit_measured_growth(validate_growth_observations(samples), holdout_plant_ids=["plant-6", "plant-7", "plant-8"])
    assert report["status"] == "insufficient_data"
    assert report["parameters"] is None


def test_small_samples_do_not_claim_fitted_curve_and_invalid_mass_fails():
    report = fit_measured_growth(validate_growth_observations(rows()[:4]), holdout_plant_ids=[])
    assert report["status"] == "insufficient_data"
    assert report["validation"] is None
    with pytest.raises(ValueError, match="finite"):
        validate_growth_observations([{**rows()[0], "fresh_mass_g": float("nan")}])


def test_source_changes_invalidate_saved_report(tmp_path):
    path, output = tmp_path / "growth.csv", tmp_path / "growth.json"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows())
    output.write_text(json.dumps(fit()), encoding="utf-8")
    assert current_measured_growth_status(path, output)["status"] == "experimental_fitted"
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writerow({**rows()[0], "observation_id": "new-plant-day", "plant_id": "new-plant"})
    assert current_measured_growth_status(path, output)["status"] == "stale_report"
