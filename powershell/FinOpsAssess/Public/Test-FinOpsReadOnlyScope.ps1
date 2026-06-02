function Test-FinOpsReadOnlyScope {
    <#
    .SYNOPSIS
        Classifies a credential's granted scopes as read-only or write-capable.

    .DESCRIPTION
        Non-throwing companion to Assert-FinOpsReadOnlyScope. Performs the
        actual token-claim introspection required by docs/plan.md sec.1.7a
        criterion 9: given a JWT access token it inspects the `aud`, `scp`
        (delegated) and `roles` (application) claims; given an explicit list
        of granted scope strings (e.g. a GitHub X-OAuth-Scopes header) it
        classifies each one.

        Classification is pattern-based for the WRITE decision, so a novel or
        renamed write scope is still caught. WRITE always wins over READ.

        Azure Resource Manager (ARM) write capability is RBAC-side and is NOT
        present in token claims; ARM-audience tokens are therefore reported
        with ClaimsSufficient = $false (the guard cannot certify them
        read-only from claims alone -- that lands with the Phase-6 collectors'
        RBAC introspection).

    .PARAMETER AccessToken
        A JWT access token to introspect (Graph / ARM / Azure DevOps).

    .PARAMETER Scope
        An explicit list of granted scope strings (e.g. GitHub OAuth scopes).
        An empty list cannot be certified read-only (ClaimsSufficient =
        $false) -- this safely covers GitHub fine-grained PATs whose
        permissions are not exposed as scope strings.

    .PARAMETER Surface
        Optional surface hint when classifying an explicit -Scope list.

    .OUTPUTS
        [pscustomobject] with IsReadOnly, Surface, ClaimSource,
        ClaimsSufficient, WriteScopes, ReadScopes, UnknownScopes, Scopes.

    .EXAMPLE
        Test-FinOpsReadOnlyScope -Scope 'read:org','read:packages'
    #>
    [CmdletBinding(DefaultParameterSetName = 'Token')]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Token')]
        [string] $AccessToken,

        [Parameter(Mandatory, ParameterSetName = 'Scope')]
        [AllowEmptyCollection()]
        [string[]] $Scope,

        [Parameter(ParameterSetName = 'Scope')]
        [ValidateSet('Graph', 'AzureResourceManager', 'AzureDevOps', 'GitHub', 'Unspecified')]
        [string] $Surface = 'Unspecified'
    )

    $policy = Get-FinOpsReadOnlyScopePolicy

    $surface = $Surface
    $claimSource = 'scope-parameter'
    $claimsSufficient = $true
    [string[]] $scopes = @()

    if ($PSCmdlet.ParameterSetName -eq 'Token') {
        $claims = Get-FinOpsTokenClaim -AccessToken $AccessToken
        $names = @($claims.PSObject.Properties.Name)

        # Derive the surface from the audience claim.
        $surface = 'Unspecified'
        if ($names -contains 'aud') {
            $aud = [string]$claims.aud
            foreach ($entry in $policy.AudienceSurfaces) {
                foreach ($pattern in $entry.Patterns) {
                    if ($aud -match $pattern) { $surface = $entry.Surface; break }
                }
                if ($surface -ne 'Unspecified') { break }
            }
        }

        # Delegated scopes live in `scp` (space-delimited string or array);
        # application permissions live in the `roles` array.
        $sources = @()
        if ($names -contains 'scp') {
            $scpValue = $claims.scp
            if ($scpValue -is [string]) {
                $scopes += @($scpValue -split '\s+' | Where-Object { $_ })
            } else {
                $scopes += @($scpValue | ForEach-Object { [string]$_ } | Where-Object { $_ })
            }
            if (@($scopes).Count -gt 0) { $sources += 'scp' }
        }
        if ($names -contains 'roles') {
            $roleValues = @($claims.roles | ForEach-Object { [string]$_ } | Where-Object { $_ })
            if ($roleValues.Count -gt 0) {
                $scopes += $roleValues
                $sources += 'roles'
            }
        }
        $claimSource = if ($sources.Count -gt 0) { $sources -join '+' } else { 'none' }

        # ARM tokens cannot be certified read-only from claims (RBAC-side).
        if ($surface -eq 'AzureResourceManager') {
            $claimsSufficient = $false
        } elseif (@($scopes).Count -eq 0) {
            # A token with no permission claims on a resource surface cannot
            # be certified read-only.
            $claimsSufficient = $false
        }
    } else {
        $scopes = @($Scope | Where-Object { $_ })
        if (@($scopes).Count -eq 0) {
            # Empty granted-scope list (e.g. fine-grained PAT): cannot certify.
            $claimsSufficient = $false
        }
    }

    $writeScopes = [System.Collections.Generic.List[string]]::new()
    $readScopes = [System.Collections.Generic.List[string]]::new()
    $unknownScopes = [System.Collections.Generic.List[string]]::new()

    foreach ($s in @($scopes)) {
        # A token-shaped string passed as a scope is not a scope: fail-closed.
        $isOpaque = $false
        foreach ($prefix in $policy.OpaqueTokenPrefixes) {
            if ($s.StartsWith($prefix)) { $isOpaque = $true; break }
        }
        if ($isOpaque) { $unknownScopes.Add($s); continue }

        $isWrite = $false
        foreach ($pattern in $policy.WritePatterns) {
            if ($s -match $pattern) { $isWrite = $true; break }
        }
        if ($isWrite) { $writeScopes.Add($s); continue }

        $isRead = $false
        foreach ($pattern in $policy.ReadPatterns) {
            if ($s -match $pattern) { $isRead = $true; break }
        }
        if ($isRead) { $readScopes.Add($s) } else { $unknownScopes.Add($s) }
    }

    $isReadOnly = ($writeScopes.Count -eq 0) -and ($unknownScopes.Count -eq 0) -and $claimsSufficient

    [pscustomobject]@{
        IsReadOnly       = $isReadOnly
        Surface          = $surface
        ClaimSource      = $claimSource
        ClaimsSufficient = $claimsSufficient
        WriteScopes      = $writeScopes.ToArray()
        ReadScopes       = $readScopes.ToArray()
        UnknownScopes    = $unknownScopes.ToArray()
        Scopes           = @($scopes)
    }
}
