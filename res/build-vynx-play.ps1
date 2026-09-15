param(
    [Parameter(Mandatory = $true)]
    [string]$RendezvousServer,

    [Parameter(Mandatory = $true)]
    [string]$RendezvousPublicKey,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0x)?[0-9A-Fa-f]{1,4}$')]
    [string]$UsbVid,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0x)?[0-9A-Fa-f]{1,4}$')]
    [string]$UsbPid,

    [string]$VcpkgRoot = 'C:\vcpkg'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$manifestPath = Join-Path $projectRoot 'Cargo.toml'

$vidValue = if ($UsbVid.StartsWith('0x', [System.StringComparison]::OrdinalIgnoreCase)) {
    [Convert]::ToUInt16($UsbVid.Substring(2), 16)
} else {
    [Convert]::ToUInt16($UsbVid, 10)
}
$pidValue = if ($UsbPid.StartsWith('0x', [System.StringComparison]::OrdinalIgnoreCase)) {
    [Convert]::ToUInt16($UsbPid.Substring(2), 16)
} else {
    [Convert]::ToUInt16($UsbPid, 10)
}
if ($vidValue -eq 0 -or $pidValue -eq 0) {
    throw 'Assigned, non-zero USB VID and PID values are required for a product build.'
}

if (-not (Test-Path -LiteralPath (Join-Path $VcpkgRoot 'installed'))) {
    throw "Vcpkg installation not found at $VcpkgRoot."
}

$env:VCPKG_ROOT = (Resolve-Path -LiteralPath $VcpkgRoot).Path
$env:VCPKGRS_DYNAMIC = '0'
$env:VYNXDESK_RENDEZVOUS_SERVER = $RendezvousServer
$env:VYNXDESK_RENDEZVOUS_PUB_KEY = $RendezvousPublicKey
$env:VYNX_INPUT_BRIDGE_VID = $UsbVid
$env:VYNX_INPUT_BRIDGE_PID = $UsbPid

cargo build --manifest-path $manifestPath --release --features vynx-play
if ($LASTEXITCODE -ne 0) {
    throw "VynxDesk Play build failed with exit code $LASTEXITCODE."
}

$binary = Join-Path $projectRoot 'target\release\rustdesk.exe'
if (-not (Test-Path -LiteralPath $binary)) {
    throw "Build completed but $binary was not produced."
}

Write-Host "VynxDesk Play binary ready: $binary"
