# What to learn to understand and develop ASTRA-BIO

Prepared on 12 October 2026 for someone who already knows basic Python or JavaScript. This is a project-specific learning syllabus. Follow the exercises on development copies/test data, keeping synthetic packets labelled synthetic and keeping credentials out of screenshots, source control and exports.

Your first goal is to explain three complete flows: a submitted scenario becoming a saved plan; a plant photograph becoming a screening result; and a device observation becoming a dashboard reading. Your next goal is to change one of these flows without breaking validation, provenance or reproducibility.

| Component | Role in this project | Concepts to learn |
| --- | --- | --- |
| React | Interactive interface | Components, props, state, controlled forms, effects, immutable updates, accessibility |
| Vite/Recharts | Frontend tooling and plots | Development versus production builds; plotting actual returned values, units and empty/error states |
| FastAPI/Uvicorn | Application backend/server | HTTP routes, JSON contracts, validation, status codes, errors, request handling |
| Pyomo/HiGHS | Planning engine | Variables, constraints, objective, LP/MILP, solver status, shortages |
| SQLite | Planning configuration, run and dietary snapshots | SQL, IDs, transactions, versioned JSON snapshots, durability |
| PyMongo/MongoDB Atlas | Configured sensor telemetry | Documents, filters, sorting, indexes, UTC dates, TLS, connection pooling |
| PyTorch/MobileNetV3 | Offline image-model training | Transfer learning, frozen backbone, classifier training, validation |
| ONNX Runtime | Local deployed image inference | Exported graph, tensor shapes, preprocessing, mapping, integrity and parity |
| Arduino/PlatformIO/ESP32 | Physical device uploader | C++, drivers, GPIO/buses, Wi-Fi, TLS, timestamps, retries and persistent packets |

**Study module 1: understand the architecture.** A frontend displays and collects data; a backend validates and performs work; a database persists data; a solver or inference engine produces a specific output. These are separate responsibilities. A Python server process is different from a stored database, and a cloud database does not host the app.

The current planning flow is React form → HTTP/JSON → FastAPI validation → Pyomo/HiGHS solve → SQLite run snapshot → returned JSON → React charts. The photograph flow is upload → image validation/preprocessing → selected local ONNX model → confidence/species guards → tentative or withheld result. The device flow is ESP32 → Wi-Fi/HTTPS → token-authenticated gateway → validated observation → Atlas → backend query → dashboard.

Learn the meanings of localhost, private LAN IP, public outbound IP, port, DNS, client, server and gateway. `127.0.0.1` on an ESP32 refers to that device, while `127.0.0.1` on the laptop refers to the laptop. The dashboard uses port 8501 and the separate HTTPS ingress uses 8502. MQTT is an older optional path, not an additional requirement for current Atlas delivery.

Exercise: draw all three flows and explain exactly which process stops working when the laptop sleeps, Wi-Fi disconnects or Atlas becomes unavailable.

**Study module 2: read the Python application structure.** Practice modules/imports, dictionaries/lists, type hints, dataclasses, immutable replacement, exceptions, file paths and JSON serialization. Distinguish a data record from a service that operates on records. Start with `astra_bio/model.py`: `FoodSpec`, `CropSpec`, `HabitatConfig` and `Scenario`. Follow their validation methods before reading solver internals.

Learn virtual environments, `pyproject.toml`, `uv.lock`, installed versus declared dependencies, relative versus absolute paths and running a module with `python -m`. Learn to read a traceback from the final exception back to the application call that caused it. Read `run.ps1` and `setup.ps1` to understand installation/build/startup responsibilities.

Exercise: instantiate a tiny configuration in a separate scratch file, serialize it, restore it and reject a negative resource budget without changing production defaults.

**Study module 3: learn HTTP and FastAPI contracts.** Understand GET/POST, path and query parameters, headers, request/response bodies, JSON objects/arrays, multipart photo uploads, content types and status codes. GET normally retrieves; a submitted solve is POST because it performs work and saves a result. Identify error responses rather than assuming every fetch returns valid success data.

Read `/api/bootstrap`, `/api/config/validate`, `/api/plans`, `/api/plant-image`, `/api/models` and `/api/telemetry` in `astra_bio/api.py`. The current code validates dictionaries through project dataclasses/helpers; also learn Pydantic schemas for future structured API development. Understand the solver lock, a concurrent-solve 409 response, input-validation 422 responses and unavailable-telemetry 503 responses. Use the local `/docs` page to inspect application contracts; the device-only gateway deliberately has no public Swagger page.

Study `async/await`, promises and the difference between waiting on network I/O and doing CPU-heavy inference/optimization. An `async` function does not automatically make blocking work nonblocking. Read the gateway's `run_in_threadpool` call to see how synchronous ingestion is moved off its async request handler.

Official learning resources: [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/), [FastAPI concurrency](https://fastapi.tiangolo.com/async/) and [MDN Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).

Exercise: trace a crew-count edit from the form through validation into a saved comparison. Inspect one valid and one invalid request in browser developer tools. Never print private runtime settings when debugging.

**Study module 4: understand React state and interface behavior.** Learn JSX, components, props, `useState`, `useEffect`, event handlers, controlled inputs, immutable updates, derived values and effect cleanup. Know the difference between an editable draft, validated active configuration and a saved run. Editing inputs invalidates the old displayed comparison; selecting a starter does not solve automatically.

Read `frontend/src/main.jsx`, then the smaller `HabitatOverview.jsx`, `MissionExplorer.jsx`, `NutritionPanel.jsx`, `ModelEvidence.jsx` and `useTelemetry.js`. Trace its request helper and the simulator submit handler. Learn loading, empty, rejected and failure states alongside successful rendering. Telemetry polls every ten seconds and cancels obsolete requests; this is polling, not a WebSocket subscription.

Study semantic HTML, labels, keyboard focus, Escape behavior, contrast, responsive CSS and chart units. Preserving a form during navigation is different from persisting it across browser reloads. Vite's development server and the built `frontend/dist` bundle are different run modes.

Official starting points: [Thinking in React](https://react.dev/learn/thinking-in-react), [Managing State](https://react.dev/learn/managing-state) and [Preserving/Resetting State](https://react.dev/learn/preserving-and-resetting-state).

Exercise: display one existing response metric with its correct unit and loading/error behavior. Change only presentation, then run the relevant frontend test.

**Study module 5: learn storage and telemetry semantics.** SQLite stores local configuration/run/dietary snapshots. Configured Atlas stores observations. Study tables versus documents, IDs, CRUD, filtering, sorting, transactions, schema versions, compound indexes and UTC date storage. An index is an access/integrity mechanism, not a measurement-quality check.

Read `workspace.py`, `storage.py`, `mongo_telemetry.py` and `mongo_runtime.py`. A saved run preserves the submitted inputs and both policies; restoring it does not rerun the solver. The observation identity is `(device_id, source, sample_id)`. An identical retry returns the original record; changed content under that identity is rejected. This is idempotency. It does not guarantee that every physical measurement was sampled or recorded during an outage.

Learn missing versus zero, hardware versus synthetic, device time versus receipt time, `null` versus invalid numeric values, units, calibration and provenance. A missing temperature must not become 0 °C; a low-water flag does not measure liters consumed; freshness does not prove calibration. MongoDB failure remains an error when configured rather than silently showing SQLite measurements.

Study connection pools and operation deadlines. Our cloud driver uses an eight-second per-operation deadline. Several operations in one request and initial DNS lookup behavior require separate reasoning; an operation timeout is not automatically a complete HTTP deadline. Resources: [PyMongo indexes](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/indexes/) and [driver timeouts](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-options/csot/).

Exercise: explain the successful synthetic test's 201/200 responses and exactly-one-record result from `docs/MONGODB_VERIFICATION.json`. In a test repository, verify identical retry, conflicting retry, invalid reading and missing reading behavior.

**Study module 6: learn optimization before calling the planner AI.** An optimizer chooses values under supplied rules and coefficients. Learn decision variables, parameters, constraints, objective, feasible solution, optimal solution, solver termination and soft constraints. Continuous planting area gives a linear program; integer tray counts make it a mixed-integer linear program. Pyomo expresses the mathematical problem; HiGHS solves it.

In our planner, decision variables include food consumed, remaining inventory, waste, new planting area, retained existing crop area, nutrient shortfalls and reserve gaps. Learn the two central relations:

```text
closing inventory = opening inventory + harvest - consumption - waste
nutrient supply + reported shortfall >= dietary target
```

Occupied area and crop water/electricity must fit the budgets. Crew water is deducted before assigning crop water. Harvest enters the food balance only when its batch matures. Fresh crop inventory cannot carry beyond harvest day in the current implementation. Optional upper nutrient and total-food limits can make allocation harder even when some food is available.

The objective minimizes `100000 × normalized nutrient shortfall + 1000 × normalized reserve gap + small operating penalties`. Normalizing by targets avoids directly adding kcal, grams and milligrams. These weights express policy preferences; they do not create a formal strict priority guarantee for every possible input. A mathematically optimal solution can still show dietary gaps because those gaps are permitted and penalized. Small operating penalties are model preferences, not validated financial costs.

Read `planner.py::_solve_lp`, its constraint construction and result extraction. Use [Pyomo mathematical modeling](https://pyomo.readthedocs.io/en/stable/getting_started/pyomo_overview/math_modeling.html) as the external introduction.

Exercise: build a separate two-food, two-nutrient toy allocation problem. Reduce a stock/budget until a gap appears and explain the active constraint. Then inspect a project test for inventory conservation and harvest timing.

**Study module 7: understand fair what-if comparisons.** Learn state reconstruction, active crop cohorts, event-day chronology, baseline and adaptive policies. A fair comparison begins with the same inventory and crop batches and preserves the same history before the event. A crop-loss event affects crops active at that event; it does not automatically destroy every future planting.

Read `run_comparison` and `_replay_fixed_plan`. The current fixed-plan resource-stress yield reduction is a labelled proxy, not a fitted causal biological response. A difference between simulated policies shows behavior under those assumptions, not observed mission performance. Sensitivity analysis asks how conclusions change when assumptions change; it is separate from a statistical confidence interval.

Exercise: run a small test scenario and inspect the equality of both policies before the event. Explain why a crop-loss scenario can affect no harvest if no matching batch was active that day.

**Study module 8: learn nutrition as unit-aware accounting.** Logged intake is `sum(food grams / 1000 × nutrients per kg)`. Learn per-100-g versus per-kg conversion, kcal/g/mg, raw versus cooked food forms, target coverage, shortfall and upper bounds. Food composition and available food mass are separate inputs.

`nutrition.py` tracks energy, protein and vitamin C. An incomplete/absent log is different from an explicitly completed zero-intake day. A recorded target gap is not a clinical deficiency diagnosis. Reviewed crew targets are averaged for the shared planner; this does not produce individualized menus. Generic crop composition is not a nutrient assay of the tray's harvest. Declared shelf life and nutrient half lives are assumptions rather than measured microbial safety.

Exercise: manually reproduce one food log calculation and one nutrient coverage value. Then verify a missing entry remains unknown/partial instead of being silently treated as zero.

**Study module 9: separate the crop models.** `crop_growth.py` uses matched reference batch endpoints: harvest mass is area times yield per square meter, with explicit maturity timing. Learn cultivar/environment matching, measurement basis, reported aggregate versus individual-cycle records, observed ranges and engineering lighting estimates. The NASA single-held-out-trial error is 1.0415 kg/m² / 46.94%; it is not a general accuracy estimate.

`measured_growth.py` averages measured training plants by age, fits a weighted nondecreasing curve using isotonic regression, and interpolates between supported ages. Learn monotonicity, interpolation versus extrapolation and group holdouts. Its 540 records represent repeated measurements from one growing cycle, not 540 independent experiments. It holds out six entire plants and has 5.72 g/plant MAE within that source cycle. It remains separate from planner endpoint yields and is not an actuator-control model.

`crop_trials.py` offers group-weighted standardized ridge regression relating environmental/resource features to a harvest endpoint. Learn features, target, standardization fitted on training data, regression coefficients, regularization, collinearity, confounding and joint environmental support. Features can include growth duration, daily light integral, temperature, humidity, CO₂, net makeup water, lighting energy, EC, pH and density. The current template has zero real measured cycles, so this model is awaiting data. A fitted association would still require independent evaluation before it is interpreted as an intervention effect.

Study `docs/CROP_MODEL_EVIDENCE.md`, `docs/CROP_TRAINING.md`, `scripts/crop_calibrate.py`, `scripts/fit_measured_growth.py` and `scripts/crop_response.py`. Learn PPFD, photoperiod and DLI enough to preserve units; lux cannot be substituted directly without a justified calibration.

Exercise: explain what each crop model predicts and why none of its current results establishes performance on our physical tray. Design a record for one real crop cycle, including mass basis, calibrated resources and an independent experiment ID.

**Study module 10: learn image transfer learning.** Start with image tensors, RGB channels, input size, normalization, batches, feature extraction and classification. MobileNetV3 is the pretrained convolutional architecture; the project freezes its feature backbone and trains the classifier on mapped PlantDoc classes. Learn weights, logits, softmax, loss, epoch, batch size, learning rate, augmentation, class weighting, gradient updates, train/eval mode and checkpoint selection.

Read `plant_training.py` and the completed `docs/ML_FINE_TUNING.md`. The completed run used five epochs, 636 training, 160 validation and 80 test images. There are fifteen output classes but only ten represented in this benchmark. Model selection used validation evidence. Downloaded images, specialist-labelled local tray images and a controlled spaceflight experiment are different sources of evidence. [PyTorch's transfer-learning tutorial](https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html) provides a practical introduction.

Learn training versus inference: training updates weights; inference applies selected weights. PyTorch training runs in a separate environment, while the app executes the exported ONNX graph on CPU. Inputs, preprocessing and class order must match. Export parity checks numerical agreement between those implementations; it does not establish biological correctness. Study [ONNX Runtime Python](https://onnxruntime.ai/docs/get-started/with-python.html).

Exercise: trace a supported photo from `/api/plant-image` through `plant_vision.py`, identifying preprocessing, model selection, class mapping and abstention. Explain why the deployed app does not train a model when someone uploads a photo.

**Study module 11: learn evaluation and uncertainty.** Training data updates a model; validation data supports development decisions/calibration; test data evaluates the chosen candidate. Repeatedly tuning after looking at the same test set makes it development evidence. Split related photographs/measurements together, so a duplicate photo, repeated plant or shared-resource experiment does not appear across supposedly independent partitions. Study [data leakage](https://scikit-learn.org/stable/common_pitfalls.html).

| Term | Meaning you should be able to explain |
| --- | --- |
| Accuracy | Fraction of classifications correct |
| Precision | Among predicted positives, the fraction actually positive |
| Recall | Among actual positives, the fraction detected |
| Macro F1 | Average class F1 with each included class weighted equally |
| Confusion matrix | Which true/predicted classes are confused |
| MAE | Average absolute numerical prediction error, in the target unit |
| RMSE | Root mean squared error, giving greater influence to large errors |
| Calibration | Whether reported probability scores match observed frequencies on appropriate evaluation data |
| Coverage | Fraction of cases where the system accepts a result |
| Selective accuracy | Accuracy among accepted results |
| Domain shift | Deployment conditions differ from the evaluated data |
| Out-of-distribution input | An input outside the modeled/evaluated situation |

Metrics resources: [scikit-learn evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html) and [probability calibration](https://scikit-learn.org/stable/modules/calibration.html).

Temperature scaling adjusts logits using a positive fitted temperature before softmax. It changes scores without changing their class order. Fit it using validation data, then evaluate its behavior on held-out data. A score of 0.90 is not by itself proof of 90% real-world accuracy. Our candidate improved accuracy to 41.25%, while the reported test ECE worsened; different metrics assess different properties.

Read `vision_evaluation.py`, `plant_vision.py` and `plant_registry.py`. Species mass/margin and score thresholds can withhold weak results; they are screening policies requiring validation. Six of eighty test images were accepted and four were correct. That means 7.5% coverage and 66.7% selective accuracy on a very small accepted subset, not dependable field diagnosis. Image hashes, model hashes, dataset versions and class mappings make a run traceable; they do not prove external validity.

Exercise: calculate a tiny confusion matrix and MAE by hand. Explain why splitting 540 rows at random can leak plant history, and why specialist-labelled independent tray cycles are still necessary.

**Study module 12: learn the device/security contract.** Learn basic C++, confirmed GPIOs, I²C/OneWire/digital inputs as appropriate to the selected sensor, sensor libraries, startup/read failures, sampling and calibration. The current uploader's hardware hooks are empty. Filling a missing measurement with a fabricated zero makes the data misleading even if the network path works.

Read `integration/esp32-mongodb/src/main.cpp`, `telemetry_gateway.py` and `docs/ESP32_MONGODB.md`. Learn HTTPS, trusted CA certificates, certificate hostname/IP verification, UTC/NTP and device bearer tokens. TLS verifies/protects the connection; the per-device token authorizes whose data can be submitted. Atlas credentials belong only on the backend. See [Espressif's certificate guidance](https://github.com/espressif/arduino-esp32/blob/master/libraries/NetworkClientSecure/README.md).

Learn sample IDs, acknowledgements, bounded timeouts, exponential backoff, jitter and NVS persistence. The firmware keeps one unchanged pending packet until acknowledgement. It does not record all intervening readings during an outage. Learn the difference between polling, MQTT publish/subscribe and WebSockets, while keeping the selected HTTPS contract consistent.

Exercise: after a sensor model and wiring are confirmed, implement one real reading, check its units against a reference instrument and test Wi-Fi disconnection/reconnection. Use the explicit synthetic mode for network-only tests. Board compilation, flashing, successful transport and calibrated sensing are four separate checkpoints.

**Study module 13: learn behavioral testing and reproducibility.** Unit tests check a small behavior; integration tests check component boundaries; browser tests check actual interaction; live transport tests check a running data path; physical tests check real equipment. Fakes isolate controlled cases, but do not establish live Atlas or hardware connectivity. Our newest affected run passed 86 backend tests; a separate live software-path record verifies HTTPS/Atlas behavior with synthetic data.

Study fixtures, temporary files, monkeypatching, parameterized tests, assertions and failure diagnosis in `tests/`. Read frontend tests with the knowledge that some fetch/chart behavior is mocked. Good examples include inventory conservation, harvest timing, pre-event equality, duplicate retry rejection, missing intake and uncertainty withholding. Avoid interpreting a passing UI test as model accuracy or a model benchmark as electrical safety.

Learn Git status/diff/branches/commits, `.gitignore`, locked dependencies, source licenses, pinned versions, dataset manifests, fingerprints and seeds. Read `UPSTREAM_SOURCES.json` and `THIRD_PARTY_NOTICES.md`. The app reuses libraries and model artifacts; you need to explain the integration, attribution and actual original extensions. Resources: [pytest](https://docs.pytest.org/en/stable/) and [Pro Git](https://git-scm.com/book/en/v2).

Exercise: change one small validation rule on a development copy, write a relevant failure/success case and inspect the diff. Use an isolated test repository rather than sending test fixtures to the live database accidentally.

**Study module 14: learn the next product layer after understanding the current one.** Durable hosting, service management, user authentication/roles, migrations, backup/restore, operational monitoring, alerts, background jobs, offline packet history and deployment rollback are product-readiness topics. For equipment control, learn setpoints, feedback, hysteresis, actuator limits, interlocks, local low-water cutoff and manual override before advanced PID/MPC work. Control performance needs a suitable measured plant/resource response and physical testing.

The present system displays telemetry but does not map it automatically into model inputs, retrain models, initiate solves, diagnose deficiencies, remove crops or operate equipment. Learn how to define a quality/freshness gate and a reviewed update policy before implementing that feedback. Advanced reinforcement learning, large-language-model training and distributed infrastructure are later specializations rather than starting points for this codebase.

**A practical study sequence** is architecture/contracts → Python data models → React/FastAPI request flow → storage/provenance → optimizer/simulation → nutrition/crop models → image training/inference → evaluation → ESP32 integration → testing/reproducibility → deployment and safe feedback/control. At each step, produce a small exercise and explain its failure behavior. Advance when you can trace inputs, transformation, output, persistence and limits without relying on the project name or an AI-generated summary.

**Questions you should be able to answer for a demo or review:**

1. What exactly happens when Run comparison is clicked?
2. Which inputs are measured, sourced, manually entered or synthetic?
3. What chooses food and crops: optimization, a trained classifier or an LLM?
4. What makes the two scenario policies comparable?
5. Why can an optimal result still report nutrient shortages?
6. Why can't a new crop satisfy an immediate food gap?
7. What is stored in SQLite versus Atlas?
8. What happens after the same device packet is submitted twice?
9. How are missing readings, stale packets and synthetic data presented?
10. What does the plant model support, and when does it abstain?
11. What do 41.25% accuracy and 6/80 accepted images establish?
12. Why are 540 growth records not 540 independent experiments?
13. Why is sensor connectivity separate from useful model calibration?
14. Which parts have been tested on real hardware?
15. What is still needed before automatic device control or a shared hosted product?

The readiness goal is being able to answer these with the actual source, saved inputs and scoped evidence. Consult `docs/PROJECT_OVERVIEW.md` for current feature status and the linked evidence documents for exact experimental limits.
