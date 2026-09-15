[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputFullPath = if ([IO.Path]::IsPathRooted($OutputPath)) {
    [IO.Path]::GetFullPath($OutputPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputPath))
}
$outputName = $outputFullPath.ToLowerInvariant()
if (-not ($outputName.EndsWith('.zip') -or $outputName.EndsWith('.tar.gz') -or $outputName.EndsWith('.tgz'))) {
    throw 'OutputPath must end with .zip, .tar.gz, or .tgz.'
}
if ((Test-Path -LiteralPath $outputFullPath) -and -not $Force) {
    throw "Source archive already exists: $outputFullPath"
}

$outputDirectory = Split-Path -Parent $outputFullPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$tarArguments = @(
    '-a',
    '-cf',
    $outputFullPath,
    '--exclude=./.git',
    '--exclude=./target',
    '--exclude=./dist',
    '--exclude=./flutter/build',
    '--exclude=./flutter/.dart_tool',
    '--exclude=./flutter/android/.gradle',
    '--exclude=./flutter/android/app/src/main/jniLibs',
    '--exclude=./flutter/android/key.properties',
    '--exclude=./flutter/split-debug-info',
    '--exclude=*.jks',
    '--exclude=*.keystore',
    '--exclude=./vynxdesk.exe',
    '--exclude=./sciter.dll',
    '.'
)

Push-Location $repoRoot
try {
    & tar.exe @tarArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Source archive creation failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$archive = Get-Item -LiteralPath $outputFullPath
$hash = Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256
Write-Host "Source archive: $($archive.FullName)"
Write-Host "Bytes: $($archive.Length)"
Write-Host "SHA256: $($hash.Hash)"
