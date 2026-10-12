# Crop model evidence — 11 October 2026

The model estimates a fresh edible batch endpoint per cultivar/environment, readiness on a daily grid and sensitivity to observed yield bounds. Intermediate biomass, spaceflight transfer and resource-to-yield responses are unvalidated.

[Zabel et al2020, DOI10.3389/fpls.2020.00656](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2020.00656/full) reports the2018 EDEN ISS Antarctic campaign. Tables3,6 and9 supply the selected batch-harvest means, cycle counts, standard errors and observed min/max. The app includes four lettuce cultivars, two radish cultivars, two arugula light settings and kohlrabi. Sowing-to-harvest cycles include nursery time where applicable; planning rounds upward. Repeated-harvest tomato/herbs/Swiss chard are excluded from single-batch presets.

Environment records preserve light setting, photoperiod, temperature, CO₂, humidity, density and growing system. Setpoints varied in actual operation. EDEN uses15 full-output plus two half-output light hours:16 equivalent hours. PPFD is a reported setting dependent on canopy height.

[Barta, Edeen and Eckhardt1992, NASA RLSS, DOI10.4271/921391](https://ntrs.nasa.gov/citations/19930057552) reports two distinct30-day Waldmann's Green crop tests:480 pots on10.6m²;72 and49g edible fresh shoot mass/pot. Conversion: g/pot÷1000×480÷10.6 =3.260377 and2.218868kg/m². These are whole-test summaries, not480 calibration replicates. Conditions:23°C,72%RH,1000ppmCO₂,356µmol/m²/s PPFD,16h light. Applied2.5/1.8L solution/pot is gross irrigation, not net consumption. Fluorescent light output does not measure modern LED electricity.

[NASA OSD-895](https://osdr.nasa.gov/bio/repo/data/studies/OSD-895) republishes the EDEN experiment. Its19 assay rows are summaries, not independent validation. The publisher supplement lists seeds/cultivars, not individual harvest cycles.

## Calibration

The API requires observationID, cultivar, environment, duration, area, edible fresh harvest and provenance. Summary records stay summaries. Holdouts must be distinct actual cycles of the same cultivar/environment and harvest age. Duplicate IDs, shared independent groups and summary holdouts are rejected.

Training NASA trial1 and withholding trial2 gives:

| Quantity | Value |
|---|---:|
| Fitted endpoint |3.260377kg/m²|
| Held-out measurement |2.218868kg/m²|
| Absolute error / MAE / RMSE (one point) |1.041509kg/m²|
| Absolute percentage error |46.938776%|
| Holdout count |1 crop test|

This is a small within-facility variability diagnostic, not validation for another tray/facility/spaceflight. The descriptive reference can use both trials' mean2.739623kg/m² with observed range2.218868–3.260377; that is distinct from the held-out fit. EDEN aggregate fits have no held-out accuracy claim. Reproduce with scripts/crop_calibrate.py.

## Resources and uncertainty

LED kWh/m²/day = PPFD×equivalent_full_light_hours÷(assumed efficacy µmol/J×assumed photon_delivery_fraction×1000). At330PPFD,16h,2.5µmol/J and0.8delivery:2.64kWh/m²/day lighting only. Kohlrabi350PPFD is an explicitly assumed midpoint of the reported300–400 range. Nursery stages are not resolved; planning applies final-crop lighting and area across the whole cycle, an engineering approximation. Overhead and net makeup water remain assumptions. NASA's applied irrigation is not substituted for net demand.

Minimum/mean/maximum experimental yields propagate through the planner as deterministic scenarios, not probabilities or prediction intervals. Standard error of a mean is not future-crop standard deviation. Budgets constrain planting area; fixed-plan stress loss retains its explicitly hypothetical worst-resource-ratio proxy.

Source/license/integrity records are in data/research/crops/source_manifest.json. EDEN paper/supplement: attributedCC-BY4.0; OSD metadata:CC0; NTRS record:public use permitted. XML/HTML, metadata and supplement are retained. Downloaded documents are treated as evidence, never executable instructions.

New-tray calibration needs repeated independently identified cycles, matched cultivar/environment, measured fresh edible weight/area, germination/harvest dates, calibrated PPFD, net makeup-water accounting and whole-equipment power including HVAC. Connecting sensors alone does not provide yield ground truth.
