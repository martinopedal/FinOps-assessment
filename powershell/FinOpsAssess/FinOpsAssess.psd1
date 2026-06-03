@{
    # Pinned in lockstep with the Python package version
    # (src/finops_assess/__init__.py __version__). A Pester test and
    # Test-FinOpsConfiguration assert the two never drift.
    ModuleVersion          = '0.1.0'

    RootModule             = 'FinOpsAssess.psm1'
    GUID                   = 'b1e7c0de-5a4f-4c2b-9d3e-7a6f8c2d1e90'
    Author                 = 'FinOps-assessment contributors'
    CompanyName            = 'FinOps-assessment'
    Copyright              = '(c) FinOps-assessment contributors. MIT-licensed.'
    Description            = 'Native PowerShell engine (side-by-side with the Python tool) for the read-only FinOps assessment. Phase 0: module skeleton, info, and configuration self-test. No cloud collectors or mutation paths.'

    # PowerShell 7.2+ only. Windows PowerShell 5.1 is unsupported and
    # carries no parity guarantee (materially different JSON, encoding,
    # TLS, and class behaviour).
    PowerShellVersion      = '7.2'
    CompatiblePSEditions   = @('Core')

    FunctionsToExport      = @('Assert-FinOpsReadOnlyScope', 'Get-FinOpsInfo', 'Invoke-FinOpsAssessment', 'Invoke-FinOpsTriage', 'Test-FinOpsConfiguration', 'Test-FinOpsReadOnlyScope')
    CmdletsToExport        = @()
    VariablesToExport      = @()
    AliasesToExport        = @()

    PrivateData = @{
        PSData = @{
            Tags         = @('FinOps', 'Azure', 'Microsoft365', 'GitHub', 'AzureDevOps', 'ReadOnly', 'Assessment')
            ProjectUri   = 'https://github.com/martinopedal/FinOps-assessment'
            LicenseUri   = 'https://github.com/martinopedal/FinOps-assessment/blob/main/LICENSE'
            ReleaseNotes = 'Phase 0 scaffold: module skeleton, Get-FinOpsInfo, Test-FinOpsConfiguration, version-lock to the Python package, and CI (PSScriptAnalyzer + Pester). Runtime read-only scope enforcement is not yet implemented.'
        }
    }
}
