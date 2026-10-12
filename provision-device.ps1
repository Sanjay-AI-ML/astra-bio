param([Parameter(Mandatory = $true)][string]$DeviceId)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m astra_bio.mqtt_runtime provision $DeviceId
    if ($LASTEXITCODE -ne 0) { throw 'Device provisioning failed.' }
} finally { Pop-Location }
