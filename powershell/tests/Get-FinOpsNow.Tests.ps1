#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsNow' {
    BeforeEach {
        $script:PrevOverride = $env:FINOPS_NOW_OVERRIDE
        Remove-Item Env:FINOPS_NOW_OVERRIDE -ErrorAction SilentlyContinue
    }

    AfterEach {
        if ($null -eq $script:PrevOverride) { Remove-Item Env:FINOPS_NOW_OVERRIDE -ErrorAction SilentlyContinue }
        else { $env:FINOPS_NOW_OVERRIDE = $script:PrevOverride }
    }

    It 'returns the fixed instant from FINOPS_NOW_OVERRIDE' {
        $env:FINOPS_NOW_OVERRIDE = '2025-06-01'
        $now = InModuleScope FinOpsAssess { Get-FinOpsNow }
        $now | Should -Be ([System.DateTimeOffset]'2025-06-01T00:00:00+00:00')
    }

    It 'returns current UTC time when override is absent' {
        $before = [System.DateTimeOffset]::UtcNow
        $now = InModuleScope FinOpsAssess { Get-FinOpsNow }
        $after = [System.DateTimeOffset]::UtcNow
        $now | Should -BeGreaterOrEqual $before
        $now | Should -BeLessOrEqual $after
    }

    It 'parses override with invariant yyyy-MM-dd and AssumeUniversal semantics' {
        $env:FINOPS_NOW_OVERRIDE = '2025-06-01'
        $now = InModuleScope FinOpsAssess { Get-FinOpsNow }
        $now.Offset.TotalHours | Should -Be 0
        $now.UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ssK') | Should -Be '2025-06-01T00:00:00Z'
    }

    It 'throws on malformed override values' {
        $env:FINOPS_NOW_OVERRIDE = '2025/06/01'
        { InModuleScope FinOpsAssess { Get-FinOpsNow } } | Should -Throw
    }
}
