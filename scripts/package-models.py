"""Build a deterministic, verified serving-only model release for cloud deployment.

Run with the app environment: python scripts/package-models.py
This command does not download, train, export, activate, or publish models.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUNDLE_NAME = "astra-bio-models-v1.tar.gz"
RELEASE_URL = (
    "https://github.com/Sanjay-AI-ML/astra-bio/releases/download/"
    "model-assets-20261013-v1/" + BUNDLE_NAME
)
CANDIDATE_ID = "plantdoc-20261011T142833Z"


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def verified_sources() -> tuple[dict[str, Path], list[dict], dict]:
    """Validate the model graphs/evidence, then return an explicit file allowlist."""
    from astra_bio import fruit_vision, plant_registry, plant_vision

    base = plant_vision.model_status(plant_vision.DEFAULT_MODEL_DIR)
    if not base.get("ready"):
        raise ValueError(f"Base leaf model is unavailable: {base.get('reason')}")
    # Check the input/output signature as well as all pinned base file hashes.
    plant_vision._session(str(plant_vision.DEFAULT_MODEL_DIR))
    candidate_directory = plant_registry.candidate_path(CANDIDATE_ID)
    candidate = plant_registry.candidate_status(candidate_directory)
    if not candidate.get("ready") or not candidate.get("eligible"):
        raise ValueError(f"Fine-tuned leaf evidence failed: {candidate.get('reason')}")
    plant_vision._session(str(candidate_directory))
    pointer = json.loads(plant_registry.ACTIVE.read_text(encoding="utf-8"))
    _, active_status = plant_registry.resolve_active()
    if active_status is not None and not active_status.get("ready"):
        raise ValueError(f"Active leaf selection is invalid: {active_status.get('reason')}")
    if pointer.get("candidate_id") not in {"base", CANDIDATE_ID}:
        raise ValueError("Active selection is not included in the explicit serving bundle.")

    files: dict[str, Path] = {}

    def include(directory: Path, names: tuple[str, ...]) -> None:
        for name in names:
            source = directory / name
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Missing or unsupported serving artifact: {source.relative_to(ROOT)}")
            files[source.relative_to(ROOT).as_posix()] = source

    include(plant_vision.DEFAULT_MODEL_DIR, (
        "README.md", "class_names.json", "training_config.json", "model.onnx",
        "model.onnx.data", "PROVENANCE.json",
    ))
    include(candidate_directory, ("model.onnx", "class_names.json", "manifest.json", "report.json"))
    files[plant_registry.ACTIVE.relative_to(ROOT).as_posix()] = plant_registry.ACTIVE
    notices = ROOT / "THIRD_PARTY_NOTICES.md"
    if not notices.is_file() or notices.is_symlink():
        raise ValueError("The model bundle requires third-party notices.")
    files["runtime/model-deployment/THIRD_PARTY_NOTICES.md"] = notices

    candidate_manifest = json.loads((candidate_directory / "manifest.json").read_text(encoding="utf-8"))
    sources = [
        {
            "id": "leaf-base",
            "source_url": "https://huggingface.co/" + plant_vision.REPOSITORY,
            "revision": plant_vision.REVISION,
            "license_declared": base["license"],
            "model_card": "runtime/plant-model/README.md",
            "provenance": "runtime/plant-model/PROVENANCE.json",
        },
        {
            "id": CANDIDATE_ID,
            "source_url": "https://huggingface.co/" + candidate_manifest["base_repository"],
            "revision": candidate_manifest["base_revision"],
            "dataset_source_url": "https://github.com/pratikkayal/PlantDoc-Dataset",
            "dataset_revision": candidate_manifest["dataset_revision"],
            "license_declared": candidate["license"],
            "changes": "ASTRA-BIO fine-tuning, ONNX export and validation-temperature fitting.",
            "provenance": f"runtime/plant-candidates/{CANDIDATE_ID}/manifest.json",
            "evaluation": f"runtime/plant-candidates/{CANDIDATE_ID}/report.json",
        },
    ]
    fruit_verified = []
    for identifier in fruit_vision.MODEL_SPECS:
        # Explicit graph validation remains required even if registry listing is lazy.
        manifest, _ = fruit_vision._load(identifier, fruit_vision.DEFAULT_MODEL_ROOT)
        include(fruit_vision.DEFAULT_MODEL_ROOT / identifier,
                ("model.onnx", "manifest.json", "MODEL_CARD.md", "source-metadata.json"))
        fruit_verified.append(identifier)
        sources.append({
            "id": identifier,
            "source_url": manifest["source_url"],
            "revision": manifest["revision"],
            "license_declared": manifest["license_declared"],
            "artifact_license": manifest.get("artifact_license", "not specified"),
            "framework_license": manifest.get("framework_license", "not specified"),
            "changes": "ASTRA-BIO ONNX serving export and integrity/class-mapping manifest.",
            "model_card": f"runtime/fruit-models/{identifier}/MODEL_CARD.md",
            "provenance": f"runtime/fruit-models/{identifier}/manifest.json",
        })
    verification = {
        "leaf_base": "ready",
        "leaf_candidate": CANDIDATE_ID,
        "leaf_candidate_eligible": True,
        "active_leaf_id": pointer["candidate_id"],
        "fruit_models": fruit_verified,
        "scope": "Artifact integrity, graph signatures and retained evaluation evidence; not field accuracy.",
    }
    return files, sources, verification


def add_member(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    metadata = tarfile.TarInfo(name)
    metadata.size = len(content)
    metadata.mtime = 0
    metadata.mode = 0o644
    metadata.uid = metadata.gid = 0
    metadata.uname = metadata.gname = ""
    archive.addfile(metadata, BytesIO(content))


def build(output: Path, manifest_path: Path, url: str) -> dict:
    files, sources, verification = verified_sources()
    records = {
        name: {"sha256": sha256(source), "size": source.stat().st_size}
        for name, source in sorted(files.items())
    }
    bundle_manifest = {
        "schema_version": 1,
        "profile": "serving-only",
        "sources": sources,
        "verification": verification,
        "files": records,
        "notices": "runtime/model-deployment/THIRD_PARTY_NOTICES.md",
        "excluded": ["training checkpoints", "training environment", "datasets", "sample photographs", "credentials"],
    }
    embedded_manifest = json_bytes(bundle_manifest)
    embedded_name = "runtime/model-deployment/BUNDLE_MANIFEST.json"
    records[embedded_name] = {"sha256": hashlib.sha256(embedded_manifest).hexdigest(), "size": len(embedded_manifest)}
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + ".", suffix=".pending", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            with gzip.GzipFile(filename="", fileobj=temporary, mode="wb", mtime=0, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as archive:
                    for name in sorted(records):
                        content = embedded_manifest if name == embedded_name else files[name].read_bytes()
                        record = records[name]
                        if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                            raise ValueError(f"Serving artifact changed while packaging: {name}")
                        add_member(archive, name, content)
        temporary_path.replace(output)
        manifest = {
            "schema_version": 1,
            "url": url,
            "archive_sha256": sha256(output),
            "archive_size": output.stat().st_size,
            "files": records,
            "sources": sources,
            "verification": verification,
            "notices": bundle_manifest["notices"],
        }
        manifest_path.write_bytes(json_bytes(manifest))
        return manifest
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/model-deployment" / BUNDLE_NAME)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/models/deployment.json")
    parser.add_argument("--url", default=RELEASE_URL)
    arguments = parser.parse_args()
    manifest = build(arguments.output, arguments.manifest, arguments.url)
    print(json.dumps({"archive": str(arguments.output), "manifest": str(arguments.manifest),
                      "sha256": manifest["archive_sha256"], "size": manifest["archive_size"],
                      "files": len(manifest["files"]), "active_leaf_id": manifest["verification"]["active_leaf_id"]}, indent=2))


if __name__ == "__main__":
    main()
