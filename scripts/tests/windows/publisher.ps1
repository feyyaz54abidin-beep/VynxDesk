[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$temp = Join-Path ([IO.Path]::GetTempPath()) ('vynx-publisher-' + [guid]::NewGuid())
$passed = 0
$failed = 0

# Controlled signature statuses only. Never installs certificates or signs files.
function Invoke-Fixture([string]$Pin, [string]$Signer, [string]$Status = 'Valid', [bool]$AllowUnsigned = $false) {
    $root = Join-Path $temp ([guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $artifactPath = Join-Path $root 'vynxdesk.exe'
    $sourcePath = Join-Path $root 'source.zip'
    Set-Content -LiteralPath $artifactPath -Value 'not a runnable executable'
    Set-Content -LiteralPath $sourcePath -Value 'source archive fixture'
    function Get-Item {
        param([string]$LiteralPath)
        if ($LiteralPath -eq $artifactPath) {
            return [pscustomobject]@{
                PSIsContainer=$false; FullName=$artifactPath; Name='vynxdesk.exe';
                BaseName='vynxdesk'; Extension='.exe'; DirectoryName=$root;
                VersionInfo=[pscustomobject]@{ProductName='VynxDesk'; FileVersion='1.5.0'}
            }
        }
        Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath
    }
    function Get-AuthenticodeSignature {
        param([string]$LiteralPath)
        [pscustomobject]@{
            Status=$Status;
            SignerCertificate=[pscustomobject]@{Thumbprint=$Signer; Subject='CN=Fixture'; Issuer='CN=Fixture CA'};
            TimeStamperCertificate=[pscustomobject]@{Subject='CN=Fixture TSA'}
        }
    }
    function cargo { $global:LASTEXITCODE = 0 }
    try {
        & (Join-Path $repo 'res\commercial-release.ps1') -ArtifactPath $artifactPath -SourceArchive $sourcePath -CertificateThumbprint $Pin -AllowUnsigned:$AllowUnsigned | Out-Null
        return [pscustomobject]@{Accepted=$true; Message=''}
    } catch {
        return [pscustomobject]@{Accepted=$false; Message=$_.Exception.Message}
    }
}
function Check([string]$Name, [scriptblock]$Body) {
    try { & $Body; $script:passed++; Write-Host "PASS $Name" }
    catch { $script:failed++; Write-Host "FAIL $Name : $($_.Exception.Message)" }
}
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
    $a = 'A' * 40; $b = 'B' * 40
    Check 'Different trusted publisher is not VYNX' {
        $r = Invoke-Fixture $a $b
        Assert (-not $r.Accepted -and $r.Message -match 'publisher|identity') 'Wrong publisher passed verification'
    }
    Check 'Signed release requires an explicit publisher pin' {
        $r = Invoke-Fixture '' $a
        Assert (-not $r.Accepted -and $r.Message -match 'thumbprint|publisher') 'Missing publisher pin was accepted'
    }
    Check 'Malformed publisher pin is rejected' {
        $r = Invoke-Fixture 'not-a-certificate' $a
        Assert (-not $r.Accepted -and $r.Message -match 'thumbprint') 'Malformed publisher pin was accepted'
    }
    Check 'Configured publisher is accepted case-insensitively' {
        $r = Invoke-Fixture (' aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa ') $a
        Assert $r.Accepted "Expected publisher was rejected: $($r.Message)"
    }
    Check 'Explicit unsigned manual testing remains available' {
        $r = Invoke-Fixture '' '' 'NotSigned' $true
        Assert $r.Accepted "Unsigned manual fixture was rejected: $($r.Message)"
    }
    Check 'AllowUnsigned never skips signed publisher mismatch' {
        $r = Invoke-Fixture $a $b 'Valid' $true
        Assert (-not $r.Accepted -and $r.Message -match 'publisher|identity') 'AllowUnsigned bypassed identity policy'
    }
    Check 'Damaged signature remains rejected in unsigned mode' {
        $r = Invoke-Fixture '' '' 'HashMismatch' $true
        Assert (-not $r.Accepted) 'Damaged signature was accepted'
    }
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
Write-Host "Publisher tests: $passed passed, $failed failed"
if ($failed) { exit 1 }
