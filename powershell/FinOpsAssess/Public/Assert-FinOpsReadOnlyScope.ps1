function Assert-FinOpsReadOnlyScope {
    <#
    .SYNOPSIS
        Refuses to proceed unless a credential is provably read-only.

    .DESCRIPTION
        The load-bearing runtime scope guard (docs/plan.md sec.4.1 / sec.9). Given
        a JWT access token or an explicit list of granted scopes, it throws a
        terminating error if ANY scope is write-capable, or -- fail-closed by
        default -- if any scope is UNKNOWN or the credential's claims are
        insufficient to certify read-only (e.g. an Azure Resource Manager
        token, whose write capability is RBAC-side and not in claims).

        This guard is intended to be called by every credential-bearing code
        path BEFORE the credential is used. No such paths ship yet (the live
        collectors land in Phase 6), so the module advertises
        RuntimeScopeGuardEnforced = $false even though the guard itself is
        implemented and tested here.

    .PARAMETER AccessToken
        A JWT access token to introspect.

    .PARAMETER Scope
        An explicit list of granted scope strings.

    .PARAMETER Surface
        Optional surface hint when asserting against an explicit -Scope list.

    .PARAMETER AllowUnknownScopes
        Opt-in override that downgrades UNKNOWN scopes (and claim-insufficient
        credentials) from a hard refusal to a loud warning. WRITE scopes are
        ALWAYS refused regardless of this switch. Using this switch is a
        documented, deliberate weakening of the sec.9 read-only guarantee.

    .EXAMPLE
        Assert-FinOpsReadOnlyScope -Scope 'read:org'

    .EXAMPLE
        Assert-FinOpsReadOnlyScope -AccessToken $graphToken
    #>
    [CmdletBinding(DefaultParameterSetName = 'Token')]
    [OutputType([void])]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Token')]
        [string] $AccessToken,

        [Parameter(Mandatory, ParameterSetName = 'Scope')]
        [AllowEmptyCollection()]
        [string[]] $Scope,

        [Parameter(ParameterSetName = 'Scope')]
        [ValidateSet('Graph', 'AzureResourceManager', 'AzureDevOps', 'GitHub', 'Unspecified')]
        [string] $Surface = 'Unspecified',

        [switch] $AllowUnknownScopes
    )

    $result = if ($PSCmdlet.ParameterSetName -eq 'Token') {
        Test-FinOpsReadOnlyScope -AccessToken $AccessToken
    } else {
        Test-FinOpsReadOnlyScope -Scope $Scope -Surface $Surface
    }

    # WRITE scopes are an unconditional refusal.
    if ($result.WriteScopes.Count -gt 0) {
        throw "Read-only scope guard refused: the credential carries write/admin scope(s): $($result.WriteScopes -join ', '). This tool is read-only by construction and will not run with a write-capable credential."
    }

    # Fail-closed on UNKNOWN scopes / claim-insufficient credentials unless
    # the operator explicitly opts out.
    $cannotCertify = ($result.UnknownScopes.Count -gt 0) -or (-not $result.ClaimsSufficient)
    if ($cannotCertify) {
        $reasons = @()
        if ($result.UnknownScopes.Count -gt 0) {
            $reasons += "unrecognised scope(s): $($result.UnknownScopes -join ', ')"
        }
        if (-not $result.ClaimsSufficient) {
            if ($result.Surface -eq 'AzureResourceManager') {
                $reasons += 'Azure Resource Manager token: read-only cannot be proven from token claims (RBAC-side); claim introspection is insufficient for this surface'
            } else {
                $reasons += 'credential exposed no permission claims to inspect'
            }
        }
        $detail = $reasons -join '; '

        if ($AllowUnknownScopes) {
            Write-Warning "Read-only scope guard could not fully certify the credential ($detail). Proceeding because -AllowUnknownScopes was supplied; this is a deliberate weakening of the read-only guarantee."
        } else {
            throw "Read-only scope guard refused (fail-closed): $detail. Re-run with a credential whose read-only scopes are recognised, or pass -AllowUnknownScopes to override at your own risk."
        }
    }
}
