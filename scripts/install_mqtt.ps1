param()

# Workspace-only binary extraction. No vendor installer, MSI actions, Windows
# service registration, registry writes, or firewall changes are executed.
$ErrorActionPreference = 'Stop'
$astraProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$astraRuntimeRoot = Join-Path $astraProjectRoot 'runtime\mqtt'
$astraDownloads = Join-Path $astraRuntimeRoot 'downloads'
$astraTools = Join-Path $astraRuntimeRoot 'tools'
$astraBin = Join-Path $astraRuntimeRoot 'bin'
$astraMosquittoUrl = 'https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe'
$astraSevenZipUrl = 'https://github.com/ip7z/7zip/releases/download/26.04/7z2604-x64.msi'
foreach ($astraDirectory in @($astraDownloads, $astraTools, $astraBin)) {
    New-Item -ItemType Directory -Path $astraDirectory -Force | Out-Null
}

if (-not ('AstraBioMsiArchive' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

// Read-only MSI database access and embedded-CAB extraction. The Windows
// Installer engine is never asked to install, advertise, or execute actions.
public static class AstraBioMsiArchive {
    public sealed class Row { public string[] Values; }
    [DllImport("msi.dll", CharSet=CharSet.Unicode, EntryPoint="MsiOpenDatabaseW")]
    static extern uint Open(string path, IntPtr persist, out uint database);
    [DllImport("msi.dll", CharSet=CharSet.Unicode, EntryPoint="MsiDatabaseOpenViewW")]
    static extern uint View(uint database, string query, out uint view);
    [DllImport("msi.dll", EntryPoint="MsiViewExecute")]
    static extern uint Execute(uint view, uint record);
    [DllImport("msi.dll", EntryPoint="MsiViewFetch")]
    static extern uint Fetch(uint view, out uint record);
    [DllImport("msi.dll", EntryPoint="MsiRecordGetFieldCount")]
    static extern uint Fields(uint record);
    [DllImport("msi.dll", CharSet=CharSet.Unicode, EntryPoint="MsiRecordGetStringW")]
    static extern uint GetString(uint record, uint field, StringBuilder value, ref uint length);
    [DllImport("msi.dll", EntryPoint="MsiRecordReadStream")]
    static extern uint ReadStream(uint record, uint field, byte[] data, ref uint length);
    [DllImport("msi.dll", EntryPoint="MsiCloseHandle")]
    static extern uint Close(uint handle);

    static void Check(uint code, string operation) {
        if (code != 0) throw new InvalidOperationException(operation + " failed: Windows Installer code " + code);
    }
    static string Text(uint record, uint field) {
        uint length = 2048;
        var value = new StringBuilder((int)length);
        uint result = GetString(record, field, value, ref length);
        if (result == 234) {
            value = new StringBuilder((int)length + 1); length++;
            result = GetString(record, field, value, ref length);
        }
        Check(result, "Read MSI field");
        return value.ToString();
    }
    public static List<Row> Query(string path, string query) {
        uint database=0, view=0, record=0;
        var rows = new List<Row>();
        try {
            Check(Open(path, IntPtr.Zero, out database), "Open read-only MSI");
            Check(View(database, query, out view), "Open MSI query");
            Check(Execute(view, 0), "Execute read-only MSI query");
            while (true) {
                uint result = Fetch(view, out record);
                if (result == 259) break;
                Check(result, "Fetch MSI row");
                var values = new string[Fields(record)];
                for (uint index=1; index <= values.Length; index++) values[index-1] = Text(record, index);
                rows.Add(new Row { Values = values });
                Close(record); record=0;
            }
            return rows;
        } finally {
            if (record != 0) Close(record);
            if (view != 0) Close(view);
            if (database != 0) Close(database);
        }
    }
    public static void ExtractStream(string path, string streamName, string output) {
        uint database=0, view=0, record=0;
        try {
            Check(Open(path, IntPtr.Zero, out database), "Open read-only MSI");
            string escaped = streamName.Replace("'", "''");
            Check(View(database, "SELECT `Data` FROM `_Streams` WHERE `Name`='" + escaped + "'", out view), "Open CAB stream query");
            Check(Execute(view, 0), "Execute CAB stream query");
            Check(Fetch(view, out record), "Fetch embedded CAB");
            using (var file = new FileStream(output, FileMode.Create, FileAccess.Write, FileShare.None)) {
                var bytes = new byte[65536];
                while (true) {
                    uint length = (uint)bytes.Length;
                    Check(ReadStream(record, 1, bytes, ref length), "Read embedded CAB");
                    if (length == 0) break;
                    file.Write(bytes, 0, (int)length);
                }
            }
        } finally {
            if (record != 0) Close(record);
            if (view != 0) Close(view);
            if (database != 0) Close(database);
        }
    }
}
'@
}

function Get-AstraVendorDownload([string]$Url, [string]$Destination, [string]$ExpectedSha256) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Write-Host ('Downloading official vendor artifact: ' + [IO.Path]::GetFileName($Destination))
        $astraPartialDownload = $Destination + '.part'
        Invoke-WebRequest -Uri $Url -OutFile $astraPartialDownload -TimeoutSec 180
        if ((Get-FileHash -LiteralPath $astraPartialDownload -Algorithm SHA256).Hash -ne $ExpectedSha256) {
            throw ('Vendor artifact does not match the recorded, pinned SHA256: ' + $Destination)
        }
        Move-Item -LiteralPath $astraPartialDownload -Destination $Destination -Force
    }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $ExpectedSha256) {
        throw ('Cached vendor artifact does not match the recorded, pinned SHA256: ' + $Destination)
    }
}

$astraSevenMsi = Join-Path $astraDownloads '7z2604-x64.msi'
$astraMosquittoInstaller = Join-Path $astraDownloads 'mosquitto-2.1.2-install-windows-x64.exe'
# Hashes pin the artifacts first downloaded from these official HTTPS endpoints.
# They are local provenance records, not independently published vendor hashes.
Get-AstraVendorDownload $astraSevenZipUrl $astraSevenMsi '0B01334A418654293513449F61D6BFC99E5196CA371E3C3DC961EDA57CD535C6'
Get-AstraVendorDownload $astraMosquittoUrl $astraMosquittoInstaller '58008AD7A22ADA0B4073AFA415801746E027C5F583E4FA52D0F4E9193B98D6AA'

$astraSevenExtract = Join-Path $astraTools '7zip-26.04'
$astraCabExtract = Join-Path $astraTools '7zip-cab-files'
New-Item -ItemType Directory -Path $astraSevenExtract, $astraCabExtract -Force | Out-Null
$astraFiles = [AstraBioMsiArchive]::Query($astraSevenMsi, 'SELECT `File`, `FileName` FROM `File`')
$astraAdminSequence = [AstraBioMsiArchive]::Query($astraSevenMsi, 'SELECT `Action`, `Condition`, `Sequence` FROM `AdminExecuteSequence`')
$astraMedia = [AstraBioMsiArchive]::Query($astraSevenMsi, 'SELECT `Cabinet` FROM `Media`')
$astraCabCount = 0
foreach ($astraMediaRow in $astraMedia) {
    $astraCabName = $astraMediaRow.Values[0]
    if (-not $astraCabName.StartsWith('#')) { throw 'Expected an embedded vendor CAB; external CAB downloads are not supported.' }
    $astraCabPath = Join-Path $astraTools ('7zip-' + $astraCabCount + '.cab')
    [AstraBioMsiArchive]::ExtractStream($astraSevenMsi, $astraCabName.Substring(1), $astraCabPath)
    & "$env:SystemRoot\System32\expand.exe" '-F:*' $astraCabPath $astraCabExtract | Out-Null
    if ($LASTEXITCODE -ne 0) { throw ('Embedded CAB extraction failed: ' + $LASTEXITCODE) }
    $astraCabCount++
}
if ($astraCabCount -eq 0) { throw 'No embedded CAB was found in the official 7-Zip MSI.' }
foreach ($astraFileRow in $astraFiles) {
    $astraFileId = $astraFileRow.Values[0]
    $astraFileName = ($astraFileRow.Values[1] -split '\|')[-1]
    if ([IO.Path]::GetFileName($astraFileName) -ne $astraFileName) { throw 'Invalid path in vendor File table.' }
    $astraFileSource = Join-Path $astraCabExtract $astraFileId
    if (-not (Test-Path -LiteralPath $astraFileSource)) { $astraFileSource = Join-Path $astraCabExtract $astraFileName }
    if (Test-Path -LiteralPath $astraFileSource) {
        Copy-Item -LiteralPath $astraFileSource -Destination (Join-Path $astraSevenExtract $astraFileName) -Force
    }
}
$astraSevenExe = Join-Path $astraSevenExtract '7z.exe'
if (-not (Test-Path -LiteralPath $astraSevenExe) -or -not (Test-Path -LiteralPath (Join-Path $astraSevenExtract '7z.dll'))) {
    throw 'The MSI CAB did not yield full 7z.exe and 7z.dll.'
}

$astraMosquittoExtract = Join-Path $astraRuntimeRoot 'vendor-payload'
New-Item -ItemType Directory -Path $astraMosquittoExtract -Force | Out-Null
& $astraSevenExe 'x' $astraMosquittoInstaller ('-o' + $astraMosquittoExtract) '-y' | Out-Null
if ($LASTEXITCODE -ne 0) { throw ('NSIS payload extraction failed: ' + $LASTEXITCODE) }
$astraBrokerFile = Get-ChildItem -LiteralPath $astraMosquittoExtract -File -Recurse -Filter 'mosquitto.exe' | Select-Object -First 1
if ($null -eq $astraBrokerFile) { throw 'mosquitto.exe is missing from the vendor payload.' }
foreach ($astraVendorFile in (Get-ChildItem -LiteralPath $astraBrokerFile.DirectoryName -File)) {
    # Keep installer utilities in the complete preserved vendor payload, rather
    # than presenting them alongside the runnable broker and client tools.
    if ($astraVendorFile.Name -in @('Uninstall.exe', 'vc_redist.x64.exe')) { continue }
    Copy-Item -LiteralPath $astraVendorFile.FullName -Destination (Join-Path $astraBin $astraVendorFile.Name) -Force
}
foreach ($astraRequired in @('mosquitto.exe', 'mosquitto_passwd.exe', 'mosquitto_pub.exe', 'mosquitto_sub.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $astraBin $astraRequired))) { throw ('Missing runtime binary: ' + $astraRequired) }
}

$astraHelp = & (Join-Path $astraBin 'mosquitto.exe') '-h' 2>&1 | Out-String
if ($astraHelp -notmatch 'mosquitto version 2\.1\.2') { throw 'Extracted broker version could not be verified. Check that the Visual C++ runtime is already available.' }
# Validate against a throwaway local-only config without opening a listener.
$astraTestConfig = Join-Path $astraRuntimeRoot 'extraction-test.conf'
@('listener 1883 127.0.0.1', 'allow_anonymous false', 'persistence false') | Set-Content -LiteralPath $astraTestConfig -Encoding utf8
& (Join-Path $astraBin 'mosquitto.exe') '-c' $astraTestConfig '--test-config'
if ($LASTEXITCODE -ne 0) { throw ('Extracted broker config validation failed: ' + $LASTEXITCODE) }

$astraManifest = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString('o')
    extraction_method = 'Read-only MSI database embedded CAB extraction; full 7-Zip NSIS payload extraction. No vendor installer or MSI action executed.'
    downloads = @(
        [ordered]@{ name = '7-Zip'; version = '26.04'; url = $astraSevenZipUrl; sha256 = (Get-FileHash -LiteralPath $astraSevenMsi -Algorithm SHA256).Hash; source = 'https://www.7-zip.org/download.html' },
        [ordered]@{ name = 'Eclipse Mosquitto'; version = '2.1.2'; url = $astraMosquittoUrl; sha256 = (Get-FileHash -LiteralPath $astraMosquittoInstaller -Algorithm SHA256).Hash; source = 'https://mosquitto.org/download/' }
    )
    msi_admin_execute_sequence_inspected_but_not_executed = @($astraAdminSequence | ForEach-Object { [ordered]@{ action = $_.Values[0]; condition = $_.Values[1]; sequence = [int]$_.Values[2] } })
    binary_path = $astraBin
    broker_help_version_verified = $true
    broker_test_config_passed = $true
    binaries = @(Get-ChildItem -LiteralPath $astraBin -File | Where-Object { $_.Extension -in @('.exe', '.dll') } | ForEach-Object { [ordered]@{ name = $_.Name; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash } })
    licenses = @(Get-ChildItem -LiteralPath $astraMosquittoExtract, $astraSevenExtract -File -Recurse | Where-Object { $_.Name -match '^(NOTICE|LICENSE|COPYING|epl|edl|readme)' } | ForEach-Object { $_.FullName.Substring($astraRuntimeRoot.Length + 1) })
    provenance_note = 'SHA256 records these HTTPS-downloaded artifacts; it is a local integrity record, not an independently published vendor checksum.'
}
$astraManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $astraRuntimeRoot 'BINARY_PROVENANCE.json') -Encoding utf8
Write-Host ('Mosquitto 2.1.2 ready: ' + (Join-Path $astraBin 'mosquitto.exe'))
Write-Host 'Config validation passed. No broker listener or Windows service was started.'
