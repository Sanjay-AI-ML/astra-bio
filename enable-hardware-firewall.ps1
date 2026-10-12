# Optional hardware setup step. Run once in elevated PowerShell when a board
# on the same private Wi-Fi network needs to reach this laptop.
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This hardware network step needs an elevated PowerShell terminal.'
}
$privateConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime\mqtt\credentials.json') -Raw | ConvertFrom-Json
$lanAddress = $privateConfig.lan_host
$ipConfig = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $lanAddress }
if (-not $ipConfig) { throw 'Configured IP changed; rerun setup-mqtt.ps1 -LanHost first.' }
$netProfile = Get-NetConnectionProfile -InterfaceIndex $ipConfig.InterfaceIndex
if ($netProfile.NetworkCategory -ne 'Private') { throw 'Hardware setup needs your trusted Wi-Fi network to use the Private profile.' }
$ruleName = 'ASTRA-BIO-Private-TLS-MQTT'
$brokerPath = Join-Path $PSScriptRoot 'runtime\mqtt\bin\mosquitto.exe'
$existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existingRule) { $existingRule | Remove-NetFirewallRule }
$ruleParams = @{
    Name = $ruleName; DisplayName = 'ASTRA-BIO MQTT TLS on private local subnet'
    Direction = 'Inbound'; Action = 'Allow'; Protocol = 'TCP'; LocalPort = 8883
    LocalAddress = $lanAddress; RemoteAddress = 'LocalSubnet'; Profile = 'Private'
    Program = $brokerPath
}
New-NetFirewallRule @ruleParams | Out-Null
Write-Output ('Allowed private local-subnet devices to reach TLS {0}:8883.' -f $lanAddress)
