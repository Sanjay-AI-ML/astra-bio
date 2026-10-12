r"""Run a labeled, reproducible sample through the actual local planning API.

Usage from the application root: .venv\Scripts\python.exe scripts/run-sample-mission.py
The API must already be running. No hardware telemetry or Atlas images change.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from astra_bio.model import FoodSpec, Scenario, default_config
from astra_bio.nutrition import apply_usda_composition
from astra_bio.presets import research_preset

API = "http://127.0.0.1:8501/api"
OUTPUT = ROOT / "data" / "samples" / "nutrient-mission"


def sample_inputs():
    config = replace(default_config(), crew=4, days=90, area_m2=20,
        water_budget_l_per_day=55, power_budget_kwh_per_day=40,
        reserve_days=3, max_total_food_kg_per_crew_day=1.2)
    config = apply_usda_composition(config, {"oats": 140, "lentils": 45, "peanut_butter": 20})
    config = research_preset(config, ["arugula_330", "arugula_600", "radish_raxe", "kohlrabi", "lettuce_waldmann_nasa"],
        water_l_per_m2_day=1.5)
    # This explicit synthetic coefficient provides an initial vitamin bridge;
    # it is not an observed food, a supplement dose or a measured stored meal.
    bridge = FoodSpec("sample_vitamin_bridge", "Fortified bridge food (synthetic sample)", 5,
        {"energy": 1000, "protein": 0, "vitamin_c": 5000})
    provenance = dict(config.input_provenance)
    provenance["sample_mission"] = {"status": "Illustrative sample scenario, not a physical habitat",
        "stocks": "User-requested sample masses; not measured food inventory",
        "targets": "2200 kcal, 90 g protein, 100 mg vitamin C per person per day are sample planning targets, not clinical prescriptions",
        "resources": "20 m², 55 L/day water, 40 kWh/day power and crop makeup water are sample assumptions",
        "sample_vitamin_bridge": "5 kg synthetic food @ 1000 kcal/kg, 0 g protein/kg, 5000 mg vitamin C/kg; coefficient placeholder only",
        "preparation": "USDA lentils/oats are dry ingredient forms; cooking, hydration, preparation resources and recipes are not modeled",
        "hardware": "No ESP32 or camera observations are used"}
    config = replace(config, foods=[*config.foods, bridge], input_provenance=provenance)
    config.validate()
    scenario = Scenario("sample-protein-rise", "SAMPLE · Protein target +40% from Day 30", event_day=30,
        target_factors={"protein": 1.4})
    scenario.validate(config)
    return config, scenario


def post(path, payload):
    request = urllib.request.Request(API + path, data=json.dumps(payload, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def write(name, payload):
    (OUTPUT / name).write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def main():
    config, scenario = sample_inputs()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write("inputs.json", {"schema_version": 1, "config": asdict(config), "scenario": asdict(scenario)})
    run = post("/plans", {"config": asdict(config), "scenario": asdict(scenario)})
    if not run.get("metadata", {}).get("adaptive", {}).get("daily"):
        raise ValueError("Sample solve did not return a completed plan; no success is claimed.")
    write("run.json", run)
    reports = {}
    for day in (1, 31):
        for priority in ("protein", "vitamin_c", "energy", "balanced"):
            report = post("/crop-advisor", {"metadata": run["metadata"], "day": day, "priority": priority, "area_m2": .25})
            write(f"advisor-day-{day}-{priority}.json", report)
            reports[f"day_{day}_{priority}"] = {"top_crop_id": report["top_choice_crop_id"],
                "forecast": report["forecast"]}
    summary = {"scope": "Illustrative sample simulation; references and assumptions are separately labeled",
        "saved_run_id": run.get("history_id"), "scenario": asdict(scenario),
        "fixed": run["metadata"]["baseline"]["metrics"],
        "adaptive": run["metadata"]["adaptive"]["metrics"], "recommendations": reports,
        "limitation": "Only energy, protein and vitamin C tracked; remaining shortages are retained, not hidden"}
    write("summary.json", summary)
    post("/snapshots/config", {"name": "SAMPLE · USDA crops and protein scenario", "config": asdict(config)})
    print("Sample mission saved. Earlier runs remain available in workspace history.")
    for label, key in (("Fixed schedule", "baseline"), ("Adaptive schedule", "adaptive")):
        plan = run["metadata"][key]
        print(f"{label}: {plan['metrics']['shortfall_days']} days below tracked targets; "
              f"{plan['metrics']['total_harvest_kg']:.2f} kg modeled harvest.")
    print("Day 1 protein recommendation:", reports["day_1_protein"]["top_crop_id"])
    print("Reports:", OUTPUT)
    print("Refresh ASTRA-BIO to open this sample run.")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, ValueError, OSError) as error:
        print(f"Sample mission failed: {error}. Ensure the local API is running with run.ps1.", file=sys.stderr)
        raise SystemExit(1)
