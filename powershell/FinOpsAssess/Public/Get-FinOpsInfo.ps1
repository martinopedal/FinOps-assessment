function Get-FinOpsInfo {
    <#
    .SYNOPSIS
        Reports module version, read-only posture, and in-scope surfaces.

    .DESCRIPTION
        The PowerShell equivalent of the Python ``finops-assess info``
        subcommand. Performs no cloud calls. The read-only scope guard
        (Assert-FinOpsReadOnlyScope / Test-FinOpsReadOnlyScope) IS
        implemented and unit-tested, but ``RuntimeScopeGuardEnforced`` is
        reported as ``$false`` because no credential-bearing code path ships
        yet (the live collectors land in Phase 6) for the guard to be
        enforced at. The structured ``ScopeGuard`` field reports per-surface
        coverage honestly, including the Azure Resource Manager limitation.

    .OUTPUTS
        [pscustomobject] with module/version/posture fields.

    .EXAMPLE
        Get-FinOpsInfo
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param()

    $manifest = Import-PowerShellDataFile -Path (Join-Path $script:ModuleRoot 'FinOpsAssess.psd1')

    $referencePackageVersion = $null
    try {
        $referencePackageVersion = Get-FinOpsPackageVersion
    } catch {
        Write-Verbose "Reference package version unavailable: $($_.Exception.Message)"
    }

    $scopeGuard = [pscustomobject]@{
        Available     = $true
        Enforced      = $false  # no live credential path exists yet (Phase 6)
        DefaultPolicy = 'fail-closed-on-write-or-unknown'
        Coverage      = [pscustomobject]@{
            GraphDelegated       = 'claims:scp'
            GraphAppOnly         = 'claims:roles'
            AzureDevOps          = 'claims:scp'
            GitHubClassicScopes  = 'scopes:X-OAuth-Scopes'
            GitHubFineGrainedPat = 'unsupported:fail-closed'
            AzureResourceManager = 'insufficient:token-claims; RBAC introspection required (Phase 6)'
        }
    }

    [pscustomobject]@{
        ModuleVersion              = $manifest.ModuleVersion
        ReferencePackageVersion    = $referencePackageVersion
        SupportedPowerShellVersion = $manifest.PowerShellVersion
        Surfaces                   = @('Microsoft 365', 'Azure', 'GitHub', 'Azure DevOps')
        ReadOnly                   = $true
        RuntimeScopeGuardEnforced  = $false
        ScopeGuard                 = $scopeGuard
        PostureStatement           = 'Read-only by design: no cloud calls, collectors, or mutation paths ship in this phase. The read-only scope guard is implemented and unit-tested (Assert-FinOpsReadOnlyScope), but enforcement at the credential boundary lands with the Phase-6 collectors; until then RuntimeScopeGuardEnforced is $false. ARM read-only cannot be proven from token claims (RBAC-side) and is refused fail-closed. Do not treat this module as security-complete.'
    }
}
