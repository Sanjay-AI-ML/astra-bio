# ASTRA-BIO model work — 11 October 2026

The first local fine-tuning run is completed and selected for experimental plant screening. It improves a difficult source-dataset benchmark, but its accuracy remains low. Actual tray validation is still required. Neither image screening nor either crop-fitting workflow actuates devices.

## Plant-image fine-tuning

The base is the pinned [MobileNetV3 model](https://huggingface.co/imaflower/plantvillage-mobilenetv3), revision `d76fe187be1c4c3a5474f835a7a70cd08c7ab085`. Training uses precisely mapped classes from the cropped [PlantDoc repository](https://github.com/pratikkayal/PlantDoc-Dataset), revision `5467f6012d78d1c446145d5f582da6096f852ae8`. PlantDoc declares CC BY 4.0; the base card declares MIT. Original source paths, Git blob identities, downloaded bytes and decoded-image fingerprints are retained locally.

Of 951 selected source files, four invalid images, 56 conflicting-label images and 15 duplicate representatives were excluded. Connected groups use exact decoded-pixel hashes and 64-bit difference hashes with Hamming distance at most eight. Groups containing official test images keep the test representative and remove its development duplicates. The final split contains **636 training, 160 validation and 80 test images**, spanning ten mapped classes. The full output head retains fifteen classes; five have no examples in this benchmark.

The RTX 3050 A laptop GPU ran five epochs with seed 42 and batch size 16. The feature backbone remains frozen; the classifier is fine-tuned with training augmentation, weighted cross entropy, AdamW and anchoring to the original classifier. Epoch five had the highest validation macro F1 and was selected using validation only. A scalar temperature was fitted on the same validation images. Test images did not choose weights, augmentation, learning rate or temperature. The single completed test comparison gates selection of the candidate; it must not become an iterative tuning target.

| Held-out measurement | Original weights | Fine-tuned weights |
|---|---:|---:|
| Accuracy, 80 images | 28.75% | 41.25% |
| Macro F1, ten represented classes | 0.20588 | 0.36593 |
| Balanced accuracy | Recorded in report | 38.47% |
| Negative log likelihood, validation-calibrated | 2.35868 | 1.59784 |
| Expected calibration error, test set | 0.07971 | 0.13419 |

Improved classification and likelihood did **not** improve every calibration metric. Candidate temperature is `0.9207915711`, fitted on 160 validation images. Fixed screening safeguards accept only **6/80 images (7.5% coverage)**; four of those six classifications are correct (**66.7% selective accuracy**). This is too small and inaccurate to establish dependable screening. Unknown/non-leaf rejection was not evaluated in this closed-set benchmark. The evaluator assumes the known crop species from the true source label; real users must supply crop identity.

Per-class counts, precision, recall, F1, confusion matrix, confidence bins, abstention outcomes, epoch history, hashes and limitations are in [the completed report](../data/reports/plantdoc-finetune-20261011.json). The [artifact manifest](../data/reports/plantdoc-model-manifest-20261011.json) pins exported files and class order. The selected candidate is `plantdoc-20261011T142833Z`; artifacts are private local files under `runtime/plant-candidates/`. ONNX export matched the selected PyTorch checkpoint on the export probe with maximum absolute logit error `5.2452e-6`. That checks export parity, not biological accuracy.

PlantDoc consists of internet photographs, not ASTRA-BIO trays. Capture identities are unavailable, so hash grouping cannot prove plant-level independence. Unknown overlap with the upstream model's PlantVillage pretraining cannot be excluded. New, specialist-labelled tray photos across separate growing cycles are required for external validation. Do not present the upstream card's accuracy as this app's accuracy.

## Reproduce or switch models

Training uses a separate environment; the application does not import PyTorch or train on page load. Exact installed packages are recorded in [the environment snapshot](../data/reports/plant-training-environment-20261011.txt).

```powershell
# Install training dependencies, fetch pinned files, audit splits and run training.
.\scripts\fine-tune-plant.ps1 -Action Full -Epochs 5 -BatchSize 16

# Inspect completed candidates; selection requires a valid improvement report.
.\scripts\fine-tune-plant.ps1 -Action Status
.\scripts\fine-tune-plant.ps1 -Action Activate -CandidateId plantdoc-20261011T142833Z

# Explicitly restore the original pretrained model.
.\scripts\fine-tune-plant.ps1 -Action Base
```

Use `-CpuOnly` during Setup/Full if CUDA is unavailable. `Train` reuses prepared files and verifies every image before fitting. `Full` does not activate a new candidate automatically. The app's Plant screening disclosure also permits explicit model selection. Changed artifacts or a changed active manifest make screening unavailable until a valid model is explicitly selected.

## Measured crop growth and environmental response

The [pinned UC Davis lettuce dataset](https://zenodo.org/records/17041810) supplies **540 measured plant/day fresh-mass records** from eighteen plants in one NFT cycle. Twelve complete plants form training and six complete plants form the holdout. A monotone age curve gives **5.72 g/plant MAE** and **10.26 g/plant RMSE**, versus 47.58 g/plant MAE for a training-mean baseline. This is a within-cycle diagnostic, with zero independent test cycles. The source does not establish that its fresh mass is edible harvest, and source calendar dates are inconsistent with its README year.

The curve is available under **Workspace settings → Model settings → Measured growth and crop response**. It refuses unmatched profiles and ages outside the observed 1–30 days after transplant. It does not replace the planner's edible harvest endpoint or estimate water-stress effects. Details, source checksums and import commands are in [the crop-training guide](CROP_TRAINING.md) and [the growth report](../data/reports/measured-growth.json).

The separate environmental-response pipeline is implemented but remains **awaiting measurements**. Its CSV template is blank. It requires independent repeated cycles, matched profiles, environmental coverage and a held-out improvement over the training baseline. Predictions must remain inside the joint training support. Sensors provide exposure measurements; real harvest weights and independent experiments provide outcome labels. The relevant [Wageningen treatment dataset](https://data.4tu.nl/datasets/5a7472f0-8a67-4ec0-84c9-9d032990d654/1) was identified, but its raw-data download returned HTTP 503 during this run; metadata alone was not fitted.

Nutrition remains reviewed arithmetic and optimization remains Pyomo/HiGHS. They are not relabelled as trained neural models. Physical photos, crop cycles, board flashing and sensor calibration remain external work; software readiness does not establish physical performance.

