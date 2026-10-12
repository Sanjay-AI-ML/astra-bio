# Plant overview: fruit photo and optional leaf close-up

## Current flow — 13 October 2026

Upload a **Plant photograph** and optionally a **Leaf close-up** from the same
labeled plant, then choose **Analyze plant**. Fruit detection uses the original
plant photo. Leaf classification uses the close-up when supplied, otherwise
the original image. One leaf should fill most of the frame with sharp, even
lighting. Tomato, potato and bell pepper retain the existing leaf coverage.

The MobileNet classifier does not locate individual leaves in a wide scene.
A fruit-dominated photo can therefore produce an uncertain or rejected leaf
result while its fruit detections remain usable. Separate result badges and
input-source labels make this explicit. Existing species/score safeguards are
unchanged; no result is accepted merely to populate the interface.

Schema v3 records the plant and leaf image hashes, leaf input source and input
mode. Each upload is limited to 10 MiB; duplicate/unknown uploads, empty files
and unsupported inputs are rejected. Photos remain in local inference. The
optional Gemini action selects existing text facts; photographs are not sent
and Gemini cannot override model findings.

Actual CPU smoke checks used public images from different source plants: a
wide tomato example returned uncertain leaf evidence; a separate leaf close-up
returned a tentative healthy-class match. Original fruit observations were
identical at 18 detections. This proves the input routing and installed-model
execution, not paired biological validation or diagnosis. Browser automation
could verify the upload controls, but its extension file-access setting blocked
automated file selection; actual uploads/inference were verified through the
local HTTP endpoint instead. See `docs/CREW_AND_LEAVES_VERIFICATION.json`.

## Earlier single-photo implementation history

The visible plant flow is now **Plant overview**, with no separate leaf-screening or fruit-monitoring tabs. Choose a plant/batch label and species, upload exactly one photo, and press **Analyze plant**. Both existing local models receive the same bytes. Tomato, bell pepper and potato retain their established model coverage. Multiple uploads are rejected; no pairing confirmation is needed.

The current leaf classifier processes the whole frame and does not locate individual leaves. A wide plant or fruit-dominated photo may not supply enough leaf detail; unresolved or rejected leaf evidence stays unresolved while usable fruit observations remain visible. This interface change does not train a whole-plant disease detector or infer root, stem, nutrient or pathogen measurements from a photo.

The output combines a short evidence-based description, distinct leaf/fruit observations, practical next checks and possible harvest use. Numbered fruit detections are drawn on the same uploaded photo, with stage/score details in an expandable observation table. A healthy-leaf class is not a whole-plant health finding. Visible counts/maturity labels are not a measurement of harvest mass or food safety. No treatment dose, pesticide instruction, inventory credit or equipment command is generated. Tomato general care references [University of Minnesota Extension](https://extension.umn.edu/garden-and-home/yard-and-garden/gardening-in-minnesota/yard-and-garden-problems/tomato-leaf-spot-diseases).

## Optional Gemini connection

The complete local overview requires no API key. The user selected Gemini for optional AI curation. Use a Gemini API key on the server; account session credentials are never copied into this feature.

Either provide `GEMINI_API_KEY` and optionally `GEMINI_MODEL` in the server environment, or fill `runtime/gemini/plant-summary.json` privately. A shareable placeholder is in `integration/gemini/plant-summary.example.json`. The runtime directory is already ignored by Git. Never put the key into frontend code, source control, browser storage or a shared screenshot. The default model is [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), the current stable model suitable for this brief selection task. API access depends on your project's key, available model access and quota. Private-file configuration is read when a summary is requested, so entering it does not require restarting the application.

Gemini is called only when **Create brief Gemini overview** is pressed. The request sends the bounded local summary's text facts, not images, filenames, plant label, medical profiles or database credentials. It uses [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en) to select existing fact IDs. Visible prose stays within the established evidence and care notes. New cures, diagnoses and food-safety claims cannot be introduced by the model. Provider errors leave the full local overview available and never expose credentials. The key is sent in the provider's authentication header, not its URL. Google API data handling depends on the account/tier used.

The uploaded image bytes are used only during local inference; the API does not persist or transmit photographs. Its single-photo response records an image hash and `input_mode: single_photo`. The AI evidence cache stores summaries in process memory for 15 minutes, with at most 32 entries. Expired summaries need another explicit analysis. Live Gemini access was verified on 2026-10-12 using the earlier paired-photo flow; optional text-fact curation is retained in the one-photo flow.

Implementation is separated in `plant_overview.py`, `plant_overview_routes.py` and `PlantOverview.jsx`. The main frontend renders only the overview flow; independent inference APIs are retained internally. No crew/nutrition configuration or ESP32 firmware is changed by this feature.

## Side-chat preview

The current single-photo preview is `http://127.0.0.1:5174/#vision`, using an isolated build under ignored `runtime/plant-single-photo-preview` and an isolated server helper. It leaves the main port-8501 application and earlier port-5173 preview running. Source changes are integrated into the normal application and will appear there after its normal rebuild/restart.

Single-photo verification: 38 affected backend tests and 38 affected frontend tests passed, and the isolated production build succeeded. An actual installed-model request on the publisher example verified matching image hashes for both models: leaf status `uncertain`, fruit status `observed`, 18 visible detections. This verifies execution and shared input, not independent biological accuracy. Tests cover exactly-one-file validation, compatible non-tomato defaults, size/empty-input rejection, stale-result invalidation, fruit-marker coordinates, and retention of fruit evidence when leaf evidence is unresolved.

The following records describe the earlier paired-photo implementation:

This feature was prepared in a side conversation while the main chat was handling crew/nutrition graphs. To avoid restarting or replacing its running frontend, the preview build is kept under ignored `runtime/plant-overview-preview` and an isolated API instance serves it on `http://127.0.0.1:5173/#vision`. The original port-8501 app remains running. `scripts/plant_overview_preview.py` provides that isolated entrypoint. The code is already integrated in the normal source; a normal frontend rebuild/API restart in the main workflow will also include it.

Verification: 33 affected backend tests and 49 affected frontend tests passed, including pairing confirmation, tentative evidence, absent/rejected views, stale-result invalidation, provider schema parsing, unknown fact rejection and credential-redacted fallback. The backend tests passed again after correcting the REST JSON MIME enum to APPLICATION_JSON, as required by the [API reference](https://ai.google.dev/api/generate-content#TextResponseFormat). The live browser flow then successfully completed a Gemini request. Unit tests mock provider requests and do not spend API quota.

A live browser check used the existing public publisher tomato image in both input slots, explicitly labeled as a software check of the same pictured batch. Both actual local ONNX paths ran: leaf screening returned uncertain and the fruit model reported 18 unripe-stage detections. The overview kept leaf condition unresolved, showed the fruit observations and requested a sharper single-leaf view. This checks integration, not independent accuracy or real tray health. The result screenshot is under `docs/designs/2026-10-12/plant-overview/combined-result.png`.
