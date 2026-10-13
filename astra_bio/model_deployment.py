"""Install a pinned, serving-only model bundle before accepting cloud requests."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/models/deployment.json"
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_INSTALLED_BYTES = 200 * 1024 * 1024
ALLOWED_ROOTS = {"plant-model", "plant-candidates", "fruit-models", "model-deployment"}
LOG = logging.getLogger(__name__)


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _validated_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ValueError("Invalid serving-model bundle manifest.")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("archive_sha256", "")):
        raise ValueError("Model bundle needs a pinned SHA256.")
    if not manifest.get("url", "").startswith("https://github.com/Sanjay-AI-ML/astra-bio/releases/download/"):
        raise ValueError("Model bundle URL is outside the configured release source.")
    total = 0
    for name, metadata in manifest["files"].items():
        parts = PurePosixPath(name).parts
        allowed = (len(parts) >= 3 and parts[0] == "runtime" and parts[1] in ALLOWED_ROOTS) or name == "runtime/plant-active.json"
        if not allowed or "\\" in name or PurePosixPath(name).is_absolute() or any(part in {"..", "."} for part in parts) or str(PurePosixPath(name)) != name:
            raise ValueError("Model bundle path is not an allowed runtime artifact.")
        if not isinstance(metadata, dict) or type(metadata.get("size")) is not int or not 0 < metadata["size"] <= 128 * 1024 * 1024:
            raise ValueError("Invalid serving artifact size.")
        if not re.fullmatch(r"[0-9a-f]{64}", metadata.get("sha256", "")):
            raise ValueError("Invalid serving artifact hash.")
        total += metadata["size"]
    if total > MAX_INSTALLED_BYTES:
        raise ValueError("Serving-model bundle exceeds its installed size limit.")
    return manifest


def _installed(root: Path, files: dict) -> bool:
    for name, metadata in files.items():
        path = root / name
        if name == "runtime/plant-active.json" and path.is_file():
            continue
        if not path.is_file() or path.stat().st_size != metadata["size"] or _digest(path) != metadata["sha256"]:
            return False
    return True


def install_models(*, root: Path = ROOT, manifest_path: Path = MANIFEST, archive_path: Path | None = None) -> dict:
    """Verify the entire archive in staging before replacing any serving file."""
    root = Path(root).resolve()
    manifest = _validated_manifest(Path(manifest_path))
    if _installed(root, manifest["files"]):
        return {"status": "verified", "files": len(manifest["files"])}
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="model-install-", dir=runtime) as temporary:
        stage = Path(temporary)
        archive = Path(archive_path) if archive_path is not None else stage / "models.tar.gz"
        if archive_path is None:
            request = Request(manifest["url"], headers={"User-Agent": "ASTRA-BIO model deployment"})
            with urlopen(request, timeout=180) as response, archive.open("wb") as destination:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise ValueError("Model download exceeds its size limit.")
                    destination.write(chunk)
        if archive.stat().st_size > MAX_ARCHIVE_BYTES or _digest(archive) != manifest["archive_sha256"]:
            raise ValueError("Serving-model archive failed its pinned integrity check.")
        seen = set()
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle:
                metadata = manifest["files"].get(member.name)
                if not member.isfile() or metadata is None or member.name in seen or member.size != metadata["size"]:
                    raise ValueError("Model archive contains an unexpected entry.")
                target = stage / "files" / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with bundle.extractfile(member) as source, target.open("wb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Serving artifact is truncated.")
                        digest.update(chunk)
                        output.write(chunk)
                        remaining -= len(chunk)
                if digest.hexdigest() != metadata["sha256"]:
                    raise ValueError("Serving artifact failed its pinned integrity check.")
                seen.add(member.name)
        if seen != set(manifest["files"]):
            raise ValueError("Model archive is missing required files.")
        for name in sorted(seen):
            destination = root / name
            # Refuse a pre-existing symlink that would redirect a write outside runtime.
            if not destination.resolve().is_relative_to(runtime.resolve()):
                raise ValueError("Model installation target leaves the runtime directory.")
        for name in sorted(seen):
            destination = root / name
            # Preserve a deliberate operator selection when refreshing serving weights.
            if name == "runtime/plant-active.json" and destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            (stage / "files" / name).replace(destination)
    LOG.info("Installed %s verified serving-model files.", len(seen))
    return {"status": "installed", "files": len(seen)}


def initialize_deployment_models() -> None:
    enabled = os.getenv("ASTRA_INSTALL_MODELS", "1" if os.getenv("RENDER") == "true" else "0")
    if enabled == "1":
        LOG.info("Verifying cloud screening artifacts before application startup.")
        install_models()


if __name__ == "__main__":
    print(json.dumps(install_models()))
