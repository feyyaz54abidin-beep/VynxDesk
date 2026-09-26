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

$pythonArguments = @((Join-Path $repoRoot 'scripts/package_source.py'), '--output', $outputFullPath)
if ($Force) { $pythonArguments += '--force' }
& python @pythonArguments
if ($LASTEXITCODE -ne 0) {
    throw "Exact source archive creation failed with exit code $LASTEXITCODE."
}

$archive = Get-Item -LiteralPath $outputFullPath
$hash = Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256
Write-Host "Source archive: $($archive.FullName)"
Write-Host "Bytes: $($archive.Length)"
Write-Host "SHA256: $($hash.Hash)"
