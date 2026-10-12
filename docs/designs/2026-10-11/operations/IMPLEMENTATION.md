# Operational interface implementation

Historical revision completed locally on 11 October 2026 following the user's request for professional website research and a practical redesign. [Research sources and applied patterns](RESEARCH.md) document the design rationale. Previous Stitch concepts remain preserved. The user subsequently selected Seed & Star and requested a less boxy layout; [the logo and spacing revision](../logo-and-spacing/IMPLEMENTATION.md) describes the current product.

## Delivered behavior

- Charcoal surfaces, system sans typography, a compact sidebar/header, consistent form controls, quiet tabs and dense tables across all six workspaces.
- Saved mission context and four metrics precede the nutrient chart, review items, harvest schedule and independent hardware observations. The decorative slogan, tray illustration and journey tiles are removed.
- Adaptive/fixed selection reads saved policies and updates all related overview results together. The same selected policy carries into crop schedules and back to the overview.
- Chart period filtering changes the displayed mission-day range only. Metrics explicitly remain whole-run totals. Chart axes use a limited number of readable labels and a 100% target reference.
- Review items derive from actual missing results, modeled target gaps, solver notes, input provenance and unavailable/stale/error device observations.
- Fixed harvest batches explicitly show nominal estimates; realized harvest under disruption remains in the daily comparison. Crop timelines have mission-day endpoints and a bounded keyboard-scrollable view, while full tables and CSV exports remain available.
- No backend contracts were changed. Model setup, clinical boundaries, stored-food inventory, intake logs, visual screening, local persistence and MQTT remain available.

## Verification

- 24 React interaction tests passed, including policy/period scope, crop drill-down context, explicit solving, drafts/logs, grouped/legacy navigation, saving, keyboard behavior, actual hardware measurement fields, empty readings and telemetry refresh failure.
- Production Vite build passed. No dependency or backend change was needed.
- Actual app reviewed in the browser at the default 1280×720 viewport and a temporary 390×844 phone viewport; the phone override was reset afterward.
- All six primary pages had no page-wide horizontal overflow at both sizes. Phone navigation closed after selecting a workspace. Escape closed the drawer, returned focus to the toggle and released the body scroll lock. Closed drawers are hidden from keyboard navigation.
- Phone inventory tables scroll internally. Secondary model controls remain closed until selected. The crop timeline is approximately 310px tall and scrolls rather than stretching the page through forty rows.
- The existing local 90-day/60%-water demonstration run restored after reload. Actual fixed/adaptive selection and event-day filters produced the expected saved context. These are software checks with synthetic coefficients, not experimental project results.
- Hardware remained empty; a generated MQTT stream displayed the explicit SYNTHETIC MQTT TEST notice. Physical monitoring was restored afterward. Browser console inspection returned no captured entries.

## Preview files

- [Desktop overview, fixed-plan example](desktop-fixed.jpg)
- [Desktop harvest and hardware detail](desktop-detail.jpg)
- [Phone overview](mobile.jpg)
- [Phone chart and review list](mobile-chart.jpg)
- [Previous overview](before.jpg)

Screenshots show the running application. The design is informed by professional interfaces but has not undergone a formal usability study. Local harvest accuracy and physical sensors remain unvalidated, and outputs remain disabled. No external deployment was performed.
