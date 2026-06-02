Set-StrictMode -Version Latest

# Native port of finops_assess.rules_impl.github_rules -- the four GitHub
# savings rules. Each rule is a scriptblock in the registry returned by
# Get-FinOpsGitHubRuleRegistry, keyed by the YAML rule id (kept in lockstep
# with data/rules/github.yaml). Ordinal / case-sensitive semantics throughout
# for Python parity.

function Get-FinOpsGitHubSaving {
    <#
    .SYNOPSIS
        Return round(catalog_price, 2) for a GitHub seat, or null.
    #>
    [CmdletBinding()] [OutputType([object])]
    param([Parameter()] [object] $Seat, [Parameter()] [object] $Context)
    if ($null -eq $Seat.sku_id) { return $null }
    if (-not $Context.Catalog.ContainsKey([string] $Seat.sku_id)) { return $null }
    $sku = $Context.Catalog[[string] $Seat.sku_id]
    if ($null -eq $sku.list_price_usd_month) { return $null }
    return [math]::Round([double] $sku.list_price_usd_month, 2)
}

function Get-FinOpsRunnerRecommendation {
    <#
    .SYNOPSIS
        Compute the tier-action string for GH.RUNNER_TIER_MISMATCH
        (github_rules._runner_recommendation).
    #>
    [CmdletBinding()] [OutputType([string])]
    param(
        [Parameter(Mandatory)] [int] $Used,
        [Parameter(Mandatory)] [int] $Included,
        [Parameter()] [AllowNull()] [object] $Tier
    )
    $pct = if ($Included -gt 0) { ($Used - $Included) / [double] $Included * 100.0 } else { 0.0 }
    $tierLabel = if ($null -ne $Tier -and [string] $Tier -ne '') { [string] $Tier } else { 'current' }
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    if ($pct -ge 25.0) {
        $pctStr = [math]::Round($pct, 0).ToString('F0', $inv)
        return ("Consumption is {0}% above the {1} tier's included quota; verify whether moving to a higher-tier bundle beats per-minute overage pricing." -f $pctStr, $tierLabel)
    } else {
        $absPctStr = [math]::Round([math]::Abs($pct), 0).ToString('F0', $inv)
        return ("Consumption is {0}% below the {1} tier's included quota; verify whether a lower-tier bundle would still cover peak months." -f $absPctStr, $tierLabel)
    }
}

function Get-FinOpsGitHubRuleRegistry {
    <#
    .SYNOPSIS
        Returns a hashtable of rule-id -> scriptblock for the four GitHub
        rules. Each scriptblock takes the rule context and returns an array
        of finding dictionaries.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param()

    $registry = @{}

    # -----------------------------------------------------------------------
    # GH.INACTIVE_SEAT_90D
    # Enterprise / Team seats with no activity in the configured window.
    # -----------------------------------------------------------------------
    $registry['GH.INACTIVE_SEAT_90D'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 90 }
        $activeSeatTypes = [System.Collections.Generic.HashSet[string]]::new(
            [string[]]@('enterprise', 'team'), [System.StringComparer]::Ordinal)
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($seat in @($ctx.Dataset.github_seats)) {
            if (-not $activeSeatTypes.Contains([string] $seat.seat_type)) { continue }
            if ($null -eq $seat.last_activity_days) { continue }
            if ([int] $seat.last_activity_days -lt $days) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $seat.principal) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $skuId = if ($null -ne $seat.sku_id) { [string] $seat.sku_id } else { $null }
            $savings = Get-FinOpsGitHubSaving -Seat $seat -Context $ctx
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'github'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $skuId
                recommended_sku               = $null
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal   = $redacted
                    current_sku = if ($null -ne $skuId) { $skuId } else { 'GitHub' }
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    org                = [string] $seat.org
                    seat_type          = [string] $seat.seat_type
                    last_activity_days = [int] $seat.last_activity_days
                    window_days        = $days
                }
            })
        }
        return $out.ToArray()
    }

    # -----------------------------------------------------------------------
    # GH.COPILOT_INACTIVE_30D
    # Copilot Business / Enterprise seats with zero acceptances in 30 days.
    # -----------------------------------------------------------------------
    $registry['GH.COPILOT_INACTIVE_30D'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 30 }
        $copilotSeatTypes = [System.Collections.Generic.HashSet[string]]::new(
            [string[]]@('copilot_business', 'copilot_enterprise'), [System.StringComparer]::Ordinal)
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($seat in @($ctx.Dataset.github_seats)) {
            if (-not $copilotSeatTypes.Contains([string] $seat.seat_type)) { continue }
            if ($null -eq $seat.copilot_acceptances_30d) { continue }
            if ([int] $seat.copilot_acceptances_30d -gt 0) { continue }
            # Corroborate with last_activity_days if present.
            if ($null -ne $seat.last_activity_days -and [int] $seat.last_activity_days -lt $days) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $seat.principal) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $skuId = if ($null -ne $seat.sku_id) { [string] $seat.sku_id } else { $null }
            $savings = Get-FinOpsGitHubSaving -Seat $seat -Context $ctx
            $lastActivityDays = if ($null -ne $seat.last_activity_days) { [int] $seat.last_activity_days } else { $null }
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'github'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $skuId
                recommended_sku               = $null
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal   = $redacted
                    current_sku = if ($null -ne $skuId) { $skuId } else { 'GitHub Copilot' }
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    org                       = [string] $seat.org
                    seat_type                 = [string] $seat.seat_type
                    copilot_acceptances_30d   = [int] $seat.copilot_acceptances_30d
                    last_activity_days        = $lastActivityDays
                    window_days               = $days
                }
            })
        }
        return $out.ToArray()
    }

    # -----------------------------------------------------------------------
    # GH.GHAS_OVER_PROVISIONED
    # GHAS enabled on more repos than are actively scanned.
    # -----------------------------------------------------------------------
    $registry['GH.GHAS_OVER_PROVISIONED'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($org in @($ctx.Dataset.github_orgs)) {
            if ($null -eq $org.ghas_repo_count) { continue }
            if ($null -eq $org.actively_scanned_repos) { continue }
            if ($null -eq $org.active_committers) { continue }
            if ([int] $org.ghas_repo_count -le [int] $org.actively_scanned_repos) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $org.org) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'github'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = 'GH.GHAS'
                recommended_sku               = $null
                estimated_monthly_savings_usd = $null
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    ghas_repo_count    = [int] $org.ghas_repo_count
                    active_committers  = [int] $org.active_committers
                    actively_scanned   = [int] $org.actively_scanned_repos
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    ghas_repo_count       = [int] $org.ghas_repo_count
                    actively_scanned_repos = [int] $org.actively_scanned_repos
                    active_committers     = [int] $org.active_committers
                }
            })
        }
        return $out.ToArray()
    }

    # -----------------------------------------------------------------------
    # GH.RUNNER_TIER_MISMATCH
    # Runner minute consumption materially above or below included quota.
    # -----------------------------------------------------------------------
    $registry['GH.RUNNER_TIER_MISMATCH'] = {
        param($ctx)
        $threshold = 25.0
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($org in @($ctx.Dataset.github_orgs)) {
            if ($null -eq $org.runner_minutes_used) { continue }
            if ($null -eq $org.runner_minutes_included) { continue }
            if ([int] $org.runner_minutes_included -le 0) { continue }
            $used = [int] $org.runner_minutes_used
            $included = [int] $org.runner_minutes_included
            $deltaMins = [math]::Abs($used - $included)
            $deltaPct = $deltaMins / [double] $included * 100.0
            if ($deltaPct -lt $threshold) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $org.org) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $tierLabel = if ($null -ne $org.runner_tier -and [string] $org.runner_tier -ne '') { [string] $org.runner_tier } else { $null }
            $tierActionRec = Get-FinOpsRunnerRecommendation -Used $used -Included $included -Tier $tierLabel
            $deltaPctRounded = [math]::Round($deltaPct, 1)
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'github'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $tierLabel
                recommended_sku               = $null
                estimated_monthly_savings_usd = $null
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    used_minutes                = $used
                    included_minutes            = $included
                    tier_action_recommendation  = $tierActionRec
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    runner_tier            = $tierLabel
                    runner_minutes_used    = $used
                    runner_minutes_included = $included
                    delta_pct              = $deltaPctRounded
                }
            })
        }
        return $out.ToArray()
    }

    return $registry
}
