[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RendezvousServer,

    [Parameter(Mandatory = $true)]
    [string]$RendezvousPublicKey,

    [string]$AndroidSdkRoot = (Join-Path $env:LOCALAPPDATA 'Android\Sdk'),

    [string]$VcpkgRoot = 'C:\vcpkg-android',

    [string]$NdkVersion = '28.2.13676358',

    [switch]$SkipDependencyInstall,

    [switch]$AllowTestConfiguration
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($RendezvousServer)) {
    throw 'RendezvousServer must not be empty.'
}
if (-not $AllowTestConfiguration -and $RendezvousServer.EndsWith('.invalid')) {
    throw 'A production build cannot use an .invalid rendezvous server.'
}
try {
    $publicKeyBytes = [Convert]::FromBase64String($RendezvousPublicKey)
} catch {
    throw 'RendezvousPublicKey must be valid base64.'
}
if ($publicKeyBytes.Length -ne 32) {
    throw 'RendezvousPublicKey must decode to exactly 32 bytes.'
}

$vcpkgExe = Join-Path $VcpkgRoot 'vcpkg.exe'
$ndkRoot = Join-Path $AndroidSdkRoot "ndk\$NdkVersion"
$prebuiltRoot = Join-Path $ndkRoot 'toolchains\llvm\prebuilt\windows-x86_64'
$sysroot = Join-Path $prebuiltRoot 'sysroot'
$targetRoot = Join-Path $VcpkgRoot 'installed\arm64-android'

foreach ($required in @(
    $vcpkgExe,
    (Join-Path $prebuiltRoot 'bin\clang.exe'),
    (Join-Path $repoRoot 'Cargo.toml')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Android build dependency is missing: $required"
    }
}
if (-not (Get-Command cargo-ndk -ErrorAction SilentlyContinue)) {
    throw 'cargo-ndk is not installed or is not available on PATH.'
}

$env:ANDROID_NDK_HOME = $ndkRoot
$env:ANDROID_NDK_ROOT = $ndkRoot
$env:VCPKG_ROOT = $VcpkgRoot
$env:VCPKG_INSTALLED_ROOT = Join-Path $VcpkgRoot 'installed'

if (-not $SkipDependencyInstall) {
    Push-Location $repoRoot
    try {
        & $vcpkgExe install --triplet arm64-android "--x-install-root=$($env:VCPKG_INSTALLED_ROOT)"
        if ($LASTEXITCODE -ne 0) {
            throw "Android codec dependency installation failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }

    Push-Location $VcpkgRoot
    try {
        & $vcpkgExe install 'libsodium:arm64-android' 'openssl:arm64-android' "--x-install-root=$($env:VCPKG_INSTALLED_ROOT)"
        if ($LASTEXITCODE -ne 0) {
            throw "Android crypto dependency installation failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

$androidSodium = Join-Path $targetRoot 'lib\libsodium.a'
$opensslLib = Join-Path $targetRoot 'lib'
$opensslInclude = Join-Path $targetRoot 'include'
if (-not (Test-Path -LiteralPath $androidSodium)) {
    throw "Android libsodium archive is missing: $androidSodium"
}
foreach ($opensslArchive in @('libssl.a', 'libcrypto.a')) {
    $path = Join-Path $opensslLib $opensslArchive
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Android OpenSSL archive is missing: $path"
    }
}

Push-Location $repoRoot
try {
    $metadata = cargo metadata --locked --format-version 1 | ConvertFrom-Json -AsHashtable
    if ($LASTEXITCODE -ne 0) {
        throw "cargo metadata failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
$sodiumPackage = $metadata.packages |
    Where-Object { $_.name -eq 'libsodium-sys' -and $_.version -eq '0.2.7' } |
    Select-Object -First 1
if (-not $sodiumPackage) {
    throw 'libsodium-sys 0.2.7 was not found in Cargo metadata.'
}
$sodiumSourceRoot = Split-Path -Parent $sodiumPackage.manifest_path
$windowsSodium = Join-Path $sodiumSourceRoot 'msvc\x64\Release\v142\libsodium.lib'
if (-not (Test-Path -LiteralPath $windowsSodium)) {
    throw "Windows host libsodium archive is missing: $windowsSodium"
}

$compatRoot = Join-Path $repoRoot 'target\android-native-bridge\arm64'
New-Item -ItemType Directory -Path $compatRoot -Force | Out-Null
Copy-Item -LiteralPath $windowsSodium -Destination (Join-Path $compatRoot 'libsodium.lib') -Force
Copy-Item -LiteralPath $androidSodium -Destination (Join-Path $compatRoot 'liblibsodium.a') -Force

$clangVersion = Get-ChildItem -LiteralPath (Join-Path $prebuiltRoot 'lib\clang') -Directory |
    Sort-Object { [int]$_.Name } -Descending |
    Select-Object -First 1
if (-not $clangVersion) {
    throw 'NDK Clang resource directory was not found.'
}
$clangResource = Join-Path $clangVersion.FullName 'include'

function Convert-ToForwardSlash([string]$Path) {
    return $Path.Replace('\', '/')
}

$ndkForward = Convert-ToForwardSlash $ndkRoot
$sysrootForward = Convert-ToForwardSlash $sysroot
$clangResourceForward = Convert-ToForwardSlash $clangResource
$targetForward = Convert-ToForwardSlash $targetRoot
$compatForward = Convert-ToForwardSlash $compatRoot

$env:ANDROID_NDK_HOME = $ndkForward
$env:ANDROID_NDK_ROOT = $ndkForward
$env:VCPKG_ROOT = Convert-ToForwardSlash $VcpkgRoot
$env:VCPKG_INSTALLED_ROOT = Convert-ToForwardSlash (Join-Path $VcpkgRoot 'installed')
$env:SODIUM_LIB_DIR = $compatForward
$env:OPENSSL_NO_VENDOR = '1'
$env:OPENSSL_LIB_DIR = "$targetForward/lib"
$env:OPENSSL_INCLUDE_DIR = "$targetForward/include"
$env:OPENSSL_STATIC = '1'
$env:CFLAGS = '--target=aarch64-linux-android21'
$env:CXXFLAGS = '--target=aarch64-linux-android21'
$env:BINDGEN_EXTRA_CLANG_ARGS = "--target=aarch64-linux-android21 --sysroot=$sysrootForward -I$clangResourceForward -I$sysrootForward/usr/include -I$sysrootForward/usr/include/aarch64-linux-android"
$env:VYNXDESK_RENDEZVOUS_SERVER = $RendezvousServer
$env:VYNXDESK_RENDEZVOUS_PUB_KEY = $RendezvousPublicKey

Push-Location $repoRoot
try {
    cargo ndk --platform 21 --target aarch64-linux-android build --locked --release --lib --features flutter,hwcodec
    if ($LASTEXITCODE -ne 0) {
        throw "Android arm64 Rust build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$jniRoot = Join-Path $PSScriptRoot 'android\app\src\main\jniLibs\arm64-v8a'
New-Item -ItemType Directory -Path $jniRoot -Force | Out-Null
$rustLibrary = Join-Path $repoRoot 'target\aarch64-linux-android\release\liblibrustdesk.so'
$cppRuntime = Join-Path $sysroot 'usr\lib\aarch64-linux-android\libc++_shared.so'
foreach ($required in @($rustLibrary, $cppRuntime)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Expected Android runtime library is missing: $required"
    }
}
Copy-Item -LiteralPath $rustLibrary -Destination (Join-Path $jniRoot 'librustdesk.so') -Force
Copy-Item -LiteralPath $cppRuntime -Destination (Join-Path $jniRoot 'libc++_shared.so') -Force

Write-Host "Android arm64 native libraries are ready in $jniRoot"
