# Biological production workspace

Updated 13 October 2026. ASTRA-BIO now has a prospective production planner for microbial biomass, unusual aquatic crops, and catalyst-assisted research. This is a planning and evidence-comparison feature. It does not culture organisms, command equipment, diagnose crew, credit unharvested biomass as food, or replace an approved ration.

## Candidate portfolio

| Route | Organism or process | What the evidence supports | What ASTRA-BIO can calculate |
| --- | --- | --- | --- |
| Microbial protein | *Limnospira indica* (Spirulina-type cyanobacterium), PC8005 | One matched continuous-culture run in an 83 L terrestrial photobioreactor reports 0.82 g dry biomass/L at 0.025 h⁻¹ dilution, which gives 0.492 g dry/L/day; its protein value is 42.0% dry mass. The simulator retains this matched pair. | A linear literature-rate projection for reviewed reactor volume, startup, power, water and medium inputs. It is not a small-reactor scale-up result. |
| Protein-rich aquatic crop | *Wolffia globosa* in study-specific Chlorella medium | A terrestrial eight-week study reports weekly net fresh-growth rates for repeated harvests. Week one is 42.14 g fresh/m²/day, 4.83 g dry/m²/day and 46.10% protein on dry mass. The reported fresh and dry values make 2.23 g protein/m²/day a derived week-one value. | Week-indexed fresh biomass and a dry-basis protein estimate. It explicitly carries the study's week-one dry fraction and medium-level protein fraction into later weeks; this transfer is not measured for every harvest. No yield is extrapolated after week eight. |
| Protein composition study | *Euglena gracilis* CCAP 1224/5Z | A specific heterotrophic treatment reports 66.10% crude protein on dry mass. The paper does not supply the matched operational yield and resource dataset needed for a production projection. Protein composition is strain- and method-specific. | Evidence card only. No biomass or protein yield is calculated. This research strain is not interchangeable with a separately evaluated food ingredient strain. |
| Targeted nutrient research | NASA engineered yeast strains | NASA BioNutrients demonstrated nutrient-specific engineered yeast experiments, including a 48-hour incubation for beta-carotene/zeaxanthin work. Published experiment duration is not a measured edible nutrient yield. | Evidence card only; no capsule-equivalent or nutrient output is invented. |
| Catalyst-to-biology route | Electrochemical CO₂-to-acetate feeding tested microbes or seedlings | A two-stage electrochemical system produced acetate used by tested organisms; isotope tracing demonstrated acetate-carbon incorporation in some crop tissues. The catalyst and electrolyser are external feedstock production steps. Seedling incorporation does not establish mature edible yield, fruit nutrient gains, or a complete habitat energy balance. | Evidence card only until the coupled reactor, acetate purity, energy, resource, and edible-yield measurements are available. |
| Plant catalyst research | Fe₃O₄ or Mn₃O₄ nanozyme treatments in cucumber seedlings | Studies report altered antioxidant response or seedling growth under their particular terrestrial conditions. They do not establish safe edible-fruit treatment or mature yield gains for ASTRA-BIO cultivars. | Evidence card only. No catalyst dose or yield multiplier is given to the operator. |
| Mineral enrichment candidate | Red-cabbage microgreens | A study shows treatment-specific iron/zinc tissue enrichment. Relative enrichment is not an absolute final nutrient concentration, and adding a mineral is a material input rather than catalysis. | Evidence card only until matched harvested composition, biomass, and food-safety measurements are supplied. |

This portfolio deliberately emphasizes *Wolffia* and microbial production rather than defaulting to soy. “Hybrid” is used carefully: combining a plant with a catalyst process does not create a genetically hybrid plant. A catalyst route is a separately measured production step. Plant breeding, gene editing, nutrient enrichment, microbial co-culture and electrocatalysis are different methods with different evidence and safety requirements.

## How the projection works

The React workspace loads its profile catalog from `GET /api/bioproduction/catalog`. An operator can add literature-supported modules, choose a mission-day window and nutrient focus, and enter capacity, startup, water, electricity, medium/feed flow and initial fill. Missing biological or operational coefficients stay unknown; a module with required unknowns is not projected. A reviewed-input acknowledgement is required before submission.

`POST /api/bioproduction/simulate` projects each day against the selected saved mission's remaining water, energy and growing area. Finite closing stores are not reused. Commissioning is charged before any production. A held module produces no output in the accounting model. The output shows biomass, protein where supported, nutrient units, daily resource use, active crew context, mission protein target share and source provenance. Existing stored-food assignments are unchanged and the projection is not entered as food inventory or consumed nutrition.

The planner also supports a what-if stress test. An operator can schedule changes to water, electrical supply, medium/feed or modeled biomass output from a selected mission day. The interface submits the same reviewed plan twice—once with events and once as the baseline—and compares daily and total protein projections. Multiple changes on the same day combine multiplicatively. These are arithmetic input perturbations: they do not model culture death, acclimation, recovery, delayed growth, or biological feedback, so the comparison is a sensitivity analysis rather than a forecast of a real disruption.

For the Wolffia reference, the study's eight weekly net fresh rates are used as a measured terrestrial sequence. The model aggregates daily growth to a seven-day harvest. It multiplies fresh harvest by a study-specific dry fraction and then dry biomass by the study's dry-basis protein fraction. Both composition transfers are identified in the profile, and they remain assumptions for weeks where the paper does not report an independently matched composition. The simulator stops after the eight supported weeks.

For Limnospira, the paired Run 6 biomass rate and protein percentage are retained together. The simulator does not combine the best biomass rate from one run with the best protein percentage from another. Its medium flow is gross throughput; recovered medium, makeup water and complete water closure are not established. A prototype operator must enter power, startup and commissioning assumptions.

## Suggested research and validation sequence

1. Compare *Limnospira* and *Wolffia* across the actual remaining mission window and constraints. Treat both as independent candidate lines until there is a measured shared-process basis.
2. Run repeated terrestrial pilot batches with defined strain/cultivar, medium recipe, light, temperature, gas exchange, inoculum, harvest method and contamination checks. Record independent batches rather than counting each daily observation as an independent experiment.
3. At each harvest measure fresh mass, dry mass, crude protein with the method and nitrogen conversion factor stated, amino-acid profile, target micronutrients and microbiological quality. Track electricity, makeup water, medium/feedstock, oxygen/CO₂ transfer and crew footprint for the same batch.
4. Evaluate CO₂-to-acetate as a separately metered research module. Measure CO₂ conversion, acetate titer/purity, electrical input, system losses and biological conversion before linking it to a crop or microbial harvest.
5. Keep nanozyme and engineered-organism trials behind laboratory food-safety and applicable regulatory review. A seedling antioxidant result is not authorization to add a catalyst to food production.
6. Only after matched independent local cycles exist should the environmental crop model be calibrated. Hold out whole production cycles for validation and report error intervals; do not train or validate on different days from the same plants as if they were independent batches.

Capsule replacement is outside the evidence. The NASA nutrient-production experiments establish a research pathway, not a complete human diet. In particular, plant biomass and protein do not establish essential amino-acid adequacy, digestibility, bioavailability, all required micronutrients, shelf stability or clinical equivalence.

## Primary sources

- Garcia-Gragera et al. [Continuous culture of *Limnospira indica* in a ground photobioreactor](https://enviromicro-journals.onlinelibrary.wiley.com/doi/10.1111/1751-7915.13882).
- [Cultivation of *Wolffia globosa* and functional food development](https://www.nature.com/articles/s41598-025-22032-z), *Scientific Reports* (2025).
- [Optimization of heterotrophic *Euglena gracilis* culture for protein](https://www.mdpi.com/1660-3397/21/10/519), *Marine Drugs* (2023).
- NASA, [What is BioNutrients?](https://www.nasa.gov/general/what-is-bionutrients/).
- McGee et al., [Hybrid inorganic–biological artificial photosynthesis](https://www.nature.com/articles/s43016-022-00530-x), *Nature Food* (2022).
- Royal Society of Chemistry, [Plant-mimicking nanozymes for cucumber seedling salinity tolerance](https://pubs.rsc.org/en/content/articlehtml/2020/en/d0en00214c), *Environmental Science: Nano* (2020).
- [Agronomic iron and zinc biofortification of microgreens](https://www.mdpi.com/2073-4395/9/11/677), *Agronomy* (2019).
- European Space Agency, [Green smoothies in space](https://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Research/Green_smoothies_in_space), describing the ISS Spirulina demonstration and its microgravity gas-management challenge.
- NASA Office of Dietary Supplements, [Vitamin B12 consumer fact sheet](https://ods.od.nih.gov/factsheets/VitaminB12-Consumer/), for the limitation that ordinary plant biomass does not establish B12 adequacy.
