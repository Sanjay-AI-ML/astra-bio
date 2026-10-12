# ASTRA-BIO interface research and implementation

Researched 11 October 2026. The user requested a professional operational interface and deferred logo selection. This revision replaces the earlier Habitat marketing overview; previous Stitch concepts and screenshots remain preserved.

## Professional interfaces studied

| Primary source | Observed design principle | Applied to ASTRA-BIO |
| --- | --- | --- |
| [Grafana dashboard guidance](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/dashboards/build-dashboards/best-practices/) and [public dashboard demo](https://play.grafana.org/) | Give a dashboard a clear question, move from summary to detail, and use focused graphs with context. The actual demo was inspected in the browser. | Overview answers: what does the saved plan predict, and what needs review? Four metrics precede one nutrient chart. Time and policy controls are adjacent to the chart. |
| [Priva Operator](https://www.priva.com/de/blog/gartenbau/new-in-operator-for-connext-compact-cc) and [measurement tables](https://support.priva.com/hc/en-us/articles/19576328425244-Creating-and-editing-table-widgets-for-custom-dashboards) | Group related measurements, use chart tabs and configurable charts, and keep measurement context close to the data. | Nutrition, crops, scenarios and device monitoring have separate workspaces. Hardware observations identify source, availability and receipt age independently of planning results. |
| [Carbon dashboard patterns](https://www.carbondesignsystem.com/building-blocks/data-visualization/dashboards) | Prioritize relevant information, limit metrics, use consistent chart colors and units, and reveal secondary information on demand. | Neutral charcoal surfaces, system typography, compact headers, consistent green/blue/amber chart series, explicit units, and closed source/assumption disclosures. |
| [ThingsBoard dashboard documentation](https://thingsboard.io/docs/user-guide/dashboards/) | Monitoring combines entity context, time-series charts, latest readings and tables; time windows and drill-down serve distinct tasks. | A saved-run period filter changes the chart only, with whole-run metric totals labelled. Device/source selection and detailed monitoring stay in Live devices. Harvests use a table and crop drill-down. |

These are researched interface patterns and our application of them. They are not measured evidence of ASTRA-BIO usability, biological performance or commercial demand. No claim of time saved or resource savings follows from this redesign.

## Changes made

- Removed the oversized slogan, decorative grow-tray illustration and four repeated journey tiles from the overview. The first screen presents useful results.
- Added adaptive/fixed policy selection that consistently changes metrics, chart data, harvest batches and review items. Selection reads the saved result and does not start another solver run.
- Added full-horizon/from-event chart windows. Whole-run metrics retain their scope label; mission-day range appears next to the controls.
- Review items derive from missing results, modeled target gaps, model warnings, input provenance and hardware freshness. They are not clinical alarms.
- Empty planning and hardware states remain empty. No invented mission clock, oxygen value, sensor reading, healthy-system badge or percentage improvement appears.
- A thin sidebar, quiet task navigation, compact forms, underlined section tabs, consistent table density and restrained panel borders replace decorative layout.
- All existing planning, nutrition, model setup, image screening, saved-state and MQTT workflows remain wired to the existing API.
- The logo remains undecided; the interface uses a plain ASTRA-BIO wordmark.

## Interpretation and verification

Crop/yield estimates remain unvalidated for the local tray. Terrestrial references and entered resource/stress assumptions retain provenance. Only three nutrients are tracked; intake gaps are not a clinical deficiency diagnosis. Fresh receipt does not prove calibration. Outputs remain disabled.

Interaction tests cover policy/period consistency, explicit model requests, drafts and logs, navigation, saving, and honest telemetry failure states. The implementation record and screenshots document desktop and phone review; this review is not a formal user study.
