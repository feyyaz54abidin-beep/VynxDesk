[CmdletBinding()]
param([string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'This diagnostic requires Windows.' }

# No key injection, target-process memory access, configuration changes or network calls.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
try {
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} finally { $identity.Dispose() }
$services = @(Get-Service -ErrorAction Stop | Where-Object { $_.Name -ieq 'VynxDesk' })
$processes = @(Get-Process -Name 'vynxdesk' -ErrorAction SilentlyContinue)
$warnings = @(
    'This checks the diagnostic process, not the integrity level of a remote input worker or game.'
    'SendInput can be blocked by process integrity (UIPI); a successful API call is not proof a game accepted input.'
    'Compatibility profiles are host-side and read at input initialization; restart the host after a signed profile change.'
    'Raw Input or protected-game acceptance requires an actual per-title test; this tool does not bypass protections.'
)
if ($services.Count -eq 0) {
    $warnings += 'VynxDesk service was not found. Portable attended mode is not evidence of unattended/UAC support.'
}
$report = [ordered]@{
    product = 'VynxDesk'
    schema_version = 1
    read_only = $true
    powershell = $PSVersionTable.PSVersion.ToString()
    os_version = [Environment]::OSVersion.Version.ToString()
    os_64bit = [Environment]::Is64BitOperatingSystem
    diagnostic_process_elevated = $elevated
    service_states = @($services | ForEach-Object { [string]$_.Status })
    client_process_count = $processes.Count
    game_acceptance = 'not-tested'
    warnings = $warnings
}
$json = $report | ConvertTo-Json -Depth 4
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $fullPath = [IO.Path]::GetFullPath($OutputPath)
    $stream = [IO.File]::Open($fullPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}
Write-Output $json
