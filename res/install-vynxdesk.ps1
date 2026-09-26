[CmdletBinding()]
param(
    [string]$PackageDirectory = $PSScriptRoot,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "VynxDesk service installation is supported only on Windows."
}

$packageRoot = [System.IO.Path]::GetFullPath($PackageDirectory)
$executable = Join-Path $packageRoot "vynxdesk.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "vynxdesk.exe was not found in the package directory: $packageRoot"
}

$arguments = if ($Silent) { @("--silent-install") } else { @("--install") }
$process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $packageRoot -Verb RunAs -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "VynxDesk installation failed with exit code $($process.ExitCode)."
}

Write-Output "VynxDesk service installation completed."
