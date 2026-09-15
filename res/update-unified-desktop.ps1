#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$installRoot = 'C:\Program Files\VynxDesk'
$installedExe = Join-Path $installRoot 'VynxDesk.exe'
$registryPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\VynxDesk'
$resultPath = Join-Path $packageRoot 'install-result.json'
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'package.json') -Raw | ConvertFrom-Json
$backupRoot = Join-Path 'C:\ProgramData\VynxDesk\Backups' ([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
$serviceStopped = $false
$registryBefore = $null
$shortcutBackups = @()

function Save-Result($value) {
    $value | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding UTF8
}

function Payload-Path([string]$root, [string]$relative) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $path.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Payload path escapes root: $relative"
    }
    return $path
}

try {
    if (-not (Test-Path -LiteralPath $installedExe)) {
        throw 'This updater requires the existing VynxDesk installation.'
    }
    if ((Get-Item -LiteralPath $installRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The installation directory must not be a reparse point.'
    }
    $serviceInfo = Get-CimInstance Win32_Service -Filter "Name='VynxDesk'"
    if ($null -eq $serviceInfo -or $serviceInfo.PathName -ine ('"' + $installedExe + '" --service')) {
        throw 'Service executable differs from the expected installation. No files changed.'
    }
    foreach ($entry in $manifest.files) {
        $source = Payload-Path $packageRoot $entry.path
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ine $entry.sha256) {
            throw "Package hash mismatch: $($entry.path)"
        }
        $destination = Payload-Path $installRoot $entry.path
        if (Test-Path -LiteralPath $destination) {
            if ((Get-Item -LiteralPath $destination).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Payload destination is a reparse point: $destination"
            }
            $backup = Payload-Path $backupRoot $entry.path
            New-Item -ItemType Directory -Path (Split-Path $backup) -Force | Out-Null
            Copy-Item -LiteralPath $destination -Destination $backup
        }
    }
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $registryBefore = Get-ItemProperty -LiteralPath $registryPath
    $registryBefore | Select-Object DisplayIcon,BuildDate,Version,DisplayVersion |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupRoot 'registry.json') -Encoding UTF8

    $service = Get-Service -Name VynxDesk
    Stop-Service -Name VynxDesk -Force
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
    $serviceStopped = $true
    foreach ($process in Get-CimInstance Win32_Process -Filter "Name='VynxDesk.exe'") {
        if ($process.ExecutablePath -ieq $installedExe) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
    }

    foreach ($entry in $manifest.files) {
        $source = Payload-Path $packageRoot $entry.path
        $destination = Payload-Path $installRoot $entry.path
        New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ine $entry.sha256) {
            throw "Installed file hash mismatch: $($entry.path)"
        }
    }

    $icon = Join-Path $installRoot 'vynx-brand-20260913.ico'
    foreach ($pair in @(@('DisplayIcon', "$icon,0"), @('BuildDate', $manifest.build_date), @('Version', $manifest.version), @('DisplayVersion', $manifest.version))) {
        Set-ItemProperty -LiteralPath $registryPath -Name $pair[0] -Value $pair[1]
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcutRoots = @(
        [Environment]::GetFolderPath('Desktop'),
        [Environment]::GetFolderPath('CommonDesktopDirectory'),
        (Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'VynxDesk'),
        [Environment]::GetFolderPath('CommonStartup')
    )
    foreach ($root in $shortcutRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File) {
            $shortcut = $shell.CreateShortcut($file.FullName)
            if ($shortcut.TargetPath -ieq $installedExe) {
                $copy = Join-Path $backupRoot ('shortcut-' + $shortcutBackups.Count + '.lnk')
                Copy-Item -LiteralPath $file.FullName -Destination $copy
                $shortcutBackups += @{original=$file.FullName; backup=$copy}
                $shortcut.IconLocation = "$icon,0"
                $shortcut.WorkingDirectory = $installRoot
                $shortcut.Save()
            }
        }
    }
    $shortcutBackups | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupRoot 'shortcuts.json') -Encoding UTF8

    Start-Service -Name VynxDesk
    (Get-Service -Name VynxDesk).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    Save-Result @{success=$true; install_root=$installRoot; backup_root=$backupRoot; service='Running'; version=$manifest.version; build_date=$manifest.build_date}
} catch {
    $failure = $_.Exception.Message
    $rollbackError = $null
    if ($serviceStopped) {
        try {
            Stop-Service -Name VynxDesk -Force -ErrorAction SilentlyContinue
            foreach ($process in Get-CimInstance Win32_Process -Filter "Name='VynxDesk.exe'") {
                if ($process.ExecutablePath -ieq $installedExe) { Stop-Process -Id $process.ProcessId -Force }
            }
            foreach ($entry in $manifest.files) {
                $backup = Payload-Path $backupRoot $entry.path
                if (Test-Path -LiteralPath $backup) {
                    Copy-Item -LiteralPath $backup -Destination (Payload-Path $installRoot $entry.path) -Force
                }
            }
            if ($null -ne $registryBefore) {
                foreach ($name in @('DisplayIcon','BuildDate','Version','DisplayVersion')) {
                    Set-ItemProperty -LiteralPath $registryPath -Name $name -Value $registryBefore.$name
                }
            }
            foreach ($shortcut in $shortcutBackups) { Copy-Item -LiteralPath $shortcut.backup -Destination $shortcut.original -Force }
            Start-Service -Name VynxDesk
        } catch { $rollbackError = $_.Exception.Message }
    }
    Save-Result @{success=$false; error=$failure; rollback_error=$rollbackError; backup_root=$backupRoot}
    exit 1
}
