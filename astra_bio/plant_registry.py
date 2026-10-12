"""Local versioned plant models, explicit selection and integrity-checked evidence."""
from __future__ import annotations

import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "runtime/plant-candidates"
ACTIVE = ROOT / "runtime/plant-active.json"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle,"sha256").hexdigest()


def candidate_path(identifier: str, root: Path = CANDIDATES) -> Path:
    if not isinstance(identifier,str) or not re.fullmatch(r"plantdoc-[0-9]{8}T[0-9]{6}Z",identifier):
        raise ValueError("Unknown plant-model identifier.")
    path=(Path(root) / identifier).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Model path leaves its registry.")
    return path


def candidate_status(path: Path) -> dict:
    try:
        manifest=json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if type(manifest["schema_version"]) is not int or manifest["schema_version"]!=1 or manifest["candidate_id"]!=path.name:
            raise ValueError("Model manifest identity does not match its folder.")
        hashes=manifest["files_sha256"]
        for name in ("model.onnx","class_names.json","report.json"):
            if not re.fullmatch(r"[0-9a-f]{64}",hashes[name]) or digest(path / name)!=hashes[name]:
                raise ValueError(f"Integrity check failed for {name}.")
        if type(manifest["temperature"]) not in (float,int):
            raise ValueError("Invalid fitted temperature type.")
        temperature=float(manifest["temperature"])
        if not isfinite(temperature) or not .05 <= temperature <=20:
            raise ValueError("Invalid fitted temperature.")
        labels=json.loads((path / "class_names.json").read_text())
        from .plant_vision import DEFAULT_MODEL_DIR, HASHES
        # A changed base mapping cannot authenticate a candidate's class order.
        if digest(DEFAULT_MODEL_DIR / "class_names.json")!=HASHES["class_names.json"]:
            raise ValueError("Base class mapping integrity check failed.")
        if labels!=json.loads((DEFAULT_MODEL_DIR / "class_names.json").read_text()):
            raise ValueError("Fine-tuned class order differs from the verified screening classes.")
        report=json.loads((path / "report.json").read_text(encoding="utf-8"))
        if report["candidate_id"]!=path.name or type(report["schema_version"]) is not int or report["schema_version"]!=1:
            raise ValueError("Evaluation identity mismatch.")
        calibration=report["temperature_fit"]
        if (calibration["fit_split"]!="validation" or type(calibration["known_samples"]) is not int
                or calibration["known_samples"]<1 or type(calibration["temperature"]) not in (float,int)
                or not isfinite(calibration["temperature"])
                or not isclose(calibration["temperature"],temperature,rel_tol=1e-12,abs_tol=1e-12)):
            raise ValueError("Fitted temperature does not match validation evidence.")
        baseline,candidate=report["baseline"],report["candidate"]
        for metrics in (baseline,candidate):
            for key in ("accuracy","macro_f1"):
                if type(metrics[key]) not in (float,int) or not isfinite(metrics[key]) or not 0<=metrics[key]<=1:
                    raise ValueError("Invalid recorded evaluation metrics.")
        if type(report["gate"]["eligible"]) is not bool:
            raise ValueError("Invalid recorded evaluation gate.")
        eligible=report["gate"]["eligible"] and candidate["macro_f1"]>baseline["macro_f1"] and candidate["accuracy"]>=baseline["accuracy"]
        return {"ready":True,"candidate_id":path.name,"kind":"fine_tuned","reason":"Local fine-tuned ONNX and held-out report hash verified.",
            "temperature":temperature,"temperature_scope":"Fitted on PlantDoc validation images only; no tray calibration.",
            "eligible":eligible,"tested_classes":manifest["tested_classes"],"output_classes":len(labels),
            "model_sha256":hashes["model.onnx"],"manifest_sha256":digest(path / "manifest.json"),
            "repository":manifest["base_repository"],"revision":manifest["base_revision"],
            "dataset_revision":manifest["dataset_revision"],"metrics":candidate,"baseline_metrics":baseline,
            "limitations":manifest["limitations"],"license":"Base model MIT; PlantDoc data CC-BY-4.0 (upstream declarations)"}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {"ready":False,"candidate_id":path.name,"kind":"fine_tuned","reason":str(exc)}


def resolve_active(active_path: Path = ACTIVE, root: Path = CANDIDATES) -> tuple[Path | None, dict | None]:
    if not Path(active_path).exists():
        return None,None
    try:
        pointer=json.loads(Path(active_path).read_text(encoding="utf-8"))
        if type(pointer.get("schema_version")) is not int or pointer.get("schema_version")!=1:
            raise ValueError("Unsupported active-model record.")
        if pointer["candidate_id"]=="base":
            return None,None
        path=candidate_path(pointer["candidate_id"],root)
        status=candidate_status(path)
        if not status["ready"] or not status["eligible"] or status["manifest_sha256"]!=pointer["manifest_sha256"]:
            raise ValueError("Active model failed its integrity or evaluation gate; select the base model explicitly.")
        return path,status
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return None,{"ready":False,"reason":str(exc),"kind":"fine_tuned"}


def select_model(identifier: str, active_path: Path = ACTIVE, root: Path = CANDIDATES) -> dict:
    if identifier=="base":
        pointer={"schema_version":1,"candidate_id":"base"}
    else:
        path=candidate_path(identifier,root)
        status=candidate_status(path)
        if not status["ready"] or not status.get("eligible"):
            raise ValueError("This model cannot be selected: missing integrity evidence or no held-out improvement.")
        pointer={"schema_version":1,"candidate_id":identifier,"manifest_sha256":status["manifest_sha256"]}
    Path(active_path).parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(active_path).with_suffix(".pending")
    temporary.write_text(json.dumps(pointer,indent=2)+"\n",encoding="utf-8")
    temporary.replace(active_path)
    return pointer


def registry_status() -> dict:
    from .plant_vision import DEFAULT_MODEL_DIR, model_status
    _,active=resolve_active()
    candidates=[candidate_status(path) for path in sorted(CANDIDATES.glob("plantdoc-*")) if path.is_dir()]
    return {"base":{**model_status(DEFAULT_MODEL_DIR),"candidate_id":"base","kind":"pretrained"},
        "active_id":active.get("candidate_id","unavailable") if active else "base","candidates":candidates,
        "automatic_action":False}
