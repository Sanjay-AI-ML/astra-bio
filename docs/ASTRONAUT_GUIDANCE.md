# Astronaut guidance

Open the **Astronaut guidance** workspace or `#guidance`. Select a person, mission day and optional nutrient focus. The page updates when the shared crew data changes and preserves person selection across valid refreshes.

Each nutrient has its own target/intake chart and unit. Complete logs and operator-reviewed targets establish a difference to the planning target; missing or partial logs remain unknown. Targets edited in the current personal profile can be compared separately, while the saved mission continues using its accepted inputs until the roster changes are explicitly applied. This is a food-log calculation, not a prediction of blood nutrient levels or nutritional deficiency.

Food examples give the energy, protein and vitamin C in a reference portion. USDA reference edible forms are shown explicitly. Dry ingredients are not ready-to-eat serving prescriptions. Matching stored-food composition and previous-day saved inventory determine modeled availability; future crop output does not become current stock. Stock is shared across the crew and is not allocated by this page.

Existing blood/vital comparisons prompt medical review separately. The current named-crew demonstration uses invented blood measurements and no heartbeat/blood-pressure readings. Nutrition snapshots currently persist dietary logs, profiles and the sample marker, not a clinical record. Missing iron composition and clinical context are not guessed. Supplemental orders must already be available and clinician approved to be displayed; no dose is generated.

**Explain with Gemini** is available when the backend has `GEMINI_API_KEY` (or the existing ignored local Gemini configuration). The key remains on the server. An explicit request sends only reconstructed anonymous nutrition facts: no names, stable personal IDs, raw laboratory/vital readings or free-text symptoms. The provider selects existing fact IDs; unsupported quantities or advice are discarded. Core scope, log completeness, target review and sample boundaries are always retained. The API uses `store:false` and does not retain a provider conversation.

Calculations work without an API key. An unavailable provider retains local evidence. Explanation tokens expire after 15 minutes or backend restart; refresh the analysis if needed. The report does not update mission resources, food inventory, clinical targets or devices.

References:

- [USDA FoodData Central](https://fdc.nal.usda.gov/) — retained SR Legacy reference food forms and per-food source links.
- [NIH vitamin C reference](https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/) — limited adult reference already used by the application; it is not an astronaut prescription.
- [NHLBI iron-deficiency anemia](https://www.nhlbi.nih.gov/health/anemia/iron-deficiency-anemia) — cause and treatment require medical assessment.
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output) and [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview) — schema-constrained fact selection and explicit storage control.

Validation covers USDA mass calculations, per-person reviewed/draft targets, incomplete logs, sample lab provenance, saved stock/expiry, fixed reference food forms, API validation, navigation, stale responses, provider privacy, unsupported fact rejection and live Gemini response parsing. The new page has not undergone hosted browser visual verification.
