"""Reproducible local transfer learning. No training runs during application startup."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from urllib.request import urlopen
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image, ImageOps

from .plant_vision import DEFAULT_MODEL_DIR, REVISION, REPOSITORY, preprocess_image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "runtime/ml-training"
CANDIDATES = ROOT / "runtime/plant-candidates"
DATA_REVISION = "5467f6012d78d1c446145d5f582da6096f852ae8"
DATA_URL = f"https://codeload.github.com/pratikkayal/PlantDoc-Dataset/zip/{DATA_REVISION}"
WEIGHTS_SHA = "e9254cff70919a3952aafe9c6f40ef9ab2a883455594419322bf23d1323c7e62"
MAPPING = {
    "Bell_pepper leaf": "Pepper__bell___healthy",
    "Potato leaf early blight": "Potato___Early_blight",
    "Potato leaf late blight": "Potato___Late_blight",
    "Tomato Early blight leaf": "Tomato_Early_blight",
    "Tomato Septoria leaf spot": "Tomato_Septoria_leaf_spot",
    "Tomato leaf bacterial spot": "Tomato_Bacterial_spot",
    "Tomato leaf late blight": "Tomato_Late_blight",
    "Tomato leaf mosaic virus": "Tomato__Tomato_mosaic_virus",
    "Tomato leaf": "Tomato_healthy",
    "Tomato mold leaf": "Tomato_Leaf_Mold",
}
LIMITATIONS = [
    "PlantDoc cropped internet photographs, not ASTRA-BIO tray or spaceflight observations.",
    "Only ten explicitly mapped classes are evaluated; five output classes lack this benchmark.",
    "Published official test files are held out of fine-tuning and checkpoint selection.",
    "Capture identities are unavailable; hash-based grouping cannot prove biological independence.",
    "Unknown overlap with upstream PlantVillage pretraining cannot be excluded.",
    "Temperature uses validation data; scores remain unproven for unfamiliar images.",
    "No pathogen confirmation or automatic intervention.",
]


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def download(url: str, target: Path, expected: str | None = None) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and (expected is None or sha(target) == expected):
        return sha(target)
    temp = target.with_suffix(target.suffix + ".partial")
    with urlopen(url, timeout=90) as response, temp.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    digest = sha(temp)
    if expected and digest != expected:
        raise ValueError("Downloaded training weights failed their pinned hash.")
    temp.replace(target)
    return digest


def image_fingerprints(path: Path) -> tuple[str, str]:
    with Image.open(path) as photo:
        photo = ImageOps.exif_transpose(photo).convert("RGB")
        if min(photo.size) < 64 or photo.width * photo.height > 20_000_000:
            raise ValueError("Image outside screening geometry limits.")
        # Exact decoded pixels catch re-encoded images. dHash catches some near copies.
        digest = hashlib.sha256(str(photo.size).encode() + photo.tobytes()).hexdigest()
        gray = np.asarray(photo.convert("L").resize((9, 8)), dtype=np.int16)
        bits = gray[:, 1:] > gray[:, :-1]
        phash = sum(int(bit) << i for i, bit in enumerate(bits.ravel()))
        return digest, f"{phash:016x}"


def group_and_split(records: list[dict], seed: int = 42, distance: int = 8) -> tuple[list[dict], dict]:
    """Conservative connected hash groups; quarantine conflicts; test has priority."""
    rows = [dict(row) for row in records]
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, row in enumerate(rows):
        for j in range(i):
            if row["sha256"] == rows[j]["sha256"] or (int(row["phash"],16) ^ int(rows[j]["phash"],16)).bit_count() <= distance:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[find(i)].append(row)
    kept, quarantined, removed = [], [], []
    by_label = defaultdict(list)
    for members in groups.values():
        identifier = "hash-" + min(row["sha256"] for row in members)[:20]
        if len({row["label"] for row in members}) > 1:
            quarantined.extend(row["path"] for row in members)
            continue
        # Keep one representative per group; remove train copies of official test images.
        priority = sorted(members, key=lambda r:(r["original_split"] != "test", r["path"]))
        chosen = {**priority[0], "group_id": identifier}
        removed.extend(row["path"] for row in priority[1:])
        if chosen["original_split"] == "test":
            kept.append({**chosen, "split":"test"})
        else:
            by_label[chosen["label"]].append(chosen)
    rng = random.Random(seed)
    for label, members in sorted(by_label.items()):
        members.sort(key=lambda r:r["group_id"])
        rng.shuffle(members)
        if len(members) < 15:
            raise ValueError(f"Too few independent image groups for {label}: {len(members)}.")
        n_val = max(3, round(len(members) * .2))
        kept.extend({**row, "split":"validation" if i < n_val else "train"} for i,row in enumerate(members))
    return sorted(kept,key=lambda r:(r["split"],r["label"],r["path"])), {
        "perceptual_hash":"64-bit difference hash", "maximum_hamming_distance":distance,
        "conflicting_label_quarantine":quarantined, "duplicate_removals":removed,
        "capture_group_limitation":"Near-copy clusters, not verified plant/photographer IDs.",
    }


def prepare(seed: int = 42) -> dict:
    from .vision_evaluation import audit_manifest
    WORK.mkdir(parents=True, exist_ok=True)
    dataset = WORK / "plantdoc"
    dataset.mkdir(exist_ok=True)
    tree_url=f"https://api.github.com/repos/pratikkayal/PlantDoc-Dataset/git/trees/{DATA_REVISION}?recursive=1"
    with urlopen(tree_url,timeout=30) as response:
        tree_bytes=response.read(4*1024*1024)
    tree=json.loads(tree_bytes)
    if tree.get("truncated"):
        raise ValueError("Pinned repository tree is incomplete.")
    (WORK / "source-tree.json").write_bytes(tree_bytes)
    files=[]
    for entry in tree["tree"]:
        parts=Path(entry["path"]).parts
        if entry["type"]!="blob": continue
        allowed=len(parts)==1 and parts[0] in {"LICENSE.txt","README.md"}
        allowed |= len(parts)==3 and parts[0] in {"train","test"} and parts[1] in MAPPING
        if allowed: files.append(entry)
    def fetch(entry):
        parts=Path(entry["path"]).parts
        # Internet filenames contain Windows-reserved characters; store by blob ID.
        local_parts=parts if len(parts)==1 else (*parts[:2],entry["sha"]+".jpg")
        target=dataset.joinpath(*local_parts).resolve()
        if not target.is_relative_to(dataset.resolve()):
            raise ValueError("Dataset path leaves its destination.")
        def git_hash(data): return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        if target.is_file() and git_hash(target.read_bytes())==entry["sha"]:
            return
        original=dataset / entry["path"]
        try:
            if original.is_file():
                data=original.read_bytes()
                if git_hash(data)==entry["sha"]:
                    target.write_bytes(data)
                    return
        except OSError:
            pass
        url=f"https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/{DATA_REVISION}/"+quote(entry["path"],safe="/")
        error=None
        for attempt in range(3):
            try:
                with urlopen(url,timeout=40) as response:
                    data=response.read(entry["size"]+1)
                if len(data)!=entry["size"] or git_hash(data)!=entry["sha"]:
                    raise ValueError("Image bytes differ from the pinned repository blob.")
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
                return
            except (OSError,ValueError) as exc: error=exc
        raise ValueError(f"Cannot fetch pinned image {entry['path']}: {error}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fetch,entry) for entry in files]
        for i,future in enumerate(as_completed(futures),1):
            future.result()
            if i%50==0 or i==len(files): print(json.dumps({"downloaded_files":i,"total_files":len(files)}),flush=True)
    records, invalid = [], []
    for entry in files:
        parts=Path(entry["path"]).parts
        if len(parts)==3:
            split,folder=parts[:2]
            label=MAPPING[folder]
            path=dataset / split / folder / (entry["sha"]+".jpg")
            if path.is_file():
                try:
                    exact, perceptual = image_fingerprints(path)
                except (ValueError,OSError) as exc:
                    invalid.append({"path":str(path.relative_to(dataset)),"reason":str(exc)})
                    continue
                records.append({"path":str(path.relative_to(dataset)).replace("\\","/"),"source_path":entry["path"],"git_blob_sha1":entry["sha"],"label":label,
                    "original_split":split,"sha256":exact,"file_sha256":sha(path),"phash":perceptual,"source":"PlantDoc"})
    rows, duplicates = group_and_split(records, seed)
    audit = audit_manifest(rows, perceptual_distance=8)
    if not audit.get("valid", not audit.get("errors")):
        raise ValueError(f"Split integrity audit failed: {audit}")
    manifest = {"schema_version":1,"dataset":"Cropped PlantDoc","revision":DATA_REVISION,
        "source_url":"https://github.com/pratikkayal/PlantDoc-Dataset","source_tree_url":tree_url,"source_tree_sha256":hashlib.sha256(tree_bytes).hexdigest(),
        "download_integrity":"Each file verified against the Git blob SHA1 from the pinned repository revision; SHA256 also retained per image.",
        "license":"CC-BY-4.0 (repository declaration)","attribution":"Singh, Jain, Jain, Kayal, Kumawat and Batra (2020), DOI10.1145/3371158.3371196",
        "mapping":MAPPING,"excluded_folders_reason":"Generic bell-pepper leaf spot and tomato yellow virus have ambiguous crosswalk; spider-mite class has two training images and no test; other species unsupported.",
        "seed":seed,"records":rows,"invalid_images":invalid,"duplicate_audit":duplicates,"split_audit":audit,
        "counts":dict(Counter(row["split"] for row in rows)),"limitations":LIMITATIONS}
    write_json(WORK / "dataset-manifest.json",manifest)
    download(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/pytorch_model.bin",WORK / "base-state.pt",WEIGHTS_SHA)
    print(json.dumps({"prepared":manifest["counts"],"invalid_images":len(invalid),"duplicates_removed":len(duplicates["duplicate_removals"]),"quarantined":len(duplicates["conflicting_label_quarantine"]) }), flush=True)
    return manifest


def train(epochs: int = 5, seed: int = 42, batch_size: int = 16) -> dict:
    import torch
    from torchvision import models, transforms
    from torch.utils.data import Dataset, DataLoader
    from .vision_evaluation import evaluate_logits, fit_temperature, audit_manifest
    if not 1 <= epochs <= 50 or not 1 <= batch_size <= 64:
        raise ValueError("Use 1–50 epochs and a batch size of 1–64.")
    manifest = json.loads((WORK / "dataset-manifest.json").read_text(encoding="utf-8"))
    labels = json.loads((DEFAULT_MODEL_DIR / "class_names.json").read_text())
    audit = audit_manifest(manifest["records"], perceptual_distance=8)
    if not audit["valid"]:
        raise ValueError("Training manifest has split leakage or invalid identities.")
    if sha(WORK / "base-state.pt") != WEIGHTS_SHA:
        raise ValueError("Base state failed integrity check.")
    for record in manifest["records"]:
        path = (WORK / "plantdoc" / record["path"]).resolve()
        if not path.is_relative_to((WORK / "plantdoc").resolve()):
            raise ValueError("Training image path leaves its dataset.")
        parts = Path(record["path"]).parts
        if len(parts)!=3 or parts[0] not in {"train","test"} or MAPPING.get(parts[1])!=record["label"]:
            raise ValueError("Dataset class or original source split differs from the pinned crosswalk.")
        if parts[0]=="test" and record["split"]!="test":
            raise ValueError("An official test image cannot enter training or validation.")
        if sha(path) != record["file_sha256"]:
            raise ValueError("Dataset changed since split construction.")
        if image_fingerprints(path)!=(record["sha256"],record["phash"]):
            raise ValueError("Image fingerprints differ from the audited split.")
    torch.set_num_threads(4)
    torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = models.mobilenet_v3_small(weights=None)
    model.classifier[3] = torch.nn.Linear(model.classifier[3].in_features, len(labels))
    model.load_state_dict(torch.load(WORK / "base-state.pt", map_location="cpu", weights_only=True), strict=True)
    model.to(device)
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    train_transform = transforms.Compose([transforms.RandomResizedCrop(224,scale=(.8,1.0)),
        transforms.RandomHorizontalFlip(),transforms.ColorJitter(.12,.12,.12,.02),
        transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    class Photos(Dataset):
        def __init__(self, split): self.rows=[r for r in manifest["records"] if r["split"]==split]; self.split=split
        def __len__(self): return len(self.rows)
        def __getitem__(self,index):
            row=self.rows[index]
            with Image.open(WORK / "plantdoc" / row["path"]) as image:
                image=ImageOps.exif_transpose(image).convert("RGB")
                tensor=train_transform(image) if self.split=="train" else torch.from_numpy(preprocess_image(image)[0])
            return tensor,labels.index(row["label"])
    datasets={split:Photos(split) for split in ("train","validation","test")}
    generator=torch.Generator().manual_seed(seed)
    loaders={split:DataLoader(dataset,batch_size=batch_size,shuffle=split=="train",num_workers=0,generator=generator) for split,dataset in datasets.items()}
    def infer(split):
        model.eval(); outputs=[]; targets=[]
        with torch.inference_mode():
            for inputs, target in loaders[split]:
                outputs.append(model(inputs.to(device)).cpu().numpy()); targets.extend(target.tolist())
        return np.concatenate(outputs), np.asarray(targets)
    # Baseline test outputs are stored, never used to choose weights/hyperparameters.
    base_test, test_targets = infer("test")
    base_val, val_targets = infer("validation")
    counts=np.bincount([labels.index(r["label"]) for r in datasets["train"].rows],minlength=15)
    weights=np.ones(15,dtype=np.float32)
    weights[counts>0]=counts[counts>0].sum()/(np.count_nonzero(counts)*counts[counts>0])
    loss_fn=torch.nn.CrossEntropyLoss(weight=torch.tensor(weights,device=device))
    optimizer=torch.optim.AdamW(model.classifier.parameters(),lr=1e-4,weight_decay=1e-3)
    original={key:tensor.detach().clone() for key,tensor in model.classifier.named_parameters()}
    best_score=-1.0; best_state=None; history=[]
    print(json.dumps({"device":str(device),"epochs":epochs,"counts":manifest["counts"],"method":"frozen feature backbone; fine-tune classifier with augmentation and anchoring"}),flush=True)
    for epoch in range(epochs):
        model.train(); model.features.eval(); running=0.0
        for inputs,target in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            logits=model(inputs.to(device))
            penalty=sum((p-original[name]).square().mean() for name,p in model.classifier.named_parameters())
            loss=loss_fn(logits,target.to(device))+.1*penalty
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.classifier.parameters(),1.0); optimizer.step()
            running+=float(loss.detach())*len(target)
        val_logits,_=infer("validation")
        metrics=evaluate_logits(val_logits,val_targets,labels,split_name="validation")
        entry={"epoch":epoch+1,"train_loss":running/len(datasets["train"]),"validation_macro_f1":metrics["macro_f1"],"validation_accuracy":metrics["accuracy"]}
        history.append(entry); print(json.dumps(entry),flush=True)
        if entry["validation_macro_f1"]>best_score:
            best_score=entry["validation_macro_f1"]; best_state={key:tensor.cpu().clone() for key,tensor in model.state_dict().items()}
    model.load_state_dict(best_state); model.to(device)
    val_logits,_=infer("validation")
    calibration=fit_temperature(val_logits,val_targets,split_name="validation")
    candidate_test,_=infer("test")
    base_calibration=fit_temperature(base_val,val_targets,split_name="validation")
    baseline=evaluate_logits(base_test,test_targets,labels,temperature=base_calibration["temperature"],split_name="test")
    candidate=evaluate_logits(candidate_test,test_targets,labels,temperature=calibration["temperature"],split_name="test")
    eligible=candidate["macro_f1"]>baseline["macro_f1"] and candidate["accuracy"]>=baseline["accuracy"]
    identifier="plantdoc-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output=CANDIDATES / identifier; output.mkdir(parents=True)
    torch.save(best_state,output / "state.pt")
    model.cpu().eval()
    probe=torch.from_numpy(preprocess_image(Image.open(WORK / "plantdoc" / datasets["test"].rows[0]["path"])))
    torch.onnx.export(model,probe,output / "model.onnx",input_names=["input"],output_names=["logits"],opset_version=17,
        dynamic_axes={"input":{0:"batch"},"logits":{0:"batch"}},dynamo=False)
    import onnxruntime as ort
    session=ort.InferenceSession(str(output / "model.onnx"),providers=["CPUExecutionProvider"])
    with torch.inference_mode(): expected=model(probe).numpy()
    actual=session.run(None,{"input":probe.numpy()})[0]
    parity=float(np.max(np.abs(actual-expected)))
    if parity>1e-4: raise ValueError("Exported ONNX does not match the selected PyTorch checkpoint.")
    write_json(output / "class_names.json",labels)
    report={"schema_version":1,"candidate_id":identifier,"created_at_utc":datetime.now(timezone.utc).isoformat(),
        "baseline":baseline,"baseline_uncalibrated":evaluate_logits(base_test,test_targets,labels,split_name="test"),
        "candidate":candidate,"temperature_fit":calibration,"baseline_temperature_fit":base_calibration,
        "history":history,"best_epoch":max(history,key=lambda x:x["validation_macro_f1"])["epoch"],
        "gate":{"eligible":eligible,"rule":"Held-out macro F1 improves and accuracy does not decrease; subset benchmark only, not field readiness.","automatic_actuation":False},
        "onnx_max_absolute_error":parity,"data_counts":manifest["counts"],"dataset_manifest_sha256":sha(WORK / "dataset-manifest.json"),
        "seed":seed,"device":str(device),"torch_version":torch.__version__,"method":"Classifier fine-tuning; feature backbone frozen; no test-based checkpoint selection",
        "limitations":LIMITATIONS}
    write_json(output / "report.json",report)
    artifact={"schema_version":1,"candidate_id":identifier,"base_repository":REPOSITORY,"base_revision":REVISION,
        "base_weights_sha256":WEIGHTS_SHA,"dataset_revision":DATA_REVISION,"temperature":calibration["temperature"],
        "files_sha256":{name:sha(output / name) for name in ("model.onnx","class_names.json","report.json")},
        "tested_classes":sorted(MAPPING.values()),"limitations":LIMITATIONS}
    write_json(output / "manifest.json",artifact)
    write_json(WORK / "latest-run.json",{"candidate_id":identifier,"report":str(output / "report.json"),"eligible":eligible})
    print(json.dumps({"candidate_id":identifier,"baseline_accuracy":baseline["accuracy"],"candidate_accuracy":candidate["accuracy"],"baseline_macro_f1":baseline["macro_f1"],"candidate_macro_f1":candidate["macro_f1"],"eligible":eligible,"onnx_max_absolute_error":parity}),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","train"])
    parser.add_argument("--epochs",type=int,default=5); parser.add_argument("--seed",type=int,default=42); parser.add_argument("--batch-size",type=int,default=16)
    args=parser.parse_args()
    if args.action=="prepare": prepare(args.seed)
    else: train(args.epochs,args.seed,args.batch_size)


if __name__=="__main__": main()
