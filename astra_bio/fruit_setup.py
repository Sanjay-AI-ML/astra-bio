"""Explicit, pinned fruit artifact setup/export. Never imported by inference."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / 'runtime/fruit-models'
CATALOG = {
    'tomato-ripeness-3': {'name': 'Tomato maturity · three stages', 'repo': 'pablofntdz/yolov8-tomato-detection', 'revision': '244eb93615708602716b57f2d09da479e2d899d4', 'file': 'model_hub_n.pt', 'source_sha256': '3a224cb79efb76d041995b07beae69d663f36b3d46356dcd5fa7cc2b64a43d40', 'species': ['tomato'], 'size': 640, 'license_declared': 'MIT (publisher declaration)', 'capability': 'visual_maturity'},
    'tomato-ripeness-6': {'name': 'Tomato maturity · six stages', 'repo': 'afeefaazam/tomato-ripeness-detector', 'revision': '318c3e91578a748fa7020da80cbef00a357002e3', 'file': 'model.pt', 'source_sha256': '5104214ad969156b2173b01f63f3923bcbe4b86d42d9aed51cfa736a7864ef90', 'species': ['tomato'], 'size': 1024, 'license_declared': 'MIT (publisher declaration)', 'capability': 'visual_maturity'},
    'tomato-detection': {'name': 'Tomato detection · count only', 'repo': 'AitorConS/tomatoACLv1', 'revision': 'a228d44bdf24306cedec6d433da093242c4fb05d', 'file': 'tomatoACLv1.onnx', 'source_sha256': '993908fcb60285115a53a9f5e4a47d0bbe6e1ca312c17ca6e5a493ca3a7514bd', 'species': ['tomato'], 'size': 960, 'license_declared': 'MIT (publisher declaration; artifact declares AGPL-3.0)', 'capability': 'detection_only'},
    'produce-detection': {'name': 'Produce detection · tomato, pepper, potato', 'repo': 'Piyu12/fruit-veg-yolo11m-detector', 'revision': '82c9865261175e778ba5641cf8560b5d10439ec6', 'file': 'best.pt', 'source_sha256': '499ccee2169731363de26146d9989942c27f3849f64509e0b5190cbd1c679c19', 'species': ['tomato', 'bell pepper', 'potato'], 'size': 640, 'license_declared': 'AGPL-3.0', 'capability': 'detection_only'},
}
REVIEWED_GLOBALS = {
    'collections.OrderedDict', 'builtins.set', 'ultralytics.utils.IterableSimpleNamespace',
    'ultralytics.utils.loss.v8DetectionLoss', 'ultralytics.utils.loss.BboxLoss',
    'ultralytics.utils.tal.TaskAlignedAssigner', 'ultralytics.nn.tasks.DetectionModel',
    *('torch.nn.modules.' + name for name in ('container.ModuleList', 'container.Sequential',
        'loss.BCEWithLogitsLoss', 'batchnorm.BatchNorm2d', 'upsampling.Upsample',
        'conv.Conv2d', 'pooling.MaxPool2d', 'activation.SiLU', 'linear.Identity')),
    *('ultralytics.nn.modules.' + name for name in ('conv.Concat', 'conv.Conv', 'conv.DWConv',
        'head.Detect', 'block.C2f', 'block.SPPF', 'block.DFL', 'block.Bottleneck',
        'block.C2PSA', 'block.C3k2', 'block.Attention', 'block.C3k', 'block.PSABlock')),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(model_id: str) -> None:
    spec = CATALOG[model_id]
    directory = MODEL_ROOT / model_id
    directory.mkdir(parents=True, exist_ok=True)
    for filename, expected in ((spec['file'], spec['source_sha256']), ('README.md', None)):
        target = directory / (filename if filename != 'README.md' else 'MODEL_CARD.md')
        if expected and target.exists() and digest(target) == expected:
            continue
        temporary = target.with_suffix(target.suffix + '.download')
        try:
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{filename}"
            with urlopen(Request(url, headers={'User-Agent': 'ASTRA-BIO explicit model setup'}), timeout=90) as response, temporary.open('wb') as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 150 * 1024 * 1024:
                        raise ValueError('Artifact exceeds the pinned setup size limit.')
                    output.write(chunk)
            if expected and digest(temporary) != expected:
                raise ValueError('Downloaded artifact does not match its pinned SHA256.')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    (directory / 'source-metadata.json').write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    print(f'{model_id}: pinned download verified.', flush=True)


def _safe_checkpoint(path: Path):
    """Reject unknown pickle globals; allow only reviewed framework classes."""
    import collections
    import torch
    from ultralytics.utils import IterableSimpleNamespace
    from ultralytics.utils.loss import v8DetectionLoss
    allowed = [collections.OrderedDict, set, IterableSimpleNamespace, v8DetectionLoss]
    for name in torch.serialization.get_unsafe_globals_in_checkpoint(path):
        if name not in REVIEWED_GLOBALS:
            raise ValueError(f'Unreviewed checkpoint global: {name}')
        if name in {'collections.OrderedDict', 'builtins.set'}:
            continue
        module, _, attribute = name.rpartition('.')
        if not module.startswith(('torch.nn.modules.', 'ultralytics.nn.', 'ultralytics.utils.loss', 'ultralytics.utils.tal')):
            if name == 'ultralytics.utils.IterableSimpleNamespace':
                continue
            raise ValueError(f'Unreviewed checkpoint global: {name}')
        value = getattr(importlib.import_module(module), attribute)
        if not isinstance(value, type) or (not issubclass(value, torch.nn.Module) and value is not v8DetectionLoss):
            raise ValueError(f'Checkpoint global is not an allowed framework class: {name}')
        allowed.append(value)
    with torch.serialization.safe_globals(allowed):
        return torch.load(path, map_location='cpu', weights_only=True)


def export(model_id: str) -> None:
    spec = CATALOG[model_id]
    directory = MODEL_ROOT / model_id
    source = directory / spec['file']
    if not source.exists() or digest(source) != spec['source_sha256']:
        raise ValueError('Run pinned download first; source artifact integrity failed.')
    target = directory / 'model.onnx'
    parity = None
    if source.suffix == '.onnx':
        shutil.copyfile(source, target)
    else:
        import numpy as np
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(2)
        checkpoint = _safe_checkpoint(source)
        model = checkpoint.get('ema')
        if model is None:
            model = checkpoint.get('model')
        if not isinstance(model, torch.nn.Module):
            raise ValueError('Checkpoint contains no supported detection network.')
        model = model.cpu().float().eval()
        model.task = 'detect'
        if not isinstance(model.args, dict):
            model.args = vars(model.args).copy()
        runner = YOLO('yolov8n.yaml' if model_id == 'tomato-ripeness-3' else 'yolo11n.yaml')
        runner.model = model
        runner.task = 'detect'
        runner.overrides = {'task': 'detect', 'imgsz': spec['size'], 'device': 'cpu'}
        runner.model.pt_path = str(source)
        path = runner.export(format='onnx', imgsz=spec['size'], opset=17, dynamic=False, simplify=False, nms=False, device='cpu', batch=1)
        if Path(path).resolve() != target.resolve():
            shutil.copyfile(path, target)
        import onnxruntime as ort
        session = ort.InferenceSession(target.read_bytes(), providers=['CPUExecutionProvider'])
        probe = np.random.default_rng(42).random((1, 3, spec['size'], spec['size']), dtype=np.float32)
        # Exported models switch the detection head into tensor-output mode.
        with torch.inference_mode():
            expected = model(torch.from_numpy(probe))
        if isinstance(expected, (tuple, list)):
            expected = expected[0]
        predicted = session.run(None, {session.get_inputs()[0].name: probe})[0]
        reference = expected.detach().cpu().numpy()
        parity = {'probe': 'seeded numerical tensor; not biological accuracy', 'maximum_absolute_error': float(np.max(np.abs(reference - predicted))), 'passed': bool(np.allclose(reference, predicted, rtol=2e-3, atol=2e-2))}
        if not parity['passed']:
            raise ValueError('Exported detector failed numerical parity.')
    import onnxruntime as ort
    session = ort.InferenceSession(target.read_bytes(), providers=['CPUExecutionProvider'])
    metadata = session.get_modelmeta().custom_metadata_map
    names = ast.literal_eval(metadata['names'])
    labels = [names[i] for i in range(len(names))] if isinstance(names, dict) else list(names)
    shape = session.get_inputs()[0].shape
    if shape != [1, 3, spec['size'], spec['size']] or session.get_inputs()[0].type != 'tensor(float)':
        raise ValueError('Unexpected detector input signature.')
    manifest = {'schema_version': 1, 'id': model_id, 'name': spec['name'], 'task': 'detect', 'capability': spec['capability'], 'species': spec['species'], 'labels': labels, 'input_size': shape[2:], 'sha256': digest(target), 'source_sha256': spec['source_sha256'], 'source_url': 'https://huggingface.co/' + spec['repo'], 'revision': spec['revision'], 'license_declared': spec['license_declared'], 'artifact_license': metadata.get('license', 'not specified'), 'framework_license': 'Ultralytics AGPL-3.0 / Enterprise; review upstream terms', 'validation': 'Public checkpoint; no ASTRA-BIO tray benchmark', 'export_parity': parity}
    manifest['export_environment'] = {package: version(package) for package in ('torch', 'torchvision', 'ultralytics', 'onnx', 'onnxruntime', 'numpy', 'Pillow')}
    manifest['preprocessing'] = 'Pillow RGB bilinear square letterbox, fill 114, float32 NCHW /255; numerical export parity checks tensors, not image-path parity'
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'id': model_id, 'labels': labels, 'input_size': shape[2:], 'sha256': manifest['sha256'], 'export_parity': parity}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('download', 'export'))
    parser.add_argument('--model-id', choices=tuple(CATALOG))
    args = parser.parse_args()
    for model_id in ([args.model_id] if args.model_id else CATALOG):
        (download if args.action == 'download' else export)(model_id)


if __name__ == '__main__':
    (MODEL_ROOT / 'tool-settings').mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(MODEL_ROOT / 'tool-settings'))
    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
    main()
