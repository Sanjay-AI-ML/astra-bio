# Measured growth and crop-response training

ASTRA-BIO now has two separate research pipelines. Neither automatically changes
the planning endpoint, triggers watering, or makes the model valid in space.

1. A source-specific **age → fresh mass** curve can learn from measured plants.
   Complete plants are held out, including every recorded day for each plant.
   This tests interpolation within the same growing cycle, not new-cycle transfer.
2. A **measured environment → final fresh edible yield** pipeline can fit a
   regularized linear association after real independent experiments are captured.
   It refuses missing exposures, insufficient independent cycles, collinear
   treatments, failed holdout validation and unsupported prediction conditions.

The existing `crop_growth.py` endpoint model remains the planning default.

## Source-specific age curve

The normalized source CSV is `data/research/growth/growth_observations.csv`.
Provenance, licensing and source ambiguities are retained alongside the data.
The predictor uses days after transplant, not a corrected calendar date invented
to reconcile conflicting source metadata. The source mass basis must remain
`unspecified_fresh` when the paper/data do not establish edible-only mass.

The fit pools **training-only** fresh-mass observations into age means and applies
a weighted monotone fit. Linear interpolation is allowed between measured ages.
Whole held-out plants contribute equally to reported MAE, RMSE and bias. The
report includes a training-mean baseline, complete plant IDs, source checksum and
each scored observation. There is no generated measurement or synthetic training
augmentation in this crop dataset.

Run after importing the pinned measured source:

```powershell
.\.venv\Scripts\python.exe scripts/fit_measured_growth.py --holdout-plant B25 --holdout-plant B26 --holdout-plant B35 --holdout-plant B36 --holdout-plant B45 --holdout-plant B46
```

Output: `data/reports/measured-growth.json`. Inspect the report's exact species,
cultivar, environment, mass basis, measured age range and within-cycle error. No
edible-harvest conversion or new-cultivar/tray prediction is supported. A curve
with one source cycle has **zero independent test cycles**, even when it contains
hundreds of measurements.

The first actual fit, reproduced on 2026-10-11, uses 540 measured fresh-mass cells
from 18 source plants at DAT 1–30. Twelve complete plants (360 observations) train
the curve; six complete plants (180 observations) are held out. Each held-out
plant has equal weight in the diagnostics:

| Within-cycle metric | Measured-growth curve | Training-mean mass baseline |
|---|---:|---:|
| MAE | 5.7193 g/plant | 47.5846 g/plant |
| RMSE | 10.2565 g/plant | 53.6306 g/plant |
| Bias (predicted minus measured) | −3.7150 g/plant | −3.7150 g/plant |

These numbers describe unknown-basis fresh mass of source plants within one
cycle. They are **not** edible-yield prediction error, spaceflight performance,
or proof of general accuracy on our trays. The original XLSX calendar serials
correspond to 2022 while the README describes 2024; normalized data retains both
and the curve uses the source DAT index without inventing corrected dates.

The source-specific fit has status `experimental_fitted`. The separate resource
response pipeline has status `awaiting_measurements` with zero captured physical
tray cycles. A promising [four-cycle light/temperature dataset](https://data.4tu.nl/datasets/5a7472f0-8a67-4ec0-84c9-9d032990d654/1)
was identified, but its original XLSX download returned HTTP 503 during repository
storage maintenance on 2026-10-11. The manifest under
`data/research/growth/wur_response_candidate/` records this access limitation.
Metadata and a paper do not substitute for raw training rows, and that experiment
does not establish a water-scarcity response.

## Capture repeated physical tray cycles

`data/measurements/crop_cycles.csv` is a **header-only blank template**. It contains
no trial results. Use one row per final harvest of one tray-cycle:

| Field | Meaning and units |
|---|---|
| `cycle_id`, `tray_id` | Unique recorded cycle and physical tray identities. A renamed duplicate is not another trial. |
| `independent_group_id` | Entire experiment/run that will remain together in train or test. Correlated trays in one run are one group. |
| `shared_resource_group_id` | Shared reservoir/chamber/run identity. Trays sharing resources in the same environment must have the same independent group. |
| Species, cultivar, environment, cultivation system | Preserve the actual cultivar and facility/system. Do not pool different profiles under one name. |
| `evidence_setting` | `terrestrial_controlled` or `spaceflight`; do not relabel terrestrial trials. |
| `start_basis`, dates | `sowing` or `transplant` and ISO dates; measured cycle age is derived from dates. |
| `area_m2` | Measured cultivated tray area, not whole room area. |
| `fresh_edible_harvest_kg` | Measured fresh edible mass in kg after subtracting tare and removing excluded tissues. Zero crop failures are retained. |
| `mass_basis`, `observation_type` | Exactly `fresh_edible` and `crop_cycle`. Published averages, dry mass, nominal yields and synthetic rows cannot supply trial replication. |
| `source_reference` | Traceable experiment notebook, raw file/sheet/row or publication measurement record. Keep the original measurements. |
| `environment_coverage_pct` | Fraction of the full growing period with valid exposure readings under the declared sampling protocol. Missing telemetry is not zero exposure. |
| `mean_ppfd_umol_m2_s`, `photoperiod_hours` | Measured representative canopy PPFD and actual equivalent illuminated hours/day. Their product derives daily light integral in mol/m²/day. A lamp setting alone is not measured canopy light. |
| Temperature, RH and CO₂ | Time-weighted growing-period means in °C, percent and ppm. Retain raw time series and note gaps. |
| `net_makeup_water_l_per_m2_day` | Actual net added water per cultivation m²/day, with the measurement boundary recorded. Recirculated irrigation flow is not net consumption. |
| `lighting_kwh_per_m2_day` | Metered lighting electricity per cultivation m²/day. Record HVAC/pumps separately; a mission electricity budget is not plant light exposure. |
| EC, pH, planting density | Measured mS/cm, pH and plants/m²; retain protocol and control deviations. |
| `notes` | Diseases, discarded plants, sensor outages, treatment allocation, mass basis, exclusions and other confounders. |

Plan and preregister treatments and held-out runs **before** looking at harvests.
Use a control treatment, randomized tray placement when practicable, calibrated
instruments, consistent harvest age/tissue selection, and repeated experiments.
Separately vary light, temperature and water if you want to identify their
associations; reducing light and power together cannot isolate both coefficients.
Record failed crops and exclusions rather than dropping inconvenient outcomes.
Avoid intentionally stressing plants before establishing a safe baseline protocol.

Do not subdivide one chamber experiment into fake independent groups. The
validator can catch reused tray-cycles and shared resource IDs across groups,
but the experimenter must verify real independence and correct provenance.

## Fit the optional response association

```powershell
.\.venv\Scripts\python.exe scripts/crop_response.py --csv data/measurements/crop_cycles.csv --features daily_light_integral_mol_m2_day mean_temperature_c net_makeup_water_l_per_m2_day --holdout-group run-test-01 --holdout-group run-test-02 --holdout-group run-test-03
```

Use actual recorded holdout IDs in that command. Empty/missing data generates an
honest status report; it never invents a fitted model. The CLI returns exit code
2 for an unmet fit gate, and 0 only for an eligible experimental fit.

The current project safeguards require at least `max(12, 4 × (features + 1))`
training experiment groups, at least three held-out experiment groups, at least
80% environmental measurement coverage, observed feature variation and a
full-rank design. These are **prototype policy choices**, not a universal sample
size or accuracy guarantee. A study with fewer groups may still be valuable
evidence, but is not automatically promoted by this pipeline.

The ridge fit gives each independent group equal total weight so additional
correlated trays cannot inflate its influence. Scaling is learned from training
data only, and regularization alpha is specified before evaluating holdouts.
Validation reports group-weighted MAE/RMSE/bias and the training-mean endpoint
baseline. If the fit cannot improve held-out MAE or any held-out condition is
unsupported, its status is `failed_validation` and prediction remains unavailable.

Prediction requires the same profile and an age observed or fitted by the model.
A HiGHS feasibility check requires each proposed condition to lie inside the
**joint convex hull of measured training conditions**. Separate minimum/maximum
checks would permit unseen combinations, so they are not sufficient. A solver
failure also refuses prediction. No uncertainty interval is invented from these
small diagnostics; observational regression coefficients are not causal stress
laws, even after these checks pass.

Both status functions compare the fit report's source fingerprint to current
measurements. Changed data returns `stale_report`; the stored fit is not silently
treated as current evidence.

## Method and evidence sources

- [Ridge regression objective and regularization, scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).
- [Group-isolated validation for dependent observations](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
- [Training-only preprocessing and data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
- [Isotonic monotone regression](https://scikit-learn.org/stable/modules/isotonic.html).
- [EDEN ISS measured biomass study](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2020.00656/full): measured harvest summaries support endpoints but do not independently identify arbitrary water or power stress responses.
- [Zenodo measured lettuce dataset](https://zenodo.org/records/16912088), linked by [Aalto's dataset record](https://research.aalto.fi/en/datasets/lettuce-dataset-with-rgb-canopy-images-biomass-nutrient-solution-/): the downloaded version and exact mass/date ambiguities are pinned in the local source manifest.

Implementation uses existing NumPy and HiGHS dependencies; scikit-learn is a
method reference, not an added runtime dependency. Synthetic data appears only
in tests of split logic and guard behavior, never in the published measurement
reports.
