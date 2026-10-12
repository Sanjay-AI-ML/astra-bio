$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$runtimeRoot = Join-Path $appRoot 'runtime\node-red'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $nodeCommand) { throw 'Node.js 24 is required for the local telemetry runtime.' }
$entry = Join-Path $runtimeRoot 'node_modules\node-red\red.js'
if (-not (Test-Path -LiteralPath $entry)) {
    throw 'Install telemetry dependencies with: npm ci --prefix .\runtime\node-red'
}
Push-Location $appRoot
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $appRoot 'data') | Out-Null
    & $nodeCommand.Source $entry --userDir (Join-Path $runtimeRoot 'userdir') --settings (Join-Path $runtimeRoot 'settings.js')
} finally { Pop-Location }
