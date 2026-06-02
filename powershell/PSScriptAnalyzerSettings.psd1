@{
    # PSScriptAnalyzer configuration for the PowerShell engine. The CI
    # step (.github/workflows/ci.yml :: lint-and-test-powershell) treats
    # any Error or Warning surfaced here as a build failure.
    Severity            = @('Error', 'Warning')
    IncludeDefaultRules = $true

    # Enforce read-only, injection-safe style. PSAvoidUsingInvokeExpression
    # is a default rule (banning Invoke-Expression); it is reinforced by
    # the Pester "read-only tripwire" test, which also scans for cloud
    # mutation cmdlets and *.ReadWrite.* literals.
    ExcludeRules        = @()
}
