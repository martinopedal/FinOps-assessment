function Get-FinOpsInfo {
    <#
    .SYNOPSIS
        Reports module version, read-only posture, and in-scope surfaces.

    .DESCRIPTION
        The PowerShell equivalent of the Python ``finops-assess info``
        subcommand. Performs no cloud calls. In Phase 0 this is an
        informational cmdlet only: it advertises the read-only design
        posture but deliberately reports ``RuntimeScopeGuardEnforced =
        $false`` because runtime credential-scope enforcement is not yet
        implemented (deferred to the dedicated scope-guard PR).

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

    [pscustomobject]@{
        ModuleVersion              = $manifest.ModuleVersion
        ReferencePackageVersion    = $referencePackageVersion
        SupportedPowerShellVersion = $manifest.PowerShellVersion
        Surfaces                   = @('Microsoft 365', 'Azure', 'GitHub', 'Azure DevOps')
        ReadOnly                   = $true
        RuntimeScopeGuardEnforced  = $false
        PostureStatement           = 'Phase-0 module: no cloud calls, collectors, or mutation paths. Read-only by design. Runtime credential-scope enforcement is NOT yet implemented (deferred to the scope-guard PR); do not treat this module as security-complete.'
    }
}
