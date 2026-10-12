"""Local, tentative PlantVillage image screening; never diagnosis or control.

Artifact setup is an explicit command. Inference never downloads a model or
uploads an image. Upstream MIT-declared model: imaflower/plantvillage-mobilenetv3.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = ROOT / "runtime/plant-model"
REPOSITORY = "imaflower/plantvillage-mobilenetv3"
REVISION = "d76fe187be1c4c3a5474f835a7a70cd08c7ab085"
MODEL_CARD = f"https://huggingface.co/{REPOSITORY}/blob/{REVISION}/README.md"
HASHES = {
    "README.md": "c50e846478029621fe7d4526eab4334945298d0ca8abcd48d7045cf5325e02e2",
    "class_names.json": "75e9ab85f377dbee0719281946d0b8e6fee163b534512229742c93cd669a657a",
    "training_config.json": "01f811ac89185dda84c02001c35ff91b3107a96326644f9b3193c4579f06921d",
    "model.onnx": "c6a962f699ddc820108231b23454b6a4e242407044c2c2514a0f6294d35428fc",
    "model.onnx.data": "c03d114add89db13d850e5bbe0a7c09040cf6caf1acfbbd489c21234fa6dcb5e",
}
SAMPLE_URL = ("https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/"
    "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/raw/color/Tomato___healthy/"
    "000146ff-92a4-4db6-90ad-8fce2ae4fddd___GH_HL%20Leaf%20259.1.JPG")
SAMPLE_HASH = "a294299b0518a50ebc275c0ec4519b022cab8b34735039f6c2a089a911f6964e"
SUPPORTED_SPECIES = ("tomato", "potato", "bell pepper")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
LIMITATIONS = [
    "Tentative similarity to terrestrial leaf classes; not pathogen confirmation.",
    "Softmax scores are not calibrated probabilities of correctness; unfamiliar images can score highly.",
    "Not validated in space, under hydroponic lighting, or for species outside tomato, potato and bell pepper.",
    "No crop isolation, removal, treatment, scenario changes or actuator commands occur automatically.",
]


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def model_status(model_dir: Path | None = None) -> dict:
    if model_dir is None:
        from .plant_registry import resolve_active
        _, status = resolve_active()
        if status is not None:
            return status
        model_dir = DEFAULT_MODEL_DIR
    model_dir = Path(model_dir)
    for name, expected in HASHES.items():
        path = model_dir / name
        if not path.is_file():
            return {"ready": False, "reason": "Local model is not installed. Run scripts/setup-plant-model.ps1."}
        try:
            actual_hash = _sha(path)
        except OSError:
            return {"ready": False, "reason": f"Local model file {name} cannot be read."}
        if actual_hash != expected:
            return {"ready": False, "reason": f"Integrity check failed for {name}; rerun explicit model setup."}
    return {"ready": True, "reason": "Pinned local ONNX model and class mapping verified.",
        "repository": REPOSITORY, "revision": REVISION, "license": "MIT (upstream model-card declaration)",
        "model_sha256": HASHES["model.onnx"], "weights_sha256": HASHES["model.onnx.data"],
        "class_mapping_sha256": HASHES["class_names.json"], "model_card": MODEL_CARD}


def _download(url: str, target: Path, digest: str) -> None:
    # Only the explicit setup command calls this function with pinned URLs.
    if target.is_file() and _sha(target) == digest:
        return
    with urlopen(url, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Downloaded artifact failed the size or pinned SHA256 check: {target.name}")
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def setup_model(model_dir: Path = DEFAULT_MODEL_DIR, *, include_sample: bool = False) -> dict:
    """Explicit download of fixed, public artifacts; requires no account/API key."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    for filename, digest in HASHES.items():
        _download(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{filename}", model_dir / filename, digest)
    manifest = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY, "revision": REVISION, "license": "MIT as declared in retained upstream README.md",
        "source": MODEL_CARD, "files_sha256": HASHES,
        "preprocessing": {"rgb": True, "resize_shorter_side": 256, "center_crop": 224,
            "interpolation": "Pillow bilinear", "layout": "NCHW float32", "scale": "divide by 255",
            "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
        "training_metrics": "Self-reported upstream metrics; not ASTRA-BIO or spaceflight validation."}
    if include_sample:
        _download(SAMPLE_URL, model_dir / "tomato-healthy-sample.jpg", SAMPLE_HASH)
        manifest["sample"] = {"filename": "tomato-healthy-sample.jpg", "url": SAMPLE_URL,
            "sha256": SAMPLE_HASH, "dataset_label": "Tomato___healthy", "license": "CC-BY-SA-3.0",
            "license_source": "https://huggingface.co/datasets/mohanty/PlantVillage",
            "attribution": "PlantVillage: Sharada P. Mohanty, David P. Hughes and Marcel Salathe, 2016, DOI10.3389/fpls.2016.01419",
            "changes": "Downloaded original unchanged; resized/cropped in memory for inference.",
            "independence": "Dataset sample may have appeared in upstream training; smoke check, not independent accuracy test."}
    (model_dir / "PROVENANCE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return model_status(model_dir)


def decode_image(data: bytes) -> Image.Image:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a nonempty JPG, PNG or WebP image smaller than 10 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Only a single JPG, PNG or WebP photograph is supported.")
                if min(image.size) < 64 or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Use an image at least 64 pixels per side and no larger than 20 megapixels.")
                image.load()
                return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("The image could not be safely decoded; choose a different leaf photograph.") from exc


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Match model-card Resize(256), CenterCrop(config.img_size=224), Normalize."""
    image = image.convert("RGB")
    width, height = image.size
    if width <= height:
        resized = (256, int(256 * height / width))
    else:
        resized = (int(256 * width / height), 256)
    image = image.resize(resized, resample=Image.Resampling.BILINEAR)
    left, top = round((resized[0] - 224) / 2), round((resized[1] - 224) / 2)
    image = image.crop((left, top, left + 224, top + 224))
    array = np.asarray(image, dtype=np.float32) / np.float32(255)
    array = (array - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None], dtype=np.float32)


def _species(label: str) -> str:
    if label.startswith("Tomato"):
        return "tomato"
    if label.startswith("Potato"):
        return "potato"
    if label.startswith("Pepper"):
        return "bell pepper"
    raise ValueError("Unexpected label species in the pinned model mapping.")


@lru_cache(maxsize=2)
def _session(directory: str):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(Path(directory) / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or inputs[0].type != "tensor(float)" or inputs[0].shape[1:] != [3, 224, 224] or len(outputs) != 1 or outputs[0].shape[-1] != 15:
        raise ValueError("Pinned model input/output signature does not match the verified preprocessing.")
    return session


def classify_logits(logits, labels: list[str], crop_species: str) -> dict:
    """Species-matched ranking with original scores and explicit abstention."""
    species = crop_species.strip().lower()
    species = {"pepper": "bell pepper", "pepper bell": "bell pepper"}.get(species, species)
    if species not in SUPPORTED_SPECIES:
        return {"status": "rejected", "reason": f"{crop_species} is outside this model's species coverage.", "predictions": []}
    values = np.asarray(logits, dtype=np.float64).reshape(-1)
    if len(values) != len(labels) or len(labels) != 15 or not np.isfinite(values).all():
        raise ValueError("Model logits or label mapping are invalid.")
    exponent = np.exp(values - values.max())
    probabilities = exponent / exponent.sum()
    selected = [i for i, label in enumerate(labels) if _species(label) == species]
    ranking = sorted(selected, key=lambda i: probabilities[i], reverse=True)
    global_top = int(np.argmax(probabilities))
    mass = float(probabilities[selected].sum())
    def condition(label: str) -> str:
        prefix = "Pepper__bell" if label.startswith("Pepper") else species.capitalize()
        return " ".join(label[len(prefix):].split("_" )).strip()
    predictions = [{"class_label": labels[i], "condition": condition(labels[i]),
        "score": float(probabilities[i]), "healthy_label": labels[i].lower().endswith("healthy")} for i in ranking[:3]]
    first = float(probabilities[ranking[0]])
    second = float(probabilities[ranking[1]]) if len(ranking) > 1 else 0.0
    if _species(labels[global_top]) != species or mass < .5:
        status, reason = "rejected", "Image/model species evidence conflicts with the selected crop; result withheld."
    elif first < .7 or first - second < .15:
        status, reason = "uncertain", "Scores are weak or ambiguous; retake a clear single-leaf photograph and request human review."
    else:
        status, reason = "tentative", "Tentative visual match only; confirm with a crop specialist before any intervention."
    return {"status": status, "reason": reason, "crop_species": species,
        "predictions": predictions if status != "rejected" else [], "selected_species_score": mass,
        "score_definition": "Original global softmax scores across all 15 classes; never renormalized within crop species.",
        "thresholds": {"minimum_score": .7, "minimum_margin": .15, "minimum_species_mass": .5,
            "validation": "Conservative UI abstention rules, not clinically/agronomically calibrated thresholds."}}


def assess_image(image_bytes: bytes, crop_species: str, model_dir: Path | None = None) -> dict:
    """Return local screening evidence. Image bytes are not written or transmitted."""
    base = {"warnings": list(LIMITATIONS), "local_only": True, "automatic_action": False}
    if crop_species.strip().lower() not in (*SUPPORTED_SPECIES, "pepper", "pepper bell"):
        return {**base, "status": "rejected", "reason": f"{crop_species} is unsupported by this pretrained model.", "predictions": []}
    try:
        image = decode_image(image_bytes)
    except ValueError as exc:
        return {**base, "status": "rejected", "reason": str(exc), "predictions": []}
    # Flat/nonphotographic input is a modest quality rejection, not a leaf detector.
    if float(np.asarray(image.resize((64, 64)), dtype=np.float32).std(axis=(0, 1)).mean()) < 2:
        return {**base, "status": "rejected", "reason": "Image contains too little visual variation for leaf screening.", "predictions": []}
    if model_dir is None:
        from .plant_registry import resolve_active
        selected, active_status = resolve_active()
        model_dir = selected or DEFAULT_MODEL_DIR
        provenance = active_status if active_status is not None else model_status(model_dir)
    else:
        provenance = model_status(model_dir)
    if not provenance["ready"]:
        return {**base, "status": "unavailable", "reason": provenance["reason"], "predictions": []}
    try:
        labels = json.loads((Path(model_dir) / "class_names.json").read_text())
        session = _session(str(Path(model_dir).resolve()))
        logits = session.run(None, {session.get_inputs()[0].name: preprocess_image(image)})[0][0]
        temperature = provenance.get("temperature", 1.0)
        result = classify_logits(logits / temperature, labels, crop_species)
        result["score_calibration"] = {"temperature": temperature, "scope": provenance.get("temperature_scope", "Original uncalibrated upstream scores.")}
        return {**base, **result, "provenance": provenance, "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_size": list(image.size), "inference_provider": "CPUExecutionProvider"}
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        return {**base, "status": "unavailable", "reason": f"Local inference failed ({type(exc).__name__}); inspect the model installation.", "predictions": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("--sample", action="store_true", help="Download one attributed real PlantVillage smoke sample.")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--image", type=Path, default=DEFAULT_MODEL_DIR / "tomato-healthy-sample.jpg")
    args = parser.parse_args()
    if args.action == "setup":
        print(json.dumps(setup_model(include_sample=args.sample), indent=2))
        return 0
    result = assess_image(args.image.read_bytes(), "tomato")
    print(json.dumps(result, indent=2))
    (DEFAULT_MODEL_DIR / "SMOKE_RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["status"] in {"tentative", "uncertain"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
