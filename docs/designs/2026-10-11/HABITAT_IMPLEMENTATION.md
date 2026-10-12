# C — Habitat implementation

The user selected C on 11 October 2026 and requested improvement. Google Stitch refined the selected concept in project [4810757081816229455](https://stitch.withgoogle.com/projects/4810757081816229455). The implementation is now served by the local React/FastAPI app at http://127.0.0.1:8501/.

## Refined direction

Deep forest surfaces, ivory text, muted sage accents, a serif overview headline and open mission statistics replace the earlier orbital dashboard. A local SVG cultivation illustration keeps the installed app independent of external image/font requests. Six primary groups reduce navigation clutter; related workflows use tabs. Optional composition, model and calibration details remain available behind disclosures.

The exported refined Stitch source is `C-habitat-refined.stitch.html`; it remains a design preview. The functional React implementation is `frontend/src/HabitatOverview.jsx`, `main.jsx`, `NutritionPanel.jsx`, `useTelemetry.js` and `style.css`. Original A/B/C concepts and the pre-selection frontend baseline remain preserved here. Stitch's generated title begins with “A”; the manifest records that tool title separately from the user's selected C direction.

## Verification

- All 21 frontend interaction tests passed; production Vite build and FastAPI health passed.
- Desktop 1280×720 and phone 390×844 browser review: no page-wide horizontal overflow; drawer opening/closing/navigation and internal table scrolling worked. Temporary viewport overrides were reset.
- A 90-day comparison with 60% water remaining completed through the UI and existing solver API, saved locally and restored on reload. Its synthetic crop/food coefficients remain visibly labelled. Results are a software smoke check, not experimental benefit or model accuracy.
- Physical hardware readings remained empty; the independent MQTT synthetic stream displayed a clear test-data label. Outputs stayed disabled.
- Model settings disclosures stayed closed; plant screening showed the installed local model and its supported-species limits. No captured browser console warnings/errors.

Actual app captures: `habitat-desktop.jpg` (full overview), `habitat-mobile.jpg` (phone overview) and `habitat-preview.jpg` (desktop viewport). Original concept screenshots remain linked in the gallery/manifest. No external deployment or physical device validation was performed in this UI phase.
