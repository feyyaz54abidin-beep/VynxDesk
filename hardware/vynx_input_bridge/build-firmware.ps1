param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0x)?[0-9A-Fa-f]{1,4}$')]
    [string]$UsbVid,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0x)?[0-9A-Fa-f]{1,4}$')]
    [string]$UsbPid,

    [string]$PicoSdkPath = $env:PICO_SDK_PATH,
    [string]$Board = 'pico'
)

$ErrorActionPreference = 'Stop'
$firmwareRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildRoot = Join-Path $firmwareRoot 'build'

if ([string]::IsNullOrWhiteSpace($PicoSdkPath) -or
    -not (Test-Path -LiteralPath (Join-Path $PicoSdkPath 'external\pico_sdk_import.cmake'))) {
    throw 'Pico SDK not found. Pass -PicoSdkPath or set PICO_SDK_PATH.'
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw 'CMake is required to build the bridge firmware.'
}

$env:PICO_SDK_PATH = (Resolve-Path -LiteralPath $PicoSdkPath).Path
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

$generatorArgs = @()
if (Get-Command ninja -ErrorAction SilentlyContinue) {
    $generatorArgs = @('-G', 'Ninja')
}

cmake @generatorArgs -S $firmwareRoot -B $buildRoot `
    "-DPICO_BOARD=$Board" `
    "-DVYNX_USB_VID=$UsbVid" `
    "-DVYNX_USB_PID=$UsbPid"
if ($LASTEXITCODE -ne 0) {
    throw "Firmware configure failed with exit code $LASTEXITCODE."
}

cmake --build $buildRoot --config Release
if ($LASTEXITCODE -ne 0) {
    throw "Firmware build failed with exit code $LASTEXITCODE."
}

$uf2 = Join-Path $buildRoot 'vynx_input_bridge.uf2'
if (-not (Test-Path -LiteralPath $uf2)) {
    throw "Firmware build completed but $uf2 was not produced."
}

Write-Host "Firmware ready: $uf2"
