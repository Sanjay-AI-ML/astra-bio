# ASTRA-BIO project memory

Saved 12 October 2026 at the user's request. Read this alongside BUILD_STATUS.md when resuming; verification documents take precedence over conversational assumptions.

## Purpose and preferences

ASTRA-BIO connects crew nutritional requirements, food inventory, crop production and constrained resources for long-duration habitat decision support. Core loop: health requirements → nutrition → crops → resources → revised food plan. What-if scenarios include water/power reductions, crop losses or delays, crew changes and nutritional target changes. This is currently a terrestrial prototype, not a validated autonomous space habitat or clinical diagnostic system.

Team: BRAND NEW HACK. Team lead: SHREE RAM VISHAL M. SEDHACKS'26 domain: Medical, Food & Agriculture in Space. Hardware + software category.

User prefers concrete implementation, reuse of suitable open-source components, professional reference-informed UI and spacious layouts. Current application preference is white mode with the supplied ASTRA-BIO logo. Historical presentation preference was dark mode; do not confuse it with the app. Avoid decorative grids of tightly packed boxes. Research should use credible sources and distinguish demonstrated results from proposed capabilities. User knows basic Python/JavaScript and benefits from plain explanations.

## Biological production and catalyst research — 13 October 2026

The user wants ASTRA-BIO to foreground unusual plants and microorganisms instead of ordinary soy, and to explore catalyst-assisted production. A Biological production React workspace now compares Limnospira (Spirulina-type cyanobacterium) and Wolffia globosa as numerical terrestrial-reference candidates. Euglena, NASA engineered yeast, CO₂-to-acetate microbial/plant routes, nanozyme cucumber seedlings and mineral-enriched red-cabbage microgreens are evidence cards with limits. “Catalyst” is not treated as a nutrient or plant hybrid: electrolysis makes an acetate feedstock outside organisms; nanozymes change catalytic reactions in plant studies; mineral enrichment adds matter and is not catalysis.

The backend is an additional prospective projection from reviewed assumptions. It uses a matched Limnospira run pair (0.492 g dry/L/day × 42% protein) and a week-indexed eight-week Wolffia terrestrial fresh-growth series. Wolffia protein uses the study's dry fraction and dry-basis composition with explicit transfer assumptions for weeks without matched weekly composition. Research-only pathways cannot become food-yield forecasts by entering arbitrary coefficients. Resources are charged before production, saved mission resource commitments and growing area constrain capacity, harvest is timed, and output remains outside pantry and crew intake. No energy, nutrient, food-safety, space-transfer or capsule-equivalence claim is implied. Read `docs/BIOLOGICAL_PRODUCTION.md` for sources and experimental sequence.

## Implemented and verified scope

- Crew & nutrition now owns a shared editable roster. Its explicit Use this crew & replan action stores exact names and reviewed targets in a dated mission event, preserves elapsed history/resources and updates Overview. Initial rosters are serialized in config.crew_profiles; arbitrary count-only arrivals keep identities unknown. Overview shows the effective saved roster and automatic crop advice with an editable harvest deadline. Unapplied nutrition drafts are clearly separate. Only energy/protein/vitamin C are tracked; blood examples never determine targets. See CREW_ROSTER_PLANNING.md.
- Plant overview accepts an optional leaf close-up. The leaf classifier uses it while fruit detection retains the original plant photo; it cannot locate individual leaves in wide scenes. Tentative/uncertain/rejected results and image-source hashes remain explicit. Existing Gemini text-fact curation remains optional. Local CPU smoke checks do not establish tray accuracy. See PLANT_OVERVIEW.md.
- Interactive crew changes are available directly on the Mission overview timeline. Pause at any selected day, edit the full roster/targets, review and replan the remaining days from saved stock/resources/crop ages. The editor defaults to replacing pending crew arrivals, preserving unrelated future disruptions. The earlier Day-31/32 six-person arrivals were demonstration events, not a required simulator rule. The explicit Start a new mission action clears inherited events/disruptions and begins at Day 1 while retaining old history. See ROLLING_MISSION_CHANGES.md.

- React frontend and FastAPI backend; Streamlit removed. Mission overview, crew/nutrition, crop/food planning, what-if comparisons, plant screening, fruit monitoring and live devices.
- Pyomo/HiGHS constrained planning. Recovery planning compares stored food, additional water or electricity options; stress replay tests fixed plans under lower yields and delays. These scenarios are assumptions, not measured failure probabilities. See RECOVERY_PLANNING.md.
- MongoDB Atlas storage through an authenticated server gateway. Never put Atlas credentials on the ESP32 or in shared source files.
- ESP32-S3 N16R8, GC2145 camera, COM8. Physical capture → certificate-verified Wi-Fi HTTPS gateway on port 8502 → original image bytes in Atlas → dashboard has been verified. Camera currently captures 160×120 RGB565 converted to JPEG. Default capture is once on boot; another capture uses lowercase `c` in a 115200-baud serial monitor with newline. Recurring automatic capture is not enabled. External power, reachable gateway and Wi-Fi are required after unplugging USB. See CAMERA_MONGODB.md and CAMERA_VERIFICATION.json.
- Numerical sensor and actuator hardware behavior remains unverified. Earlier MQTT software/TLS tests used synthetic telemetry; do not describe them as physical sensor validation.
- Leaf screening uses a fine-tuned MobileNetV3 ONNX classifier for tomato, potato and bell pepper leaf classes. It is tentative screening, not pathogen confirmation. PlantDoc fine-tuning used 636 train, 160 validation and 80 test images; only ten classes were represented among fifteen outputs. Reported held-out accuracy was 41.25%; local tray validation is missing.
- Fruit monitoring reuses four pretrained ONNX YOLO checkpoints for tomato maturity/counting and generic tomato/bell-pepper/exposed-potato detection. Actual software inference was smoke-tested, not independently accuracy-validated. Fruit count is not harvest mass; photos cannot certify food safety, nutrient content or bacteria.

## Data and limitations

Ten terrestrial EDEN ISS/NASA crop profiles support reference harvest estimates; nine USDA food forms support energy/protein/vitamin C calculations. These are reference data, not measurements of our crops. An experimental lettuce age–mass curve uses 540 plant/day records within one cycle (12 training plants, 6 held-out plants), not 540 independent experiments. There are zero real measured environmental crop-cycle rows for fitting our tray's environmental response. Camera images stored in Atlas are real observations but are not automatically labeled biological training data. Check ML_VALIDATION.md and CROP_MODEL_EVIDENCE.md before quoting metrics.

## Latest research direction, not implemented

User asked what innovation would be strongest and requested thorough research. Research supports linking verified crop observations to updated harvest forecasts, predicted nutrient gaps and explainable, resource-feasible recovery options, followed by confirmed harvest logging and calibration against outcomes. Generic recovery optimization already exists in this repository. The missing contribution is qualified observation/harvest feedback into the planner and validation on local growing cycles.

Do not claim world-first integration or guaranteed competition success. Prior art includes NASA's September 2026 Mars to Table winning food-system concepts, ESA MELiSSA, Wageningen autonomous greenhouses and published nutrient/crop optimization. A distinctive working demonstration needs measured evidence. Suggested evaluation: harvest-date/yield error, nutrient-gap warning lead time, resource use and constraint satisfaction against the same baseline; report uncertainty and distinguish simulations from measured outcomes.

Primary research references:

- NASA Mars to Table winners, 24 September 2026: https://www.nasa.gov/directorates/stmd/prizes-challenges-crowdsourcing-program/centennial-challenges/nasa-unveils-winning-designs-for-mars-space-food-systems-challenge/
- Wageningen autonomous greenhouse programme and dataset links: https://www.wur.nl/en/research/plant/autonomous-greenhouse-challenge
- ESA MELiSSA compartments: https://www.esa.int/Enabling_Support/Space_Engineering_Technology/Melissa/Closed_Loop_Compartments
- Crop-based nutrient optimization: https://pubs.acs.org/doi/10.1021/acsfoodscitech.3c00396
- Paired RGB-D images and measured plant biomass: https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2022.758818/full

Research recommendations are not authorization to implement new features. The detailed research recommendation requested immediately before this memory request has not yet been delivered to the user.

## Secrets

Keep Wi-Fi passwords, MongoDB credentials, device tokens, private firmware and flash backups out of this memory and version control. User previously shared credentials in conversation; never reproduce them in documentation or answers.

## Latest implementation request

User wants the product to recommend crops by protein and other nutrient levels and continue simulations, rather than act only as a management dashboard. They explicitly selected continued simulations with reviewed inputs; automatic recurring ESP32 photos were not selected. The nutrient crop advisor, USDA crop-only composition update, mission playback and future-only continuation were implemented. Protein/energy/vitamin C priorities and balanced future-gap weighting are supported. Growing limits, pre-harvest gaps, reserve-eligible stock and data provenance remain explicit. Continued planning preserves simulated elapsed inventory/intake and uses remaining stock/cohorts, rather than restarting initial food. See NUTRIENT_CROP_ADVISOR.md and current BUILD_STATUS.md. These deterministic planning improvements do not claim a newly trained biological model or nutrient measurement from a camera.

User then requested a sample simulation. `scripts/run-sample-mission.py` creates a reproducible four-crew, 90-day, 20 m² sample using USDA dry-food forms and EDEN ISS/NASA crop references, with explicitly synthetic vitamin bridge food and assumed resource budgets. The sample protein target rises 40% on Day 30. The actual solve produced 49 fixed-plan versus 12 adaptive-plan target-gap days and 16.41 versus 84.16 kg modeled harvest. Day-one 0.25 m² protein advice selects `arugula_600`, first harvest Day 30; later additive crop capacity is constrained. Inputs, result and eight advisor comparisons are saved in `data/samples/nutrient-mission/`. The sample is saved as a new local run; earlier runs remain available. No synthetic hardware telemetry or camera data was published. Browser playback was started after confirming results.

User requested named sample people and very clear graphs in Crew & nutrition: Shree Ram Vishal, Shamyuktha, Sanjay and Vamshika, with Vamshika a fictional iron-deficiency example. Implemented seven days of food-derived energy/protein/vitamin C graphs and distinct haemoglobin/ferritin comparisons with discrete Day 1/15/30 histories. All personal attributes and lab readings are invented for demonstration; no actual health claim. WHO cutoffs are scoped references, not normal bands or treatment targets. Increasing active/configured sample crew gives numbered Sample Crew 5/6/etc.; new blood tests remain unknown. Fictional snapshot markers prevent invented labs being attached to ordinary restored logs. See CREW_SAMPLE_GRAPHS.md. The three-nutrient planner still does not optimize iron intake or diagnose deficiency.
