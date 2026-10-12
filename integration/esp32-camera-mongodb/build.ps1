# Compile only: this script never uploads firmware or opens a serial port.
$ErrorActionPreference = 'Stop'
$astraFirmwareRoot = $PSScriptRoot
$astraApplicationRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$astraCompilerPython = Join-Path $astraApplicationRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $astraCompilerPython)) { throw 'Run the application setup.ps1 first.' }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv from https://docs.astral.sh/uv/ first.' }
$astraLocalConfig = Join-Path $astraFirmwareRoot 'include\config.h'
if (-not (Test-Path -LiteralPath $astraLocalConfig)) {
    Copy-Item -LiteralPath (Join-Path $astraFirmwareRoot 'include\config.example.h') -Destination $astraLocalConfig
    Write-Host 'Using placeholder configuration for compile only. Copy the generated private device header before hardware use.'
}
$astraToolingRoot = Join-Path $astraApplicationRoot 'runtime\hardware\esp32-mongodb-tooling'
New-Item -ItemType Directory -Path $astraToolingRoot -Force | Out-Null
$astraActualCore = Join-Path $astraToolingRoot 'platformio-core'
New-Item -ItemType Directory -Path $astraActualCore -Force | Out-Null
# Old Xtensa GCC exceeds Windows subprocess command length limits when hundreds
# of framework include paths contain the full cache prefix. A short junction
# changes only the path used by the compiler; actual files stay in runtime/.
$astraShortCore = Join-Path (Split-Path -Parent $astraApplicationRoot) 'p'
if (Test-Path -LiteralPath $astraShortCore) {
    $astraExistingAlias = Get-Item -LiteralPath $astraShortCore -Force
    if ($astraExistingAlias.LinkType -ne 'Junction' -or
        @($astraExistingAlias.Target).Count -ne 1 -or
        [IO.Path]::GetFullPath([string]@($astraExistingAlias.Target)[0]) -ne [IO.Path]::GetFullPath($astraActualCore)) {
        throw "Toolchain alias $astraShortCore already exists and belongs to another path; it will not be changed."
    }
} else {
    New-Item -ItemType Junction -Path $astraShortCore -Value $astraActualCore | Out-Null
}
$astraToolTempRoot = Join-Path $astraToolingRoot 'tmp'
New-Item -ItemType Directory -Path $astraToolTempRoot -Force | Out-Null
$astraBuildVariables = @{
    UV_CACHE_DIR = Join-Path $astraToolingRoot 'uv-cache'
    UV_TOOL_DIR = Join-Path $astraToolingRoot 'uv-tools'
    UV_TOOL_BIN_DIR = Join-Path $astraToolingRoot 'uv-bin'
    UV_PYTHON_DOWNLOADS = 'never'
    PIP_CACHE_DIR = Join-Path $astraToolingRoot 'pip-cache'
    PIP_INDEX_URL = 'https://pypi.org/simple'
    TEMP = $astraToolTempRoot
    TMP = $astraToolTempRoot
    PLATFORMIO_CORE_DIR = $astraShortCore
    PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'No'
}
$astraPreviousVariables = @{}
try {
    foreach ($astraBuildVariable in $astraBuildVariables.Keys) {
        $astraPreviousVariables[$astraBuildVariable] = [Environment]::GetEnvironmentVariable($astraBuildVariable, 'Process')
        [Environment]::SetEnvironmentVariable($astraBuildVariable, $astraBuildVariables[$astraBuildVariable], 'Process')
    }
    & uv tool run --python $astraCompilerPython --from platformio==6.2.0 --index-url https://pypi.org/simple pio run --project-dir $astraFirmwareRoot
    if ($LASTEXITCODE -ne 0) { throw 'ESP32-S3 compile failed. Review the compiler output above.' }
} finally {
    foreach ($astraBuildVariable in $astraPreviousVariables.Keys) {
        [Environment]::SetEnvironmentVariable($astraBuildVariable, $astraPreviousVariables[$astraBuildVariable], 'Process')
    }
}
