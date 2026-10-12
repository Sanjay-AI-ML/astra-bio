# Nutrient-driven crop choice and continued simulations

Implemented 12 October 2026. The user selected continued simulations with reviewed inputs; automatic recurring camera capture remains unchanged.

## Use the product

1. Open Mission overview and use **Play simulation** to advance saved model results every 1.5 seconds. Pause, restart or select a day. Playback does not rerun the solver or consume real food.
2. Open **Crops & food → Crop schedules → What should we grow next?** Choose protein, vitamin C, energy or balanced nutrition, a planting area and a mission day, then **Suggest crops**.
3. Inspect the recommended growing batch, alternatives, first harvest day, resource limits and predicted nutrient gaps. Review stored food for the days before harvest.
4. Optionally expand **Crop nutrition data → Use USDA crop nutrition**. This updates matched crop food composition without changing pantry food/quantities, crop yield or resource coefficients. It clears the current comparison; run a new simulation with the updated configuration. Unmatched soy and microgreens retain explicitly labeled configured assumptions.
5. To keep planning from a saved simulation, choose a completed day. Optionally enter a reviewed future nutrient target change, then **Continue from Day N**. The solver starts at Day N+1 with the saved simulated remaining stock and growing cohorts. Elapsed daily records, intake allocations and inventories remain unchanged. The result is saved as a new local run; the original remains available.

Only energy, protein and vitamin C are supported by the current extracted composition data. These are planning targets, not clinical diagnoses. A protein-rich stored ingredient is not automatically a supported plantable crop.

## Ranking and feasibility

Each configured crop is evaluated as one additional batch:

`nutrient output per m² per growth day = edible yield kg/m² × nutrient per kg ÷ growth days`

For ranking, each nutrient's output is divided by its daily crew target at the hypothetical harvest day, producing a dimensionless target share. An explicit protein/energy/vitamin C priority gives that nutrient weight one. Balanced mode weights normalized cumulative future shortages in the saved simulation; if there are none, it gives each tracked positive target equal weight. Kcal, grams and milligrams are never added directly.

The advisor checks the entire growth window against remaining area, water and power in the saved schedule, including future scenario changes, tray increments and the mission horizon. A high nutrient-density crop that arrives too late or cannot fit growing resources is shown as blocked. The highest-ranked candidate that fits growing limits becomes the first crop to consider. This is an additive-batch comparison, not a proof of a complete meal plan; the mission solver chooses combinations and may reallocate existing crops.

Total nutrients in a batch are potential harvest output. The fresh-food consumption cap applies across all crops on harvest day, so excess can be discarded. Crops do not cover shortages before harvest. Resource needs remain configured assumptions unless separately measured and calibrated. USDA labels are shown only when all three configured composition values match the known reference proxy; edited or unmatched values retain the assumption label.

## Continuation integrity

`POST /api/plans/continue` accepts a saved run ID or metadata, `through_day`, and optional positive `target_factors`. It checks the source configuration, bounds and saved inventory. It freezes the elapsed prefix and uses end-of-day stock rather than refilling original inventory. Known original scenario conditions and crop-loss factors remain in effect. Previously planned meals/plantings are the fixed comparison, assessed against the same revised future targets as the new plan. Parent boundaries and source crop cohorts are recorded for inspection.

Continuation updates future planting and food allocation. It does not add an automatically selected crop, turn image predictions into crop losses, issue hardware commands, infer crew health, or extend the mission beyond its configured horizon. The local solver lock prevents overlapping solve operations. Recovery comparisons from a continued run start at its next day, preserving the elapsed prefix as well.

`POST /api/crop-advisor` is read-only. It accepts configuration or saved metadata/run ID, `day`, `priority` and `area_m2`. Returned evidence includes per-100-g composition, estimated batch output, crop timing, growing resource headroom, earliest nutrient-gap dates, stock bridge options and provenance. `POST /api/config/crop-nutrition` changes only matched reference crop nutrition after explicit user action.

## Evidence and remaining validation

Reference crop composition comes from the preserved [USDA FoodData Central SR Legacy data](https://fdc.nal.usda.gov/data-documentation/), rather than nutrient measurements of our harvest. Controlled-environment growth references are separately documented in CROP_MODEL_EVIDENCE.md. [NASA crop research](https://www.nasa.gov/science-research/nasa-plant-researchers-explore-question-of-deep-space-food-crops/) discusses soybeans as a protein source, but our configured soy growth/composition remains synthetic and is not presented as a calibrated crop.

Verification covers nutrient priority changes, mixed-unit normalization, unknown composition, late harvest, future resource reductions, expiry/retention, missing stock, reference labels, unchanged history, stock conservation, known future crop loss, saved continuation restoration, concurrent solver rejection, UI request wiring and stale-response rejection. This establishes software behavior, not plant-model accuracy or nutrient sufficiency in a real habitat. Local crop cycles, weighed edible harvests and measured environmental-response data are still needed.

The affected backend suite passed **92 tests**, the complete frontend suite passed **98 tests**, and the production build passed. Final crop-advisor presentation adjustments additionally passed all **14 advisor tests**. A live browser check played mission days, displayed protein recommendations and continued the existing mission after Day 30 with a reviewed 20% future protein-target increase. All first 30 daily records matched the original saved run; Day 30's crew protein target remained 360 g and Day 31's became 432 g. Safe evidence is in CROP_ADVISOR_VERIFICATION.json. These quantities are simulation inputs/results, not measured dietary requirements.
