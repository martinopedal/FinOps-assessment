#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ReleaseReadinessPath = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Test-ReleaseReadiness.ps1'
    . $script:ReleaseReadinessPath
}

Describe 'Test-ReleaseTagVersion' {
    It 'parses a stable release tag' {
        Test-ReleaseTagVersion -TagName 'ps-v0.1.0' | Should -Be '0.1.0'
    }

    It 'rejects an uppercase V prefix' {
        { Test-ReleaseTagVersion -TagName 'ps-V0.1.0' } | Should -Throw
    }

    It 'parses a prerelease tag' {
        Test-ReleaseTagVersion -TagName 'ps-v0.1.0-rc1' | Should -Be '0.1.0-rc1'
    }

    It 'rejects build metadata tags' {
        { Test-ReleaseTagVersion -TagName 'ps-v0.1.0+sha' } | Should -Throw
    }

    It 'rejects tags with surrounding whitespace' {
        { Test-ReleaseTagVersion -TagName ' ps-v0.1.0 ' } | Should -Throw
    }
}

Describe 'Test-ReleaseTagMatchesManifest' {
    It 'passes when tag version equals manifest ModuleVersion' {
        $manifestPath = Join-Path $TestDrive 'FinOpsAssess.psd1'
        @"
@{
    ModuleVersion = '0.1.0'
    PrivateData = @{ PSData = @{} }
}
"@ | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        { Test-ReleaseTagMatchesManifest -TagName 'ps-v0.1.0' -ManifestPath $manifestPath } | Should -Not -Throw
    }

    It 'throws on tag and manifest mismatch with a clear message' {
        $manifestPath = Join-Path $TestDrive 'FinOpsAssess.psd1'
        @"
@{
    ModuleVersion = '0.1.0'
    PrivateData = @{ PSData = @{} }
}
"@ | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        { Test-ReleaseTagMatchesManifest -TagName 'ps-v0.1.1' -ManifestPath $manifestPath } |
            Should -Throw -ExpectedMessage '*tag/manifest mismatch*'
    }
}

Describe 'Test-ReleaseChangelogSection' {
    It 'passes when version section exists and Unreleased is empty' {
        $changelogPath = Join-Path $TestDrive 'CHANGELOG.md'
        @"
# Changelog

## Unreleased

## [0.1.0] - 2026-06-04

### Added

- Release workflow shipped.
"@ | Set-Content -LiteralPath $changelogPath -Encoding UTF8

        { Test-ReleaseChangelogSection -ChangelogPath $changelogPath -Version '0.1.0' } | Should -Not -Throw
    }

    It 'throws when the version section is missing' {
        $changelogPath = Join-Path $TestDrive 'CHANGELOG.md'
        @"
# Changelog

## Unreleased

## [0.1.1] - 2026-06-04
"@ | Set-Content -LiteralPath $changelogPath -Encoding UTF8

        { Test-ReleaseChangelogSection -ChangelogPath $changelogPath -Version '0.1.0' } |
            Should -Throw -ExpectedMessage '*missing a section heading*'
    }

    It 'throws when Unreleased contains stale content' {
        $changelogPath = Join-Path $TestDrive 'CHANGELOG.md'
        @"
# Changelog

## Unreleased

- TODO: move me before release

## [0.1.0] - 2026-06-04
"@ | Set-Content -LiteralPath $changelogPath -Encoding UTF8

        { Test-ReleaseChangelogSection -ChangelogPath $changelogPath -Version '0.1.0' } |
            Should -Throw -ExpectedMessage '*Unreleased section must be empty*'
    }
}
