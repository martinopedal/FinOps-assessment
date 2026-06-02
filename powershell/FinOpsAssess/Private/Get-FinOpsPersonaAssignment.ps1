function Get-FinOpsPersonaAssignment {
    <#
    .SYNOPSIS
        Assigns each principal in a normalised dataset to exactly one persona.

    .DESCRIPTION
        Native PowerShell port of ``finops_assess.persona.assign_personas``.
        Persona assignment is rule-independent, so it ships in the report
        contract phase (it populates ``summary.persona_distribution``) ahead
        of any savings-rule logic.

        Signal priority (highest first), matching the Python engine exactly:

          1. Explicit override in ``overrides.yaml`` (confidence ``high``).
          2. Job-title regex match (confidence ``high``).
          3. Group-membership regex match (confidence ``medium``).
          4. Usage / type fallback (confidence ``low``): guests -> ``guest``;
             service / shared-mailbox / disabled / ``svc-*`` principals ->
             ``service_account``; otherwise ``information_worker``; last
             resort the first declared persona.

        Regex parity is load-bearing. The Python engine uses ``re.search``
        (find anywhere, case-sensitive, honouring inline ``(?i)``). The
        ported engine therefore uses ``[regex]::IsMatch`` (also unanchored
        and case-sensitive by default, also honouring inline ``(?i)``)
        rather than PowerShell's ``-match`` operator, which is
        case-insensitive by default and would diverge on any pattern that
        omits ``(?i)``.

    .PARAMETER Dataset
        A normalised dataset as returned by ``Get-FinOpsNormalizedDataset``
        (carries ``users`` and ``overrides``).

    .PARAMETER Personas
        The persona definitions, in Python loader order. Defaults to the
        shared data projection.

    .OUTPUTS
        [System.Collections.Specialized.OrderedDictionary] keyed by
        principal; each value is an ordered map with ``principal``,
        ``persona_id``, ``matched_by``, and ``confidence``.

    .EXAMPLE
        $ds = Get-FinOpsNormalizedDataset -InputDirectory ./tenant
        $assignments = Get-FinOpsPersonaAssignment -Dataset $ds
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [object] $Dataset,

        [Parameter()]
        [object[]] $Personas = (Get-FinOpsDataProjection).Personas
    )

    if (-not $Personas -or @($Personas).Count -eq 0) {
        throw 'at least one persona must be defined'
    }

    $personasById = [ordered]@{}
    foreach ($persona in $Personas) {
        $personasById[$persona.id] = $persona
    }
    # Python's last-resort fallback is ``next(iter(personas_by_id))`` -- the
    # first declared persona id.
    $firstPersonaId = @($personasById.Keys)[0]

    $overrides = $Dataset.overrides

    $assignments = [ordered]@{}
    foreach ($user in @($Dataset.users)) {
        $principal = $user.principal

        $override = $null
        if ($overrides -and $overrides.Contains($principal)) {
            $override = $overrides[$principal]
        }
        if ($override) {
            if (-not $personasById.Contains($override)) {
                throw "override for $principal references unknown persona '$override'"
            }
            $assignments[$principal] = [ordered]@{
                principal  = $principal
                persona_id = $override
                matched_by = 'override'
                confidence = 'high'
            }
            continue
        }

        $titleMatch = Get-FinOpsTitleMatch -User $user -Personas $Personas
        if ($titleMatch) {
            $assignments[$principal] = [ordered]@{
                principal  = $principal
                persona_id = $titleMatch
                matched_by = 'title'
                confidence = 'high'
            }
            continue
        }

        $groupMatch = Get-FinOpsGroupMatch -User $user -Personas $Personas
        if ($groupMatch) {
            $assignments[$principal] = [ordered]@{
                principal  = $principal
                persona_id = $groupMatch
                matched_by = 'group'
                confidence = 'medium'
            }
            continue
        }

        $assignments[$principal] = [ordered]@{
            principal  = $principal
            persona_id = Get-FinOpsFallbackPersona -User $user -PersonasById $personasById -FirstPersonaId $firstPersonaId
            matched_by = 'fallback'
            confidence = 'low'
        }
    }

    $assignments
}

function Get-FinOpsTitleMatch {
    <#
    .SYNOPSIS
        Returns the id of the first persona whose title pattern matches the user.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $User,
        [Parameter(Mandatory)] [object[]] $Personas
    )

    $title = $User.job_title
    if ([string]::IsNullOrEmpty($title)) {
        return $null
    }
    foreach ($persona in $Personas) {
        foreach ($pattern in @($persona.title_patterns)) {
            if ([regex]::IsMatch($title, $pattern)) {
                return $persona.id
            }
        }
    }
    return $null
}

function Get-FinOpsGroupMatch {
    <#
    .SYNOPSIS
        Returns the id of the first persona whose group pattern matches a
        group the user belongs to.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $User,
        [Parameter(Mandatory)] [object[]] $Personas
    )

    $groups = @($User.groups)
    if ($groups.Count -eq 0) {
        return $null
    }
    foreach ($persona in $Personas) {
        foreach ($group in $groups) {
            foreach ($pattern in @($persona.group_patterns)) {
                if ([regex]::IsMatch($group, $pattern)) {
                    return $persona.id
                }
            }
        }
    }
    return $null
}

function Test-FinOpsServicePrincipal {
    <#
    .SYNOPSIS
        Returns $true when the principal's local part looks like a service account.

    .DESCRIPTION
        Mirrors Python's ``_looks_like_service_principal``: a leading
        ``svc-`` / ``svc_`` (case-insensitive) on the local part of the
        principal (the portion before ``@``).
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)] [string] $Principal
    )

    $local = $Principal.Split('@', 2)[0]
    return [regex]::IsMatch($local, '^svc[-_]', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

function Get-FinOpsFallbackPersona {
    <#
    .SYNOPSIS
        Resolves the usage/type fallback persona for a user.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $User,
        [Parameter(Mandatory)] [System.Collections.Specialized.OrderedDictionary] $PersonasById,
        [Parameter(Mandatory)] [string] $FirstPersonaId
    )

    if ($User.user_type -eq 'guest' -and $PersonasById.Contains('guest')) {
        return 'guest'
    }
    if (($User.user_type -in @('service', 'shared_mailbox')) -and $PersonasById.Contains('service_account')) {
        return 'service_account'
    }
    if (-not $User.account_enabled -and $PersonasById.Contains('service_account')) {
        return 'service_account'
    }
    if ((Test-FinOpsServicePrincipal -Principal $User.principal) -and $PersonasById.Contains('service_account')) {
        return 'service_account'
    }
    if ($PersonasById.Contains('information_worker')) {
        return 'information_worker'
    }
    return $FirstPersonaId
}
