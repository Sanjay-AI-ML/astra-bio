# Named crew nutrition and blood examples

Implemented 12 October 2026 at the user's request. The four names are presentation labels: **Shree Ram Vishal, Shamyuktha, Sanjay and Vamshika**. Ages, reference sex, dietary amounts, targets and blood readings are fictional sample attributes, not records of those people.

## What the interface shows

Crew & nutrition opens with seven days of sample food logs. A shared zero-based axis compares one nutrient at a time: protein in grams, energy in kcal, or vitamin C in mg. Each person has their own editable target marker, numeric intake, percentage and log-completeness status. Values above 100% remain visible. Exact values are available beneath each chart. Editing logs/targets invalidates the result until assessment; an empty assessment does not reuse old sample values.

A separate graph compares haemoglobin in g/dL or ferritin in µg/L. Latest fictional test values are labeled as Day 30, independent of the selected food-log day. Three discrete sample points, on Days 1, 15 and 30, can be inspected for a selected person. No daily interpolation or treatment response is invented.

Vamshika is the requested **fictional low-iron scenario**, with latest haemoglobin 10.8 g/dL and ferritin 8 µg/L. Lower-reference comparisons illustrate the scenario. They do not establish an actual diagnosis, prescribe treatment or change crop/crew planning targets.

WHO's [2024 haemoglobin guideline table](https://www.ncbi.nlm.nih.gov/books/NBK602185/table/ch5.tab2/) supplies adult lower cutoffs: 12 g/dL for nonpregnant women and 13 g/dL for men aged 15–65. Reference sex or age outside the scope leaves the marker unknown. These are classification cutoffs rather than a normal band or daily nutrient goal; clinical context, including altitude, matters.

The [WHO ferritin guideline](https://www.who.int/publications/i/item/9789240000124) supplies the 15 µg/L lower reference for apparently healthy adults. The example assumes no infection/inflammation; pregnancy and inflammation need a different interpretation. Ferritin indicates iron stores, rather than dietary iron intake or blood iron concentration.

## Crew changes and local persistence

The sample initially includes four people. Increasing configured or active simulated crew generates **Sample Crew 5**, **Sample Crew 6**, etc., up to the supported twelve-person sample. Additional profiles have varied illustrative targets and food logs; unavailable blood measurements remain unknown. Existing named sample edits/logs are retained when expanding the default sample roster. These displays do not rerun the mission solver or apply personal targets automatically.

**Load named sample crew** restores the demonstration. Profile/log editors and detailed tables sit below the graphs. Local nutrition snapshots preserve a small fictional-fixture marker; restoring an ordinary intake snapshot does not attach invented blood tests. The standard snapshot contains profiles and food logs, with blood examples generated separately only for flagged sample records.

## Data and verification

`astra_bio/crew_samples.py` deterministically builds the sample and computes its food-log intake with the existing USDA composition and assessment routines. `/api/nutrition/sample?count=4` exposes this fixture locally; bootstrap includes an initial sample. Dry oats/raw lentils remain ingredient-form references, not cooked plate masses. Iron intake is not extracted or optimized in the current three-nutrient planner. Blood values are neither sensed by ESP32 nor inferred by ML.

The affected backend tests passed **36 checks**, the full frontend suite passed **116 tests**, and the production build passed. Tests cover names/counts, USDA-derived intake, separate laboratory data, unknown extra-crew labs, appropriate reference scopes, displayed units, zero baselines, over-target values, day/person selection, edited-data invalidation and snapshot separation. The live browser displayed all four names, switched nutrient/lab metrics and showed Vamshika's three discrete ferritin points. Software verification does not establish clinical validation.
