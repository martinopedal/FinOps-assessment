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
    Description            = 'FinOpsAssess is a read-only FinOps assessment module for the Microsoft ecosystem. It audits licensing, identity, usage, and cost across Microsoft 365 (Graph), Azure (ARM), GitHub, and Azure DevOps, and emits evidence-backed right-sizing and savings findings. Documentation: https://github.com/martinopedal/FinOps-assessment/blob/main/docs/powershell.md'

    # PowerShell 7.2+ only. Windows PowerShell 5.1 is unsupported and
    # carries no parity guarantee (materially different JSON, encoding,
    # TLS, and class behaviour).
    PowerShellVersion      = '7.2'
    CompatiblePSEditions   = @('Core')

    FunctionsToExport      = @('Assert-FinOpsReadOnlyScope', 'Export-FinOpsFocusAligned', 'Export-FinOpsPlaybook', 'Get-FinOpsInfo', 'Invoke-FinOpsAssessment', 'Invoke-FinOpsLiveCollection', 'Invoke-FinOpsTriage', 'Test-FinOpsCatalogCoverage', 'Test-FinOpsConfiguration', 'Test-FinOpsReadOnlyScope')
    CmdletsToExport        = @()
    VariablesToExport      = @()
    AliasesToExport        = @()

    # RequiredModules intentionally omitted: Az.Accounts is soft-detected at runtime.
    PrivateData = @{
        PSData = @{
            Tags         = @('FinOps', 'Azure', 'Microsoft365', 'M365', 'GitHub', 'AzureDevOps', 'ADO', 'ReadOnly', 'Assessment', 'Cost', 'Audit', 'Licensing')
            ProjectUri   = 'https://github.com/martinopedal/FinOps-assessment'
            LicenseUri   = 'https://github.com/martinopedal/FinOps-assessment/blob/main/LICENSE'
            ReleaseNotes = '0.1.0 ships the first PowerShell Gallery release of FinOpsAssess with native PowerShell parity and full read-only posture. Phase 6 all-surfaces enforcement is complete across Microsoft 365 Graph, Azure ARM, GitHub, and Azure DevOps live collectors. The module stays version-locked to the Python package at 0.1.0.'
        }
    }
}
