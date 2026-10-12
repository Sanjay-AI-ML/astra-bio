# ASTRA-BIO

Local nutrition-aware food, crop and resource planning with a **React frontend and FastAPI backend**. Streamlit has been removed. Pyomo/HiGHS solves allocations; Recharts draws results; SQLite stores configurations, runs and dietary logs. ESP32 Wi-Fi telemetry and camera JPEG storage support **MongoDB Atlas** through a separate HTTPS gateway; SQLite telemetry remains available until MongoDB is configured.

## Run

Requires Python 3.12, uv and Node.js 24. From PowerShell:

~~~powershell
cd D:\Seds\astra-bio
.\setup.ps1
.\run.ps1
~~~

Open [ASTRA-BIO](http://127.0.0.1:8501). Setup installs locked dependencies and builds React. The app, optimizer, evidence data and installed image model then run locally without a paid API. Ctrl+C stops the foreground app. API contracts are at /docs.

Frontend development: npm run dev --prefix frontend with the API running; Vite proxies API requests to8501. Production frontend update: npm run build --prefix frontend, then refresh the browser. Restart the app after backend source changes.

## Workflows

- **Mission overview:** explore a saved simulation day, with scenario, nominal-harvest and first-target-gap markers. Open crew, food-reserve, crop and resource nodes link to their related workflows; the selected day survives navigation. Nutrients, Water and Electricity chart views use saved daily values and budgets, with selected-day/scenario markers. A fixed-to-adaptive comparison shows signed absolute whole-run differences in target-gap days, harvest and water; these are calculated outcomes, not measured savings. Policy selection keeps related results together; chart-period filtering does not relabel whole-run totals. Review items link to assumptions, target gaps, sources and device status. The exact Seed & Star logo, white/sage palette and open spacing remain. Empty results remain empty; hardware observations refresh independently.
- **Crew & nutrition:** Nutrition & logs provides nine USDA foods, crew profiles, food-form logs, complete/partial declarations, intake gaps, example crop contributions and local profile/log snapshots. Mission inputs provides reviewed targets, crew/resource budgets, reserves, whole planting increments and optional food-mass/upper nutrient bounds. Reviewed mean targets apply to the shared planner explicitly.
- **Crops & food:** Crop schedules provides actual planting/harvest timelines and CSV export; editable coefficients sit under Crop profiles & assumptions. Food inventory provides stored stock, reserve eligibility, declared expiry and optional nutrient retention.
- **What-if simulator:** fixed nominal plan versus a replan from the same event-day state. Five editable starters cover water shortage, crop loss, crew increase, dietary change and nominal conditions; choosing one requires an explicit **Run comparison** to solve. Water/power reduction, active-cohort loss, more crew and target changes preserve historical decisions. Every completed run saves its submitted inputs and both policies. Explanations use verified saved facts.
- **Plant screening:** separate **Leaf screening** and **Fruit monitoring** tabs. Leaf screening uses local ONNX MobileNetV3 for tomato, potato and bell pepper; unsupported crops, invalid photos and weak/species-conflicting results are withheld. Fruit monitoring provides four pretrained local ONNX detectors: three- or six-stage tomato maturity, tomato detection only, and generic tomato/bell-pepper/exposed-potato detection. Uploaded photos show boxes, visible counts, source labels and model scores, with evidence JSON export. Manual screening uploads are processed transiently and are not sent to an external inference service. Device photographs stored through the separate camera gateway remain in Atlas. Neither workflow confirms pathogens or food safety; fruit observations do not credit inventory or trigger actions. See [fruit monitoring](docs/FRUIT_MONITORING.md).
- **Live devices:** independent hardware/synthetic streams, collector health, last availability, packet freshness, missing sensors and CSV export. Stale/offline readings and refresh errors remain explicit. Camera images provides an independent physical/synthetic photo channel, device filter, original JPEG viewer, receipt/capture time, transport and checksum. The attached GC2145 camera has delivered real photographs over verified Wi-Fi HTTPS into Atlas, with exact readback and duplicate checks. Refresh never replans or actuates. See [camera setup and operation](docs/CAMERA_MONGODB.md).
- **Workspace settings**, outside primary navigation: Saved plans contains named configuration snapshots, JSON import/export and run history restored without solving again. Model settings contains optional references, measured-profile setup, CSV calibration and yield sensitivity behind closed disclosures. Ten terrestrial EDEN ISS/NASA RLSS profiles and USDA composition connect explicitly to the planner.

The six primary groups use tabs for related work. Navigation search finds ten destinations through the visible control or **Ctrl/Cmd K**, including food/crop keywords; it searches destinations, not stored records. Unsubmitted mission/inventory drafts and crew dietary logs survive navigation. The mobile drawer supports keyboard focus, Escape and route/desktop closing. There is no primary Research page; existing research bookmarks open Model settings.

## Evidence and calibration

The **What-if simulator** now includes **Compare recovery options** for a saved run: ranked interventions, minimum additional stored food/daily water/electricity, optional hard reserve protection and fixed-policy lower-yield/delayed-harvest stress tests. Event-day relief preserves pre-event history. The analysis changes no inventory or equipment; results depend on the submitted coefficients. See [recovery planning](docs/RECOVERY_PLANNING.md).

Default demo inputs remain synthetic until explicitly replaced. Source provenance distinguishes measurements from assumptions. Lighting electricity derives from reported PPFD/photoperiod with assumed efficacy/delivery; net makeup water and whole-system HVAC/pump energy are missing from the reference measurements. Applied irrigation is not net consumption.

The crop model fits fresh edible batch endpoints, not intermediate biomass, microgravity response or mechanistic water-stress dynamics. Fitting NASA's first30-day lettuce trial and withholding its second gives **1.042kg/m² absolute error /46.94% error on one held-out trial**. This exposes limited transferability; it is not robust general accuracy. EDEN aggregate means are never expanded into invented individual cycles.

~~~powershell
.\.venv\Scripts\python.exe scripts\crop_calibrate.py
~~~

See [crop evidence](docs/CROP_MODEL_EVIDENCE.md), [nutrition evidence](docs/NUTRITION_EVIDENCE.md) and [plant model](docs/PLANT_VISION.md). Source bytes, identifiers, units, license notes and hashes are retained in data/research and runtime/plant-model/PROVENANCE.json.

Fruit models need explicit setup on a fresh clone; their binaries remain Git-ignored. Run the following after normal setup. Downloads are pinned and hash-checked, export uses a separate ML environment, and subsequent inference runs locally on CPU without downloading artifacts. All four have executed locally, but no independent ASTRA-BIO fruit benchmark or fruit fine-tuning has been completed. [Setup, exact sources and observation limits](docs/FRUIT_MONITORING.md).

~~~powershell
.\scripts\setup-fruit-models.ps1 -Action Full
.\scripts\setup-fruit-models.ps1 -Action Status
~~~

The first local image fine-tuning run is completed and selected: **41.25% held-out accuracy versus 28.75% for original weights**, across 80 PlantDoc images and ten represented classes. Accuracy remains low; fixed safeguards accept six images, with four correct. Measured lettuce growth now has a separate source-specific age curve fitted from 540 plant/day records, with **5.72 g/plant held-out MAE within one cycle**. Neither result validates your tray or spaceflight. Environmental-response fitting is implemented and awaits real repeated cycles. Model selection, metrics, the growth curve and a blank trial template are available through secondary model disclosures. See [fine-tuning results and commands](docs/ML_FINE_TUNING.md), [validation protocol](docs/ML_VALIDATION.md) and [crop-training guide](docs/CROP_TRAINING.md).

## ESP32 Wi-Fi and MongoDB Atlas

The current board choice is **ESP32-S3 WROOM**, with Atlas as the telemetry database. Read [the setup guide](docs/ESP32_MONGODB.md) for the Atlas database user, network allowlist and private connection URI.

~~~powershell
.\setup-mongodb.ps1 -DeviceId tray-01
.\.venv\Scripts\python.exe -m astra_bio.mongo_runtime check
.\run-gateway.ps1
~~~

Setup prompts for credentials privately and generates a device header with Wi-Fi details, its token and the gateway's public CA. The gateway exposes authenticated HTTPS numerical telemetry and bounded JPEG ingestion on the laptop's private Wi-Fi IP:8502. Atlas credentials stay on the backend. Device tokens reload on each request; restart the gateway after IP/port/certificate changes. The existing dashboard reads MongoDB when configured and reports outages without silently switching to SQLite.

In a second terminal, `.\test-mongodb.ps1 -DeviceId tray-01` sends one explicitly synthetic reading, retries the identical sample and verifies one MongoDB record. It requires a configured Atlas connection and running gateway. The firmware source is under `integration/esp32-mongodb`; its release compile passed for a generic ESP32-S3 DevKitC-1 N8/no-PSRAM profile with placeholder credentials. The attached camera board was separately identified as ESP32-S3 N16R8 and flashed with [camera firmware](integration/esp32-camera-mongodb/README.md). Its GC2145 camera-to-Atlas Wi-Fi path is physically verified; additional sensor models, wiring, drivers and calibration remain required. Missing sensor values are omitted. No actuator control is added.

The app now uses a white canvas, pale sage surfaces and dark green controls while preserving the supplied logo. Desktop/mobile theme checks and captures are under [white-mode verification](docs/designs/2026-10-12/white-mode/IMPLEMENTATION.md). **86 affected Python checks and 44 frontend checks passed; the production build passed.** These Python checks use controlled repositories for the MongoDB contract and do not establish a live Atlas write.

On 12 October 2026 the configured Atlas connection also passed a live software-path check: one synthetic `tray-01` sample was accepted through verified HTTPS, its identical retry was acknowledged without another record, and the dashboard read it from Atlas. [Credential-free verification report](docs/MONGODB_VERIFICATION.json). Cloud operations now allow eight seconds for a cold TLS/authentication connection; loopback MongoDB retains three seconds. Actual ESP32 Wi-Fi credentials, sensor drivers and physical flashing remain outstanding. Atlas network access was already working and was not changed.

## MQTT and hardware

~~~powershell
npm ci --prefix runtime/node-red
.\setup-mqtt.ps1
.\provision-device.ps1 -DeviceId tray-01
.\run-stack.ps1
~~~

The managed foreground stack runs authenticated Mosquitto, Node-RED and FastAPI when needed. Node-RED is localhost:1880; collector MQTT is authenticated localhost:1883; physical devices use CA-verified TLS on the laptop's private IPv4:8883. Credentials and builds are private and Git-ignored.

Use .\test-mqtt.ps1 -Tls for synthetic transport/ACL verification; .\simulate-device.ps1 -Count 0 -Tls publishes generated observations. ESP32-S3 firmware is compiled but **unflashed and uncalibrated**. Outputs are disabled. Stop the stack with .\stop-stack.ps1; see [hardware quickstart](docs/MQTT_QUICKSTART.md).

## Verify

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
~~~

Tests cover conservation, harvest timing, event-day continuity, expiry/retention, bounds/increments, source conversions, calibration leakage, missing intake, actual inference/abstention, snapshots, API workflows and MQTT/Node-RED contracts. The model work adds split/duplicate audits, confidence mathematics, candidate integrity/selection, measured age curves and environmental support guards. **193 Python tests and 13 subtests passed, with one Windows symlink test skipped; 43 frontend tests passed.** Checks include mission-day/event context, policy differences, resource chart fields, navigation search, editable presets, grouped navigation, explicit submission, retained drafts/logs, keyboard behavior, model evidence and missing/stale/error telemetry. Earlier product browser checks passed at 1280px, 1002px and 390×844: saved-day values and retention, policy/chart switching, search, editable presets without automatic solving, responsive layout and drawer closing. Warning/error logs were empty. See [product research](docs/designs/2026-10-11/product-experience/RESEARCH.md) and [verification/screenshots](docs/designs/2026-10-11/product-experience/IMPLEMENTATION.md) for that checked scope; this was not a full audit of every page.

## Scope

Only energy, protein and vitaminC are tracked. Crops supplement stored food. Fresh harvests are used/discarded the same day. Specified expiry/retention is sensitivity policy, not microbial-safety prediction. Crew allocations remain aggregate. Individual menus, cooking/preparation resources, full diet adequacy, crew work time, oxygen/CO₂ and waste recycling are outside this prototype. No clinical deficiency detector or autonomous device control is claimed.

Optional local Ollama fact selection has a bounded timeout and verified fallback; no daemon/model is required or installed. Grocy/Mealie remain optional references. The original Apache-2.0 starter license/Git origin are preserved. [UPSTREAM_SOURCES.json](UPSTREAM_SOURCES.json) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) document reuse and attribution.
