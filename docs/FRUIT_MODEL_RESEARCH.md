# Pretrained fruit-monitoring model shortlist

Initial research checked on 12 October 2026. This is an availability assessment, not an inference benchmark. At that research stage, no fruit model had been installed or executed. The leaf model remains separate.

Implementation follow-up on the same date: the first three tomato candidates and the multi-produce candidate below are now pinned, installed, integrated and running locally on CPU. Actual ONNX input sizes, ordered graph labels, artifact licensing and software checks are recorded in [FRUIT_MONITORING.md](FRUIT_MONITORING.md) and [FRUIT_VERIFICATION.json](FRUIT_VERIFICATION.json). Four publisher-example runs establish execution, not independent ASTRA-BIO accuracy or biological validation. The graph's three-stage class order differs from the card's table; deployed mapping follows the graph.

## First candidate: tomato ripeness

[pablofntdz/yolov8-tomato-detection](https://huggingface.co/pablofntdz/yolov8-tomato-detection) provides a YOLOv8n detector with unripe, semi-ripe and fully-ripe tomato labels and 640×640 input. The [file listing](https://huggingface.co/pablofntdz/yolov8-tomato-detection/tree/main) contains `model_hub_n.pt` (6.26 MB) and an [OpenVINO INT8 export](https://huggingface.co/pablofntdz/yolov8-tomato-detection/tree/main/model_hub_n_int8_openvino_model) with XML/BIN/metadata files. Thus it is an actual released checkpoint, not only training code. The card reports precision 0.817, recall 0.771, mAP50 0.843 and mAP50–95 0.693; those are uploader-reported detection metrics, not ASTRA-BIO accuracy. Split sizes and detailed class-wise evaluation are not given. The card describes combined public sources while the [GitHub README](https://github.com/pablofntdz/yolov8-tomato-detection) describes manual greenhouse collection, leaving provenance questions. The repository/card declares MIT; underlying framework/model terms must also be reviewed. This is the preferred first candidate to benchmark, not a validated deployment choice.

## More detailed tomato maturity

[afeefaazam/tomato-ripeness-detector](https://huggingface.co/afeefaazam/tomato-ripeness-detector) releases a YOLO11s `model.pt` (19.3 MB in the [file listing](https://huggingface.co/afeefaazam/tomato-ripeness-detector/tree/main)), with Green, Breakers, Turning, Pink, Light Red and Red classes. Its card reports a 479/100/98 image split and test precision 0.581, recall 0.498, mAP50 0.507 and mAP50–95 0.388. More labels do not establish better reliability; some classes are weak. Video code uses tracking to reduce repeated-frame overcount. Its weight conversion uses an uncalibrated default average fruit mass, which must not become confirmed inventory. The card declares MIT, subject to reviewing framework/model provenance as well. Keep as a comparison candidate rather than assuming finer stages are useful for our tray.

## Direct ONNX tomato detection

[AitorConS/tomatoACLv1](https://huggingface.co/AitorConS/tomatoACLv1) releases both `.pt` and [`.onnx` files](https://huggingface.co/AitorConS/tomatoACLv1/tree/main). The ONNX file is listed as 10.8 MB. The card describes a YOLO11n architecture trained on a tomato detection dataset, with one target object class. It can provide boxes and visible counts but has no ripeness or disease labels. ONNX is compatible with our installed runtime, though preprocessing/output decoding still requires implementation and testing. The available metrics file marks measurements pending, so no measured accuracy is established by this research. The card declares MIT; upstream terms still require review.

## Research-backed segmentation alternative

[LaboroTomato](https://github.com/laboroai/LaboroTomato) provides an 804-image dataset with six labels combining normal/cherry size and three visual maturity stages. Its README links pretrained Mask R-CNN R50-FPN checkpoints and reports baseline bounding-box AP 64.3 and mask AP 65.7. The named download links were identified; their binary availability and current-environment execution were not tested. This is a heavier MMDetection integration than the nano detector. The project declares CC BY-NC-SA 4.0 and requests contact for commercial use. Keep it as a documented research reference unless its runtime and reuse conditions fit our intended product.

## Multi-produce candidate

[Piyu12/fruit-veg-yolo11m-detector](https://huggingface.co/Piyu12/fruit-veg-yolo11m-detector) lists 35 object classes including Tomato, Capsicum and Potato, with `best.pt` weights and YOLO11m architecture. It reports aggregate mAP50 0.925 and mAP50–95 0.691 on its source data and declares AGPL-3.0. It provides produce identity/localization, not crop-specific ripeness or bacterial-disease labels. Aggregate metrics do not establish greenhouse pepper accuracy. Consider as an identity/counting benchmark rather than claiming fully supported bell-pepper maturity monitoring. Potato observations would concern visible harvested tubers, not estimating hidden tubers from aerial foliage.

## Leads that do not yet qualify

[Pepper-Det](https://github.com/fjnuhyk/Pepper-Det) claims weights in its README, but the inspected [models directory](https://github.com/fjnuhyk/Pepper-Det/tree/main/models) listed only `readme.md`; the advertised weights directory was absent from the inspected root. A checkpoint and clear reuse licence were not verified. Do not mark it downloadable or deployable from the README alone. A generic fresh/rotten-fruit classifier is also not evidence for tomato/pepper bacterial disease classification; many search results were leaf models despite tomato-disease names. This search did not establish a suitable fruit-pathogen model for our crops.

## Integration and evaluation plan

Start with a separate tomato-photo workflow: explicit crop selection, detected boxes, visible count by maturity class, confidence scores and a no-detection/error state. Keep the leaf-screening model separate. Run inference locally on the laptop/backend; no ESP32 camera integration is needed for the photo-based first step. The author's depth-camera/3D wrapper is unnecessary for 2D photo monitoring.

Before implementation selection, pin the exact repository revision and artifact hashes, inspect labels and preprocessing, preserve licence/source attribution, verify graph/runtime compatibility and test labelled independent photographs with occlusions, different light levels and non-tomato/empty images. Published/uploader-reported mAP is not a probability of correctness or our model's evaluated accuracy. A usable public checkpoint can save initial training work while still requiring local validation.

For a YOLO checkpoint that needs export, [Ultralytics documents ONNX support for YOLOv8/YOLO11 detection](https://docs.ultralytics.com/integrations/onnx/). Export/parity testing should be isolated from the application environment; do not assume third-party `.pt` checkpoints or extra custom code are safe to execute without inspection. The [Ultralytics licence page](https://www.ultralytics.com/license) describes AGPL and Enterprise options. An uploader's MIT tag alone does not resolve all framework, inherited-weight or dataset obligations. No project-licence or GitHub visibility change was made here.

Visible maturity does not diagnose bacteria, establish edibility/safety, measure nutrients or confirm harvested mass. Hidden fruits are not counted from a single visible image. New photos must not repeatedly credit the same fruits as available food. The first version should retain observation evidence and require reviewed, weighed harvest logging before inventory/planning changes.

Recommendation: benchmark the small three-stage tomato model first. Keep the six-stage model as a comparison and the direct ONNX single-class detector as a detection-only alternative. Bell-pepper and potato-specific readiness/disease capabilities require separate evidence rather than inheriting tomato labels.
