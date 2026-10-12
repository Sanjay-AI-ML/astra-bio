import json

import pytest

from astra_bio.crew_samples import crew_sample
from astra_bio.nutrition import assess_intake, load_compositions, restore_state


def test_four_named_profiles_and_fictional_iron_scenario_are_explicit():
    sample = crew_sample()
    assert sample["schema_version"] == 1
    assert sample["sample_only"] is True
    assert sample["crew_count"] == 4
    assert [person["name"] for person in sample["profiles"]] == [
        "Shree Ram Vishal", "Shamyuktha", "Sanjay", "Vamshika"]
    assert [person["profile_id"] for person in sample["profiles"]] == [f"crew-{n}" for n in range(1, 5)]
    assert sample["conditions"]["crew-4"] == "Iron deficiency scenario (fictional)"
    assert "fictional" in sample["provenance"]["identity"]
    assert "invented" in sample["scope"]
    assert all(person["targets_reviewed"] is False for person in sample["profiles"])
    assert len({tuple(person["targets"].values()) for person in sample["profiles"]}) == 4
    json.dumps(sample, allow_nan=False)


def test_intake_graph_values_are_derived_from_the_existing_food_compositions():
    sample = crew_sample()
    profiles, entries, complete_days = restore_state(sample)
    catalog = load_compositions()
    for day in range(1, 8):
        assessments = [row for row in sample["assessments"] if row["day"] == day]
        complete = {person.profile_id: complete_days[f"{person.profile_id}:{day}"] for person in profiles}
        assert assessments == assess_intake(profiles, entries, day, complete, catalog)
        for row in assessments:
            expected_intake = sum(catalog[entry.food_key].nutrients_per_kg[row["nutrient"]] * entry.grams / 1000
                for entry in entries if entry.day == day and entry.profile_id == row["profile_id"])
            assert row["intake"] == pytest.approx(expected_intake)
            assert row["coverage_pct"] == pytest.approx(100 * expected_intake / row["target"])
            assert row["log_complete"] is True
    assert len(sample["assessments"]) == 4 * 7 * 3
    assert len(sample["entries"]) == 4 * 7 * 5


def test_labs_have_separate_units_and_do_not_become_intake_or_targets():
    sample = crew_sample()
    assert sample["units"]["hemoglobin_g_dl"] == "g/dL"
    assert sample["units"]["ferritin_ug_l"] == "µg/L"
    assert {row["day"] for row in sample["blood_samples"]} == {1, 15, 30}
    latest = next(row for row in sample["blood_samples"] if row["profile_id"] == "crew-4" and row["day"] == 30)
    assert latest["hemoglobin_g_dl"] == 10.8
    assert latest["ferritin_ug_l"] == 8.0
    assert latest["hemoglobin_g_dl"] < sample["references"]["hemoglobin"]["female_cutoff_g_dl"]
    assert latest["ferritin_ug_l"] < sample["references"]["ferritin"]["cutoff_ug_l"]
    assert all(set(person["targets"]) == {"energy", "protein", "vitamin_c"} for person in sample["profiles"])
    assert all("hemoglobin" not in row["nutrient"] for row in sample["assessments"])
    assert "not modeled" in sample["provenance"]["limitations"][0]


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8, 12])
def test_count_matches_every_identity_and_added_crew_labs_stay_unknown(count):
    sample = crew_sample(count)
    ids = {person["profile_id"] for person in sample["profiles"]}
    assert len(ids) == count
    assert {entry["profile_id"] for entry in sample["entries"]} == ids
    assert {row["profile_id"] for row in sample["assessments"]} == ids
    assert set(sample["conditions"]) == ids
    assert {row["profile_id"] for row in sample["blood_samples"]} == {f"crew-{index + 1}" for index in range(min(count, 4))}
    assert len(sample["blood_samples"]) == 3 * min(count, 4)
    for index, person in enumerate(sample["profiles"][4:], start=5):
        assert person["name"] == f"Sample Crew {index}"
        assert person["sex"] == "unspecified"
        assert sample["conditions"][person["profile_id"]] == "No sample blood measurements"


@pytest.mark.parametrize("count", [True, False, 0, -1, 13, 4.0, "4", None])
def test_invalid_crew_count_fails_instead_of_silently_coercing(count):
    with pytest.raises(ValueError, match="integer from 1 to 12"):
        crew_sample(count)


def test_samples_are_reproducible_and_return_independent_snapshots():
    first = crew_sample(6)
    second = crew_sample(6)
    assert first == second
    first["profiles"][0]["targets"]["protein"] = 999
    first["entries"][0]["grams"] = 0
    first["references"]["ferritin"]["cutoff_ug_l"] = 0
    assert second == crew_sample(6)
