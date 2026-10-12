param(
    [ValidateSet('Full','Download','Export','Status')][string]$Action = 'Full',
    [ValidateSet('tomato-ripeness-3','tomato-ripeness-6','tomato-detection','produce-detection')][string]$ModelId = ''
)
$ErrorActionPreference = 'Stop'
$astraFruitRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$astraFruitAppPython = Join-Path $astraFruitRoot '.venv\Scripts\python.exe'
$astraFruitExportPython = Join-Path $astraFruitRoot 'runtime\ml-training\.venv\Scripts\python.exe'
Push-Location $astraFruitRoot
try {
    if (-not (Test-Path -LiteralPath $astraFruitAppPython)) { throw 'Run setup.ps1 first.' }
    $astraFruitSelection = if ($ModelId) { @('--model-id', $ModelId) } else { @() }
    if ($Action -in @('Full','Export')) {
        if (-not (Test-Path -LiteralPath $astraFruitExportPython)) {
            & uv venv runtime/ml-training/.venv --python $astraFruitAppPython
            if ($LASTEXITCODE -ne 0) { throw 'Model export environment creation failed.' }
            & uv pip install --python $astraFruitExportPython torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
            if ($LASTEXITCODE -ne 0) { throw 'Official PyTorch installation failed.' }
        }
        & $astraFruitExportPython -c 'from importlib.metadata import version; assert version("torch").split("+")[0] == "2.14.1" and version("torchvision").split("+")[0] == "0.29.1", "Export requires torch 2.14.1 and torchvision 0.29.1; use the documented setup environment."'
        if ($LASTEXITCODE -ne 0) { throw 'Existing model export environment has different PyTorch versions; it was not overwritten.' }
        & uv pip install --python $astraFruitExportPython ultralytics==8.4.21 onnx==1.23.2 onnxruntime==1.31.0 Pillow==12.3.0 numpy==2.5.2
        if ($LASTEXITCODE -ne 0) { throw 'Pinned fruit export dependencies failed.' }
    }
    if ($Action -in @('Full','Download')) {
        & $astraFruitAppPython -m astra_bio.fruit_setup download @astraFruitSelection
        if ($LASTEXITCODE -ne 0) { throw 'Pinned fruit artifact download failed.' }
    }
    if ($Action -in @('Full','Export')) {
        & $astraFruitExportPython -m astra_bio.fruit_setup export @astraFruitSelection
        if ($LASTEXITCODE -ne 0) { throw 'Fruit export/label/integrity/parity check failed.' }
    }
    if ($Action -eq 'Status') {
        & $astraFruitAppPython -c 'import json; from astra_bio.fruit_vision import fruit_registry_status; print(json.dumps(fruit_registry_status(),indent=2))'
        if ($LASTEXITCODE -ne 0) { throw 'Fruit model status check failed.' }
    }
} finally { Pop-Location }
