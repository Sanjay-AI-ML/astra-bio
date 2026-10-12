# ASTRA-BIO UI selection brief

Requested on 11 October 2026: use Google Stitch, preserve the supplied SEDS design direction as one option, show alternatives before choosing and wiring a replacement UI, and remove unnecessary research-oriented frontend clutter.

Reference: https://seds-web-mu.vercel.app/

Observed reference style: near-black background, violet accents, bold geometric headlines, spaced mission labels, orbital arcs, subtle stars, thin borders and pill actions. Its event registration flows and institutional branding are not ASTRA-BIO product content.

Stitch project: https://stitch.withgoogle.com/projects/4810757081816229455

## Proposed product navigation

| Primary area | Existing functionality retained |
| --- | --- |
| Mission overview | Crew, horizon, growing area, current plan and action summary |
| Crew & nutrition | Reviewed targets, per-person intake logs and tracked nutrient gaps |
| Crops & food | Pantry inventory, crop profiles, planting and harvest schedules |
| What-if simulator | Water/power shortage, crop loss, increased crew and changed targets; fixed/adaptive comparison |
| Plant screening | Local photo upload, supported species, uncertain results and review |
| Live devices | Source-labelled measurements, freshness, connectivity and device setup |

Secondary Workspace settings can contain saved configurations/runs, imports/exports and advanced calibration. No research page in the primary navigation. Operational screens retain concise source, assumption and uncertainty details when they affect a decision.

## Design options

- **A — Orbit:** the SEDS-inspired near-black/violet direction.
- **B — Flight deck:** an alternative operator-first, graphite/amber direction.
- **C — Habitat:** an alternative biology-first, deep-forest/ivory direction.

The user selected **C — Habitat** on 11 October 2026 and requested further refinement. A and B, and the original C concept, remain preserved for comparison. Stitch produced a refined Habitat screen; `C-habitat-refined.stitch.html` is its exported design source. The local app implements this direction in React with forest surfaces, ivory typography, a locally authored grow-tray illustration, grouped navigation, responsive drawer and real API states.

The original Stitch concepts contain example values. The running app uses committed configuration, submitted planner results and independently queried hardware observations; its empty states do not invent harvests or connected devices. The original frontend is separately archived in `current-frontend/` before simplification. No external deployment was performed.

## Necessary truth in every concept

Keep demo/simulated inputs visibly labelled. Show unavailable hardware readings as unavailable. Crop yields and harvest dates are model estimates. Nutrient gaps are comparisons against entered targets, not clinical diagnoses. Manual review and disabled outputs remain visible; no automatic intervention is implied.

No external deployment, real health data, private telemetry or MQTT credentials are used to create these design concepts.
