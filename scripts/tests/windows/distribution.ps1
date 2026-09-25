[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$temp = Join-Path ([IO.Path]::GetTempPath()) ('vynxdesk-test-' + [guid]::NewGuid())
$failed = 0
$passed = 0
# Signature policy is isolated here; this test never modifies a certificate store.
function Get-AuthenticodeSignature {
    param([string]$LiteralPath)
    [pscustomobject]@{Status=[System.Management.Automation.SignatureStatus]::NotSigned}
}
function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Run-Test([string]$Name, [scriptblock]$Body) {
    try { & $Body; $script:passed++; Write-Host "PASS $Name" }
    catch { $script:failed++; Write-Host "FAIL $Name : $($_.Exception.Message)" }
}
function Fixture {
    $root = Join-Path $temp ([guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path (Join-Path $root 'res'), (Join-Path $root 'build\data\flutter_assets') -Force | Out-Null
    foreach ($scriptName in @('package-windows-desktop.ps1','install-vynxdesk.ps1','diagnose-input.ps1')) {
        $source = Join-Path $repo "res\$scriptName"
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $root "res\$scriptName") }
    }
    foreach ($file in @('LICENCE','NOTICE','PRIVACY.md')) {
        Set-Content -LiteralPath (Join-Path $root $file) -Value 'fixture'
    }
    foreach ($file in @('vynxdesk.exe','librustdesk.dll','flutter_windows.dll','dylib_virtual_display.dll')) {
        Set-Content -LiteralPath (Join-Path $root "build\$file") -Value 'unsigned fixture, not an application'
    }
    Set-Content -LiteralPath (Join-Path $root 'build\data\flutter_assets\test.txt') -Value 'asset'
    return $root
}
try {
    Run-Test 'ZIP contains actual runtime files and assets' {
        $root = Fixture
        $out = Join-Path $root 'dist\package [test]'
        & (Join-Path $root 'res\package-windows-desktop.ps1') -BuildDirectory (Join-Path $root 'build') -OutputDirectory $out -AllowUnsigned
        Assert-True (Test-Path -LiteralPath "$out.zip") 'ZIP not produced'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead("$out.zip")
        try {
            $names = @($zip.Entries | ForEach-Object { $_.FullName.Replace('\','/') })
            Assert-True ($names -contains 'vynxdesk.exe') 'Missing primary executable'
            Assert-True ($names -contains 'data/flutter_assets/test.txt') 'Missing nested asset'
            Assert-True ($names -contains 'SHA256SUMS.txt') 'Missing checksum file'
        } finally { $zip.Dispose() }
        foreach ($line in Get-Content -LiteralPath (Join-Path $out 'SHA256SUMS.txt')) {
            $fields = $line -split '  ', 2
            $actual = (Get-FileHash -LiteralPath (Join-Path $out $fields[1]) -Algorithm SHA256).Hash
            Assert-True ($actual -ieq $fields[0]) 'Incorrect file checksum'
        }
    }
    Run-Test 'Missing Rust runtime DLL is rejected' {
        $root = Fixture
        Remove-Item -LiteralPath (Join-Path $root 'build\librustdesk.dll')
        $rejected = $false
        try { & (Join-Path $root 'res\package-windows-desktop.ps1') -BuildDirectory (Join-Path $root 'build') -OutputDirectory (Join-Path $root 'dist\missing') -AllowUnsigned -SkipArchive }
        catch { $rejected = $_.Exception.Message -match 'librustdesk.dll' }
        Assert-True $rejected 'Missing Rust DLL was accepted'
    }
    Run-Test 'Unsigned mode never permits a damaged signature' {
        $root = Fixture
        function Get-AuthenticodeSignature {
            param([string]$LiteralPath)
            [pscustomobject]@{Status=[System.Management.Automation.SignatureStatus]::HashMismatch}
        }
        $rejected = $false
        try { & (Join-Path $root 'res\package-windows-desktop.ps1') -BuildDirectory (Join-Path $root 'build') -OutputDirectory (Join-Path $root 'dist\bad') -AllowUnsigned -SkipArchive }
        catch { $rejected = $_.Exception.Message -match 'Invalid binary signature:.*HashMismatch' }
        Assert-True $rejected 'Tampered signatures were allowed'
    }
    Run-Test 'Read-only diagnostics never claim game acceptance' {
        $json = & (Join-Path $repo 'res\diagnose-input.ps1')
        $report = ($json -join [Environment]::NewLine) | ConvertFrom-Json
        Assert-True ($report.product -eq 'VynxDesk') 'Wrong diagnostic product'
        Assert-True ($report.game_acceptance -eq 'not-tested') 'Diagnostic claimed game compatibility'
        Assert-True ($report.read_only -eq $true) 'Diagnostic is not marked read-only'
    }
    Run-Test 'Installer works under Windows PowerShell 5.1 up to preflight' {
        $root = Fixture
        $stdout = Join-Path $root 'installer.stdout'
        $stderr = Join-Path $root 'installer.stderr'
        $arguments = '-NoProfile -NonInteractive -File "{0}" -PackageDirectory "{1}"' -f (Join-Path $root 'res\install-vynxdesk.ps1'), (Join-Path $root 'not-present')
        $process = Start-Process -FilePath powershell.exe -ArgumentList $arguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        Assert-True ($process.ExitCode -ne 0) 'Missing package unexpectedly accepted'
        $text = (Get-Content -LiteralPath $stdout, $stderr | Out-String)
        Assert-True ($text -match 'vynxdesk.exe was not found') "Unexpected preflight error: $text"
        Assert-True ($text -notmatch 'IsWindows') 'PowerShell 7-only variable leaked into Windows PowerShell'
    }
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
Write-Host "Distribution tests: $passed passed, $failed failed"
if ($failed) { exit 1 }
