Set-StrictMode -Version Latest

function Test-ReleaseTagVersion {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$TagName
    )

    if ([string]::IsNullOrWhiteSpace($TagName)) {
        throw "Release tag must not be empty."
    }

    if ($TagName -ne $TagName.Trim()) {
        throw "Release tag '$TagName' must not contain leading or trailing whitespace."
    }

    $match = [regex]::Match($TagName, '^ps-v(?<version>\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?)$')
    if (-not $match.Success) {
        throw "Release tag '$TagName' must match ^ps-v\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$."
    }

    return $match.Groups['version'].Value
}

function Test-ReleaseTagMatchesManifest {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$TagName,

        [Parameter(Mandatory)]
        [string]$ManifestPath
    )

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        throw "Manifest path not found: $ManifestPath"
    }

    $tagVersion = Test-ReleaseTagVersion -TagName $TagName
    $manifest = Import-PowerShellDataFile -LiteralPath $ManifestPath

    $manifestVersion = [string]$manifest.ModuleVersion
    $manifestPrerelease = $null
    if ($manifest.ContainsKey('PrivateData') -and ($manifest.PrivateData -is [hashtable])) {
        $psData = $manifest.PrivateData['PSData']
        if ($psData -is [hashtable] -and $psData.ContainsKey('Prerelease')) {
            $manifestPrerelease = [string]$psData['Prerelease']
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($manifestPrerelease)) {
        $manifestVersion = "$manifestVersion-$manifestPrerelease"
    }

    if ($tagVersion -ne $manifestVersion) {
        throw "tag/manifest mismatch: tag version '$tagVersion' != manifest version '$manifestVersion'."
    }

    return $manifestVersion
}

function Test-ReleaseChangelogSection {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [string]$ChangelogPath,

        [Parameter(Mandatory)]
        [string]$Version
    )

    if (-not (Test-Path -LiteralPath $ChangelogPath)) {
        throw "CHANGELOG path not found: $ChangelogPath"
    }

    $content = Get-Content -LiteralPath $ChangelogPath -Raw -Encoding UTF8
    $escapedVersion = [regex]::Escape($Version)
    $versionHeadingPattern = "(?m)^##\s+\[$escapedVersion\]\s*(?:-|\u2014)\s*.+$"
    if (-not [regex]::IsMatch($content, $versionHeadingPattern)) {
        throw "CHANGELOG is missing a section heading for version '$Version'."
    }

    $unreleasedMatch = [regex]::Match($content, '(?ms)^##\s+Unreleased\s*\r?\n(?<body>.*?)(?=^##\s|\z)')
    if (-not $unreleasedMatch.Success) {
        throw "CHANGELOG is missing the '## Unreleased' section."
    }

    $remainingLines = @(
        $unreleasedMatch.Groups['body'].Value -split '\r?\n' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -ne '' }
    )

    if ($remainingLines.Count -eq 0) {
        return $true
    }

    foreach ($line in $remainingLines) {
        if ($line -notmatch '^(?:[-*]\s*)?(?:_?None\.?_?|_?No changes yet\.?_?)$') {
            throw "CHANGELOG Unreleased section must be empty or an approved stub; found leftover content."
        }
    }

    return $true
}



