# Fruit monitoring UI verification

12 October 2026. Current white/sage design and supplied logo are preserved.

- Initial browser upload of the public publisher tomato example succeeded. Explicit screening showed 18 three-stage detections, real normalized box overlays and a stage/score list. Switching to the six-stage model cleared the old observations; explicit screening returned 21 detections.
- Dense overlay labels were simplified to compact numbers, retaining full accessible titles and the stage/score table. Generic-model descriptions now show only the selected crop's labels.
- The final production screen verifies all four available model choices. Bell pepper automatically selects the generic detector and displays Capsicum; potato displays the exposed-tuber limitation and Potato label. Tomato offers both maturity models and both detection-only alternatives.
- At 390×844, selectors stack, copy wraps and the empty photo workflow has no page overflow (380 px page width inside the 390 px viewport). This is a form/layout check, not a mobile photo-overlay check. The temporary viewport was reset.
- Final browser warning/error logs were empty. `desktop.png` and `mobile.png` were saved and visually inspected.
- Browser permissions denied the evidence download and a fresh photo upload after the compact-marker rebuild. No retry or workaround was attempted for those blocked actions. Final overlay rendering and export-handler logic pass component tests, but the final photo upload/download was not browser-verified.

All 60 frontend tests and the final production build passed. Separate affected Python checks passed 32 tests. Four actual local multipart HTTP inference runs and image/crop/threshold guards are recorded in [FRUIT_VERIFICATION.json](../../../FRUIT_VERIFICATION.json). The public publisher example is a pipeline smoke test, not an independent count, maturity or accuracy benchmark.
