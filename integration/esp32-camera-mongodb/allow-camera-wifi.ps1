param(
    [Parameter(Mandatory = $true)][string]$DeviceIp,
    [Parameter(Mandatory = $true)][string]$LaptopIp,
    [ValidateRange(1024,65535)][int]$Port = 8502,
    [ValidateSet('Public','Private','Domain')][string]$Profile = 'Public'
)
$ErrorActionPreference = 'Stop'
function Test-AstraLan([string]$Address) {
    $astraParsedAddress = [Net.IPAddress]::Parse($Address)
    if ($astraParsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $astraOctets = $astraParsedAddress.GetAddressBytes()
    return $astraOctets[0] -eq 10 -or ($astraOctets[0] -eq 172 -and $astraOctets[1] -ge 16 -and $astraOctets[1] -le 31) -or ($astraOctets[0] -eq 192 -and $astraOctets[1] -eq 168)
}
if (-not (Test-AstraLan $DeviceIp) -or -not (Test-AstraLan $LaptopIp) -or $DeviceIp -eq $LaptopIp) {
    throw 'Specify distinct private IPv4 addresses for this camera and laptop.'
}
$astraLocalInterface = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $LaptopIp)
if ($astraLocalInterface.Count -ne 1) { throw 'LaptopIp must match exactly one current laptop interface.' }
$astraIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$astraPrincipal = [Security.Principal.WindowsPrincipal]::new($astraIdentity)
if (-not $astraPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an Administrator PowerShell window to add the scoped camera rule.'
}
$astraRuleName = 'ASTRA-BIO-Camera-' + $Port + '-' + $DeviceIp.Replace('.','-')
if (Get-NetFirewallRule -Name $astraRuleName -ErrorAction SilentlyContinue) {
    throw 'This camera rule already exists. Inspect it rather than changing an existing rule automatically.'
}
New-NetFirewallRule -Name $astraRuleName -DisplayName "ASTRA-BIO camera HTTPS ($DeviceIp)" -Group 'ASTRA-BIO camera' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -LocalAddress $LaptopIp -RemoteAddress $DeviceIp -InterfaceAlias $astraLocalInterface[0].InterfaceAlias -Profile $Profile | Out-Null
Write-Host "Allowed only $DeviceIp to reach HTTPS TCP port $Port at $LaptopIp on the $Profile profile."
Write-Host "To remove this rule: Remove-NetFirewallRule -Name '$astraRuleName'"
