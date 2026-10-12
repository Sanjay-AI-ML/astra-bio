$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$appPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $appPython)) {
    throw 'Run .\setup.ps1 first to install the Python environment.'
}
Push-Location $appRoot
try {
    & $appPython -m astra_bio.telemetry
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize demo telemetry.' }
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot 'frontend\dist\index.html'))) {
        & npm.cmd ci --prefix frontend
        if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
        & npm.cmd run build --prefix frontend
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    & $appPython -m uvicorn astra_bio.api:app --host 127.0.0.1 --port 8501
    if ($LASTEXITCODE -ne 0) { throw 'The ASTRA-BIO API stopped with an error.' }
} finally { Pop-Location }
