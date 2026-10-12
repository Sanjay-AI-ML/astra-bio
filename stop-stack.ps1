$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m astra_bio.mqtt_runtime stop
    if ($LASTEXITCODE -ne 0) { throw 'Could not request stack shutdown.' }
} finally { Pop-Location }
