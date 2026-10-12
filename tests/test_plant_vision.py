"""Local screening abstention, geometry, provenance and real artifact checks."""
from io import BytesIO
import json

import numpy as np
from PIL import Image
import pytest

from astra_bio import plant_vision as vision

LABELS = ["Pepper__bell___Bacterial_spot", "Pepper__bell___healthy", "Potato___Early_blight",
    "Potato___Late_blight", "Potato___healthy", "Tomato_Bacterial_spot", "Tomato_Early_blight",
    "Tomato_Late_blight", "Tomato_Leaf_Mold", "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites_Two_spotted_spider_mite", "Tomato__Target_Spot",
    "Tomato__Tomato_YellowLeaf__Curl_Virus", "Tomato__Tomato_mosaic_virus", "Tomato_healthy"]


def photo_bytes(color=None):
    if color is None:
        array = np.zeros((96, 96, 3), dtype=np.uint8)
        array[:48] = [40, 160, 60]
        array[48:] = [90, 110, 35]
        image = Image.fromarray(array)
    else:
        image = Image.new("RGB", (96, 96), color)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_tensor_matches_rgb_imagenet_and_does_not_stretch_to_square():
    tensor = vision.preprocess_image(Image.new("RGB", (500, 300), (255, 0, 0)))
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == np.float32 and tensor.flags.c_contiguous
    assert tensor[0, :, 0, 0] == pytest.approx([(1 - .485) / .229, -.456 / .224, -.406 / .225])
    # Side patches outside a wide image's center crop must disappear.
    wide = np.zeros((256, 768, 3), dtype=np.uint8)
    wide[:, :256] = [255, 0, 0]
    wide[:, 256:512] = [0, 255, 0]
    wide[:, 512:] = [0, 0, 255]
    cropped = vision.preprocess_image(Image.fromarray(wide))
    assert cropped[0, :, 100, 0] == pytest.approx([-.485 / .229, (1 - .456) / .224, -.406 / .225])


def test_invalid_unsupported_and_flat_inputs_are_withheld():
    assert vision.assess_image(b"not an image", "tomato")["status"] == "rejected"
    assert vision.assess_image(photo_bytes(), "kale")["predictions"] == []
    assert vision.assess_image(photo_bytes("green"), "tomato")["status"] == "rejected"
    with pytest.raises(ValueError):
        vision.decode_image(b"x" * (vision.MAX_IMAGE_BYTES + 1))


def test_missing_model_never_downloads_or_fabricates_predictions(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "urlopen", lambda *args, **kwargs: pytest.fail("Inference attempted a network call"))
    result = vision.assess_image(photo_bytes(), "tomato", tmp_path)
    assert result["status"] == "unavailable"
    assert result["predictions"] == []
    assert result["local_only"] is True and result["automatic_action"] is False
    assert list(tmp_path.iterdir()) == []


def test_modified_artifact_is_rejected_before_inference(tmp_path):
    (tmp_path / "README.md").write_text("changed model card")
    assert vision.model_status(tmp_path)["ready"] is False
    assert "Integrity" in vision.model_status(tmp_path)["reason"]


def test_scores_preserve_global_probability_and_species_mismatch_abstains():
    logits = np.zeros(15)
    logits[14] = 4
    result = vision.classify_logits(logits, LABELS, "tomato")
    assert result["status"] == "tentative"
    assert result["predictions"][0]["class_label"] == "Tomato_healthy"
    assert result["predictions"][0]["score"] == pytest.approx(np.exp(4) / (np.exp(4) + 14))
    assert vision.classify_logits(logits, LABELS, "potato")["status"] == "rejected"
    assert vision.classify_logits(logits, LABELS, "potato")["predictions"] == []


def test_weak_or_ambiguous_logits_abstain_without_calling_healthy_a_diagnosis():
    logits = np.zeros(15)
    logits[5:] = 1
    assert vision.classify_logits(logits, LABELS, "tomato")["status"] == "uncertain"
    logits[14], logits[7] = 8, 7.9
    assert vision.classify_logits(logits, LABELS, "tomato")["status"] == "uncertain"
    with pytest.raises(ValueError):
        vision.classify_logits(np.full(15, np.nan), LABELS, "tomato")


@pytest.mark.skipif(not (vision.DEFAULT_MODEL_DIR / "tomato-healthy-sample.jpg").is_file(), reason="Explicit optional model/sample setup not installed")
def test_real_local_onnx_artifact_runs_on_attributed_plantvillage_sample(monkeypatch):
    monkeypatch.setattr(vision, "urlopen", lambda *args, **kwargs: pytest.fail("Inference attempted a network call"))
    result = vision.assess_image((vision.DEFAULT_MODEL_DIR / "tomato-healthy-sample.jpg").read_bytes(), "tomato", vision.DEFAULT_MODEL_DIR)
    assert result["status"] == "tentative"
    assert result["predictions"][0]["class_label"] == "Tomato_healthy"
    assert result["predictions"][0]["score"] == pytest.approx(.912459, abs=.001)
    assert result["inference_provider"] == "CPUExecutionProvider"
    assert result["provenance"]["revision"] == vision.REVISION
    manifest = json.loads((vision.DEFAULT_MODEL_DIR / "PROVENANCE.json").read_text())
    assert manifest["sample"]["license"] == "CC-BY-SA-3.0"
    assert "not independent" in manifest["sample"]["independence"]
