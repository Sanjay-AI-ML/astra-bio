param(
    [ValidateSet('Setup','Prepare','Train','Full','Status','Activate','Base')][string]$Action = 'Full',
    [int]$Epochs = 5,
    [int]$BatchSize = 16,
    [string]$CandidateId = '',
    [switch]$CpuOnly
)
$ErrorActionPreference = 'Stop'
$astraTrainingRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$astraMlPython = Join-Path $astraTrainingRoot 'runtime\ml-training\.venv\Scripts\python.exe'
Push-Location $astraTrainingRoot
try {
    if ($Action -in @('Setup','Full')) {
        if (-not (Test-Path -LiteralPath $astraMlPython)) {
            & uv venv runtime/ml-training/.venv --python .venv/Scripts/python.exe
            if ($LASTEXITCODE -ne 0) { throw 'Training environment creation failed.' }
        }
        $astraTorchIndex = if ($CpuOnly) { 'https://download.pytorch.org/whl/cpu' } else { 'https://download.pytorch.org/whl/cu130' }
        & uv pip install --python $astraMlPython torch==2.14.1 torchvision==0.29.1 --index-url $astraTorchIndex
        if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
        & uv pip install --python $astraMlPython onnx==1.23.2 onnxruntime Pillow numpy
        if ($LASTEXITCODE -ne 0) { throw 'Training dependencies failed.' }
    }
    if ($Action -in @('Prepare','Full')) {
        & .\.venv\Scripts\python.exe -m astra_bio.plant_training prepare
        if ($LASTEXITCODE -ne 0) { throw 'Pinned dataset preparation or split audit failed.' }
    }
    if ($Action -in @('Train','Full')) {
        & $astraMlPython -m astra_bio.plant_training train --epochs $Epochs --batch-size $BatchSize
        if ($LASTEXITCODE -ne 0) { throw 'Training/evaluation/export failed. Existing active model remains selected.' }
    }
    if ($Action -eq 'Status') {
        & .\.venv\Scripts\python.exe -c 'import json; from astra_bio.plant_registry import registry_status; print(json.dumps(registry_status(),indent=2))'
    }
    if ($Action -in @('Activate','Base')) {
        if ($Action -eq 'Base') { $CandidateId = 'base' }
        if (-not $CandidateId) { throw 'Provide -CandidateId from the evaluation report.' }
        & .\.venv\Scripts\python.exe -c 'import json,sys; from astra_bio.plant_registry import select_model; print(json.dumps(select_model(sys.argv[1]),indent=2))' $CandidateId
        if ($LASTEXITCODE -ne 0) { throw 'Model selection failed its evaluation/integrity gate.' }
    }
} finally { Pop-Location }
