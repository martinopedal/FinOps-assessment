Set-StrictMode -Version Latest

# Engine helpers + rule runner -- native port of finops_assess.engine.
#
# Parity notes (load-bearing):
#  * All string comparisons and lookups use ORDINAL / case-SENSITIVE
#    semantics ([StringComparer]::Ordinal, -ceq) to match Python, whose
#    string comparisons are case-sensitive. PowerShell's defaults are
#    case-insensitive, which would silently diverge on SKU ids / feature
#    tags / signals.
#  * sorted() in Python is Unicode code-point (ordinal) order, so list
#    contents that Python builds with sorted() are sorted here with
#    Get-FinOpsOrdinalSorted, NOT Sort-Object (which is culture-sensitive).

# Feature implication map (engine.py _FEATURE_IMPLIES): holding the key
# feature also satisfies every value feature.
$script:FinOpsFeatureImplies = @{
    'mailbox.100gb'        = @('mailbox.100gb', 'mailbox.50gb', 'mailbox.2gb')
    'mailbox.50gb'         = @('mailbox.50gb', 'mailbox.2gb')
    'mailbox.2gb'          = @('mailbox.2gb')
    'office.desktop'       = @('office.desktop', 'office.web')
    'office.web'           = @('office.web')
    'teams.full'           = @('teams.full', 'teams.basic')
    'teams.basic'          = @('teams.basic')
    'sharepoint.advanced'  = @('sharepoint.advanced', 'sharepoint.full', 'sharepoint.read')
    'sharepoint.full'      = @('sharepoint.full', 'sharepoint.read')
    'sharepoint.read'      = @('sharepoint.read')
    'intune.mdm'           = @('intune.mdm', 'intune.mam')
    'intune.mam'           = @('intune.mam')
    'entra.p2'             = @('entra.p2', 'entra.p1')
    'entra.p1'             = @('entra.p1')
    'entra.p1.frontline'   = @('entra.p1.frontline')
    'defender.o365.p2'     = @('defender.o365.p2', 'defender.o365.p1')
    'defender.o365.p1'     = @('defender.o365.p1')
}

# Feature-tag prefix -> surface (engine.py _FEATURE_SURFACE_PREFIXES).
$script:FinOpsFeatureSurfacePrefixes = [ordered]@{
    'mailbox.'    = 'm365'
    'office.'     = 'm365'
    'teams.'      = 'm365'
    'sharepoint.' = 'm365'
    'intune.'     = 'm365'
    'entra.'      = 'm365'
    'defender.'   = 'm365'
    'purview.'    = 'm365'
    'powerbi.'    = 'm365'
    'power.'      = 'm365'
    'copilot.'    = 'm365'
    'windows.'    = 'm365'
    'vm.'         = 'azure'
    'disk.'       = 'azure'
    'sql.'        = 'azure'
    'logs.'       = 'azure'
    'network.'    = 'azure'
    'github.'     = 'github'
    'ghas.'       = 'github'
    'ado.'        = 'ado'
}

function Build-FinOpsOrdinalSet {
    <#
    .SYNOPSIS
        Returns an empty ordinal (case-sensitive) string set.
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Generic.HashSet[string]])]
    param()
    return , [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
}

function Get-FinOpsOrdinalSorted {
    <#
    .SYNOPSIS
        Sorts strings by Unicode code point (Python ``sorted()`` parity).

    .DESCRIPTION
        PowerShell ``Sort-Object`` is culture-sensitive; Python ``sorted()``
        on strings is ordinal. Several rule evidence lists are built with
        ``sorted()`` in Python, so the PowerShell port must reproduce that
        exact ordering for the cross-engine byte compare.
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param([Parameter()] [AllowEmptyCollection()] [string[]] $InputObject = @())

    $list = [System.Collections.Generic.List[string]]::new()
    foreach ($item in $InputObject) { [void] $list.Add($item) }
    $list.Sort([System.StringComparer]::Ordinal)
    return , $list.ToArray()
}

function Get-FinOpsRedactedPrincipal {
    <#
    .SYNOPSIS
        Returns the raw principal or a salted SHA-256 of it (engine.py redact).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Principal,
        [Parameter(Mandatory)] [bool] $RedactPii,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Salt
    )

    if (-not $RedactPii) { return $Principal }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes("$Salt`:$Principal")
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($bytes)
    } finally {
        $sha.Dispose()
    }
    $hex = [System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
    return "sha256:$($hex.Substring(0, 16))"
}

function Get-FinOpsEffectiveFeatureSet {
    <#
    .SYNOPSIS
        All feature tags a SKU exposes, walking ``includes`` and expanding
        via the feature-implication map (engine.py effective_features).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Generic.HashSet[string]])]
    param(
        [Parameter(Mandatory)] [string] $SkuId,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string, object]] $Catalog
    )

    $seen = Build-FinOpsOrdinalSet
    $raw = Build-FinOpsOrdinalSet
    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($SkuId)
    while ($stack.Count -gt 0) {
        $sid = $stack.Pop()
        if (-not $seen.Add($sid)) { continue }
        if (-not $Catalog.ContainsKey($sid)) { continue }
        $entry = $Catalog[$sid]
        foreach ($f in @($entry.features)) { [void] $raw.Add($f) }
        foreach ($child in @($entry.includes)) { $stack.Push($child) }
    }

    # _expand: each feature contributes itself plus everything it implies.
    $out = Build-FinOpsOrdinalSet
    foreach ($f in $raw) {
        if ($script:FinOpsFeatureImplies.ContainsKey($f)) {
            foreach ($implied in $script:FinOpsFeatureImplies[$f]) { [void] $out.Add($implied) }
        } else {
            [void] $out.Add($f)
        }
    }
    return , $out
}

function Get-FinOpsTransitiveIncludeSet {
    <#
    .SYNOPSIS
        Every child SKU id reachable via ``includes`` (excluding ``SkuId``)
        (engine.py transitive_includes).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Generic.HashSet[string]])]
    param(
        [Parameter(Mandatory)] [string] $SkuId,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string, object]] $Catalog
    )

    $out = Build-FinOpsOrdinalSet
    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($SkuId)
    while ($stack.Count -gt 0) {
        $cur = $stack.Pop()
        if (-not $Catalog.ContainsKey($cur)) { continue }
        foreach ($child in @($Catalog[$cur].includes)) {
            if ($out.Add($child)) { $stack.Push($child) }
        }
    }
    return , $out
}

function Get-FinOpsSurfaceFeatureSet {
    <#
    .SYNOPSIS
        Filter features to those whose prefix maps to ``Surface``
        (engine.py features_for_surface).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Generic.HashSet[string]])]
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object] $Feature,
        [Parameter(Mandatory)] [string] $Surface
    )

    $out = Build-FinOpsOrdinalSet
    foreach ($feat in @($Feature)) {
        foreach ($prefix in $script:FinOpsFeatureSurfacePrefixes.Keys) {
            if ($feat.StartsWith($prefix, [System.StringComparison]::Ordinal) -and
                $script:FinOpsFeatureSurfacePrefixes[$prefix] -ceq $Surface) {
                [void] $out.Add($feat)
                break
            }
        }
    }
    return , $out
}

function Test-FinOpsSubset {
    <#
    .SYNOPSIS
        Returns $true when every member of $Required is in $Candidate
        (mirrors Python ``required.issubset(candidate)``).
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $Required,
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $Candidate
    )
    foreach ($r in $Required) {
        if (-not $Candidate.Contains($r)) { return $false }
    }
    return $true
}

function Get-FinOpsCheapestCoveringSku {
    <#
    .SYNOPSIS
        Cheapest SKU on ``Cloud`` whose effective features cover ``Required``
        (engine.py cheapest_covering_sku). Stable tie-break by catalog order.
    #>
    [CmdletBinding()]
    [OutputType([object])]
    param(
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $Required,
        [Parameter(Mandatory)] [object[]] $CatalogList,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string, object]] $Catalog,
        [string] $Cloud = 'm365'
    )

    $candidates = [System.Collections.Generic.List[object]]::new()
    $index = 0
    foreach ($entry in $CatalogList) {
        $idx = $index
        $index++
        if ($entry.cloud -cne $Cloud -or $null -eq $entry.list_price_usd_month) { continue }
        $features = Get-FinOpsEffectiveFeatureSet -SkuId $entry.id -Catalog $Catalog
        if (Test-FinOpsSubset -Required $Required -Candidate $features) {
            [void] $candidates.Add([pscustomobject]@{
                    Price = [double] $entry.list_price_usd_month
                    Index = $idx
                    Entry = $entry
                })
        }
    }
    if ($candidates.Count -eq 0) { return $null }
    # Stable: primary price, secondary original catalog order (Python's
    # list.sort is stable and sorts by price only).
    $sorted = $candidates | Sort-Object -Property Price, Index
    return $sorted[0].Entry
}

function Format-FinOpsRecommendation {
    <#
    .SYNOPSIS
        Render a recommendation template, collapsing whitespace and leaving
        unknown placeholders intact (engine.py render).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Template,
        [Parameter(Mandatory)] [hashtable] $Values
    )

    # " ".join(template.split()) -- split on runs of whitespace, drop
    # leading/trailing, rejoin with single spaces.
    $collapsed = ([regex]::Split($Template.Trim(), '\s+') | Where-Object { $_ -ne '' }) -join ' '
    if ([string]::IsNullOrEmpty($collapsed)) { return '' }

    # Substitute {placeholder} tokens, leaving unknown placeholders intact
    # (engine.py _SafeDict). A manual match loop is used (rather than a
    # Regex.Replace MatchEvaluator) so $Values is referenced in this scope
    # and the analyser can see it is used.
    $result = [System.Text.StringBuilder]::new()
    $cursor = 0
    foreach ($match in [regex]::Matches($collapsed, '\{(\w+)\}')) {
        [void] $result.Append($collapsed.Substring($cursor, $match.Index - $cursor))
        $key = $match.Groups[1].Value
        if ($Values.ContainsKey($key)) {
            [void] $result.Append([string] $Values[$key])
        } else {
            [void] $result.Append($match.Value)
        }
        $cursor = $match.Index + $match.Length
    }
    [void] $result.Append($collapsed.Substring($cursor))
    return $result.ToString()
}

function Invoke-FinOpsRuleEngine {
    <#
    .SYNOPSIS
        Runs every rule that has a native implementation over the dataset
        (native port of engine.run_rules).

    .DESCRIPTION
        Phase 2 implements the eight ``M365.*`` rules. Rules without a native
        implementation are recorded in ``RulesSkipped`` (mirroring Python's
        ``rules_skipped_no_impl``). Returns an object with Findings (ordered
        finding dictionaries), RuleCounts, RulesSkipped, Salt, and SaltMode.

    .PARAMETER Dataset
        Normalised dataset (Get-FinOpsNormalizedDataset).

    .PARAMETER PersonaAssignments
        Persona assignment map (Get-FinOpsPersonaAssignment).

    .PARAMETER RedactPii
        Whether to salt-hash principals (default $true).

    .PARAMETER Salt
        Fixed salt -> salt_mode 'tenant_stable'. Omit for a per-run random
        salt -> 'per_run'.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [object] $Dataset,
        [Parameter(Mandatory)] [System.Collections.Specialized.OrderedDictionary] $PersonaAssignments,
        [bool] $RedactPii = $true,
        [string] $Salt
    )

    $data = Get-FinOpsDataProjection
    $catalogList = @($data.Catalog)
    $catalog = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    foreach ($entry in $catalogList) { $catalog[$entry.id] = $entry }
    $personas = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    foreach ($p in @($data.Personas)) { $personas[$p.id] = $p }

    # assignments_by_principal: principal -> ordered list of sku ids (input order).
    $assignmentsByPrincipal = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    $assignmentOrder = [System.Collections.Generic.List[string]]::new()
    foreach ($a in @($Dataset.assignments)) {
        if (-not $assignmentsByPrincipal.ContainsKey($a.principal)) {
            $assignmentsByPrincipal[$a.principal] = [System.Collections.Generic.List[string]]::new()
            [void] $assignmentOrder.Add($a.principal)
        }
        [void] $assignmentsByPrincipal[$a.principal].Add($a.sku_id)
    }

    # usage_by_principal: principal -> (signal -> last_activity_days), last-write-wins.
    $usageByPrincipal = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    foreach ($u in @($Dataset.usage)) {
        if (-not $usageByPrincipal.ContainsKey($u.principal)) {
            $usageByPrincipal[$u.principal] = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        }
        $usageByPrincipal[$u.principal][$u.signal] = $u.last_activity_days
    }

    if ($PSBoundParameters.ContainsKey('Salt')) {
        $saltValue = $Salt
        $saltMode = 'tenant_stable'
    } else {
        $saltValue = [System.Guid]::NewGuid().ToString('N') + [System.Guid]::NewGuid().ToString('N')
        $saltMode = 'per_run'
    }

    $registry = Get-FinOpsM365RuleRegistry

    $findings = [System.Collections.Generic.List[object]]::new()
    $counts = [ordered]@{}
    $skipped = [System.Collections.Generic.List[string]]::new()

    foreach ($rule in @($data.Rules)) {
        if (-not $rule.enabled) { continue }
        if (-not $registry.ContainsKey($rule.id)) {
            [void] $skipped.Add($rule.id)
            continue
        }
        $context = [pscustomobject]@{
            Catalog                = $catalog
            CatalogList            = $catalogList
            Personas               = $personas
            PersonaAssignments     = $PersonaAssignments
            Dataset                = $Dataset
            Rule                   = $rule
            RedactPii              = $RedactPii
            Salt                   = $saltValue
            AssignmentsByPrincipal = $assignmentsByPrincipal
            AssignmentOrder        = $assignmentOrder
            UsageByPrincipal       = $usageByPrincipal
        }
        $produced = @(& $registry[$rule.id] $context)
        $counts[$rule.id] = $produced.Count
        foreach ($f in $produced) { [void] $findings.Add($f) }
    }

    return [pscustomobject]@{
        Findings     = $findings.ToArray()
        RuleCounts   = $counts
        RulesSkipped = (Get-FinOpsOrdinalSorted -InputObject $skipped.ToArray())
        Salt         = $saltValue
        SaltMode     = $saltMode
    }
}
