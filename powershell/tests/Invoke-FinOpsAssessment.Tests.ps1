#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
    $script:DemoDir = Join-Path $script:RepoRoot 'src' 'finops_assess' 'demo'
    $script:PersonaGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-personas.json'
    $script:StructuralGolden = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-report-structural.canonical.json'
    $script:Canonicaliser = Join-Path $script:RepoRoot 'scripts' 'canonicalize_report.py'
    $script:ReportSchema = Join-Path $script:RepoRoot 'src' 'finops_assess' 'schemas' 'report.schema.json'

    Get-Module FinOpsAssess | Remove-Module -Force -ErrorAction SilentlyContinue
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Get-Module FinOpsAssess | Remove-Module -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsPersonaAssignment over the demo tenant (layer-2 conformance)' {

    It 'ships the committed persona golden fixture' {
        Test-Path -LiteralPath $script:PersonaGolden |
            Should -BeTrue -Because 'scripts/generate_ps_report_fixtures.py must have produced it'
    }

    It 'deep-equals the Python persona-assignment oracle' {
        $golden = Get-Content -LiteralPath $script:PersonaGolden -Raw -Encoding utf8 | ConvertFrom-Json
        $goldenPrincipals = @($golden.PSObject.Properties.Name)

        InModuleScope FinOpsAssess -Parameters @{ DemoDir = $script:DemoDir } {
            param($DemoDir)
            $script:Demo = Get-FinOpsNormalizedDataset -InputDirectory $DemoDir
            $script:Assignments = Get-FinOpsPersonaAssignment -Dataset $script:Demo
        }
        $assignments = InModuleScope FinOpsAssess { $script:Assignments }

        @($assignments.Keys).Count | Should -Be $goldenPrincipals.Count

        foreach ($principal in $goldenPrincipals) {
            $expected = $golden.$principal
            $actual = $assignments[$principal]
            $actual | Should -Not -BeNullOrEmpty -Because "PS must assign a persona to $principal"
            $actual.principal  | Should -BeExactly $expected.principal
            $actual.persona_id | Should -BeExactly $expected.persona_id
            $actual.matched_by | Should -BeExactly $expected.matched_by
            $actual.confidence | Should -BeExactly $expected.confidence
        }
    }

    It 'exercises the override, title, and fallback signal paths' {
        $golden = Get-Content -LiteralPath $script:PersonaGolden -Raw -Encoding utf8 | ConvertFrom-Json
        $matchedBy = @($golden.PSObject.Properties.Value | ForEach-Object { $_.matched_by } | Sort-Object -Unique)
        $matchedBy | Should -Contain 'override'
        $matchedBy | Should -Contain 'title'
        $matchedBy | Should -Contain 'fallback'
    }
}

Describe 'Get-FinOpsPersonaAssignment regex + fallback parity' {

    It 'uses case-sensitive matching so a non-(?i) pattern does not over-match' {
        InModuleScope FinOpsAssess {
            $user = [pscustomobject]@{
                principal = 'x@y.example'; job_title = 'ANALYST'; groups = @()
                user_type = 'member'; account_enabled = $true
            }
            # Python re.search('analyst', 'ANALYST') is None (case-sensitive);
            # the ported engine must agree (no inline (?i) here).
            Get-FinOpsTitleMatch -User $user -Personas @(
                [pscustomobject]@{ id = 'iw'; title_patterns = @('analyst'); group_patterns = @() }
            ) | Should -BeNullOrEmpty
        }
    }

    It 'honours an inline (?i) flag like Python does' {
        InModuleScope FinOpsAssess {
            $user = [pscustomobject]@{
                principal = 'x@y.example'; job_title = 'ANALYST'; groups = @()
                user_type = 'member'; account_enabled = $true
            }
            Get-FinOpsTitleMatch -User $user -Personas @(
                [pscustomobject]@{ id = 'iw'; title_patterns = @('(?i)analyst'); group_patterns = @() }
            ) | Should -Be 'iw'
        }
    }

    It 'treats svc- prefixed principals as service accounts when no stronger signal exists' {
        InModuleScope FinOpsAssess {
            Test-FinOpsServicePrincipal -Principal 'svc-backup@contoso.example' | Should -BeTrue
            Test-FinOpsServicePrincipal -Principal 'SVC_sync@contoso.example' | Should -BeTrue
            Test-FinOpsServicePrincipal -Principal 'service@contoso.example' | Should -BeFalse
        }
    }
}

Describe 'Build-FinOpsReport + report determinism' {

    It 'renders the SOURCE_DATE_EPOCH=0 timestamp identically to Python' {
        InModuleScope FinOpsAssess {
            $prev = $env:SOURCE_DATE_EPOCH
            try {
                $env:SOURCE_DATE_EPOCH = '0'
                Get-FinOpsGeneratedAt | Should -BeExactly '1970-01-01T00:00:00+00:00'
            } finally {
                if ($null -eq $prev) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue }
                else { $env:SOURCE_DATE_EPOCH = $prev }
            }
        }
    }

    It 'falls back to wall-clock UTC for a malformed epoch (no throw)' {
        InModuleScope FinOpsAssess {
            $prev = $env:SOURCE_DATE_EPOCH
            try {
                $env:SOURCE_DATE_EPOCH = 'not-a-number'
                Get-FinOpsGeneratedAt | Should -Match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$'
            } finally {
                if ($null -eq $prev) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue }
                else { $env:SOURCE_DATE_EPOCH = $prev }
            }
        }
    }

    It 'redacts the input path to its leaf when redaction is on' {
        InModuleScope FinOpsAssess {
            ConvertTo-FinOpsRedactedInput -InputPath '/Users/alice/customers/contoso/tenant' -RedactPii $true |
                Should -BeExactly '<redacted>/tenant'
            ConvertTo-FinOpsRedactedInput -InputPath '/tmp/tenant' -RedactPii $false |
                Should -BeExactly '/tmp/tenant'
        }
    }

    It 'records salt_mode=tenant_stable only when a salt is pinned' {
        InModuleScope FinOpsAssess -Parameters @{ DemoDir = $script:DemoDir } {
            param($DemoDir)
            $ds = Get-FinOpsNormalizedDataset -InputDirectory $DemoDir
            $assn = Get-FinOpsPersonaAssignment -Dataset $ds
            $perRun = Build-FinOpsReport -Dataset $ds -PersonaAssignments $assn -InputPath $DemoDir
            $perRun.run.salt_mode | Should -Be 'per_run'
            $stable = Build-FinOpsReport -Dataset $ds -PersonaAssignments $assn -InputPath $DemoDir -SaltMode 'tenant_stable'
            $stable.run.salt_mode | Should -Be 'tenant_stable'
            $stable.summary.salt_mode | Should -Be 'tenant_stable'
        }
    }

    It 'marks summary.pii_redaction=disabled only when redaction is off' {
        InModuleScope FinOpsAssess -Parameters @{ DemoDir = $script:DemoDir } {
            param($DemoDir)
            $ds = Get-FinOpsNormalizedDataset -InputDirectory $DemoDir
            $assn = Get-FinOpsPersonaAssignment -Dataset $ds
            $on = Build-FinOpsReport -Dataset $ds -PersonaAssignments $assn -InputPath $DemoDir -RedactPii $true
            $on.summary.Contains('pii_redaction') | Should -BeFalse
            $off = Build-FinOpsReport -Dataset $ds -PersonaAssignments $assn -InputPath $DemoDir -RedactPii $false
            $off.summary['pii_redaction'] | Should -Be 'disabled'
        }
    }
}

Describe 'JSON report contract (layer-4 schema + layer-5 canonical equality)' {

    BeforeAll {
        $script:OutFile = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-report-{0}.json" -f ([guid]::NewGuid()))
        $prev = $env:SOURCE_DATE_EPOCH
        try {
            $env:SOURCE_DATE_EPOCH = '0'
            Invoke-FinOpsAssessment -InputDirectory $script:DemoDir -OutputPath $script:OutFile -WarningAction SilentlyContinue | Out-Null
        } finally {
            if ($null -eq $prev) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue }
            else { $env:SOURCE_DATE_EPOCH = $prev }
        }
        $script:RawReport = Get-Content -LiteralPath $script:OutFile -Raw -Encoding utf8
    }

    AfterAll {
        Remove-Item -LiteralPath $script:OutFile -ErrorAction SilentlyContinue
    }

    It 'emits LF-only newlines' {
        $bytes = [System.IO.File]::ReadAllBytes($script:OutFile)
        ([System.Text.Encoding]::UTF8.GetString($bytes)) | Should -Not -Match "`r`n"
    }

    It 'validates against the shared report JSON schema (layer 4)' {
        $schema = Get-Content -LiteralPath $script:ReportSchema -Raw -Encoding utf8
        Test-Json -Json $script:RawReport -Schema $schema | Should -BeTrue
    }

    It 'canonical projection byte-equals the Python structural golden (layer 5)' {
        $canon = Join-Path ([System.IO.Path]::GetTempPath()) ("ps-report-{0}.canonical.json" -f ([guid]::NewGuid()))
        try {
            & python $script:Canonicaliser --profile report-structural-v1 --input $script:OutFile --output $canon
            $LASTEXITCODE | Should -Be 0 -Because 'the shared canonicaliser must succeed'
            $actual = [System.IO.File]::ReadAllBytes($canon)
            $expected = [System.IO.File]::ReadAllBytes($script:StructuralGolden)
            [System.Linq.Enumerable]::SequenceEqual($actual, $expected) |
                Should -BeTrue -Because 'PS structural projection must match the committed Python golden'
        } finally {
            Remove-Item -LiteralPath $canon -ErrorAction SilentlyContinue
        }
    }

    It 'reports every rule as skipped (no native rule impl yet)' {
        $report = $script:RawReport | ConvertFrom-Json
        @($report.summary.rules_skipped_no_impl).Count | Should -Be 28
        @($report.findings).Count | Should -Be 0
        $report.summary.total_findings | Should -Be 0
    }
}
