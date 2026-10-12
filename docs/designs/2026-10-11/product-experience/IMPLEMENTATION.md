# Product-experience implementation — 11 October 2026

The user requested further research into winning products and comparable websites, followed by useful UI improvements. [RESEARCH.md](RESEARCH.md) records verified awards, primary documentation and the distinction between documented patterns and design inferences. The exact selected logo, open forest/ivory layout and subtle CSS star/nebula background remain.

## Implemented behavior

- **Mission-day explorer:** select an existing saved daily row using the range input or previous/next controls. Selection survives navigation. Scenario, nominal-harvest and first-target-gap milestones jump to the corresponding day. A short brief shows events or the next planned harvest.
- **Connected ecosystem:** open crew, food-reserve, crop and resource nodes display the selected daily values and link to Nutrition & logs, Food inventory, Crop schedules and What-if simulator respectively. Active crop counts use nominal planting/harvest dates. Navigation links open existing workflows; no crop-batch peek panel was added.
- **Whole-run comparison:** fixed and adaptive saved metrics show signed absolute differences in target-gap days, calculated harvest and modeled water use. The displayed period is the submitted run horizon; selecting a day or chart window does not turn those totals into daily values.
- **Chart views:** Nutrients uses energy/protein/vitamin-C coverage; Water uses `water_l` and `water_available_l`; Electricity uses `power_kwh` and `power_available_kwh`. Selected-day and scenario markers preserve time context. All values come from the saved result.
- **Navigation search:** visible search control and Ctrl/Cmd K open ten destinations. Food/crop names act as navigation keywords. Search does not query stored records or mutate data.
- **Scenario starters:** Water shortage, Crop loss, Crew increase, Dietary change and Nominal prefill editable inputs. The user must press **Run comparison** to solve. Editing inputs does not rewrite an existing saved result.

Source: `frontend/src/MissionExplorer.jsx`, `frontend/src/HabitatOverview.jsx`, `frontend/src/CommandPalette.jsx`, `frontend/src/main.jsx` and `frontend/src/style.css`.

## Verification status

**39 React tests passed before the final cosmetic CSS wrap correction. The final production Vite rebuild passed after that correction.** Automated checks include selected-day/event context, retained selection, ecosystem destinations, comparison math, resource chart fields, navigation search/keyboard behavior, scenario submission and existing workflows.

Browser validation used the actual saved **90-day/four-crew synthetic comparison**, rather than a newly generated example:

- Selected Day 30 displayed reserve **15.83 days / 315.56 kg**, modeled harvest **0 kg**, and water use **29.51 L** against the saved **30 L** available budget. Opening Crop schedules and returning retained Day 30. Keyboard ArrowRight advanced the range to Day 31, showing **0.83 kg** harvest and **30 L / 30 L** water; Previous returned to Day 30.
- Fixed/adaptive selection switched saved whole-run totals. Water and Electricity views displayed the corresponding use/budget series and day/scenario context.
- Ctrl K search with `mqtt` opened Live devices. On mobile, empty-search Escape restored focus to Search.
- Presets filled water remaining **60%**; crew increase **+2** with water reset to **100%**; vitamin C target **+40%** with crew increase reset to **0**; and kale loss **50%**. These were prefills only: no solve ran, and the saved result remained unchanged.
- Layouts at **1280px**, **1002px** and **390×844** had no horizontal overflow. The comparison layout stacks at widths up to 1100px, keeping numeric values on one line after the correction. Drawer navigation closed the drawer on route change.
- Browser warning/error logs were empty. This covered the changed interactions and representative responsive layouts, not a complete audit of every page.

The following actual screenshots were captured and visually reviewed:

| Screenshot | View |
| --- | --- |
| [desktop.jpg](desktop.jpg) | Mission overview and day explorer |
| [mission-day.jpg](mission-day.jpg) | Selected day and ecosystem detail |
| [comparison.jpg](comparison.jpg) | Policy comparison and chart context |
| [search.jpg](search.jpg) | Navigation search |
| [mobile.jpg](mobile.jpg) | Responsive mission overview |
| [mobile-ecosystem.jpg](mobile-ecosystem.jpg) | Mobile ecosystem and day context |
| [resources.jpg](resources.jpg) | Resource-use and available-budget chart |

Backend code did not change for this revision. The earlier 102 Python tests plus 13 subtests and authenticated MQTT/TLS validation remain historical backend evidence, not newly rerun checks.

## Interpretation limits

The explorer shows **simulated mission days**, separate from independent device telemetry. Nominal harvest markers are batch-date estimates, not observations; realized daily simulated yield remains distinct. Demo coefficients remain synthetic, while terrestrial reference and calibration limits remain visible. Comparison differences are calculated outcomes, not measured savings. Only three nutrients are tracked; there is no clinical diagnosis, proven biological feedback, calibrated spaceflight response or autonomous hardware actuation.

Physical firmware remains compiled but unflashed and uncalibrated. Outputs remain disabled. This revision introduces no external deployment or new biological model.
