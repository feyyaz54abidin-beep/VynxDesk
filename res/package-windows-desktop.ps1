[CmdletBinding()]
param(
    [string]$BuildDirectory = "",
    [string]$OutputDirectory = "",
    [switch]$AllowUnsigned,
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($BuildDirectory)) {
    $BuildDirectory = Join-Path $projectRoot "flutter\build\windows\x64\runner\Release"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
    $OutputDirectory = Join-Path $projectRoot "dist\vynxdesk-windows-x64-$stamp"
}

$buildRoot = [System.IO.Path]::GetFullPath($BuildDirectory)
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$distRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "dist"))
$distPrefix = $distRoot.TrimEnd('\') + '\'

if (-not $outputRoot.StartsWith($distPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must be inside $distRoot"
}
if (-not (Test-Path -LiteralPath $buildRoot -PathType Container)) {
    throw "Windows release directory was not found: $buildRoot"
}
if (Test-Path -LiteralPath $outputRoot) {
    throw "Output directory already exists: $outputRoot"
}

$requiredBuildItems = @(
    "vynxdesk.exe",
    "flutter_windows.dll",
    "data\flutter_assets"
)
foreach ($item in $requiredBuildItems) {
    $path = Join-Path $buildRoot $item
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required desktop runtime item is missing: $path"
    }
}

$virtualDisplayCandidates = @(
    (Join-Path $buildRoot "dylib_virtual_display.dll"),
    (Join-Path $projectRoot "target\release\dylib_virtual_display.dll"),
    (Join-Path $projectRoot "target\release\deps\dylib_virtual_display.dll")
)
$virtualDisplayDll = $virtualDisplayCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $virtualDisplayDll) {
    throw "Headless support is incomplete: dylib_virtual_display.dll was not built. Build libs/virtual_display/dylib first."
}

$null = New-Item -ItemType Directory -Path $outputRoot
Copy-Item -Path (Join-Path $buildRoot "*") -Destination $outputRoot -Recurse -Force
Copy-Item -LiteralPath $virtualDisplayDll -Destination (Join-Path $outputRoot "dylib_virtual_display.dll") -Force

$distributionFiles = @(
    "LICENCE",
    "NOTICE",
    "PRIVACY.md",
    "res\install-vynxdesk.ps1"
)
foreach ($relativePath in $distributionFiles) {
    $source = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required distribution file is missing: $source"
    }
    $destination = Join-Path $outputRoot (Split-Path -Leaf $relativePath)
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$binaryFiles = Get-ChildItem -LiteralPath $outputRoot -File -Recurse |
    Where-Object { $_.Extension -in @(".exe", ".dll") }
$untrusted = @()
foreach ($file in $binaryFiles) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        $untrusted += [PSCustomObject]@{
            File = $file.FullName.Substring($outputRoot.Length + 1)
            Status = [string]$signature.Status
        }
    }
}
if ($untrusted.Count -gt 0 -and -not $AllowUnsigned) {
    $details = ($untrusted | ForEach-Object { "$($_.File): $($_.Status)" }) -join [Environment]::NewLine
    throw "Unsigned or untrusted binaries cannot be released:`n$details"
}

$exe = Get-Item -LiteralPath (Join-Path $outputRoot "vynxdesk.exe")
$metadata = [ordered]@{
    product = "VynxDesk"
    version = $exe.VersionInfo.ProductVersion
    website = "https://vynx.com.tr"
    platform = "windows"
    architecture = "x64"
    created_utc = [DateTime]::UtcNow.ToString("o")
    headless_runtime_included = $true
    all_binary_signatures_valid = ($untrusted.Count -eq 0)
    distribution_trust = if ($untrusted.Count -eq 0) { "signed" } else { "unsigned-manual" }
    update_policy = if ($untrusted.Count -eq 0) { "controlled-release-channel" } else { "manual-download-only" }
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputRoot "release.json") -Encoding UTF8

$hashLines = Get-ChildItem -LiteralPath $outputRoot -File -Recurse |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($outputRoot.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$hashLines | Set-Content -LiteralPath (Join-Path $outputRoot "SHA256SUMS.txt") -Encoding ASCII

$archivePath = "$outputRoot.zip"
if (-not $SkipArchive) {
    Compress-Archive -LiteralPath (Join-Path $outputRoot "*") -DestinationPath $archivePath
}

Write-Output "Windows desktop package prepared: $outputRoot"
Write-Output "Headless runtime: included"
Write-Output "Trusted signatures: $($untrusted.Count -eq 0)"
if (-not $SkipArchive) {
    Write-Output "Distribution archive: $archivePath"
}
