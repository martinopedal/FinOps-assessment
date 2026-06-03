function Get-FinOpsInfo {
    <#
    .SYNOPSIS
        Reports module version, read-only posture, and in-scope surfaces.

    .DESCRIPTION
        The PowerShell equivalent of the Python ``finops-assess info``
        subcommand. Performs no cloud calls itself. The read-only scope
        guard (Assert-FinOpsReadOnlyScope / Test-FinOpsReadOnlyScope) is
        enforced at the credential boundary by live collectors for all
        four surfaces (Graph, ARM, GitHub, and Azure DevOps). The
        structured ``ScopeGuard`` field reports per-surface coverage and
        enforcement honestly via the ``EnforcedBySurface`` sub-map and
        ``Enforced='all-surfaces'`` once all collector paths are guarded.
        ``RuntimeScopeGuardEnforced`` remains ``$true``. The Azure Resource
        Manager
        limitation (RBAC-side; cannot be proven from token claims) is
        called out explicitly in the same map.

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
        Enforced      = 'all-surfaces'
        DefaultPolicy = 'fail-closed-on-write-or-unknown'
        EnforcedBySurface = [pscustomobject]@{
            Graph                = $true
            AzureResourceManager = $true
            GitHub               = $true
            AzureDevOps          = $true
        }
        Coverage      = [pscustomobject]@{
            GraphDelegated       = 'claims:scp'
            GraphAppOnly         = 'claims:roles'
            AzureDevOps          = 'claims:scp'
            GitHubClassicScopes  = 'scopes:X-OAuth-Scopes'
            GitHubFineGrainedPat = 'unsupported:fail-closed'
            AzureResourceManager = 'operator-attested via two-key consent; RBAC introspection deferred'
        }
    }

    [pscustomobject]@{
        ModuleVersion              = $manifest.ModuleVersion
        ReferencePackageVersion    = $referencePackageVersion
        SupportedPowerShellVersion = $manifest.PowerShellVersion
        Surfaces                   = @('Microsoft 365', 'Azure', 'GitHub', 'Azure DevOps')
        ReadOnly                   = $true
        RuntimeScopeGuardEnforced  = @(
            $scopeGuard.EnforcedBySurface.Graph,
            $scopeGuard.EnforcedBySurface.AzureResourceManager,
            $scopeGuard.EnforcedBySurface.GitHub,
            $scopeGuard.EnforcedBySurface.AzureDevOps
        ) -contains $true
        ScopeGuard                 = $scopeGuard
        PostureStatement           = 'Read-only by design. Live collectors enforce Assert-FinOpsReadOnlyScope at the credential boundary for all four surfaces: Graph, AzureResourceManager, GitHub, AzureDevOps. ARM read-only is operator-attested via two-key consent (-AcceptArmRbacRisk + FINOPS_ACCEPT_ARM_RBAC_RISK=1); RBAC cannot be proven from token claims. GitHub fine-grained PATs and ADO PATs are operator-attested when -AllowUnknownScopes is used; classic GitHub PATs and ADO bearer tokens are certifiable from claims/headers. Phase 6 live-collector parity is complete.'
    }
}
