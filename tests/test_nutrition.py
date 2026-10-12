from dataclasses import replace

import pytest

from astra_bio.model import default_config
from astra_bio.nutrition import CrewProfile, FoodLogEntry, assess_intake, apply_usda_composition, load_compositions, restore_state, serialize_state, vitamin_c_reference


def test_usda_composition_units_and_provenance_are_traceable():
    food = load_compositions()["oats"]
    assert food.fdc_id == 169705
    assert food.nutrients_per_kg["energy"] == 3890
    assert food.nutrients_per_kg["protein"] == pytest.approx(168.9)
    model = apply_usda_composition(default_config(), {"oats": 20, "lentils": 10, "peanut_butter": 5})
    assert model.foods[0].initial_kg == 20
    assert model.crops[1].grow_days == default_config().crops[1].grow_days
    assert model.input_provenance["food_composition"]["dataset"] == "USDA FoodData Central SR Legacy"


def test_incomplete_empty_log_and_missing_composition_remain_unknown():
    profile = CrewProfile("p", "Alias", {"energy": 2200, "protein": 90, "vitamin_c": 100})
    assert all(row["intake"] is None for row in assess_intake([profile], [], 1))
    assert all(row["intake"] == 0 for row in assess_intake([profile], [], 1, {"p": True}))
    foods = load_compositions()
    foods["oats"] = replace(foods["oats"], nutrients_per_kg={**foods["oats"].nutrients_per_kg, "vitamin_c": None})
    result = assess_intake([profile], [FoodLogEntry("p", 1, "oats", 100)], 1, compositions=foods)
    assert next(row for row in result if row["nutrient"] == "vitamin_c")["intake"] is None


def test_logged_food_form_mass_and_saved_state_roundtrip():
    profile = CrewProfile("p", "Alias", {"energy": 2200, "protein": 90, "vitamin_c": 100})
    entry = FoodLogEntry("p", 1, "oats", 100)
    rows = assess_intake([profile], [entry], 1)
    assert next(row for row in rows if row["nutrient"] == "energy")["intake"] == 389
    assert restore_state(serialize_state([profile], [entry], {"p:1": False})) == ([profile], [entry], {"p:1": False})
    assert vitamin_c_reference(20, "female")["rda_mg"] == 75
    assert vitamin_c_reference(None, "unspecified") is None
