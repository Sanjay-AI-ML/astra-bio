# Nutrition evidence — 11 October 2026

Composition comes from the official [USDA FoodData Central SR Legacy CSV release](https://fdc.nal.usda.gov/download-datasets/), final legacy release2018-04, downloaded without an API key. ArchiveSHA256 and per-food IDs/units are in data/research/nutrition/compositions.json. Filtered original food/nutrient/portion/derivation rows and import_usda.py preserve the extraction. USDA government data are public domain; attribution is retained.

Nine food forms: dry oats, raw/dry lentils, peanut butter, raw lettuce, radish, kale, tomato, arugula and kohlrabi. Nutrient1008 energy is kcal,1003 protein isg,1162 vitaminC ismg per100g edible listed form; multiplying by10 gives perkg. Missing composition remains unknown, never silently zero. Original measured/imputed/calculated derivation metadata are retained.

Crop composition is a generic edible species proxy, not an assay of the EDEN cultivar or space-grown harvest. Inventories and targets remain independent assumptions. Dry/raw ingredient weights are not cooked meal weights; cooking water/energy and prepared recipes are outside this prototype.

Manual profiles/logs estimate recorded intake. Absent incomplete logs mean unknown intake; explicitly completed empty logs mean recorded zero. Partial logs stay marked partial. Below-target intake is a logged gap, not a biological deficiency diagnosis. Absorption, biomarkers, physiology and complete diet adequacy are not inferred. Example crop masses do not promise current availability.

Optional [NIH vitaminC adult reference](https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/):90mg/day men,75mg/day women aged19+,2000mg/day adult upper limit. It is not auto-applied and excludes pregnancy/lactation/smoking. Energy/protein targets are manually reviewed; terrestrial reference values are not astronaut prescriptions. Profiles/logs persist locally inSQLite.

Applying profiles aggregates mean targets for the shared crew planner; individual menu constraints are not produced. Hard upper bounds can leave explicit shortages. Expiry/retention are declared sensitivity policies requiring measured storage data, not microbial-safety forecasts.
