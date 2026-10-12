"""Reproduce the small USDA SR Legacy subset without an API key.

The ZIP is downloaded into memory; only selected source rows and derived JSON
are saved beside this script. No whole bulk archive is retained.
"""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import csv
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
SELECTED = {
    "oats": 169705, "lentils": 172420, "peanut_butter": 172470,
    "lettuce": 169249, "radish": 169276, "kale": 168421,
    "tomato": 170457, "arugula": 169387, "kohlrabi": 168424,
}
NUTRIENTS = {"energy": (1008, "KCAL"), "protein": (1003, "G"), "vitamin_c": (1162, "MG")}
FORMS = {"oats": "dry ingredient weight", "lentils": "dry ingredient weight before cooking",
    "peanut_butter": "smooth, unsalted", **{key: "raw edible portion" for key in SELECTED if key not in ("oats", "lentils", "peanut_butter")}}


def main():
    destination = Path(__file__).resolve().parent
    with urlopen(URL, timeout=60) as response:
        downloaded = response.read()
    with ZipFile(BytesIO(downloaded)) as archive:
        def table(name):
            member = next(path for path in archive.namelist() if path.endswith("/" + name))
            return list(csv.DictReader(TextIOWrapper(archive.open(member), encoding="utf-8-sig")))
        foods = {int(row["fdc_id"]): row for row in table("food.csv") if int(row["fdc_id"]) in SELECTED.values()}
        ndb = {int(row["fdc_id"]): row for row in table("sr_legacy_food.csv") if int(row["fdc_id"]) in SELECTED.values()}
        nutrients = {int(row["id"]): row for row in table("nutrient.csv") if int(row["id"]) in {item[0] for item in NUTRIENTS.values()}}
        values = [row for row in table("food_nutrient.csv") if int(row["fdc_id"]) in SELECTED.values()
            and int(row["nutrient_id"]) in nutrients]
        portions = [row for row in table("food_portion.csv") if int(row["fdc_id"]) in SELECTED.values()]
        derivation_ids = {row["derivation_id"] for row in values}
        derivations = [row for row in table("food_nutrient_derivation.csv") if row["id"] in derivation_ids]
    for key, (identifier, unit) in NUTRIENTS.items():
        if nutrients[identifier]["unit_name"].upper() != unit:
            raise ValueError(f"Unexpected USDA unit for {key}; do not convert automatically.")
    by_pair = {(int(row["fdc_id"]), int(row["nutrient_id"])): row for row in values}
    extracted = {}
    for key, identifier in SELECTED.items():
        profile = {}
        source_rows = {}
        for nutrient, (nutrient_id, _) in NUTRIENTS.items():
            source = by_pair.get((identifier, nutrient_id))
            amount = None if source is None or source["amount"] == "" else float(source["amount"])
            profile[nutrient] = amount
            source_rows[nutrient] = source
        extracted[key] = {"fdc_id": identifier, "ndb_number": ndb[identifier]["NDB_number"],
            "description": foods[identifier]["description"], "data_type": foods[identifier]["data_type"],
            "publication_date": foods[identifier]["publication_date"], "food_form": FORMS[key],
            "nutrients_per_100g": profile,
            "nutrients_per_kg": {name: None if amount is None else amount * 10 for name, amount in profile.items()},
            "source_url": f"https://fdc.nal.usda.gov/food-details/{identifier}/nutrients",
            "source_rows": source_rows,
            "portions": [row for row in portions if int(row["fdc_id"]) == identifier]}
    result = {"schema_version": 1, "dataset": {"name": "USDA FoodData Central SR Legacy",
        "release": "2018-04 (final SR Legacy release)", "download_url": URL,
        "download_page": "https://fdc.nal.usda.gov/download-datasets/",
        "download_sha256": sha256(downloaded).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_basis": "per 100 g edible food in the stated form", "per_kg_conversion": "multiply per-100-g values by 10",
        "units": {"energy": "kcal", "protein": "g", "vitamin_c": "mg"}}, "foods": extracted}
    (destination / "compositions.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for filename, selected in [("source_food.csv", list(foods.values())), ("source_sr_legacy_food.csv", list(ndb.values())),
        ("source_nutrient.csv", list(nutrients.values())), ("source_food_nutrient.csv", values),
        ("source_food_portion.csv", portions), ("source_nutrient_derivation.csv", derivations)]:
        with (destination / filename).open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=list(selected[0]))
            writer.writeheader()
            writer.writerows(selected)
    print("Verified USDA subset:")
    for key, item in extracted.items():
        print(key, item["fdc_id"], item["ndb_number"], item["description"], item["nutrients_per_100g"])
        print("  USDA portions:", [(row.get("portion_description"), row.get("modifier"), row.get("gram_weight")) for row in item["portions"]][:5])


if __name__ == "__main__":
    main()
