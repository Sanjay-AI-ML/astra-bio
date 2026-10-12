param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
if (-not $uvCommand) { throw 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ then retry.' }
Push-Location $appRoot
try {
    if ($PythonPath) {
        & $uvCommand.Source sync --locked --python $PythonPath
    } else {
        & $uvCommand.Source sync --locked --python 3.12
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & '.\.venv\Scripts\python.exe' -m astra_bio.telemetry
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize demo telemetry.' }
    & npm.cmd ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Install Node.js 24 first.' }
    & npm.cmd run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'React frontend build failed.' }
} finally { Pop-Location }
