[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,

    [Parameter(Mandatory = $true)]
    [string]$SourceArchive,

    [string]$CertificateThumbprint = $env:VYNXDESK_SIGNING_CERT_THUMBPRINT,

    [string]$TimestampUrl = 'http://timestamp.digicert.com',

    [switch]$Sign,

    [switch]$AllowUnsigned
)

$ErrorActionPreference = 'Stop'
$expectedPublisher = ([string]$CertificateThumbprint).Replace(' ', '').ToUpperInvariant()
if ($expectedPublisher -and $expectedPublisher -notmatch '\A[0-9A-F]{40}\z') {
    throw 'The publisher certificate thumbprint must contain exactly 40 hexadecimal digits.'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactItem = Get-Item -LiteralPath $ArtifactPath
$sourceItem = Get-Item -LiteralPath $SourceArchive

if ($sourceItem.PSIsContainer) {
    throw 'SourceArchive must be a source archive file for the exact release.'
}
$sourceName = $sourceItem.Name.ToLowerInvariant()
if (-not ($sourceName.EndsWith('.zip') -or $sourceName.EndsWith('.tar.gz') -or $sourceName.EndsWith('.tgz'))) {
    throw 'SourceArchive must be a .zip, .tar.gz, or .tgz archive.'
}

Push-Location $repoRoot
try {
    cargo audit
    if ($LASTEXITCODE -ne 0) {
        throw "RustSec dependency audit failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$releaseExtensions = @('.exe', '.dll', '.msi', '.msix', '.appx')
if ($artifactItem.PSIsContainer) {
    $artifacts = @(Get-ChildItem -LiteralPath $artifactItem.FullName -File -Recurse |
        Where-Object { $_.Extension.ToLowerInvariant() -in $releaseExtensions })
    $outputDirectory = $artifactItem.FullName
} else {
    if ($artifactItem.Extension.ToLowerInvariant() -notin $releaseExtensions) {
        throw "Unsupported release artifact: $($artifactItem.FullName)"
    }
    $artifacts = @($artifactItem)
    $outputDirectory = $artifactItem.DirectoryName
}

if ($artifacts.Count -eq 0) {
    throw 'No Windows release artifacts were found.'
}

function Get-SigningCertificate([string]$Thumbprint) {
    if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
        throw 'A signing certificate thumbprint is required when -Sign is used.'
    }

    $normalized = $Thumbprint.Replace(' ', '')
    $candidate = @(
        "Cert:\CurrentUser\My\$normalized",
        "Cert:\LocalMachine\My\$normalized"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

    if (-not $candidate) {
        throw "Signing certificate was not found: $normalized"
    }

    $certificate = Get-Item -LiteralPath $candidate
    if (-not $certificate.HasPrivateKey) {
        throw 'The signing certificate has no accessible private key.'
    }
    if ($certificate.Subject -eq $certificate.Issuer) {
        throw 'Self-signed certificates are not accepted by the commercial release gate.'
    }
    if ($certificate.NotAfter -le (Get-Date)) {
        throw 'The signing certificate has expired.'
    }
    return $certificate
}

function Get-SignTool {
    $kitsRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    $tool = Get-ChildItem -Path "$kitsRoot\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [version]$_.Directory.Parent.Name } -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $tool) {
        throw 'SignTool was not found. Install the Windows SDK signing tools.'
    }
    return $tool
}

if ($Sign) {
    $certificate = Get-SigningCertificate $CertificateThumbprint
    $signTool = Get-SignTool
    $installers = @('.msi', '.msix', '.appx')
    $orderedArtifacts = $artifacts | Sort-Object {
        if ($_.Extension.ToLowerInvariant() -in $installers -or $_.BaseName -match '(?i)(install|setup)') { 1 } else { 0 }
    }

    foreach ($artifact in $orderedArtifacts) {
        $existing = Get-AuthenticodeSignature -LiteralPath $artifact.FullName
        if ($existing.Status -eq 'Valid') {
            if ($artifact.BaseName -match '(?i)^(vynxdesk|librustdesk)$' -and
                $existing.SignerCertificate.Thumbprint -ne $certificate.Thumbprint) {
                throw "Product binary is signed by a different identity: $($artifact.FullName)"
            }
            continue
        }
        if ($existing.Status -ne 'NotSigned') {
            throw "Refusing to replace a broken signature: $($artifact.FullName) [$($existing.Status)]"
        }

        & $signTool sign /sha1 $certificate.Thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 /v $artifact.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "SignTool failed for $($artifact.FullName) with exit code $LASTEXITCODE."
        }
    }
}

$failures = [System.Collections.Generic.List[string]]::new()
$unsignedArtifacts = [System.Collections.Generic.List[string]]::new()
$foundPrimaryExecutable = $false
$productSignerThumbprints = [System.Collections.Generic.List[string]]::new()
foreach ($artifact in $artifacts) {
    $signature = Get-AuthenticodeSignature -LiteralPath $artifact.FullName
    $isPrimaryExecutable = $artifact.Extension -ieq '.exe' -and
        ($artifact.BaseName -match '(?i)vynxdesk' -or $artifact.VersionInfo.ProductName -eq 'VynxDesk')
    $isProductBinary = $isPrimaryExecutable -or $artifact.BaseName -match '(?i)^librustdesk$'
    if ($signature.Status -ne 'Valid') {
        if ($AllowUnsigned -and $signature.Status -eq 'NotSigned') {
            $unsignedArtifacts.Add($artifact.FullName)
        } else {
            $failures.Add("Untrusted signature: $($artifact.FullName) [$($signature.Status)]")
        }
    } elseif ($signature.SignerCertificate.Subject -eq $signature.SignerCertificate.Issuer) {
        $failures.Add("Self-signed certificate: $($artifact.FullName)")
    } elseif (-not $signature.TimeStamperCertificate) {
        $failures.Add("Missing RFC 3161 timestamp: $($artifact.FullName)")
    }
    if ($signature.Status -eq 'Valid' -and $isProductBinary) {
        $productSignerThumbprints.Add($signature.SignerCertificate.Thumbprint)
        if (-not $expectedPublisher) {
            $failures.Add('An explicit publisher certificate thumbprint is required for signed product binaries.')
        } elseif ($signature.SignerCertificate.Thumbprint -ine $expectedPublisher) {
            $failures.Add("Product publisher identity mismatch: $($artifact.FullName)")
        }
    }

    if ($isPrimaryExecutable) {
        $foundPrimaryExecutable = $true
        $version = $artifact.VersionInfo
        if ($version.ProductName -ne 'VynxDesk') {
            $failures.Add("Invalid ProductName metadata: $($artifact.FullName)")
        }
        if ([string]::IsNullOrWhiteSpace($version.FileVersion)) {
            $failures.Add("Missing FileVersion metadata: $($artifact.FullName)")
        }
    }
}
if (-not $foundPrimaryExecutable) {
    $failures.Add('No VynxDesk primary executable was found in the release artifacts.')
}
$distinctProductSigners = @($productSignerThumbprints | Sort-Object -Unique)
if ($distinctProductSigners.Count -gt 1) {
    $failures.Add('VynxDesk product binaries are not signed by one consistent identity.')
}

$requiredDocuments = @('LICENCE', 'NOTICE', 'PRIVACY.md')
foreach ($document in $requiredDocuments) {
    $source = Join-Path $repoRoot $document
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        $failures.Add("Missing repository document: $document")
    } elseif ($artifactItem.PSIsContainer) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $outputDirectory $document) -Force
    }
}

if ($artifactItem.PSIsContainer) {
    $sourceDestination = Join-Path $outputDirectory $sourceItem.Name
    if (-not $sourceItem.FullName.Equals($sourceDestination, [StringComparison]::OrdinalIgnoreCase)) {
        Copy-Item -LiteralPath $sourceItem.FullName -Destination $sourceDestination -Force
    }
}

$hashFile = Join-Path $outputDirectory 'SHA256SUMS.txt'
$distributionInputs = @($artifacts) + @($sourceItem)
if ($artifactItem.PSIsContainer) {
    $distributionInputs += @(Get-ChildItem -LiteralPath $outputDirectory -File |
        Where-Object { $_.Name -in @('LICENCE', 'NOTICE', 'PRIVACY.md') })
}
$hashInputs = $distributionInputs
$hashLines = $hashInputs | Sort-Object FullName -Unique | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant()) *$($_.Name)"
}
Set-Content -LiteralPath $hashFile -Value $hashLines -Encoding utf8

if ($failures.Count -gt 0) {
    throw ($failures -join [Environment]::NewLine)
}

if ($unsignedArtifacts.Count -gt 0) {
    Write-Warning "Unsigned manual-distribution gate passed for $($artifacts.Count) artifact(s). Keep automatic updates disabled and distribute only the matching SHA256SUMS.txt."
} else {
    Write-Host "Commercial release gate passed for $($artifacts.Count) artifact(s)."
}
