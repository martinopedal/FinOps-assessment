Set-StrictMode -Version Latest

# Native port of finops_assess.rules_impl.ado_rules -- the four Azure DevOps
# savings rules. Each rule is a scriptblock in the registry returned by
# Get-FinOpsAdoRuleRegistry, keyed by the YAML rule id (kept in lockstep
# with data/rules/ado.yaml). Ordinal / case-sensitive semantics throughout
# for Python parity.

function Get-FinOpsAdoSeatSaving {
    <#
    .SYNOPSIS
        Return round(catalog_price, 2) for an ADO seat, or null.
    #>
    [CmdletBinding()] [OutputType([object])]
    param([Parameter()] [object] $Seat, [Parameter()] [object] $Context)
    if ($null -eq $Seat.sku_id) { return $null }
    if (-not $Context.Catalog.ContainsKey([string] $Seat.sku_id)) { return $null }
    $sku = $Context.Catalog[[string] $Seat.sku_id]
    if ($null -eq $sku.list_price_usd_month) { return $null }
    return [math]::Round([double] $sku.list_price_usd_month, 2)
}

function Get-FinOpsAdoRuleRegistry {
    <#
    .SYNOPSIS
        Returns a hashtable of rule-id -> scriptblock for the four ADO
        rules. Each scriptblock takes the rule context and returns an array
        of finding dictionaries.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param()

    $registry = @{}

    # -----------------------------------------------------------------------
    # ADO.INACTIVE_BASIC_90D
    # Basic or Basic+Test seats with no activity in the configured window.
    # -----------------------------------------------------------------------
    $registry['ADO.INACTIVE_BASIC_90D'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 90 }
        $billableSeatTypes = [System.Collections.Generic.HashSet[string]]::new(
            [string[]]@('basic', 'basic_plus_test'), [System.StringComparer]::Ordinal)
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($seat in @($ctx.Dataset.ado_seats)) {
            if (-not $billableSeatTypes.Contains([string] $seat.seat_type)) { continue }
            if ($null -eq $seat.last_activity_days) { continue }
            if ([int] $seat.last_activity_days -lt $days) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $seat.principal) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $skuId = if ($null -ne $seat.sku_id) { [string] $seat.sku_id } else { $null }
            $savings = Get-FinOpsAdoSeatSaving -Seat $seat -Context $ctx
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'ado'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $skuId
                recommended_sku               = $null
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal = $redacted
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
    # ADO.STAKEHOLDER_ELIGIBLE
    # Basic seats whose only observed activity is reading boards / commenting.
    # -----------------------------------------------------------------------
    $registry['ADO.STAKEHOLDER_ELIGIBLE'] = {
        param($ctx)
        $inactiveThreshold = 90
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($seat in @($ctx.Dataset.ado_seats)) {
            if ([string] $seat.seat_type -cne 'basic') { continue }
            if (-not ($seat.only_stakeholder_activity -eq $true)) { continue }
            if ($null -eq $seat.last_activity_days) { continue }
            # Don't double-report with INACTIVE_BASIC_90D.
            if ([int] $seat.last_activity_days -ge $inactiveThreshold) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $seat.principal) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $skuId = if ($null -ne $seat.sku_id) { [string] $seat.sku_id } else { $null }
            $savings = Get-FinOpsAdoSeatSaving -Seat $seat -Context $ctx
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'ado'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $skuId
                recommended_sku               = $null
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal = $redacted
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    org                       = [string] $seat.org
                    seat_type                 = [string] $seat.seat_type
                    only_stakeholder_activity = $true
                    last_activity_days        = [int] $seat.last_activity_days
                }
            })
        }
        return $out.ToArray()
    }

    # -----------------------------------------------------------------------
    # ADO.PARALLEL_JOBS_OVER_PROVISIONED
    # Purchased hosted parallel jobs exceed P95 concurrent usage by >= 2.
    # -----------------------------------------------------------------------
    $registry['ADO.PARALLEL_JOBS_OVER_PROVISIONED'] = {
        param($ctx)
        $minSurplus = 2
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($org in @($ctx.Dataset.ado_orgs)) {
            if ($null -eq $org.purchased_parallel_jobs) { continue }
            if ($null -eq $org.p95_concurrent_jobs) { continue }
            $surplus = [int] $org.purchased_parallel_jobs - [int] $org.p95_concurrent_jobs
            if ($surplus -lt $minSurplus) { continue }
            $jobSku = if ($ctx.Catalog.ContainsKey('ADO.PARALLEL_JOB_HOSTED')) { $ctx.Catalog['ADO.PARALLEL_JOB_HOSTED'] } else { $null }
            $jobPrice = if ($null -ne $jobSku -and $null -ne $jobSku.list_price_usd_month) { [double] $jobSku.list_price_usd_month } else { $null }
            $savings = if ($null -ne $jobPrice) { [math]::Round($surplus * $jobPrice, 2) } else { $null }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $org.org) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'ado'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $null
                recommended_sku               = $null
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    purchased_parallel_jobs = [int] $org.purchased_parallel_jobs
                    p95_concurrent_jobs     = [int] $org.p95_concurrent_jobs
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    purchased_parallel_jobs = [int] $org.purchased_parallel_jobs
                    p95_concurrent_jobs     = [int] $org.p95_concurrent_jobs
                    surplus_jobs            = $surplus
                }
            })
        }
        return $out.ToArray()
    }

    # -----------------------------------------------------------------------
    # ADO.TEST_PLANS_UNUSED
    # Basic+Test Plans seats with no Test Plans activity in 60 days.
    # -----------------------------------------------------------------------
    $registry['ADO.TEST_PLANS_UNUSED'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 60 }
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($seat in @($ctx.Dataset.ado_seats)) {
            if ([string] $seat.seat_type -cne 'basic_plus_test') { continue }
            if ($null -eq $seat.last_test_plan_days) { continue }
            if ([int] $seat.last_test_plan_days -lt $days) { continue }
            $basicTestSku = if ($ctx.Catalog.ContainsKey('ADO.BASIC_TEST')) { $ctx.Catalog['ADO.BASIC_TEST'] } else { $null }
            $basicSku = if ($ctx.Catalog.ContainsKey('ADO.BASIC')) { $ctx.Catalog['ADO.BASIC'] } else { $null }
            $savings = $null
            if ($null -ne $basicTestSku -and $null -ne $basicTestSku.list_price_usd_month -and
                $null -ne $basicSku -and $null -ne $basicSku.list_price_usd_month) {
                $savings = [math]::Round([double] $basicTestSku.list_price_usd_month - [double] $basicSku.list_price_usd_month, 2)
            }
            $redacted = Get-FinOpsRedactedPrincipal -Principal ([string] $seat.principal) -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $skuId = if ($null -ne $seat.sku_id) { [string] $seat.sku_id } else { $null }
            [void] $out.Add([ordered]@{
                rule_id                       = $ctx.Rule.id
                surface                       = 'ado'
                severity                      = $ctx.Rule.severity
                principal                     = $redacted
                current_sku                   = $skuId
                recommended_sku               = 'ADO.BASIC'
                estimated_monthly_savings_usd = $savings
                recommendation                = (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal = $redacted
                })
                evidence_ref                  = $null
                confidence                    = 'high'
                evidence                      = [ordered]@{
                    org                 = [string] $seat.org
                    seat_type           = [string] $seat.seat_type
                    last_test_plan_days = [int] $seat.last_test_plan_days
                    window_days         = $days
                }
            })
        }
        return $out.ToArray()
    }

    return $registry
}
