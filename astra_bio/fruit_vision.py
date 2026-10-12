"""Local visible-fruit/tuber detection using explicitly installed ONNX artifacts.

Inference never downloads models, saves photographs, updates food inventory, or
issues crop-control commands. Scores and stage labels remain visual observations.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import threading

import numpy as np
from PIL import Image

from .plant_vision import decode_image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ROOT = ROOT / "runtime/fruit-models"
DEFAULT_MODEL_ID = "tomato-ripeness-3"
MODEL_SPECS = {
    "tomato-ripeness-3": {"name": "Tomato ripeness · 3 classes", "species": ["tomato"], "class_count": 3},
    "tomato-ripeness-6": {"name": "Tomato ripeness · 6 classes", "species": ["tomato"], "class_count": 6},
    "tomato-detection": {"name": "Tomato detection", "species": ["tomato"], "class_count": 1},
    "produce-detection": {"name": "Fruit and vegetable detection", "species": ["tomato", "bell pepper", "potato"], "class_count": 35},
}
MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_DETECTIONS = 300
NMS_IOU = 0.45
WARNINGS = [
    "Counts cover visible detections in this photograph; occluded objects can be missed and repeated photographs can count the same object again.",
    "Model scores are uncalibrated. Stage labels require visual review and do not establish harvest readiness, pathogen status or food safety.",
    "These terrestrial models have not been validated for ASTRA-BIO, spaceflight or hydroponic lighting.",
    "Potato detections refer to exposed tubers; an RGB photograph cannot establish an underground tuber count.",
    "This observation does not update inventory, estimate harvest mass or trigger automatic actions.",
]
_INFERENCE_SLOTS = threading.BoundedSemaphore(2)
_SESSION_LOCK = threading.Lock()


def normalize_species(value: str) -> str:
    value = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return {"pepper": "bell pepper", "pepper bell": "bell pepper", "capsicum": "bell pepper"}.get(value, value)


def _label_text(label: str) -> str:
    return " ".join(label.lower().replace("_", " ").replace("-", " ").split())


def _class_details(model_id: str, label: str) -> tuple[str | None, str]:
    if model_id == "produce-detection":
        species = normalize_species(label)
        return (species if species in MODEL_SPECS[model_id]["species"] else None), "detected"
    if model_id == "tomato-detection":
        return "tomato", "detected"
    text = _label_text(label)
    # Preserve source stage distinctions; variety prefixes remain in class_label.
    if "unripe" in text or "green" in text:
        stage = "unripe"
    elif "semi" in text or "half" in text:
        stage = "semi-ripe"
    elif "fully" in text or text in {"ripe", "red"}:
        stage = "fully ripe"
    else:
        stage = text
    return "tomato", stage


def _manifest(model_id: str, model_root: Path) -> tuple[dict, Path]:
    if model_id not in MODEL_SPECS:
        raise ValueError("Choose one of the installed fruit model IDs.")
    directory = model_root / model_id
    path = directory / "manifest.json"
    if not path.is_file() or not (directory / "model.onnx").is_file():
        raise ValueError("Local fruit model is not installed; use explicit model setup.")
    if path.stat().st_size > 64 * 1024:
        raise ValueError("Fruit model manifest exceeds its local size limit.")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or manifest.get("id") != model_id or manifest.get("task") != "detect":
        raise ValueError("Fruit model manifest identity or task is invalid.")
    spec = MODEL_SPECS[model_id]
    species = manifest.get("species")
    if not isinstance(species, list) or len(species) != len(spec["species"]) or set(species) != set(spec["species"]):
        raise ValueError("Fruit model manifest species coverage is invalid.")
    labels = manifest.get("labels")
    if (not isinstance(labels, list) or len(labels) != spec["class_count"]
            or any(not isinstance(label, str) or not label.strip() or len(label) > 120 for label in labels)
            or len(set(labels)) != len(labels)):
        raise ValueError("Fruit model ordered class mapping is invalid.")
    expected_stage_labels = {
        "tomato-ripeness-3": {"fully ripe", "semi ripe", "unripe"},
        "tomato-ripeness-6": {"green", "breakers", "turning", "pink", "light red", "red"},
        "tomato-detection": {"tomato"},
    }
    if model_id in expected_stage_labels and {_label_text(label) for label in labels} != expected_stage_labels[model_id]:
        raise ValueError("Fruit model labels do not match this model's tomato detection or maturity coverage.")
    if model_id == "produce-detection" and not set(spec["species"]).issubset({normalize_species(label) for label in labels}):
        raise ValueError("Produce class mapping does not cover the supported crops.")
    size = manifest.get("input_size")
    if (not isinstance(size, list) or len(size) != 2 or size[0] != size[1]
            or any(type(value) is not int or not 64 <= value <= 1536 or value % 32 for value in size)):
        raise ValueError("Fruit model input size must be a square export between 64 and 1536 pixels in multiples of 32.")
    digest = manifest.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Fruit model SHA256 declaration is invalid.")
    for field in ("name", "source_url", "revision", "license_declared"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip() or len(manifest[field]) > 2000:
            raise ValueError(f"Fruit model provenance field {field} is invalid.")
    if not manifest["source_url"].startswith("https://"):
        raise ValueError("Fruit model source must identify its public HTTPS provenance.")
    return manifest, directory / "model.onnx"


def _verified_bytes(path: Path, expected: str) -> bytes:
    if path.stat().st_size > MAX_MODEL_BYTES:
        raise ValueError("Fruit model exceeds its supported artifact size.")
    with path.open("rb") as handle:
        data = handle.read(MAX_MODEL_BYTES + 1)
    if len(data) > MAX_MODEL_BYTES:
        raise ValueError("Fruit model exceeds its supported artifact size.")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Fruit model integrity check failed; rerun explicit model setup.")
    return data


def _make_session(data: bytes):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    # Loading verified bytes also avoids resolving external tensor file paths.
    return ort.InferenceSession(data, sess_options=options, providers=["CPUExecutionProvider"])


def _graph_labels(session) -> list[str]:
    names = session.get_modelmeta().custom_metadata_map.get("names")
    if names is None:
        raise ValueError("ONNX ordered class metadata is missing.")
    try:
        parsed = json.loads(names)
    except (ValueError, TypeError):
        parsed = ast.literal_eval(names)
    if isinstance(parsed, list) and all(isinstance(label, str) for label in parsed):
        return parsed
    if isinstance(parsed, dict):
        if any(not isinstance(key, (str, int)) for key in parsed):
            raise ValueError("ONNX class metadata keys are invalid.")
        ordered = {int(key): label for key, label in parsed.items()}
        if set(ordered) == set(range(len(ordered))) and all(isinstance(label, str) for label in ordered.values()):
            return [ordered[index] for index in range(len(ordered))]
    raise ValueError("ONNX class metadata is invalid.")


def _validate_session(session, size: tuple[int, int], labels: tuple[str, ...]) -> None:
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if (len(inputs) != 1 or inputs[0].type != "tensor(float)"
            or list(inputs[0].shape) != [1, 3, *size]):
        raise ValueError("ONNX input does not match the manifest's RGB NCHW float32 preprocessing.")
    if len(outputs) != 1 or outputs[0].type != "tensor(float)":
        raise ValueError("ONNX must expose one raw float32 YOLO detection output.")
    shape = list(outputs[0].shape)
    channels = 4 + len(labels)
    if (len(shape) != 3 or shape[0] != 1 or channels not in shape[1:]
            or any(not isinstance(value, int) or value <= 0 or value > 100_000 for value in shape[1:])):
        raise ValueError("ONNX output does not match the ordered class count and raw YOLO box format.")
    graph_labels = _graph_labels(session)
    if graph_labels != list(labels):
        raise ValueError("ONNX class metadata disagrees with the manifest's ordered labels.")


@lru_cache(maxsize=4)
def _session(path: str, digest: str, size: tuple[int, int], labels: tuple[str, ...]):
    session = _make_session(_verified_bytes(Path(path), digest))
    _validate_session(session, size, labels)
    return session


def _load(model_id: str, model_root: Path) -> tuple[dict, object]:
    manifest, path = _manifest(model_id, model_root)
    # Verify current disk bytes even if the graph session is already cached.
    _verified_bytes(path, manifest["sha256"])
    with _SESSION_LOCK:
        session = _session(str(path.resolve()), manifest["sha256"], tuple(manifest["input_size"]), tuple(manifest["labels"]))
    manifest = dict(manifest)
    artifact_license = session.get_modelmeta().custom_metadata_map.get("license")
    if isinstance(artifact_license, str) and artifact_license.strip():
        manifest["artifact_license"] = artifact_license
    return manifest, session


def _provenance(manifest: dict) -> dict:
    return {key: manifest[key] for key in ("id", "name", "task", "species", "labels", "input_size", "sha256", "source_url", "revision", "license_declared", "artifact_license", "source_sha256", "framework_license", "validation", "export_parity", "capability", "export_environment", "preprocessing") if key in manifest}


def model_status(model_id: str, model_root: Path | None = None) -> dict:
    spec = MODEL_SPECS.get(model_id)
    if spec is None:
        return {"id": model_id, "ready": False, "reason": "Unknown fruit model ID."}
    base = {"id": model_id, "name": spec["name"], "task": "detect", "species": list(spec["species"]),
        "labels": [], "input_size": None, "provenance": {}}
    try:
        manifest, _ = _load(model_id, Path(model_root) if model_root is not None else DEFAULT_MODEL_ROOT)
        provenance = _provenance(manifest)
        return {**base, **provenance, "ready": True, "reason": "Local ONNX hash, ordered classes and graph signature verified.", "provenance": provenance}
    except Exception as exc:
        # ONNX Runtime errors use several types; model failure must not break the registry.
        reason = str(exc) if isinstance(exc, (ValueError, OSError)) else f"Local model validation failed ({type(exc).__name__})."
        return {**base, "ready": False, "reason": reason}


def fruit_registry_status(model_root: Path | None = None) -> dict:
    return {"default_model_id": DEFAULT_MODEL_ID,
        "models": [model_status(model_id, model_root) for model_id in MODEL_SPECS],
        "local_only": True, "automatic_action": False, "inventory_updated": False}


def letterbox_image(image: Image.Image, input_size: tuple[int, int]) -> tuple[np.ndarray, dict]:
    height, width = input_size
    scale = min(width / image.width, height / image.height)
    resized_width, resized_height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    left, top = (width - resized_width) // 2, (height - resized_height) // 2
    canvas = Image.new("RGB", (width, height), (114, 114, 114))
    canvas.paste(image.convert("RGB").resize((resized_width, resized_height), Image.Resampling.BILINEAR), (left, top))
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / np.float32(255)
    transform = {"image_width": image.width, "image_height": image.height,
        "scale_x": resized_width / image.width, "scale_y": resized_height / image.height,
        "pad_left": left, "pad_top": top}
    return np.ascontiguousarray(tensor, dtype=np.float32), transform


def undo_letterbox(boxes: np.ndarray, transform: dict) -> np.ndarray:
    boxes = np.asarray(boxes, dtype=np.float64).copy()
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - transform["pad_left"]) / transform["scale_x"]
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - transform["pad_top"]) / transform["scale_y"]
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, transform["image_width"]) / transform["image_width"]
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, transform["image_height"]) / transform["image_height"]
    return boxes


def classwise_nms(boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray, iou_threshold: float = NMS_IOU) -> list[int]:
    selected = []
    for class_id in np.unique(classes):
        order = np.flatnonzero(classes == class_id)
        order = order[np.argsort(-scores[order], kind="stable")]
        while len(order):
            index = int(order[0])
            selected.append(index)
            remaining = order[1:]
            if not len(remaining):
                break
            intersection = np.maximum(0, np.minimum(boxes[index, 2:], boxes[remaining, 2:]) - np.maximum(boxes[index, :2], boxes[remaining, :2]))
            intersection_area = intersection[:, 0] * intersection[:, 1]
            own_area = np.prod(np.maximum(0, boxes[index, 2:] - boxes[index, :2]))
            other_areas = np.prod(np.maximum(0, boxes[remaining, 2:] - boxes[remaining, :2]), axis=1)
            iou = intersection_area / np.maximum(own_area + other_areas - intersection_area, 1e-12)
            order = remaining[iou <= iou_threshold]
    return sorted(selected, key=lambda index: (-float(scores[index]), index))[:MAX_DETECTIONS]


def parse_detections(output, labels: list[str], model_id: str, crop_species: str, transform: dict, confidence: float) -> list[dict]:
    values = np.asarray(output, dtype=np.float64)
    channels = 4 + len(labels)
    if values.ndim != 3 or values.shape[0] != 1 or channels not in values.shape[1:] or not np.isfinite(values).all():
        raise ValueError("Model returned an invalid raw detection tensor.")
    rows = values[0].T if values.shape[1] == channels else values[0]
    if len(rows) > 100_000 or np.any(rows[:, 4:] < 0) or np.any(rows[:, 4:] > 1):
        raise ValueError("Model returned invalid class confidence scores.")
    classes = rows[:, 4:].argmax(axis=1)
    scores = rows[np.arange(len(rows)), 4 + classes]
    matches = np.array([_class_details(model_id, labels[int(class_id)])[0] == crop_species for class_id in classes], dtype=bool)
    keep = matches & (scores >= confidence) & (rows[:, 2] > 0) & (rows[:, 3] > 0)
    rows, classes, scores = rows[keep], classes[keep], scores[keep]
    boxes = np.column_stack((rows[:, :2] - rows[:, 2:4] / 2, rows[:, :2] + rows[:, 2:4] / 2))
    boxes = undo_letterbox(boxes, transform)
    nonempty = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    boxes, classes, scores = boxes[nonempty], classes[nonempty], scores[nonempty]
    # Maturity classes describe the same physical fruit; conflicting stages must
    # not produce duplicate counts for one overlapping tomato.
    suppression_classes = np.zeros_like(classes) if model_id.startswith("tomato-ripeness-") else classes
    indices = classwise_nms(boxes, scores, suppression_classes)
    return [{"id": number + 1, "class_label": labels[int(classes[index])],
        "stage": _class_details(model_id, labels[int(classes[index])])[1], "score": float(scores[index]),
        "box": boxes[index].tolist()} for number, index in enumerate(indices)]


def assess_fruit_image(image_bytes: bytes, crop_species: str, model_id: str = DEFAULT_MODEL_ID,
        confidence: float = 0.35, model_root: Path | None = None) -> dict:
    species = normalize_species(crop_species)
    base = {"model_id": model_id, "crop_species": species, "image_width": 0, "image_height": 0,
        "detections": [], "counts_by_stage": {}, "visible_count": 0, "warnings": list(WARNINGS),
        "local_only": True, "automatic_action": False, "inventory_updated": False, "provenance": {}}
    if model_id not in MODEL_SPECS:
        return {**base, "status": "rejected", "reason": "Choose a recognized fruit model ID."}
    if species not in MODEL_SPECS[model_id]["species"]:
        return {**base, "status": "rejected", "reason": "The selected model does not cover this crop species."}
    if not isinstance(confidence, (int, float)) or not np.isfinite(confidence) or not 0.1 <= confidence <= 0.95:
        return {**base, "status": "rejected", "reason": "Detection confidence must be between 0.10 and 0.95."}
    try:
        image = decode_image(image_bytes)
    except ValueError as exc:
        return {**base, "status": "rejected", "reason": str(exc).replace("leaf photograph", "fruit or tuber photograph")}
    base.update(image_width=image.width, image_height=image.height)
    if float(np.asarray(image.resize((64, 64)), dtype=np.float32).std(axis=(0, 1)).mean()) < 2:
        return {**base, "status": "rejected", "reason": "Image contains too little visual variation; choose a clear fruit or tuber photograph."}
    if not _INFERENCE_SLOTS.acquire(blocking=False):
        return {**base, "status": "unavailable", "reason": "Local fruit inference is busy; try again shortly."}
    try:
        manifest, session = _load(model_id, Path(model_root) if model_root is not None else DEFAULT_MODEL_ROOT)
        base["provenance"] = _provenance(manifest)
        tensor, transform = letterbox_image(image, tuple(manifest["input_size"]))
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        detections = parse_detections(output, manifest["labels"], model_id, species, transform, confidence)
        counts = {}
        for detection in detections:
            counts[detection["stage"]] = counts.get(detection["stage"], 0) + 1
        return {**base, "detections": detections, "counts_by_stage": counts, "visible_count": len(detections),
            "status": "observed" if detections else "no_detections",
            "reason": "Visible detections only; review boxes and stage labels in the photograph." if detections else "No selected-crop detections above the confidence threshold; absence is not confirmed.",
            "inference_provider": "CPUExecutionProvider", "confidence_threshold": confidence,
            "nms_iou_threshold": NMS_IOU, "detection_limit": MAX_DETECTIONS,
            "nms_class_agnostic": model_id.startswith("tomato-ripeness-"),
            "score_definition": "Original maximum class confidence across model classes; crop filtering does not renormalize scores.",
            "image_sha256": hashlib.sha256(image_bytes).hexdigest()}
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (ValueError, OSError)) else f"Local fruit inference failed ({type(exc).__name__}); inspect the model installation."
        return {**base, "status": "unavailable", "reason": reason}
    finally:
        _INFERENCE_SLOTS.release()
