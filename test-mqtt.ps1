param([switch]$Tls)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $mqttArgs = @('-m', 'astra_bio.mqtt_client', 'check')
    if ($Tls) { $mqttArgs += '--tls' }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') @mqttArgs
    if ($LASTEXITCODE -ne 0) { throw 'MQTT verification failed.' }
} finally { Pop-Location }
