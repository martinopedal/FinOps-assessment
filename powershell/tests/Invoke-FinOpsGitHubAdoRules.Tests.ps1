#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

# Phase-4 conformance: GitHub + ADO rule-slice (layer-5 findings + CSV).
# Tests in this file are intentionally isolated from the shared
# Invoke-FinOpsAssessment.Tests.ps1 to avoid parallel-agent merge conflicts.

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
    $script:DemoDir = Join-Path $script:RepoRoot 'src' 'finops_assess' 'demo'
    $script:FixedSalt = 'conformance-fixed-salt-v1'
    $script:Canonicaliser = Join-Path $script:RepoRoot 'scripts' 'canonicalize_report.py'

    $script:GhJsonGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-report-github.canonical.json'
    $script:GhCsvGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-report-github.csv'
    $script:AdoJsonGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-report-ado.canonical.json'
    $script:AdoCsvGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-report-ado.csv'

    Get-Module FinOpsAssess | Remove-Module -Force -ErrorAction SilentlyContinue
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Get-Module FinOpsAssess | Remove-Module -Force -ErrorAction SilentlyContinue
}

Describe 'GitHub rule-slice conformance (layer-5 findings + CSV)' {

    BeforeAll {
        $script:GhOutFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-gh-{0}.json" -f ([guid]::NewGuid()))
        $script:GhCsvFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-gh-{0}.csv" -f ([guid]::NewGuid()))
        $prev = $env:SOURCE_DATE_EPOCH
        try {
            $env:SOURCE_DATE_EPOCH = '0'
            Invoke-FinOpsAssessment -InputDirectory $script:DemoDir -OutputPath $script:GhOutFile `
                -PiiSalt $script:FixedSalt -WarningAction SilentlyContinue | Out-Null
            Invoke-FinOpsAssessment -InputDirectory $script:DemoDir -OutputPath $script:GhCsvFile `
                -Format csv -PiiSalt $script:FixedSalt -WarningAction SilentlyContinue | Out-Null
        } finally {
            if ($null -eq $prev) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue }
            else { $env:SOURCE_DATE_EPOCH = $prev }
        }
    }

    AfterAll {
        Remove-Item -LiteralPath $script:GhOutFile -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $script:GhCsvFile -ErrorAction SilentlyContinue
    }

    It 'ships both committed GitHub goldens' {
        Test-Path -LiteralPath $script:GhJsonGolden | Should -BeTrue
        Test-Path -LiteralPath $script:GhCsvGolden | Should -BeTrue
    }

    It 'canonical GitHub projection byte-equals the Python findings golden' {
        $canon = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-gh-{0}.canonical.json" -f ([guid]::NewGuid()))
        try {
            & python $script:Canonicaliser --profile report-github-v1 --input $script:GhOutFile --output $canon
            $LASTEXITCODE | Should -Be 0 -Because 'the shared canonicaliser must succeed'
            $actual = [System.IO.File]::ReadAllBytes($canon)
            $expected = [System.IO.File]::ReadAllBytes($script:GhJsonGolden)
            [System.Linq.Enumerable]::SequenceEqual($actual, $expected) |
                Should -BeTrue -Because 'PS GitHub findings must match the committed Python golden'
        } finally {
            Remove-Item -LiteralPath $canon -ErrorAction SilentlyContinue
        }
    }

    It 'flat GitHub CSV byte-equals the Python csv_reporter golden' {
        # Filter the combined CSV to GH.* rows, then byte-compare.
        $raw = [System.IO.File]::ReadAllText($script:GhCsvFile, [System.Text.Encoding]::UTF8)
        $lines = $raw -split "`n"
        $header = $lines[0]
        $ghLines = @($lines | Where-Object { $_ -match '^GH\.' })
        $ghCsv = ($header, ($ghLines -join "`n") -join "`n") + "`n"
        $actual = [System.Text.Encoding]::UTF8.GetBytes($ghCsv)
        $expected = [System.IO.File]::ReadAllBytes($script:GhCsvGolden)
        [System.Linq.Enumerable]::SequenceEqual($actual, $expected) |
            Should -BeTrue -Because 'PS GitHub CSV writer must match the Python csv_reporter bytes'
    }

    It 'report contains all four GitHub rule_counts' {
        $report = Get-Content -LiteralPath $script:GhOutFile -Raw -Encoding utf8 | ConvertFrom-Json
        $counts = $report.summary.rule_counts
        $counts.'GH.INACTIVE_SEAT_90D' | Should -BeGreaterOrEqual 1
        $counts.'GH.COPILOT_INACTIVE_30D' | Should -BeGreaterOrEqual 1
        $counts.'GH.GHAS_OVER_PROVISIONED' | Should -BeGreaterOrEqual 1
        $counts.'GH.RUNNER_TIER_MISMATCH' | Should -BeGreaterOrEqual 1
    }
}

Describe 'ADO rule-slice conformance (layer-5 findings + CSV)' {

    BeforeAll {
        $script:AdoOutFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-ado-{0}.json" -f ([guid]::NewGuid()))
        $script:AdoCsvFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-ado-{0}.csv" -f ([guid]::NewGuid()))
        $prev = $env:SOURCE_DATE_EPOCH
        try {
            $env:SOURCE_DATE_EPOCH = '0'
            Invoke-FinOpsAssessment -InputDirectory $script:DemoDir -OutputPath $script:AdoOutFile `
                -PiiSalt $script:FixedSalt -WarningAction SilentlyContinue | Out-Null
            Invoke-FinOpsAssessment -InputDirectory $script:DemoDir -OutputPath $script:AdoCsvFile `
                -Format csv -PiiSalt $script:FixedSalt -WarningAction SilentlyContinue | Out-Null
        } finally {
            if ($null -eq $prev) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue }
            else { $env:SOURCE_DATE_EPOCH = $prev }
        }
    }

    AfterAll {
        Remove-Item -LiteralPath $script:AdoOutFile -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $script:AdoCsvFile -ErrorAction SilentlyContinue
    }

    It 'ships both committed ADO goldens' {
        Test-Path -LiteralPath $script:AdoJsonGolden | Should -BeTrue
        Test-Path -LiteralPath $script:AdoCsvGolden | Should -BeTrue
    }

    It 'canonical ADO projection byte-equals the Python findings golden' {
        $canon = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-ado-{0}.canonical.json" -f ([guid]::NewGuid()))
        try {
            & python $script:Canonicaliser --profile report-ado-v1 --input $script:AdoOutFile --output $canon
            $LASTEXITCODE | Should -Be 0 -Because 'the shared canonicaliser must succeed'
            $actual = [System.IO.File]::ReadAllBytes($canon)
            $expected = [System.IO.File]::ReadAllBytes($script:AdoJsonGolden)
            [System.Linq.Enumerable]::SequenceEqual($actual, $expected) |
                Should -BeTrue -Because 'PS ADO findings must match the committed Python golden'
        } finally {
            Remove-Item -LiteralPath $canon -ErrorAction SilentlyContinue
        }
    }

    It 'flat ADO CSV byte-equals the Python csv_reporter golden' {
        # Filter the combined CSV to ADO.* rows, then byte-compare.
        $raw = [System.IO.File]::ReadAllText($script:AdoCsvFile, [System.Text.Encoding]::UTF8)
        $lines = $raw -split "`n"
        $header = $lines[0]
        $adoLines = @($lines | Where-Object { $_ -match '^ADO\.' })
        $adoCsv = ($header, ($adoLines -join "`n") -join "`n") + "`n"
        $actual = [System.Text.Encoding]::UTF8.GetBytes($adoCsv)
        $expected = [System.IO.File]::ReadAllBytes($script:AdoCsvGolden)
        [System.Linq.Enumerable]::SequenceEqual($actual, $expected) |
            Should -BeTrue -Because 'PS ADO CSV writer must match the Python csv_reporter bytes'
    }

    It 'report contains all four ADO rule_counts' {
        $report = Get-Content -LiteralPath $script:AdoOutFile -Raw -Encoding utf8 | ConvertFrom-Json
        $counts = $report.summary.rule_counts
        $counts.'ADO.INACTIVE_BASIC_90D' | Should -BeGreaterOrEqual 1
        $counts.'ADO.STAKEHOLDER_ELIGIBLE' | Should -BeGreaterOrEqual 1
        $counts.'ADO.PARALLEL_JOBS_OVER_PROVISIONED' | Should -BeGreaterOrEqual 1
        $counts.'ADO.TEST_PLANS_UNUSED' | Should -BeGreaterOrEqual 1
    }
}
