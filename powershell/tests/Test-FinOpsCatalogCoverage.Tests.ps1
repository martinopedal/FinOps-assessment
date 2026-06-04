#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
#
# Regression coverage for Test-FinOpsCatalogCoverage (PowerShell parity with
# `finops-assess catalog coverage`).
#
# All tests use LOCAL CSV fixtures only -- no network calls are made.
# Fixture files:
#   tests/fixtures/ms_skus_minimal.csv   - 4 unique SKUs (E3/E5/F3/Copilot), all in curated catalogue
#   tests/fixtures/ms_skus_with_gap.csv  - 2 unique SKUs (E3 + TOTALLY_NEW_SKU_2099, gap guaranteed)
#
# PESTER 5 SCOPE NOTE:
# -Skip:($expr) is evaluated at DISCOVERY time. Variables for skip conditions must therefore be
# set at top-level script scope (before any Describe block). Fixture variables that are only
# needed at execution time are set inside BeforeAll blocks to correctly bind to the run-phase scope.

# --- Discovery-time setup (top-level, runs before Describe blocks are evaluated) -

# Check by file existence -- avoids an Import-Module call at discovery time.
$script:CmdletFile      = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'Public' 'Test-FinOpsCatalogCoverage.ps1'
$script:CmdletAvailable = Test-Path -LiteralPath $script:CmdletFile -PathType Leaf

# --- Execution-time setup (BeforeAll, runs before any It block executes) ------

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    # Fixture paths: two levels up from powershell/tests/ -> repo root -> tests/fixtures/
    $script:FixturesRoot   = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot '..' '..' 'tests' 'fixtures'))
    $script:MinimalCsv     = Join-Path $script:FixturesRoot 'ms_skus_minimal.csv'
    $script:GapCsv         = Join-Path $script:FixturesRoot 'ms_skus_with_gap.csv'
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

# --- Pre-flight: fixture guard ----------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- fixture files exist' {
    It 'ms_skus_minimal.csv is present in tests/fixtures/' {
        Test-Path -LiteralPath $script:MinimalCsv -PathType Leaf |
            Should -BeTrue -Because 'ms_skus_minimal.csv must be committed under tests/fixtures/'
    }

    It 'ms_skus_with_gap.csv is present in tests/fixtures/' {
        Test-Path -LiteralPath $script:GapCsv -PathType Leaf |
            Should -BeTrue -Because 'ms_skus_with_gap.csv must be committed under tests/fixtures/'
    }

    It 'fixture CSV files contain no live tenant secrets or credentials' {
        # Lint assertion: reject any field that looks like a tenantId/clientSecret/accessToken assignment.
        foreach ($csvPath in @($script:MinimalCsv, $script:GapCsv)) {
            $content = Get-Content -LiteralPath $csvPath -Raw
            $content | Should -Not -Match '(?i)(tenantid|client.?secret|access.?token)\s*[=:,]\s*\S+' `
                -Because "$([System.IO.Path]::GetFileName($csvPath)) must contain no live credentials"
        }
    }
}

Describe 'Test-FinOpsCatalogCoverage -- module export (TDD-red until cmdlet lands)' {
    It 'Test-FinOpsCatalogCoverage.ps1 exists under Public/' {
        $cmdletFile = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'Public' 'Test-FinOpsCatalogCoverage.ps1'
        Test-Path -LiteralPath $cmdletFile -PathType Leaf |
            Should -BeTrue -Because 'the cmdlet file must exist for the module to reach 10 exported functions'
    }

    It 'Test-FinOpsCatalogCoverage is exported from the loaded module' {
        $null -ne (Get-Command Test-FinOpsCatalogCoverage -Module FinOpsAssess -ErrorAction SilentlyContinue) |
            Should -BeTrue -Because 'psm1 auto-exports all Public/*.ps1 basenames'
    }
}

# --- Result shape ------------------------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- result shape' -Skip:(-not $script:CmdletAvailable) {
    BeforeAll {
        # -NoFailOnGap: prevents BeforeAll from throwing on gap fixture.
        # -PassThru: returns structured [pscustomobject] instead of JSON text.
        $script:GapResult = Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap -PassThru
    }

    It 'returns a non-null pscustomobject' {
        $script:GapResult | Should -Not -BeNullOrEmpty
    }

    It 'result carries Source property that echoes the -Source argument' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'source'
        $script:GapResult.source | Should -Be $script:GapCsv
    }

    It 'result has UpstreamCount as a positive integer' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'upstream_count'
        $script:GapResult.upstream_count | Should -BeOfType ([int])
        $script:GapResult.upstream_count | Should -BeGreaterThan 0
    }

    It 'result has CatalogCount as a positive integer' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'catalog_count'
        $script:GapResult.catalog_count | Should -BeOfType ([int])
        $script:GapResult.catalog_count | Should -BeGreaterThan 0
    }

    It 'result has CoveragePct in the 0-100 range' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'coverage_pct'
        $script:GapResult.coverage_pct | Should -BeGreaterOrEqual 0
        $script:GapResult.coverage_pct | Should -BeLessOrEqual 100
    }

    It 'result has a Missing array property' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'missing'
        , $script:GapResult.missing | Should -BeOfType ([System.Array])
    }

    It 'result has an ExtraLocalIds array property' {
        $script:GapResult.PSObject.Properties.Name | Should -Contain 'extra_local_ids'
        , $script:GapResult.extra_local_ids | Should -BeOfType ([System.Array])
    }

    It 'Missing entries carry Id and DisplayName fields' {
        # Gate on at least one missing entry being present (guaranteed by the gap fixture).
        $script:GapResult.missing.Count | Should -BeGreaterThan 0
        $first = $script:GapResult.missing | Select-Object -First 1
        $first.PSObject.Properties.Name | Should -Contain 'id'
        $first.PSObject.Properties.Name | Should -Contain 'display_name'
    }
}

# --- Gap detection -----------------------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- gap detection' -Skip:(-not $script:CmdletAvailable) {
    BeforeAll {
        $script:GapResult = Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap -PassThru
    }

    It 'reports TOTALLY_NEW_SKU_2099 as a missing SKU' {
        $missingIds = @($script:GapResult.missing | ForEach-Object { $_.id })
        $missingIds | Should -Contain 'TOTALLY_NEW_SKU_2099' `
            -Because 'TOTALLY_NEW_SKU_2099 exists only in the gap fixture and is never in the curated catalogue'
    }

    It 'UpstreamCount equals the number of unique String_Ids in the gap fixture (2)' {
        # ms_skus_with_gap.csv has exactly 2 unique String_Ids: SPE_E3 + TOTALLY_NEW_SKU_2099.
        $script:GapResult.upstream_count | Should -Be 2
    }

    It 'reports at least one missing SKU when using the gap fixture' {
        $script:GapResult.missing.Count | Should -BeGreaterThan 0
    }
}

# --- Deduplication -----------------------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- deduplication of service-plan rows' -Skip:(-not $script:CmdletAvailable) {
    BeforeAll {
        # ms_skus_minimal.csv: 7 rows but only 4 unique String_Ids
        #   SPE_E3 x 3 rows (Exchange, SharePoint, Teams service plans)
        #   SPE_E5 x 2 rows
        #   SPE_F3 x 1 row
        #   M365_COPILOT x 1 row
        $script:MinResult = Test-FinOpsCatalogCoverage -Source $script:MinimalCsv -NoFailOnGap -PassThru
    }

    It 'collapses multiple service-plan rows for the same String_Id into one upstream entry' {
        # 7 CSV rows must collapse to exactly 4 unique upstream SKUs.
        $script:MinResult.upstream_count | Should -Be 4 `
            -Because 'ms_skus_minimal.csv has 7 rows for 4 unique String_Ids; dedup must yield 4'
    }
}

# --- Fail-on-gap behaviour ---------------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- fail-on-gap (default)' -Skip:(-not $script:CmdletAvailable) {
    It 'throws a terminating error by default when the upstream CSV contains uncatalogued SKUs' {
        { Test-FinOpsCatalogCoverage -Source $script:GapCsv } |
            Should -Throw -Because 'fail-on-gap is the conservative default (mirrors --fail-on-gap in Python CLI)'
    }

    It '-NoFailOnGap suppresses the terminating error when gaps exist' {
        { Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap } |
            Should -Not -Throw
    }

    It 'does not throw when the upstream CSV is fully covered by the curated catalogue' {
        # SPE_E3, SPE_E5, SPE_F3, and M365_COPILOT are all present in the curated catalogue.
        { Test-FinOpsCatalogCoverage -Source $script:MinimalCsv } |
            Should -Not -Throw -Because 'all 4 SKUs in ms_skus_minimal.csv are modelled in data/catalog/m365/'
    }
}

# --- m365_uncategorized exclusion --------------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- m365_uncategorized family excluded from coverage' -Skip:(-not $script:CmdletAvailable) {
    It 'still reports TOTALLY_NEW_SKU_2099 as missing even when an autogen stub exists' {
        # Mirrors Python regression: test_compute_coverage_excludes_autogen_stubs_from_local_count.
        # The cmdlet must delegate gap computation to the same logic that excludes
        # family=m365_uncategorized stubs (written by `catalog refresh --write`).
        # We can only assert the observable output: the gap fixture must always produce a gap.
        $result = Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap -PassThru
        $missingIds = @($result.missing | ForEach-Object { $_.id })
        $missingIds | Should -Contain 'TOTALLY_NEW_SKU_2099' `
            -Because 'autogen stubs with family=m365_uncategorized must not count as curated coverage'
    }
}

# --- No live calls / offline safety -----------------------------------------

Describe 'Test-FinOpsCatalogCoverage -- no live Microsoft endpoints' -Skip:(-not $script:CmdletAvailable) {
    It 'accepts a local filesystem path as -Source without hitting the network' {
        # If the implementation ignores -Source and hits the default URL, this test
        # would fail or return wrong upstream counts.
        $result = Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap -PassThru
        $result | Should -Not -BeNullOrEmpty
        $result.upstream_count | Should -Be 2 `
            -Because 'only 2 rows in ms_skus_with_gap.csv; any other count means the live URL was fetched'
    }

    It 'reports the local path as Source (not the Microsoft download URL)' {
        $result = Test-FinOpsCatalogCoverage -Source $script:GapCsv -NoFailOnGap -PassThru
        $result.source | Should -Be $script:GapCsv `
            -Because 'Source must echo the -Source argument, proving no URL substitution occurred'
        $result.source | Should -Not -Match 'download\.microsoft\.com' `
            -Because 'live Microsoft URL must not appear when a local fixture was supplied'
    }
}
