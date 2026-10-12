param([string]$LanHost = '', [string]$DeviceId = 'tray-01')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot 'scripts\install_mqtt.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'MQTT runtime extraction failed.' }
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 to create the Python environment first.' }
    & $pythonPath -c 'import paho.mqtt.client, cryptography'
    if ($LASTEXITCODE -ne 0) { throw 'Run uv sync to install the MQTT Python dependencies.' }
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $nodeCommand) { throw 'Node.js 24 is required for the local collector.' }
    $nodeEntry = Join-Path $PSScriptRoot 'runtime\node-red\node_modules\node-red\red.js'
    if (-not (Test-Path -LiteralPath $nodeEntry)) {
        $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npmCommand) { throw 'npm is required to install the pinned collector dependencies.' }
        & $npmCommand.Source ci --prefix (Join-Path $PSScriptRoot 'runtime\node-red')
        if ($LASTEXITCODE -ne 0) { throw 'Node-RED dependency installation failed.' }
    }
    $mqttArgs = @('-m', 'astra_bio.mqtt_runtime', 'setup', '--device-id', $DeviceId)
    if ($LanHost) { $mqttArgs += @('--lan-host', $LanHost) }
    & $pythonPath @mqttArgs
    if ($LASTEXITCODE -ne 0) { throw 'MQTT configuration failed.' }
} finally { Pop-Location }
