#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleRoot = Join-Path $PSScriptRoot '..' 'FinOpsAssess'
    $script:ManifestPath = Join-Path $script:ModuleRoot 'FinOpsAssess.psd1'
    $script:ManifestData = Import-PowerShellDataFile -Path $script:ManifestPath

    $script:ExpectedFunctions = @(
        'Assert-FinOpsReadOnlyScope',
        'Export-FinOpsFocusAligned',
        'Export-FinOpsPlaybook',
        'Get-FinOpsInfo',
        'Invoke-FinOpsAssessment',
        'Invoke-FinOpsLiveCollection',
        'Invoke-FinOpsTriage',
        'Test-FinOpsCatalogCoverage',
        'Test-FinOpsConfiguration',
        'Test-FinOpsReadOnlyScope'
    )

    # KEEP IN SYNC with powershell/tests/FinOpsAssess.Tests.ps1:100-107.
    $script:TripwirePatterns = @(
        'Invoke-Expression',
        '\biex\b',
        '\.ReadWrite\.',
        '(Set|Remove|New|Update|Add|Disable|Enable)-Mg',
        '(Set|Remove|New|Update)-Az[A-Z]',
        'Invoke-(RestMethod|WebRequest)[^\r\n]*-Method\s*[''"]?(POST|PUT|PATCH|DELETE)'
    )
}

Describe 'PSGallery readiness' {
    It 'validates the module manifest with Test-ModuleManifest' {
        { Test-ModuleManifest -Path $script:ManifestPath | Out-Null } | Should -Not -Throw
        $manifest = Test-ModuleManifest -Path $script:ManifestPath
        $manifest | Should -Not -BeNullOrEmpty
    }

    It 'requires a semver-compatible ModuleVersion' {
        $script:ManifestData.ModuleVersion | Should -Match '^\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$'
    }

    It 'exports exactly the expected public function set' {
        @($script:ManifestData.FunctionsToExport).Count | Should -Be 10

        $expected = $script:ExpectedFunctions | Sort-Object
        $actual = @($script:ManifestData.FunctionsToExport) | Sort-Object
        $diff = Compare-Object -ReferenceObject $expected -DifferenceObject $actual
        $diff | Should -BeNullOrEmpty
    }

    It 'has non-empty tags including key discoverability tags' {
        $tags = @($script:ManifestData.PrivateData.PSData.Tags)
        $tags | Should -Not -BeNullOrEmpty
        foreach ($tag in @('FinOps', 'ReadOnly', 'Assessment')) {
            $tags | Should -Contain $tag
        }
    }

    It 'declares valid ProjectUri and LicenseUri values' {
        $uris = @(
            $script:ManifestData.PrivateData.PSData.ProjectUri,
            $script:ManifestData.PrivateData.PSData.LicenseUri
        )

        foreach ($uri in $uris) {
            { [Uri]::new($uri) } | Should -Not -Throw
        }
    }

    It 'does not use wildcard auto-exports' {
        foreach ($field in @('CmdletsToExport', 'AliasesToExport', 'VariablesToExport')) {
            $value = @($script:ManifestData.$field)
            $value | Should -Not -Contain '*'
            $value.Count | Should -Be 0
        }
    }

    It 'reuses the exact tripwire pattern list and blocks scope-policy leaks outside policy file' {
        $tripwirePath = Join-Path $PSScriptRoot 'FinOpsAssess.Tests.ps1'
        $tripwirePatterns = @()
        $inPatternBlock = $false
        foreach ($line in Get-Content -LiteralPath $tripwirePath) {
            if (-not $inPatternBlock -and $line -match '^\s*\$patterns\s*=\s*@\(') {
                $inPatternBlock = $true
                continue
            }

            if ($inPatternBlock -and $line -match '^\s*\)\s*$') {
                break
            }

            if ($inPatternBlock) {
                $match = [regex]::Match($line, "'(?<pattern>(?:''|[^'])*)'")
                if ($match.Success) {
                    $tripwirePatterns += ($match.Groups['pattern'].Value -replace "''", "'")
                }
            }
        }
        $tripwirePatterns | Should -Not -BeNullOrEmpty

        $patternDiff = Compare-Object -ReferenceObject $tripwirePatterns -DifferenceObject $script:TripwirePatterns
        $patternDiff | Should -BeNullOrEmpty

        $allowedPath = (Resolve-Path (Join-Path $script:ModuleRoot 'Private' 'Get-FinOpsReadOnlyScopePolicy.ps1')).Path
        $files = Get-ChildItem -Path $script:ModuleRoot -Recurse -Filter '*.ps1' -File |
            Where-Object { (Resolve-Path $_.FullName).Path -ne $allowedPath }

        $hits = foreach ($file in $files) {
            $content = Get-Content -LiteralPath $file.FullName -Raw
            foreach ($pattern in $script:TripwirePatterns) {
                if ($content -match $pattern) {
                    "{0} matched /{1}/" -f $file.FullName, $pattern
                }
            }
        }

        $hits | Should -BeNullOrEmpty
    }

    It 'ships required bundled JSON data files that parse cleanly' {
        $expectedFiles = @('catalog.json', 'personas.json', 'playbooks.json', 'rules.json', 'schema.json')
        $dataRoot = Join-Path $script:ModuleRoot 'data'

        foreach ($fileName in $expectedFiles) {
            $path = Join-Path $dataRoot $fileName
            Test-Path -LiteralPath $path | Should -BeTrue
            { Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } | Should -Not -Throw
        }
    }
}
