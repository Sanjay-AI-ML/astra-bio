from dataclasses import replace

import pytest

from astra_bio.crop_growth import calibrate_harvests, estimate_led_energy, load_observations, load_reference_crops, predict_growth
from astra_bio.model import default_config
from astra_bio.presets import research_preset


def test_measured_nasa_units_are_fresh_mass_not_dry_mass_or_applied_water():
    reference = load_reference_crops()["lettuce_waldmann_nasa"]
    assert reference.yield_kg_per_m2 == pytest.approx((.072 + .049) / 2 * 480 / 10.6)
    assert reference.net_makeup_water_l_per_m2_day is None
    assert reference.whole_system_kwh_per_m2_day is None
    assert reference.grow_days == 30


def test_prediction_never_allocates_immature_harvest_or_claims_intermediate_fit():
    before = predict_growth("lettuce_batavia", 10, 2)
    ready = predict_growth("lettuce_batavia", 38, 2)
    assert before.available_harvest_kg == 0
    assert before.illustrative_biomass_kg is None
    assert ready.available_harvest_kg == pytest.approx(1.56 * 2)
    assert ready.observed_harvest_range_kg == pytest.approx((.98 * 2, 2.46 * 2))
    with pytest.raises(ValueError, match="not fitted"):
        predict_growth("lettuce_batavia", 38, 2, water_factor=.5)


def test_real_holdout_exposes_transfer_error_and_does_not_fabricate_replicates():
    report = calibrate_harvests(load_observations(), holdout_ids=["nasa_rlss_1992_cycle_2"])
    assert report["validation"]["holdout_record_count"] == 1
    assert report["validation"]["mape_pct"] == pytest.approx(100 * (72 - 49) / 49)
    assert report["validation"]["mae_kg_per_m2"] == pytest.approx((.072 - .049) * 480 / 10.6)
    assert report["fit_parameters"]["lettuce_batavia"]["training_summary_count"] == 1
    assert report["fit_parameters"]["lettuce_batavia"]["training_cycle_count"] == 0


def test_validation_rejects_summary_holdout_or_cycle_leakage():
    rows = load_observations()
    with pytest.raises(ValueError):
        calibrate_harvests(rows, holdout_ids=[rows[0]["observation_id"]])
    rows[-1] = {**rows[-1], "independent_group_id": rows[-2]["independent_group_id"]}
    with pytest.raises(ValueError, match="leak"):
        calibrate_harvests(rows, holdout_ids=["nasa_rlss_1992_cycle_2"])


def test_engineering_led_estimate_and_research_adapter_preserve_missing_data():
    assert estimate_led_energy(330, 16, efficacy_umol_per_j=2.5, photon_delivery_fraction=.8) == pytest.approx(2.64)
    config = replace(default_config(), days=45)
    preset = research_preset(config, ["lettuce_batavia"], water_l_per_m2_day=1.5)
    crop = preset.crops[0]
    assert crop.grow_days == 38
    assert crop.yield_kg_per_m2 == 1.56
    assert crop.power_kwh_per_m2_day == pytest.approx(2.79)
    assert crop.nutrients_per_kg["vitamin_c"] == pytest.approx(92)
    assert "assumed" in preset.input_provenance["crop:lettuce_batavia:resources"]
    assert preset.foods == config.foods
