param([string]$DeviceId = 'tray-01')
$ErrorActionPreference = 'Stop'
$astraMongoTestPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $astraMongoTestPython)) { throw 'Run setup.ps1 first.' }
Push-Location $PSScriptRoot
try {
    & $astraMongoTestPython -m astra_bio.mongo_runtime probe --device-id $DeviceId
    if ($LASTEXITCODE -ne 0) { throw 'MongoDB delivery check failed; review the message above.' }
} finally { Pop-Location }
