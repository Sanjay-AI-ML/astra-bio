# Measured lettuce growth data

Source: Karimzadeh, S. and Ahamed, M.S., *Lettuce Dataset with RGB Canopy Images, Biomass, Nutrient Solution, and Environmental Variables for Machine Learning Model Development*. [Pinned Zenodo record17041810](https://zenodo.org/records/17041810); concept DOI [10.5281/zenodo.16912088](https://doi.org/10.5281/zenodo.16912088). Original files are licensed [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). [Creator institution description](https://research.aalto.fi/en/datasets/lettuce-dataset-with-rgb-canopy-images-biomass-nutrient-solution-/).

`growth_observations.csv` unpivots **540 measured biomass cells**, representing **18 plants observed at DAT1–30**, from `4_Biomass.xlsx`, sheetsB2/B3/B4. Every row preserves its original sheet/cell reference. The blank DAT31harvest row supplies no biomass and is excluded. `Sum` columns are aggregates, not independent plants, and are excluded.

The dataset documents **one cultivation cycle** in a shared two-tier NFT system. Entire plant trajectories can be reserved for a within-cycle diagnostic; days and plants do not become independent cultivation cycles. It provides no randomized water/light/temperature intervention. Reservoir volume is not net crop water consumption.

The named cultivar and weighed plant part are unspecified. The normalization records `cultivar=unspecified_butterhead` and `mass_basis=unspecified_fresh`; these measurements are not edible-yield observations. The source README reports14-day seedlings at transplanting; DAT is therefore distinct from age after sowing.

**Calendar conflict:** the README describes2024-02-21to2024-03-23, but the workbook's Excel serial dates decode to2022-02-21to2022-03-23. The importer preserves the original serial/date fields and fits only the explicit DAT column. It does not silently correct the source year or invent a second cycle.

Reproduce locally:

```powershell
.venv\Scripts\python.exe scripts\import_measured_growth.py
```

Explicit source acquisition:

```powershell
.venv\Scripts\python.exe scripts\import_measured_growth.py --download
```

The importer requests selected small original members of the743MBZIP through HTTP byte ranges, validates the publisher's pinned archive metadata, validates ZIP entry CRCs and pinned member SHA256s, and retains original files unchanged. The whole archive's publisher MD5 is recorded but **not claimed verified**, because the archive was not downloaded in full. Optional source figures can be retained with `--include-figures`; canopy image files are not used by this curve.

`source_manifest.json` records attribution, license, acquisition and hashes; `normalization_report.json` describes transformations and18missing DAT31cells. The normalized CSV's SHA256 is13ec5bbe033c6854c979ffa25e4093f27b2b1e92f458c02c82e783848014a7b9.

## Separate environmental-response candidate

`wur_response_candidate/` retains metadata and access evidence only for [Meinen etal2025, original Carotti etal2021 lettuce response data](https://doi.org/10.4121/5a7472f0-8a67-4ec0-84c9-9d032990d654.v1), licensedCC-BY-4.0. The primary record describes measured light/air-temperature/root-temperature treatments across four cycles. On11October2026, its storage maintenance banner and HTTP503 prevented raw measurement acquisition. It is **not training data and no response model is fitted from its metadata**. Water was non-limiting in that experiment, so even future acquisition would not calibrate water-shortage loss.
