param([switch]$IncludeSample)
$ErrorActionPreference = 'Stop'
$astraRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $astraRoot
try {
    $astraArgs = @('-m', 'astra_bio.plant_vision', 'setup')
    if ($IncludeSample) { $astraArgs += '--sample' }
    & (Join-Path $astraRoot '.venv\Scripts\python.exe') @astraArgs
    if ($LASTEXITCODE -ne 0) { throw 'Plant model setup failed; no inference fallback fabricates predictions.' }
} finally { Pop-Location }
