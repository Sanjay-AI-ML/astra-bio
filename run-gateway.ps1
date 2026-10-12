$ErrorActionPreference = 'Stop'
$astraGatewayPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $astraGatewayPython)) { throw 'Run setup.ps1 first.' }
Push-Location $PSScriptRoot
try {
    & $astraGatewayPython -m astra_bio.mongo_runtime run
    if ($LASTEXITCODE -ne 0) { throw 'Telemetry gateway stopped with an error.' }
} finally { Pop-Location }
