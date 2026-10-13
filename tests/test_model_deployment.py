import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from astra_bio import model_deployment as deployment


def fixture_bundle(tmp_path, *, contents=None, extra=None):
    contents = contents or {"runtime/plant-model/model.onnx": b"serving model", "runtime/plant-active.json": b'{"candidate_id":"base"}'}
    archive = tmp_path / "bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, data in {**contents, **(extra or {})}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            bundle.addfile(entry, io.BytesIO(data))
    manifest = {"schema_version": 1,
        "url": "https://github.com/Sanjay-AI-ML/astra-bio/releases/download/test/models.tar.gz",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()}}
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(manifest))
    return archive, path, manifest


def test_install_is_verified_and_idempotent(tmp_path, monkeypatch):
    archive, manifest, _ = fixture_bundle(tmp_path)
    root = tmp_path / "app"
    result = deployment.install_models(root=root, manifest_path=manifest, archive_path=archive)
    assert result["status"] == "installed"
    assert (root / "runtime/plant-model/model.onnx").read_bytes() == b"serving model"
    monkeypatch.setattr(deployment, "urlopen", lambda *args, **kwargs: pytest.fail("Installed bundle should not redownload"))
    assert deployment.install_models(root=root, manifest_path=manifest)["status"] == "verified"


def test_operator_leaf_selection_is_preserved(tmp_path):
    archive, manifest, _ = fixture_bundle(tmp_path)
    root = tmp_path / "app"
    active = root / "runtime/plant-active.json"
    active.parent.mkdir(parents=True)
    active.write_text('{"candidate_id":"selected-by-operator"}')
    deployment.install_models(root=root, manifest_path=manifest, archive_path=archive)
    assert "selected-by-operator" in active.read_text()
    assert deployment.install_models(root=root, manifest_path=manifest)["status"] == "verified"


def test_corrupt_download_does_not_replace_existing_model(tmp_path):
    archive, manifest, _ = fixture_bundle(tmp_path)
    root = tmp_path / "app"
    target = root / "runtime/plant-model/model.onnx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous version")
    archive.write_bytes(b"corrupted download")
    with pytest.raises(ValueError, match="integrity"):
        deployment.install_models(root=root, manifest_path=manifest, archive_path=archive)
    assert target.read_bytes() == b"previous version"


@pytest.mark.parametrize("name", ["../escape", "runtime/plant-model/../../escape", "runtime/mongodb/settings.json", "/absolute"])
def test_unsafe_or_unrelated_manifest_paths_are_rejected(tmp_path, name):
    archive, manifest, _ = fixture_bundle(tmp_path, contents={name: b"bad"})
    with pytest.raises(ValueError, match="allowed runtime"):
        deployment.install_models(root=tmp_path / "app", manifest_path=manifest, archive_path=archive)


def test_extra_archive_entries_are_rejected_before_installation(tmp_path):
    archive, manifest, _ = fixture_bundle(tmp_path, extra={"runtime/plant-model/extra": b"unlisted"})
    root = tmp_path / "app"
    with pytest.raises(ValueError, match="unexpected entry"):
        deployment.install_models(root=root, manifest_path=manifest, archive_path=archive)
    assert not (root / "runtime/plant-model/model.onnx").exists()


def test_entry_hash_is_checked_even_with_valid_archive_hash(tmp_path):
    archive, manifest, data = fixture_bundle(tmp_path)
    data["files"]["runtime/plant-model/model.onnx"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="artifact failed"):
        deployment.install_models(root=tmp_path / "app", manifest_path=manifest, archive_path=archive)


def test_render_startup_is_enabled_and_local_startup_skips_install(monkeypatch):
    called = []
    monkeypatch.setattr(deployment, "install_models", lambda: called.append(True))
    monkeypatch.delenv("ASTRA_INSTALL_MODELS", raising=False)
    monkeypatch.delenv("ASTRA_LEAF_MODEL", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    deployment.initialize_deployment_models()
    assert not called
    monkeypatch.setenv("RENDER", "true")
    deployment.initialize_deployment_models()
    assert called == [True]
    monkeypatch.setenv("ASTRA_INSTALL_MODELS", "0")
    deployment.initialize_deployment_models()
    assert called == [True]


def test_fresh_cloud_install_selects_evaluated_candidate_and_preserves_later_choice(monkeypatch, tmp_path):
    from astra_bio import plant_registry
    selected = []
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "install_models", lambda: None)
    monkeypatch.setattr(plant_registry, "select_model", selected.append)
    monkeypatch.setenv("ASTRA_INSTALL_MODELS", "1")
    monkeypatch.delenv("ASTRA_LEAF_MODEL", raising=False)
    deployment.initialize_deployment_models()
    assert selected == ["plantdoc-20261011T142833Z"]
    active = tmp_path / "runtime/plant-active.json"
    active.parent.mkdir()
    active.write_text('{"candidate_id":"base"}')
    selected.clear()
    deployment.initialize_deployment_models()
    assert not selected
    monkeypatch.setenv("ASTRA_LEAF_MODEL", "base")
    deployment.initialize_deployment_models()
    assert selected == ["base"]
