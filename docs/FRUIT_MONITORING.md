# Fruit monitoring

Implemented on 12 October 2026 as a separate photo workflow alongside the existing leaf classifier. Four pinned public detectors are installed and have run locally through ONNX Runtime's CPU provider. The models are reused pretrained checkpoints; ASTRA-BIO has not trained or fine-tuned a fruit detector.

## Use it

1. Run the app and open **Plant screening → Fruit monitoring**.
2. Choose tomato, bell pepper or potato. Potato means harvested, exposed tubers.
3. Select an available model and a clear JPG, PNG or WebP photograph, up to 10 MiB. The backend also limits decoded images to 20 megapixels.
4. Click **Screen fruit image**. Review the numbered boxes, visible count, source labels, visual stages and model scores. Changing the crop, model or photograph clears the previous result.
5. Use **Export fruit evidence JSON** to save the observation, input filename, image hash, model provenance and limitations. This export contains no photograph bytes.

## Installed models

| Model ID | App coverage | Output | Input |
| --- | --- | --- | --- |
| `tomato-ripeness-3` | Tomato | Boxes and visible counts with Fully-ripe, Semi-ripe and Unripe labels; default model | 640×640 |
| `tomato-ripeness-6` | Tomato | Boxes and visible counts with Green, Breakers, Turning, Pink, Light Red and Red labels | 1024×1024 |
| `tomato-detection` | Tomato | Boxes and visible counts; maturity is unassessed | 960×960 |
| `produce-detection` | Tomato, bell pepper and exposed potato tubers | Boxes and visible counts; maturity is unassessed | 640×640 |

The generic detector has 35 upstream classes, but this app exposes only these three crop selections. Its `Capsicum` label maps to bell pepper. Tomato maturity models do not provide pepper or potato maturity labels. Source labels remain in the evidence; Green is displayed as unripe and Red as fully ripe in the stage summary.

For `tomato-ripeness-3`, the actual checkpoint/ONNX mapping is **ID 0 Fully-ripe, ID 1 Semi-ripe, ID 2 Unripe**. The publisher's card contains a conflicting class-ID table. ASTRA-BIO uses and verifies the graph's ordered labels rather than that table.

Pinned artifact sources:

- `tomato-ripeness-3`: [pablofntdz/yolov8-tomato-detection](https://huggingface.co/pablofntdz/yolov8-tomato-detection/tree/244eb93615708602716b57f2d09da479e2d899d4), revision `244eb93615708602716b57f2d09da479e2d899d4`, file `model_hub_n.pt`.
- `tomato-ripeness-6`: [afeefaazam/tomato-ripeness-detector](https://huggingface.co/afeefaazam/tomato-ripeness-detector/tree/318c3e91578a748fa7020da80cbef00a357002e3), revision `318c3e91578a748fa7020da80cbef00a357002e3`, file `model.pt`.
- `tomato-detection`: [AitorConS/tomatoACLv1](https://huggingface.co/AitorConS/tomatoACLv1/tree/a228d44bdf24306cedec6d433da093242c4fb05d), revision `a228d44bdf24306cedec6d433da093242c4fb05d`, file `tomatoACLv1.onnx`.
- `produce-detection`: [Piyu12/fruit-veg-yolo11m-detector](https://huggingface.co/Piyu12/fruit-veg-yolo11m-detector/tree/82c9865261175e778ba5641cf8560b5d10439ec6), revision `82c9865261175e778ba5641cf8560b5d10439ec6`, file `best.pt`.

## Setup and reproducibility

From the project root, after normal `setup.ps1`:

~~~powershell
.\scripts\setup-fruit-models.ps1 -Action Full
.\scripts\setup-fruit-models.ps1 -Action Status
~~~

`Full` explicitly downloads all four pinned artifacts and their model cards, verifies source SHA256 values, then prepares local ONNX artifacts. To install one model, add `-ModelId tomato-ripeness-3`. `Download` and `Export` actions can be run separately. `Status` checks the complete local registry. Restart the API after adding this feature's backend code.

The setup catalog, pinned revisions and expected source hashes are in `astra_bio/fruit_setup.py`. Export uses the separate `runtime/ml-training/.venv` environment. The script pins PyTorch 2.14.1, torchvision 0.29.1, Ultralytics 8.4.21, ONNX 1.23.2, ONNX Runtime 1.31.0, NumPy 2.5.2 and Pillow 12.3.0. It preserves an existing compatible PyTorch build and refuses to overwrite different PyTorch versions. A new export environment uses official CPU wheels; GPU hardware is unnecessary for app inference.

The three `.pt` sources are loaded with `weights_only=True` and an explicit reviewed framework-class allowlist, then exported with fixed input, batch 1, opset 17 and no embedded NMS. A seeded numerical tensor comparison checks PyTorch-to-ONNX export parity. The existing tomato ONNX file is copied directly and has no export-parity claim. Each `runtime/fruit-models/<model-id>/manifest.json` records actual labels, dimensions, source/export hashes, revision, license declarations and export package versions. Binary artifacts, cards, manifests and smoke photographs remain Git-ignored; a fresh clone needs explicit model setup.

Runtime uses Pillow RGB bilinear square letterboxing with fill 114, float32 NCHW and division by 255. Tensor export parity does **not** establish pixel-for-pixel parity with Ultralytics' OpenCV image preprocessing. Graph signature, ordered labels and current artifact hash are verified before use. The default score threshold is 0.35; the API accepts 0.10–0.95. IoU suppression is 0.45, with at most 300 detections. Tomato maturity suppression spans conflicting stage classes so overlapping labels do not automatically count one tomato twice.

API routes are `GET /api/fruit-models` and multipart `POST /api/fruit-image?crop_species=tomato&model_id=tomato-ripeness-3`; the form field is `file`. Responses distinguish `observed`, `no_detections`, `rejected` and `unavailable`.

## Observation boundaries

The browser previews the selected photo in memory and sends it to the local backend only when screening is submitted. The backend processes the bytes transiently; it does not save the photograph or send it to an external inference service. Inference never downloads models. Evidence is exported only when requested by the user.

Counts describe detections visible in one photograph. Occlusion, reflections, unfamiliar backgrounds, lighting and the threshold can change results. Repeated photos can count the same fruit again, and no-detection does not confirm absence. Scores are uncalibrated model outputs, not probabilities of correctness. Visual stages do not establish harvest readiness, bacterial identity, disease, edibility, nutrient content or food safety. An RGB photo cannot count underground potato tubers.

All four artifacts have executed on a publisher-provided tomato example; that is a pipeline smoke test, **not an independent accuracy benchmark**. It does not validate bell pepper, potato, this project's trays, hydroponic lighting or spaceflight. Local labelled photographs across crops, lighting, occlusion and empty/wrong-crop cases are still needed for detection/count/stage evaluation.

Fruit observations do not update food inventory, estimate harvested mass, alter a scenario or issue actuator commands. A reviewed, weighed harvest record is needed before crediting food to planning. The leaf classifier remains a separate workflow.

## Licenses and attribution

The first three publisher cards declare MIT; their installed ONNX metadata declares **AGPL-3.0**. The generic produce card and installed graph declare AGPL-3.0. Ultralytics provides [AGPL and Enterprise terms](https://www.ultralytics.com/license). These declarations are recorded separately rather than treating an uploader's MIT tag as permission for every inherited artifact or framework component. Review the upstream terms for the intended distribution or hosted use; no project-license or repository-visibility change is made by this integration.

ASTRA-BIO adds export manifests, integrity/label checks, local preprocessing/postprocessing, crop filtering and the observation UI. Original pinned checkpoints and publisher cards are retained unchanged locally. See [third-party notices](../THIRD_PARTY_NOTICES.md) and the earlier [model availability assessment](FRUIT_MODEL_RESEARCH.md) for attribution and source-reported metrics; those metrics are not ASTRA-BIO validation results.
