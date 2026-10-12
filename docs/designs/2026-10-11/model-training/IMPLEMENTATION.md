# Model evidence screens — 11 October 2026

The existing logo, forest/ivory palette, space background, open layout and six primary navigation groups remain. Model evidence stays behind secondary disclosures. Opening a disclosure reads recorded evidence and never trains a model.

Plant screening shows the active version, an explicit model selector, actual held-out accuracy and macro F1 against original weights, test/class counts, validation-only temperature, accepted coverage and selective accuracy. Per-class results include zero-support classes as unavailable. Source and transfer limitations remain visible. The API selects only integrity-verified candidates that pass the recorded improvement gate; explicit rollback to the base is available. The measured crop disclosure shows the source-specific fresh-mass age curve, within-cycle error and a pending response-calibration status, with a blank CSV download.

Verification completed:

- 193 Python tests and 13 subtests passed; one Windows symlink test skipped because this environment lacks symlink privilege. One existing Starlette test-client deprecation warning remains.
- 43 frontend tests passed. After the final metric layout/percentage-rounding correction, all four model-evidence tests and the production build passed again.
- Actual GPU training completed and ONNX export matched its PyTorch probe within `5.2452e-6` absolute logit error. The selected candidate ran local CPU image inference with its recorded fitted temperature and no automatic action.
- The actual API returned the selected fine-tuned version, experimental growth fit and awaiting-measurements response status. Existing saved comparison data remained available.
- In the browser, choosing the base option left the active model unchanged until **Use selected model** was clicked. Base selection completed, then the improved candidate was explicitly restored. Per-class results displayed their real supports, including unbenchmarked classes.
- The actual crop template downloaded to `C:/Users/sanja/Downloads/astra-bio-crop-trials.csv`; inspection confirmed all 29 header fields and zero data rows.
- Desktop and 390×844 phone views displayed the actual metrics and growth curve. Phone page width was 380px within a 390px viewport on both affected screens; metrics and the model identifier wrapped without page overflow. The temporary viewport override was reset.
- Browser warning/error logs were empty. This checks the affected model workflows, not every page of the product.

Actual screenshots: [plant evaluation](vision.jpg), [plant evaluation on mobile](vision-mobile.jpg), [growth curve](growth.jpg) and [growth on mobile](growth-mobile.jpg). The desktop growth capture includes the successful selection notification from the preceding model-switch check.

The image classifier still has low accuracy (41.25% on 80 source images). Its six accepted matches include two errors. Crop growth uses one source cycle and does not establish edible yield or resource-stress effects. Real external tray photos, specialist labels and independent crop cycles remain required; UI polish and passing software checks do not replace those observations.
