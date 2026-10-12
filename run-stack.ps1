param([switch]$NoApp)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $mqttArgs = @('-m', 'astra_bio.mqtt_runtime', 'run')
    if ($NoApp) { $mqttArgs += '--no-app' }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') @mqttArgs
    if ($LASTEXITCODE -ne 0) { throw 'Stack stopped with an error; inspect runtime/mqtt/logs.' }
} finally { Pop-Location }
