param(
    [ValidatePattern('^[a-z][a-z0-9-]{0,39}$')][string]$DeviceId = 'tray-01',
    [ValidateSet('Validate', 'Build', 'Flash')][string]$Action = 'Validate'
)
$ErrorActionPreference = 'Stop'
$uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
if (-not $uvCommand) { throw 'Install uv, as described in README.md, before running the firmware helper.' }
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$configuration = Join-Path $PSScriptRoot ('runtime\hardware\{0}\tray.yaml' -f $DeviceId)
if (-not (Test-Path -LiteralPath $configuration)) { throw 'Provision this device first with provision-device.ps1.' }
$verb = switch ($Action) { 'Validate' { 'config' }; 'Build' { 'compile' }; 'Flash' { 'run' } }
Push-Location $PSScriptRoot
try {
    # Pinned tooling; quiet configuration prevents printing private credentials.
    & $uvCommand.Source tool run --python $pythonPath --from esphome==2026.9.1 esphome --quiet $verb $configuration
    if ($LASTEXITCODE -ne 0) { throw ('Firmware {0} failed.' -f $Action) }
    Write-Output ('Firmware {0} completed for {1}.' -f $Action, $DeviceId)
} finally { Pop-Location }
