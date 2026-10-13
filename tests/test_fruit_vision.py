"""Detector integration invariants; mock outputs do not measure model accuracy."""
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from astra_bio import fruit_vision as vision
from astra_bio.api import app

LABELS = ["Unripe", "Semi_ripe", "Fully_ripe"]
PRODUCE_LABELS = ["Tomato", "Potato", "Capsicum"] + [f"Other {index}" for index in range(32)]


def photo_bytes(size=(320, 160), format="PNG"):
    pixels = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    pixels[:, :size[0] // 2] = (180, 30, 30)
    pixels[:, size[0] // 2:] = (30, 170, 40)
    stream = BytesIO()
    Image.fromarray(pixels).save(stream, format=format)
    return stream.getvalue()


def raw_rows(rows):
    return np.asarray(rows, dtype=np.float32).T[None]


class FakeSession:
    def __init__(self, labels, output=None, size=(640, 640)):
        self.input = SimpleNamespace(name="images", type="tensor(float)", shape=[1, 3, *size])
        self.output = output if output is not None else raw_rows([[320, 320, 320, 160, .91, .03, .02]])
        self.signature = SimpleNamespace(name="output0", type="tensor(float)", shape=list(self.output.shape))
        self.metadata = {"names": repr(dict(enumerate(labels))), "license": "AGPL-3.0"}
        self.calls = []

    def get_inputs(self):
        return [self.input]

    def get_outputs(self):
        return [self.signature]

    def get_modelmeta(self):
        return SimpleNamespace(custom_metadata_map=self.metadata)

    def run(self, output_names, inputs):
        self.calls.append(inputs)
        return [self.output]


@pytest.fixture
def local_model(tmp_path, monkeypatch):
    vision._session.cache_clear()
    sessions = {}
    monkeypatch.setattr(vision, "DEFAULT_MODEL_ROOT", tmp_path)
    monkeypatch.setattr(vision, "_make_session", lambda data: sessions[data])

    def install(model_id=vision.DEFAULT_MODEL_ID, labels=None, output=None, size=(640, 640)):
        labels = labels or LABELS
        directory = tmp_path / model_id
        directory.mkdir()
        data = f"verified test graph {model_id}".encode()
        (directory / "model.onnx").write_bytes(data)
        manifest = {"id": model_id, "name": "Test local detector", "task": "detect",
            "species": vision.MODEL_SPECS[model_id]["species"], "labels": labels,
            "input_size": list(size), "sha256": hashlib.sha256(data).hexdigest(),
            "source_url": "https://huggingface.co/test/detector", "revision": "a" * 40,
            "license_declared": "MIT (publisher declaration)"}
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        session = FakeSession(labels, output, size)
        sessions[data] = session
        return directory, manifest, session

    yield install
    vision._session.cache_clear()


def test_letterbox_preserves_aspect_ratio_rgb_scale_and_padding():
    tensor, transform = vision.letterbox_image(Image.new("RGB", (320, 160), (255, 0, 0)), (640, 640))
    assert tensor.shape == (1, 3, 640, 640) and tensor.dtype == np.float32
    assert tensor.flags.c_contiguous
    assert tensor[0, :, 0, 0] == pytest.approx([114 / 255] * 3)
    assert tensor[0, :, 160, 0] == pytest.approx([1, 0, 0])
    assert transform["pad_top"] == 160 and transform["pad_left"] == 0
    restored = vision.undo_letterbox(np.array([[160, 240, 480, 400], [-20, 100, 700, 600]]), transform)
    assert restored[0] == pytest.approx([.25, .25, .75, .75])
    assert restored[1] == pytest.approx([0, 0, 1, 1])


def test_non_square_source_rounding_is_reversible():
    image = Image.new("RGB", (311, 129))
    _, transform = vision.letterbox_image(image, (960, 960))
    original = np.array([[17, 13, 207, 111]], dtype=float)
    projected = original.copy()
    projected[:, [0, 2]] = projected[:, [0, 2]] * transform["scale_x"] + transform["pad_left"]
    projected[:, [1, 3]] = projected[:, [1, 3]] * transform["scale_y"] + transform["pad_top"]
    assert vision.undo_letterbox(projected, transform)[0] == pytest.approx(original[0] / [311, 129, 311, 129])


def test_nms_suppresses_same_class_only_and_orders_by_original_score():
    boxes = np.array([[0, 0, 1, 1], [.01, .01, .99, .99], [.01, .01, .99, .99], [2, 2, 3, 3]])
    assert vision.classwise_nms(boxes, np.array([.9, .8, .7, .6]), np.array([0, 0, 1, 0])) == [0, 2, 3]


def test_missing_and_corrupted_artifacts_do_not_run_inference(tmp_path, local_model):
    result = vision.assess_fruit_image(photo_bytes(), "tomato")
    assert result["status"] == "unavailable" and result["detections"] == []
    directory, _, session = local_model()
    assert vision.model_status(vision.DEFAULT_MODEL_ID)["ready"] is True
    (directory / "model.onnx").write_bytes(b"corrupted after session was cached")
    result = vision.assess_fruit_image(photo_bytes(), "tomato")
    assert result["status"] == "unavailable" and "integrity" in result["reason"]
    assert session.calls == []


def test_model_metadata_and_input_signature_must_match_manifest(local_model):
    _, _, session = local_model()
    session.metadata["names"] = repr({0: "Fully_ripe", 1: "Semi_ripe", 2: "Unripe"})
    assert "disagrees" in vision.model_status(vision.DEFAULT_MODEL_ID)["reason"]
    session.metadata["names"] = repr(dict(enumerate(LABELS)))
    session.input.shape = [1, 3, 1024, 1024]
    assert "input" in vision.model_status(vision.DEFAULT_MODEL_ID)["reason"]
    session.input.shape = [1, 3, 640, 640]
    session.signature.shape = [1, 8, 8400]
    assert "output" in vision.model_status(vision.DEFAULT_MODEL_ID)["reason"]
    session.signature.shape = [1, 7, 8400]
    del session.metadata["names"]
    assert "metadata is missing" in vision.model_status(vision.DEFAULT_MODEL_ID)["reason"]
    assert session.calls == []


def test_registry_checks_files_without_loading_all_sessions(local_model, monkeypatch):
    local_model()
    monkeypatch.setattr(vision, "_make_session", lambda data: pytest.fail("Registry must not allocate detector sessions"))
    status = vision.fruit_registry_status()
    installed = next(row for row in status["models"] if row["id"] == vision.DEFAULT_MODEL_ID)
    assert installed["ready"] is True
    assert installed["graph_validation"] == "on_first_use"
    assert vision._session.cache_info().currsize == 0


def test_tomato_registry_rejects_unrelated_class_labels_even_if_graph_agrees(local_model):
    directory, manifest, session = local_model()
    manifest["labels"] = ["Apple", "Banana", "Orange"]
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    session.metadata["names"] = repr(dict(enumerate(manifest["labels"])))
    status = vision.model_status(vision.DEFAULT_MODEL_ID)
    assert status["ready"] is False and "coverage" in status["reason"]
    assert session.calls == []


def test_species_mismatch_unknown_model_and_bogus_images_are_rejected(local_model):
    _, _, session = local_model()
    for crop in ("potato", "bell pepper", "kale"):
        result = vision.assess_fruit_image(photo_bytes(), crop)
        assert result["status"] == "rejected" and result["visible_count"] == 0
    assert vision.assess_fruit_image(photo_bytes(), "tomato", "../other")["status"] == "rejected"
    for image in (b"bad bytes", photo_bytes(format="GIF"), photo_bytes(size=(32, 32))):
        assert vision.assess_fruit_image(image, "tomato")["status"] == "rejected"
    assert session.calls == []


def test_detection_geometry_stage_counts_scores_and_provenance(local_model):
    _, manifest, session = local_model()
    result = vision.assess_fruit_image(photo_bytes(), "tomato")
    assert result["status"] == "observed" and result["visible_count"] == 1
    assert result["image_width"] == 320 and result["image_height"] == 160
    detection = result["detections"][0]
    assert detection["class_label"] == "Unripe" and detection["stage"] == "unripe"
    assert detection["score"] == pytest.approx(.91) and detection["box"] == pytest.approx([.25, .25, .75, .75])
    assert result["counts_by_stage"] == {"unripe": 1}
    assert result["provenance"]["sha256"] == manifest["sha256"]
    assert result["provenance"]["license_declared"] != result["provenance"]["artifact_license"]
    assert result["provenance"]["artifact_license"] == "AGPL-3.0"
    assert result["local_only"] is True and result["automatic_action"] is False and result["inventory_updated"] is False
    assert "CPU" in result["inference_provider"] and session.calls[0]["images"].shape == (1, 3, 640, 640)


def test_transposed_output_and_empty_threshold_result(local_model):
    output = raw_rows([[320, 320, 320, 160, .1, .2, .8], [100, 100, 40, 40, .1, .1, .1]])
    _, _, session = local_model(output=output.transpose(0, 2, 1))
    result = vision.assess_fruit_image(photo_bytes(), "tomato")
    assert result["counts_by_stage"] == {"fully ripe": 1}
    result = vision.assess_fruit_image(photo_bytes(), "tomato", confidence=.95)
    assert result["status"] == "no_detections" and result["visible_count"] == 0
    assert len(session.calls) == 2


@pytest.mark.parametrize("model_id,labels", [
    ("tomato-ripeness-3", ["Fully-ripe", "Semi-ripe", "Unripe"]),
    ("tomato-ripeness-6", ["Green", "Breakers", "Turning", "Pink", "Light Red", "Red"]),
])
def test_conflicting_maturity_boxes_count_one_physical_fruit(local_model, model_id, labels):
    rows = np.zeros((2, 4 + len(labels)), dtype=np.float32)
    rows[:, :4] = [[320, 320, 320, 160], [322, 322, 320, 160]]
    rows[0, 4], rows[1, 4 + len(labels) - 1] = .92, .81
    local_model(model_id, labels, rows.T[None])
    result = vision.assess_fruit_image(photo_bytes(), "tomato", model_id)
    assert result["visible_count"] == 1 and result["nms_class_agnostic"] is True
    assert result["detections"][0]["class_label"] == labels[0]
    assert result["detections"][0]["score"] == pytest.approx(.92)


def test_produce_uses_global_class_winner_then_filters_selected_crop(local_model):
    rows = np.zeros((4, 39), dtype=np.float32)
    rows[:, :4] = [320, 320, 320, 160]
    rows[0, 4], rows[1, 5], rows[2, 6] = .85, .81, .77
    # An unrelated winning label must not become a false tomato after filtering.
    rows[3, 4], rows[3, 7] = .45, .90
    _, _, session = local_model("produce-detection", PRODUCE_LABELS, rows.T[None])
    for species, label, score in [("tomato", "Tomato", .85), ("potato", "Potato", .81), ("bell pepper", "Capsicum", .77)]:
        result = vision.assess_fruit_image(photo_bytes(), species, "produce-detection")
        assert result["visible_count"] == 1 and result["counts_by_stage"] == {"detected": 1}
        assert result["detections"][0]["class_label"] == label
        assert result["detections"][0]["score"] == pytest.approx(score)
    assert len(session.calls) == 3


def test_invalid_model_scores_fail_closed(local_model):
    _, _, session = local_model()
    session.output[0, 4, 0] = np.nan
    result = vision.assess_fruit_image(photo_bytes(), "tomato")
    assert result["status"] == "unavailable" and result["visible_count"] == 0


def test_a_960_export_is_supported_without_stretching(local_model):
    output = raw_rows([[480, 480, 480, 240, .8]])
    local_model("tomato-detection", ["tomato"], output, (960, 960))
    result = vision.assess_fruit_image(photo_bytes(), "tomato", "tomato-detection")
    assert result["status"] == "observed"
    assert result["detections"][0]["box"] == pytest.approx([.25, .25, .75, .75])


def test_api_registry_upload_and_confidence_validation(local_model):
    local_model()
    client = TestClient(app, base_url="http://127.0.0.1")
    registry = client.get("/api/fruit-models")
    assert registry.status_code == 200
    assert registry.json()["default_model_id"] == vision.DEFAULT_MODEL_ID
    assert len(registry.json()["models"]) == 4
    assert [row["ready"] for row in registry.json()["models"]] == [True, False, False, False]
    response = client.post("/api/fruit-image?crop_species=tomato", files={"file": ("photo.png", photo_bytes(), "image/png")})
    assert response.status_code == 200 and response.json()["visible_count"] == 1
    assert response.headers["cache-control"] == "no-store"
    response = client.post("/api/fruit-image?crop_species=tomato&confidence=0.01", files={"file": ("photo.png", photo_bytes(), "image/png")})
    assert response.status_code == 422
    response = client.post("/api/fruit-image?crop_species=tomato", files={"file": ("photo.png", b"bogus", "image/png")})
    assert response.json()["status"] == "rejected"
