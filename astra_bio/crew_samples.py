"""Reproducible, explicitly fictional crew intake and blood-test examples.

Dietary estimates use the application's USDA reference food forms. Blood
measurements are invented separately for display; they do not modify planning
targets, infer diagnoses, or represent the named people's actual health.
"""
from __future__ import annotations

from astra_bio.nutrition import (
    CrewProfile,
    FoodLogEntry,
    UNITS,
    assess_intake,
    load_compositions,
    serialize_state,
)


MAX_SAMPLE_CREW = 12
_BASE_PROFILES = (
    ("Shree Ram Vishal", 22, "male", 2400.0, 100.0, 100.0),
    ("Shamyuktha", 21, "female", 2000.0, 75.0, 90.0),
    ("Sanjay", 22, "male", 2300.0, 90.0, 100.0),
    ("Vamshika", 22, "female", 2100.0, 85.0, 100.0),
)
# Daily ingredient quantities in grams, before a small deterministic day factor.
# Raw lentil / dry oat weights are ingredient weights, not ready-to-eat servings.
_PORTIONS = (
    {"oats": 235.0, "lentils": 125.0, "peanut_butter": 130.0, "tomato": 180.0, "kale": 80.0},
    {"oats": 195.0, "lentils": 100.0, "peanut_butter": 110.0, "tomato": 140.0, "kale": 55.0},
    {"oats": 225.0, "lentils": 105.0, "peanut_butter": 135.0, "tomato": 160.0, "kale": 65.0},
    {"oats": 185.0, "lentils": 90.0, "peanut_butter": 115.0, "tomato": 120.0, "kale": 40.0},
)
_DAY_FACTORS = (0.94, 1.02, 0.98, 1.06, 0.96, 1.03, 1.0)
_BLOOD_TRENDS = (
    ((14.6, 60.0), (14.7, 63.0), (14.8, 62.0)),
    ((13.3, 44.0), (13.1, 41.0), (13.2, 42.0)),
    ((15.0, 76.0), (15.2, 74.0), (15.1, 75.0)),
    ((11.0, 10.0), (10.9, 9.0), (10.8, 8.0)),
)


def crew_sample(count: int = 4) -> dict:
    """Return a fresh JSON-serializable example for one to twelve crew members.

    The first four names are user-provided presentation labels. All other
    attributes, dietary quantities and blood values are fictional assumptions.
    Added crew have sample food logs but no invented blood measurements or sex.
    """
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_SAMPLE_CREW:
        raise ValueError(f"Sample crew count must be an integer from 1 to {MAX_SAMPLE_CREW}.")

    catalog = load_compositions()
    profiles: list[CrewProfile] = []
    entries: list[FoodLogEntry] = []
    complete_days: dict[str, bool] = {}
    conditions: dict[str, str] = {}
    blood_samples: list[dict] = []
    for index in range(count):
        profile_id = f"crew-{index + 1}"
        if index < len(_BASE_PROFILES):
            name, age, sex, energy, protein, vitamin_c = _BASE_PROFILES[index]
            portions = _PORTIONS[index]
        else:
            name, age, sex = f"Sample Crew {index + 1}", 22, "unspecified"
            # Rotated example quantities keep added crew distinct and repeatable.
            energy = 2100.0 + (index % 3) * 100.0
            protein = 80.0 + (index % 3) * 5.0
            vitamin_c = 90.0 + (index % 2) * 10.0
            portions = _PORTIONS[index % len(_PORTIONS)]
        profile = CrewProfile(profile_id, name,
            {"energy": energy, "protein": protein, "vitamin_c": vitamin_c},
            age=age, sex=sex, targets_reviewed=False)
        profile.validate()
        profiles.append(profile)
        for day in range(1, len(_DAY_FACTORS) + 1):
            # Offset the seven-day pattern by person without randomness.
            shifted_factor = _DAY_FACTORS[(day - 1 + index) % len(_DAY_FACTORS)]
            for food_key, grams in portions.items():
                entries.append(FoodLogEntry(profile_id, day, food_key, round(grams * shifted_factor, 2)))
            complete_days[f"{profile_id}:{day}"] = True
        if index == 3:
            conditions[profile_id] = "Iron deficiency scenario (fictional)"
        elif index < len(_BASE_PROFILES):
            conditions[profile_id] = "Baseline comparison scenario (fictional)"
        else:
            conditions[profile_id] = "No sample blood measurements"
        if index < len(_BLOOD_TRENDS):
            for day, (hemoglobin, ferritin) in zip((1, 15, 30), _BLOOD_TRENDS[index], strict=True):
                blood_samples.append({"profile_id": profile_id, "day": day,
                    "hemoglobin_g_dl": hemoglobin, "ferritin_ug_l": ferritin})

    state = serialize_state(profiles, entries, complete_days)
    assessments = []
    for day in range(1, len(_DAY_FACTORS) + 1):
        assessments.extend(assess_intake(profiles, entries, day,
            {profile.profile_id: complete_days[f"{profile.profile_id}:{day}"] for profile in profiles}, catalog))
    return {
        **state,
        "sample_only": True,
        "crew_count": count,
        "assessments": assessments,
        "blood_samples": blood_samples,
        "conditions": conditions,
        "units": {**UNITS, "hemoglobin_g_dl": "g/dL", "ferritin_ug_l": "µg/L"},
        "scope": "Fictional crew demonstration. Names are labels; ages, reference-table sex, intake and blood values are invented, not these people's health records.",
        "provenance": {
            "identity": "Names supplied by the user for fictional presentation profiles. Age and sex are explicit sample assumptions, not inferred from the names.",
            "targets": "Illustrative manual planning targets; not reviewed, personalized prescriptions or medically derived targets.",
            "food_logs": "Seven declared-complete example ingredient logs (mission days 1–7), generated deterministically; not observed meals or a recommended complete diet.",
            "food_composition": {"dataset": "USDA FoodData Central SR Legacy", "release": "2018-04",
                "foods": {key: {"fdc_id": catalog[key].fdc_id, "food_form": catalog[key].food_form,
                    "source_url": catalog[key].source_url} for key in _PORTIONS[0]}},
            "blood_samples": "Invented measurements on mission days 1, 15 and 30, unrelated to food-log calculations. No laboratory, camera or physiological measurements were taken.",
            "limitations": [
                "Only energy, protein and vitamin C dietary intake are calculated; iron intake and blood iron are not modeled.",
                "Ferritin is a marker used to assess iron stores; it is not a blood iron concentration or a nutrient target.",
                "Dry oats and raw lentils use dry ingredient mass; cooking, absorption and nutrient retention are not modeled.",
                "Low reference comparisons illustrate a fictional scenario, not automatic diagnosis or treatment. No treatment response is assumed.",
                "Intake coverage and laboratory values use distinct units and cannot be plotted as one combined health score.",
                "Added Sample Crew profiles have no blood measurements; missing laboratory data stays unknown.",
            ],
        },
        "references": {
            "hemoglobin": {
                "source_url": "https://www.ncbi.nlm.nih.gov/books/NBK602185/table/ch5.tab2/",
                "male_cutoff_g_dl": 13.0, "female_cutoff_g_dl": 12.0,
                "scope": "WHO 2024 adult ages 15–65 nonpregnant female/male lower anaemia cutoffs; illustration assumes sea level and no smoking; not normal ranges or treatment targets.",
            },
            "ferritin": {
                "source_url": "https://www.who.int/publications/i/item/9789240000124",
                "cutoff_ug_l": 15.0,
                "scope": "WHO 2020 apparently healthy adult without infection/inflammation cutoff; inflammation and pregnancy require context.",
            },
        },
    }
