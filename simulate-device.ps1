param([int]$Count = 1, [double]$Interval = 5, [switch]$Tls)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $mqttArgs = @('-m', 'astra_bio.mqtt_client', 'simulate', '--count', $Count, '--interval', $Interval)
    if ($Tls) { $mqttArgs += '--tls' }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') @mqttArgs
    if ($LASTEXITCODE -ne 0) { throw 'Simulator failed.' }
} finally { Pop-Location }
