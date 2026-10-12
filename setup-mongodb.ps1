param([string]$DeviceId = 'tray-01', [string]$LanHost = '', [int]$Port = 8502)
$ErrorActionPreference = 'Stop'
$astraMongoPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $astraMongoPython)) { throw 'Run setup.ps1 first.' }
Push-Location $PSScriptRoot
try {
    $astraMongoArgs = @('-m', 'astra_bio.mongo_runtime', 'setup', '--device-id', $DeviceId, '--port', "$Port")
    if ($LanHost) { $astraMongoArgs += @('--lan-host', $LanHost) }
    & $astraMongoPython @astraMongoArgs
    if ($LASTEXITCODE -ne 0) { throw 'MongoDB setup failed; review the message above.' }
} finally { Pop-Location }
