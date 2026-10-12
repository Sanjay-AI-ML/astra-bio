"""Versioned model integrity, selection gates and fail-closed active pointers."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from astra_bio import plant_registry as registry, plant_vision as vision


IDENTIFIER = "plantdoc-20261012T123000Z"
LABELS = ["Pepper__bell___Bacterial_spot", "Pepper__bell___healthy", "Potato___Early_blight",
    "Potato___Late_blight", "Potato___healthy", "Tomato_Bacterial_spot", "Tomato_Early_blight",
    "Tomato_Late_blight", "Tomato_Leaf_Mold", "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites_Two_spotted_spider_mite", "Tomato__Target_Spot",
    "Tomato__Tomato_YellowLeaf__Curl_Virus", "Tomato__Tomato_mosaic_virus", "Tomato_healthy"]


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    directory = root / IDENTIFIER
    directory.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    write_json(base / "class_names.json", LABELS)
    pinned = {**vision.HASHES, "class_names.json": registry.digest(base / "class_names.json")}
    monkeypatch.setattr(vision, "DEFAULT_MODEL_DIR", base)
    monkeypatch.setattr(vision, "HASHES", pinned)
    # Deliberately opaque model bytes: this fixture tests the registry's hash
    # verification, not ONNX execution (covered by inference/export tests).
    (directory / "model.onnx").write_bytes(b"registry integrity fixture")
    write_json(directory / "class_names.json", LABELS)
    report = {"schema_version": 1, "candidate_id": IDENTIFIER,
              "baseline": {"accuracy": .6, "macro_f1": .5},
              "candidate": {"accuracy": .8, "macro_f1": .7}, "gate": {"eligible": True},
              "temperature_fit": {"temperature": 1.5, "fit_split": "validation", "known_samples": 30}}
    write_json(directory / "report.json", report)
    manifest = {"schema_version": 1, "candidate_id": IDENTIFIER, "temperature": 1.5,
                "base_repository": "test/base", "base_revision": "pinned-base",
                "dataset_revision": "pinned-data", "tested_classes": LABELS[:10],
                "limitations": ["Subset benchmark, not tray validation."],
                "files_sha256": {name: registry.digest(directory / name)
                                 for name in ("model.onnx", "class_names.json", "report.json")}}
    write_json(directory / "manifest.json", manifest)
    return {"path": directory, "root": root, "base": base, "manifest": manifest, "report": report,
            "active": tmp_path / "plant-active.json"}


def refresh_fixture(candidate, filename):
    candidate["manifest"]["files_sha256"][filename] = registry.digest(candidate["path"] / filename)
    write_json(candidate["path"] / "manifest.json", candidate["manifest"])


@pytest.mark.parametrize("identifier", ["../outside", "base", "plantdoc-20261012T123000Z/../outside",
    "plantdoc-20261012T123000Z\\other", "C:\\outside", "plantdoc-invalid", None])
def test_candidate_identifier_cannot_leave_registry(tmp_path, identifier):
    with pytest.raises(ValueError):
        registry.candidate_path(identifier, tmp_path)
    valid = registry.candidate_path(IDENTIFIER, tmp_path)
    assert valid == (tmp_path / IDENTIFIER).resolve()


def test_candidate_directory_symlink_cannot_point_outside_registry(tmp_path):
    root, outside = tmp_path / "registry", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    try:
        (root / IDENTIFIER).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows host does not allow creating symlinks.")
    with pytest.raises(ValueError, match="leaves"):
        registry.candidate_path(IDENTIFIER, root)


def test_candidate_status_verifies_content_and_full_class_order(candidate):
    result = registry.candidate_status(candidate["path"])
    assert result["ready"] and result["eligible"]
    assert result["output_classes"] == 15
    assert len(result["tested_classes"]) == 10
    assert result["temperature"] == 1.5
    assert result["model_sha256"] == registry.digest(candidate["path"] / "model.onnx")
    assert result["manifest_sha256"] == registry.digest(candidate["path"] / "manifest.json")


@pytest.mark.parametrize("filename", ["model.onnx", "class_names.json", "report.json"])
def test_any_modified_candidate_file_fails_integrity(candidate, filename):
    with (candidate["path"] / filename).open("ab") as handle:
        handle.write(b"tampered")
    result = registry.candidate_status(candidate["path"])
    assert result["ready"] is False
    assert "Integrity" in result["reason"]


def test_changed_candidate_class_order_and_changed_base_mapping_are_rejected(candidate):
    write_json(candidate["path"] / "class_names.json", list(reversed(LABELS)))
    refresh_fixture(candidate, "class_names.json")
    result = registry.candidate_status(candidate["path"])
    assert not result["ready"] and "class order" in result["reason"]
    write_json(candidate["base"] / "class_names.json", list(reversed(LABELS)))
    result = registry.candidate_status(candidate["path"])
    assert not result["ready"] and "Base class mapping integrity" in result["reason"]


@pytest.mark.parametrize("temperature", [0, -.1, 20.1, float("nan"), float("inf"), True, "1.5"])
def test_temperature_must_remain_within_validated_bounds(candidate, temperature):
    candidate["manifest"]["temperature"] = temperature
    write_json(candidate["path"] / "manifest.json", candidate["manifest"])
    result = registry.candidate_status(candidate["path"])
    assert not result["ready"]
    assert "temperature" in result["reason"]


@pytest.mark.parametrize("accuracy,macro_f1,flag", [(.5, .7, True), (.8, .5, True), (.8, .7, False)])
def test_selection_requires_actual_improvement_and_recorded_gate(candidate, accuracy, macro_f1, flag):
    candidate["report"]["candidate"].update(accuracy=accuracy, macro_f1=macro_f1)
    candidate["report"]["gate"]["eligible"] = flag
    write_json(candidate["path"] / "report.json", candidate["report"])
    refresh_fixture(candidate, "report.json")
    result = registry.candidate_status(candidate["path"])
    assert result["ready"] and not result["eligible"]
    with pytest.raises(ValueError, match="cannot be selected"):
        registry.select_model(IDENTIFIER, candidate["active"], candidate["root"])
    assert not candidate["active"].exists()


@pytest.mark.parametrize("value", [True, "0.8", None, float("nan"), -1, 1.1])
def test_recorded_accuracy_must_be_a_finite_numeric_rate_not_boolean(candidate, value):
    candidate["report"]["candidate"]["accuracy"] = value
    write_json(candidate["path"] / "report.json", candidate["report"])
    refresh_fixture(candidate, "report.json")
    status = registry.candidate_status(candidate["path"])
    assert not status["ready"]
    assert "metrics" in status["reason"]


@pytest.mark.parametrize("value", ["false", "true", 1, 0, None])
def test_recorded_improvement_gate_requires_an_actual_json_boolean(candidate, value):
    candidate["report"]["gate"]["eligible"] = value
    write_json(candidate["path"] / "report.json", candidate["report"])
    refresh_fixture(candidate, "report.json")
    status = registry.candidate_status(candidate["path"])
    assert not status["ready"]
    assert "gate" in status["reason"]


@pytest.mark.parametrize("field,value", [("temperature", 2.0), ("temperature", True),
    ("fit_split", "test"), ("fit_split", "train"), ("known_samples", 0), ("known_samples", True)])
def test_calibration_must_match_frozen_manifest_and_validation_only(candidate, field, value):
    candidate["report"]["temperature_fit"][field] = value
    write_json(candidate["path"] / "report.json", candidate["report"])
    refresh_fixture(candidate, "report.json")
    status = registry.candidate_status(candidate["path"])
    assert not status["ready"]
    assert "validation evidence" in status["reason"]


def test_select_candidate_writes_verified_manifest_hash_and_preserves_failure(candidate, monkeypatch):
    verified = {"ready": True, "eligible": True, "manifest_sha256": "a" * 64, "candidate_id": IDENTIFIER}
    monkeypatch.setattr(registry, "candidate_status", lambda path: verified)
    pointer = registry.select_model(IDENTIFIER, candidate["active"], candidate["root"])
    assert pointer["manifest_sha256"] == verified["manifest_sha256"]
    assert json.loads(candidate["active"].read_text()) == pointer
    assert not candidate["active"].with_suffix(".pending").exists()
    before = candidate["active"].read_bytes()
    monkeypatch.setattr(registry, "candidate_status", lambda path: {"ready": False, "eligible": True})
    with pytest.raises(ValueError):
        registry.select_model(IDENTIFIER, candidate["active"], candidate["root"])
    assert candidate["active"].read_bytes() == before


def test_resolving_active_candidate_requires_unchanged_manifest_and_gate(candidate):
    registry.select_model(IDENTIFIER, candidate["active"], candidate["root"])
    path, status = registry.resolve_active(candidate["active"], candidate["root"])
    assert path == candidate["path"].resolve() and status["ready"]
    # Even an innocuous manifest edit invalidates the hash recorded at selection.
    candidate["manifest"]["limitations"].append("Changed after activation.")
    write_json(candidate["path"] / "manifest.json", candidate["manifest"])
    path, status = registry.resolve_active(candidate["active"], candidate["root"])
    assert path is None and status is not None and status["ready"] is False
    assert "select the base model explicitly" in status["reason"]


@pytest.mark.parametrize("pointer", [
    {"schema_version": 99, "candidate_id": "base"},
    {"schema_version": True, "candidate_id": "base"},
    {"schema_version": 1, "candidate_id": "../outside", "manifest_sha256": "a" * 64},
    {"schema_version": 1, "candidate_id": IDENTIFIER},
    {"schema_version": 1},
])
def test_malformed_active_pointer_is_unavailable_not_silent_base_fallback(candidate, pointer):
    write_json(candidate["active"], pointer)
    path, status = registry.resolve_active(candidate["active"], candidate["root"])
    assert path is None and status is not None and status["ready"] is False
    assert status["kind"] == "fine_tuned"


def test_malformed_json_active_pointer_fails_closed_and_explicit_base_is_available(candidate):
    assert registry.resolve_active(candidate["active"], candidate["root"]) == (None, None)
    candidate["active"].write_text("broken JSON", encoding="utf-8")
    path, status = registry.resolve_active(candidate["active"], candidate["root"])
    assert path is None and status["ready"] is False
    pointer = registry.select_model("base", candidate["active"], candidate["root"])
    assert pointer == {"schema_version": 1, "candidate_id": "base"}
    assert registry.resolve_active(candidate["active"], candidate["root"]) == (None, None)
