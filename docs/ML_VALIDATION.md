# Plant-screening validation protocol

The evaluation implementation is `astra_bio/vision_evaluation.py`. It calculates
measured results from supplied logits and labels; this document does not supply
or invent a trained-model accuracy. The unit tests check mathematics and leakage
guards, not biological performance.

## Freeze the dataset before fitting

Create a manifest with `path,label,split,group_id,sha256` and, when available,
`phash,phash_algorithm,source`. Supported split names are `train`, `validation`,
`test` and `external_test`. Hashes must be calculated from the actual images.
Every photograph of one leaf/plant or one capture sequence belongs to one group.
Near duplicates should be connected into groups **before** splitting; a pairwise
similarity threshold can link larger groups transitively. Record the algorithm
and threshold, then manually review ambiguous links.

`audit_manifest(..., perceptual_distance=8)` rejects cross-split exact duplicates,
capture groups and perceptually similar images, duplicate paths, missing capture
identities and conflicting labels for identical images. Perceptual similarity is
a leakage flag; it is not proof that two leaves are identical. An audit validates
declared metadata, so the training pipeline must calculate and verify hashes
against real files. The audit cannot discover membership in the upstream model's
pretraining set.

The pretrained network was trained on PlantVillage. Testing on additional
PlantVillage images cannot establish independence from that pretraining without
the original split membership. PlantDoc is a separate, internet-scraped benchmark
with non-laboratory imagery, but it is still not a dataset from ASTRA-BIO trays.
Use precise mapped labels, retain attribution and document excluded/unmapped
classes. The upstream [PlantDoc repository](https://github.com/pratikkayal/PlantDoc-Dataset)
declares CC BY 4.0 and describes the dataset's construction.

## Keep fitting separate from final evaluation

1. Fit neural-network weights on training groups only.
2. Select a checkpoint using the validation split only.
3. Fit the scalar temperature on validation logits using `fit_temperature`.
   It refuses a `split_name` other than `validation`. Unknown labels (`-1`) are
   excluded and counted. The fitting report retains bounds and before/after NLL.
4. Freeze the checkpoint, preprocessing, class mapping, temperature and screening
   thresholds. Evaluate the test set once with these frozen choices. Reusing the
   test score to select a model turns that split into development data.
5. Use a later, separately captured tray/field collection as `external_test`.
   Record any development decisions that were informed by an earlier evaluation.

Checkpoint selection and temperature fitting may share validation data; report
that explicitly. Neither is an independent performance test. Temperature scaling
changes confidence scores while preserving the global class ranking. It does
not repair wrong labels, missing class coverage or domain shift. The approach is
described in [Guo et al., On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599).

## Report accuracy and abstention together

`evaluate_logits(logits, targets, class_names, temperature=T, split_name="test")`
returns:

- Global accuracy, balanced accuracy, per-class support/precision/recall/F1 and a
  confusion matrix (true class on rows; predicted class on columns).
- `macro_f1` averaged over classes that have true examples, plus
  `macro_f1_all_classes` over the entire output head with absent classes filled as
  zero. Class coverage and unrepresented labels are explicit; no unsupported
  class is treated as successfully validated.
- Negative log likelihood, multiclass Brier score (sum of squared probability
  error per image; range 0–2) and top-class expected calibration error in equal
  confidence bins. Empty/unlabelled sets have `null`, not zero, accuracy.
- Screening coverage (accepted known images / known images) and selective
  accuracy (correct accepted known images / accepted known images), with
  tentative, uncertain and rejected counts. Also report unknown/OOD false
  acceptance separately from closed-set accuracy.

For the deployed 15-class mapping, the evaluator uses the existing screening
rules: global score ≥0.70, same-species margin ≥0.15, species mass ≥0.50 and a
global top class matching the selected crop. These are fixed prototype rules,
not agronomically calibrated operating thresholds. All scores remain global
across the full output head, without species renormalization.

Pass operator-recorded `crop_species` for each photograph. If omitted, known
examples infer species from their true label and unknown examples are withheld;
the report discloses this favorable crop-identity assumption. OOD false acceptance
can only be meaningfully assessed when a crop identity is supplied, as in actual
use. Target `-1` means unknown/unmapped/OOD; it is excluded from disease-class
accuracy and never silently remapped to healthy.

## Independent tray capture still requires real observations

Collect unedited original photographs across growing cycles, cultivar, plant
age, camera, light spectrum, shadow, background and image quality. Record plant,
tray, cycle and capture-session identities before assigning splits. Preserve
specialist-reviewed labels and label uncertainty. Keep the final external cycle
out of fine-tuning, augmentation, checkpoint selection and temperature fitting.

Include healthy leaves, confirmed diseases where available, nutrient/stress
symptoms that resemble disease, unsupported crop species, non-leaf objects and
poor images. Stress symptoms without confirmed pathogen evidence must not be
reported as an established disease label. Report class counts and all withheld
cases; high selective accuracy on very few accepted images can hide unusably
low coverage. No dataset measurement establishes spaceflight validation or
authorizes automatic treatment, isolation or actuator control.

## Verification

Run `.venv\Scripts\python.exe -m pytest tests\test_vision_evaluation.py -q`.
The 19 tests cover hand-calculated confusion/calibration values, missing-class
metrics, validation-only temperature fitting, unknown/OOD acceptance, species
conflicts, conservative screening, stable softmax and dataset leakage checks.
