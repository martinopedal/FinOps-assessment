Set-StrictMode -Version Latest

# Native port of finops_assess.rules_impl.azure_rules -- the twelve Azure
# savings rules. Each rule is a scriptblock in the registry returned by
# Get-FinOpsAzureRuleRegistry, keyed by the YAML rule id (kept in lockstep
# with data/rules/azure.yaml). Ordinal / case-sensitive semantics throughout
# for Python parity.

# ---------------------------------------------------------------------------
# Constants mirroring azure_rules.py
# ---------------------------------------------------------------------------
$script:ReservationUtilThreshold = 80.0
$script:CommitmentUtilThreshold = 80.0
$script:SiblingMinOnDemandUsd = 50.0
$script:ReservationScopeMinNonOwnerUsd = 50.0
$script:SpMinLookbackPeriods = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@('Last30Days', 'Last60Days'),
    [StringComparer]::Ordinal
)
$script:AhbLicenceTypes = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@('Windows_Server', 'Windows_Client'),
    [StringComparer]::Ordinal
)
$script:RenewalReviewDefaultWindowDays = 60
$script:TodayOverrideEnv = 'FINOPS_NOW_OVERRIDE'

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
function Get-FinOpsAzureSavingsValue {
    [CmdletBinding()] [OutputType([object])]
    param([Parameter()] [AllowNull()] [object] $Price)
    if ($null -eq $Price) { return $null }
    return [math]::Round([double] $Price, 2)
}

function Build-FinOpsAzureFinding {
    <#
    .SYNOPSIS
        Builds a finding dictionary mirroring the Finding pydantic model for
        Azure surface (defaults: current_sku/recommended_sku/savings/evidence_ref
        null, confidence 'high', evidence {}).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [string] $RuleId,
        [Parameter(Mandatory)] [string] $Severity,
        [Parameter(Mandatory)] [string] $Principal,
        [Parameter(Mandatory)] [string] $Recommendation,
        [AllowNull()] [object] $CurrentSku = $null,
        [AllowNull()] [object] $RecommendedSku = $null,
        [AllowNull()] [object] $Savings = $null,
        [AllowNull()] [object] $EvidenceRef = $null,
        [string] $Confidence = 'high',
        [object] $Evidence = ([ordered]@{})
    )
    return [ordered]@{
        rule_id                       = $RuleId
        surface                       = 'azure'
        severity                      = $Severity
        principal                     = $Principal
        current_sku                   = $CurrentSku
        recommended_sku               = $RecommendedSku
        estimated_monthly_savings_usd = $Savings
        recommendation                = $Recommendation
        evidence_ref                  = $EvidenceRef
        confidence                    = $Confidence
        evidence                      = $Evidence
    }
}

function Get-FinOpsAzureTodayUtc {
    <#
    .SYNOPSIS
        Return today's date in UTC, honoring FINOPS_NOW_OVERRIDE env var if set.
    #>
    [CmdletBinding()] [OutputType([datetime])]
    param()
    $override = [System.Environment]::GetEnvironmentVariable($script:TodayOverrideEnv)
    if ($override) {
        try {
            return [datetime]::ParseExact($override, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
        } catch {
            Write-Warning "AZ.COMMITMENT_RENEWAL_REVIEW: invalid $($script:TodayOverrideEnv)='$override'; using wall clock"
        }
    }
    return [datetime]::UtcNow.Date
}

function Test-FinOpsDevTestOffer {
    <#
    .SYNOPSIS
        Return $true when the subscription offer is a Dev/Test variant.
    #>
    [CmdletBinding()] [OutputType([bool])]
    param([string] $Offer)
    $lower = $Offer.ToLowerInvariant() -replace '[-_\s/]', ''
    return ($lower -like '*devtest*') -or ($lower -ceq 'dev') -or ($lower -ceq 'test')
}

function Get-FinOpsBareSubId {
    <#
    .SYNOPSIS
        Extract a bare subscription ID from a full ARM path or a bare ID.
        /subscriptions/00000000 -> 00000000; 00000000 -> 00000000
    #>
    [CmdletBinding()] [OutputType([string])]
    param([string] $ArmOrBare)
    $prefix = '/subscriptions/'
    if ($ArmOrBare.ToLowerInvariant().StartsWith($prefix.ToLowerInvariant())) {
        $rest = $ArmOrBare.Substring($prefix.Length)
        return ($rest -split '/')[0]
    }
    return $ArmOrBare
}

function Format-FinOpsFloat {
    <#
    .SYNOPSIS
        Formats a float for recommendation templates, matching Python's str()
        behavior: 45.0 stays "45.0", never "45".
    #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)] [double] $Value)
    # Python's str(float) always includes at least one decimal digit for values
    # like 45.0. PowerShell's default ToString() drops it: 45.0 -> "45".
    # Use "F1" to force one decimal place, which matches Python's default for
    # round numbers and our unit tests.
    return $Value.ToString('F1', [System.Globalization.CultureInfo]::InvariantCulture)
}

function Get-FinOpsAzureRuleRegistry {
    <#
    .SYNOPSIS
        Returns a hashtable of rule-id -> scriptblock for the twelve Azure
        rules. Each scriptblock takes the rule context and returns an array
        of finding dictionaries.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param()

    return @{
        # -----------------------------------------------------------------------
        # AZ.IDLE_VM_14D
        # -----------------------------------------------------------------------
        'AZ.IDLE_VM_14D' = {
            param($ctx)
            $days = if ($null -ne $ctx.Rule.inactivity_days) { $ctx.Rule.inactivity_days } else { 14 }
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($resource.resource_type -cne 'virtualMachine') { continue }
                if ($null -eq $resource.avg_cpu_pct -or $null -eq $resource.avg_net_kbps) { continue }
                if ([double]$resource.avg_cpu_pct -ge 5.0 -or [double]$resource.avg_net_kbps -ge 100.0) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal    = $principal
                    avg_cpu_pct  = Format-FinOpsFloat ([math]::Round([double]$resource.avg_cpu_pct, 1))
                    avg_net_kbps = Format-FinOpsFloat ([math]::Round([double]$resource.avg_net_kbps, 1))
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -Savings (Get-FinOpsAzureSavingsValue -Price $resource.monthly_cost_usd) `
                    -Evidence ([ordered]@{
                        avg_cpu_pct  = $resource.avg_cpu_pct
                        avg_net_kbps = $resource.avg_net_kbps
                        window_days  = $days
                        location     = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.UNATTACHED_DISK
        # -----------------------------------------------------------------------
        'AZ.UNATTACHED_DISK' = {
            param($ctx)
            $days = if ($null -ne $ctx.Rule.inactivity_days) { $ctx.Rule.inactivity_days } else { 7 }
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($resource.resource_type -cne 'managedDisk') { continue }
                if ($null -eq $resource.attached -or $resource.attached -eq $true) { continue }
                if ($null -eq $resource.days_inactive) { continue }
                if ([int]$resource.days_inactive -lt $days) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal        = $principal
                    disk_size_gb     = '?'
                    disk_sku         = if ($resource.sku) { $resource.sku } else { '?' }
                    last_attached_at = "$($resource.days_inactive) days ago"
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -Savings (Get-FinOpsAzureSavingsValue -Price $resource.monthly_cost_usd) `
                    -Evidence ([ordered]@{
                        attached      = $false
                        days_inactive = $resource.days_inactive
                        location      = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.PUBLIC_IP_UNATTACHED
        # -----------------------------------------------------------------------
        'AZ.PUBLIC_IP_UNATTACHED' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($resource.resource_type -cne 'publicIp') { continue }
                if ($null -eq $resource.associated -or $resource.associated -eq $true) { continue }
                # SKU check is case-insensitive (Python .lower())
                $sku = if ($resource.sku) { $resource.sku } else { '' }
                if ($sku.ToLowerInvariant() -ne 'standard') { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal = $principal
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -Savings (Get-FinOpsAzureSavingsValue -Price $resource.monthly_cost_usd) `
                    -Evidence ([ordered]@{
                        associated = $false
                        location   = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.OVERSIZED_VM
        # -----------------------------------------------------------------------
        'AZ.OVERSIZED_VM' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($resource.resource_type -cne 'virtualMachine') { continue }
                if ($null -eq $resource.p95_cpu_pct -or $null -eq $resource.p95_mem_pct) { continue }
                if ([double]$resource.p95_cpu_pct -ge 40.0 -or [double]$resource.p95_mem_pct -ge 40.0) { continue }
                # Skip if genuinely idle (covered by IDLE_VM)
                if ($null -ne $resource.avg_cpu_pct -and [double]$resource.avg_cpu_pct -lt 5.0) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $recSku = if ($resource.recommended_sku) { $resource.recommended_sku } else { '<smaller SKU in same family>' }
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal       = $principal
                    current_sku     = if ($resource.sku) { $resource.sku } else { '?' }
                    recommended_sku = $recSku
                    p95_cpu_pct     = Format-FinOpsFloat ([math]::Round([double]$resource.p95_cpu_pct, 1))
                    p95_mem_pct     = Format-FinOpsFloat ([math]::Round([double]$resource.p95_mem_pct, 1))
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -RecommendedSku $resource.recommended_sku `
                    -Savings $null `
                    -Evidence ([ordered]@{
                        p95_cpu_pct = $resource.p95_cpu_pct
                        p95_mem_pct = $resource.p95_mem_pct
                        location    = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.RESERVATION_UNDERUTILIZED
        # -----------------------------------------------------------------------
        'AZ.RESERVATION_UNDERUTILIZED' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($reservation in $ctx.Dataset.azure_reservations) {
                if ($null -eq $reservation.utilization_pct) { continue }
                if ([double]$reservation.utilization_pct -ge $script:ReservationUtilThreshold) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $reservation.reservation_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal       = $principal
                    utilization_pct = Format-FinOpsFloat ([math]::Round([double]$reservation.utilization_pct, 1))
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $reservation.sku `
                    -Savings $null `
                    -Evidence ([ordered]@{
                        reservation_name = $reservation.reservation_name
                        sku              = $reservation.sku
                        scope            = $reservation.scope
                        utilization_pct  = $reservation.utilization_pct
                        monthly_cost_usd = $reservation.monthly_cost_usd
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.LOG_ANALYTICS_OVERINGEST
        # -----------------------------------------------------------------------
        'AZ.LOG_ANALYTICS_OVERINGEST' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($workspace in $ctx.Dataset.azure_log_workspaces) {
                if ($null -eq $workspace.recommended_tier) { continue }
                if ($null -eq $workspace.daily_gb) { continue }

                $estSavings = $null
                if ($null -ne $workspace.est_savings_pct -and $null -ne $workspace.monthly_cost_usd) {
                    $estSavings = [math]::Round([double]$workspace.monthly_cost_usd * [double]$workspace.est_savings_pct / 100.0, 2)
                }

                $principal = Get-FinOpsRedactedPrincipal -Principal $workspace.workspace_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $estPctStr = if ($null -ne $workspace.est_savings_pct) { Format-FinOpsFloat ([math]::Round([double]$workspace.est_savings_pct, 1)) } else { '?' }
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal        = $principal
                    daily_gb         = Format-FinOpsFloat ([math]::Round([double]$workspace.daily_gb, 1))
                    recommended_tier = $workspace.recommended_tier
                    est_savings_pct  = $estPctStr
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -Savings $estSavings `
                    -Evidence ([ordered]@{
                        workspace_name     = $workspace.workspace_name
                        daily_gb           = $workspace.daily_gb
                        commitment_tier_gb = $workspace.commitment_tier_gb
                        recommended_tier   = $workspace.recommended_tier
                        est_savings_pct    = $workspace.est_savings_pct
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.DEV_TEST_SUB_MISMATCH
        # -----------------------------------------------------------------------
        'AZ.DEV_TEST_SUB_MISMATCH' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($null -eq $resource.env_tag -or $null -eq $resource.subscription_offer) { continue }
                $env = $resource.env_tag
                $offer = $resource.subscription_offer
                $isDevTestSub = Test-FinOpsDevTestOffer -Offer $offer
                $envLower = $env.ToLowerInvariant()
                $isProdEnv = $envLower.StartsWith('prod')
                $isDevTestEnv = $envLower.StartsWith('dev') -or $envLower.StartsWith('test') -or $envLower -ceq 'nonprod'
                $isMismatch = ($isProdEnv -and $isDevTestSub) -or ($isDevTestEnv -and -not $isDevTestSub)
                if (-not $isMismatch) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $subId = if ($resource.subscription_id) { $resource.subscription_id } else { '?' }
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal          = $principal
                    env_tag            = $env
                    subscription_id    = $subId
                    subscription_offer = $offer
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -Savings $null `
                    -Evidence ([ordered]@{
                        env_tag            = $env
                        subscription_id    = $resource.subscription_id
                        subscription_offer = $offer
                        location           = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.COMMITMENT_UNDER_COVERED
        # -----------------------------------------------------------------------
        'AZ.COMMITMENT_UNDER_COVERED' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            # Aggregate on-demand spend per subscription_id from azure_resources.
            # Use an insertion-ordered, ordinal-keyed dictionary so the findings
            # below are emitted in first-appearance order, matching Python's
            # ``dict`` iteration (``sibling_spend.items()``); a plain @{} would
            # enumerate .Keys in hash-bucket order and reorder the findings.
            $siblingSpend = [System.Collections.Specialized.OrderedDictionary]::new([System.StringComparer]::Ordinal)
            foreach ($resource in $ctx.Dataset.azure_resources) {
                $sub = $resource.subscription_id
                if ($null -eq $sub -or [string]::IsNullOrWhiteSpace($sub)) { continue }
                $cost = $resource.monthly_cost_usd
                if ($null -eq $cost) { continue }
                if (-not $siblingSpend.Contains($sub)) { $siblingSpend[$sub] = 0.0 }
                $siblingSpend[$sub] += [double]$cost
            }
            if ($siblingSpend.Count -eq 0) { return @() }

            $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)

            foreach ($reservation in $ctx.Dataset.azure_reservations) {
                if ($null -eq $reservation.utilization_pct) { continue }
                if ([double]$reservation.utilization_pct -ge $script:CommitmentUtilThreshold) { continue }

                $scopeRaw = if ($reservation.scope) { $reservation.scope.Trim().ToLowerInvariant() } else { '' }
                $scopeKind = switch ($scopeRaw) {
                    'single' { 'Single' }
                    { $_ -in @('shared', 'managementgroup') } { 'Shared' }
                    default { 'Unknown' }
                }

                foreach ($siblingSub in $siblingSpend.Keys) {
                    $onDemand = $siblingSpend[$siblingSub]
                    if ($onDemand -lt $script:SiblingMinOnDemandUsd) { continue }
                    $key = "$($reservation.reservation_id)|$siblingSub"
                    if ($seen.Contains($key)) { continue }
                    [void] $seen.Add($key)

                    $principal = Get-FinOpsRedactedPrincipal -Principal $reservation.reservation_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                    $siblingSubRedacted = Get-FinOpsRedactedPrincipal -Principal $siblingSub -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                    $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                        principal                  = $principal
                        scope_kind                 = $scopeKind
                        utilization_pct            = Format-FinOpsFloat ([math]::Round([double]$reservation.utilization_pct, 1))
                        sibling_sub                = $siblingSubRedacted
                        sibling_on_demand_spend_usd = Format-FinOpsFloat ([math]::Round($onDemand, 1))
                    }
                    $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                        -Principal $principal -Recommendation $rec `
                        -CurrentSku $reservation.sku `
                        -Savings $null `
                        -Evidence ([ordered]@{
                            reservation_name           = $reservation.reservation_name
                            sku                        = $reservation.sku
                            scope_kind                 = $scopeKind
                            utilization_pct            = $reservation.utilization_pct
                            monthly_cost_usd           = $reservation.monthly_cost_usd
                            sibling_sub                = $siblingSubRedacted
                            sibling_on_demand_spend_usd = [math]::Round($onDemand, 2)
                        })
                    ))
                }
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.SAVINGS_PLAN_ELIGIBLE_SPEND
        # -----------------------------------------------------------------------
        'AZ.SAVINGS_PLAN_ELIGIBLE_SPEND' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()
            $minUncovered = if ($null -ne $ctx.Rule.min_uncovered_usd) { $ctx.Rule.min_uncovered_usd } else { 50.0 }
            $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)

            foreach ($rec in $ctx.Dataset.azure_benefit_recommendations) {
                if ($rec.benefit_kind -cne 'SavingsPlan') { continue }
                if (-not $script:SpMinLookbackPeriods.Contains($rec.lookback_period)) { continue }
                if ($null -eq $rec.net_savings_usd -or [double]$rec.net_savings_usd -le 0) { continue }
                if ($null -eq $rec.cost_without_benefit_usd) { continue }
                if ([double]$rec.cost_without_benefit_usd -lt $minUncovered) { continue }

                $key = "$($rec.scope)|$($rec.term)"
                if ($seen.Contains($key)) { continue }
                [void] $seen.Add($key)

                $principal = Get-FinOpsRedactedPrincipal -Principal $rec.scope -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $hourlyCommit = if ($null -ne $rec.recommended_hourly_commit_usd) { [math]::Round([double]$rec.recommended_hourly_commit_usd, 4) } else { 0.0 }
                $recText = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal                     = $principal
                    cost_without_benefit_usd      = Format-FinOpsFloat ([math]::Round([double]$rec.cost_without_benefit_usd, 1))
                    lookback_period               = $rec.lookback_period
                    net_savings_usd               = [math]::Round([double]$rec.net_savings_usd, 2)
                    term                          = $rec.term
                    recommended_hourly_commit_usd = $hourlyCommit
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $recText `
                    -CurrentSku $null `
                    -Savings (Get-FinOpsAzureSavingsValue -Price $rec.net_savings_usd) `
                    -Evidence ([ordered]@{
                        scope_kind                    = $rec.scope_kind
                        term                          = $rec.term
                        lookback_period               = $rec.lookback_period
                        arm_sku_name                  = $rec.arm_sku_name
                        cost_without_benefit_usd      = $rec.cost_without_benefit_usd
                        recommended_hourly_commit_usd = $rec.recommended_hourly_commit_usd
                        net_savings_usd               = $rec.net_savings_usd
                        wastage_usd                   = $rec.wastage_usd
                        benefit_kind                  = $rec.benefit_kind
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.COMMITMENT_RENEWAL_REVIEW
        # -----------------------------------------------------------------------
        'AZ.COMMITMENT_RENEWAL_REVIEW' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()
            $windowDays = if ($null -ne $ctx.Rule.inactivity_days) { $ctx.Rule.inactivity_days } else { $script:RenewalReviewDefaultWindowDays }
            $today = Get-FinOpsAzureTodayUtc

            foreach ($reservation in $ctx.Dataset.azure_reservations) {
                if ($null -eq $reservation.expiry_date) { continue }
                if ($null -eq $reservation.auto_renew) { continue }
                if ($reservation.auto_renew -eq $true) { continue }

                # Parse expiry date
                $expiry = $null
                try {
                    $expiry = [datetime]::ParseExact($reservation.expiry_date, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
                } catch {
                    Write-Warning "AZ.COMMITMENT_RENEWAL_REVIEW: malformed expiry_date '$($reservation.expiry_date)'; abstaining"
                    continue
                }
                $daysUntilExpiry = ($expiry - $today).Days
                if ($daysUntilExpiry -lt 0) { continue }
                if ($daysUntilExpiry -gt $windowDays) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $reservation.reservation_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $termStr = if ($reservation.sku) { $reservation.sku } else { '?' }
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal         = $principal
                    expiry_date       = $reservation.expiry_date
                    days_until_expiry = $daysUntilExpiry
                    term              = $termStr
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $reservation.sku `
                    -Savings $null `
                    -Evidence ([ordered]@{
                        reservation_name  = $reservation.reservation_name
                        sku               = $reservation.sku
                        scope             = $reservation.scope
                        expiry_date       = $reservation.expiry_date
                        days_until_expiry = $daysUntilExpiry
                        auto_renew        = $reservation.auto_renew
                        utilization_pct   = $reservation.utilization_pct
                        monthly_cost_usd  = $reservation.monthly_cost_usd
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.RESERVATION_SCOPE_MISMATCH
        # -----------------------------------------------------------------------
        'AZ.RESERVATION_SCOPE_MISMATCH' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()
            $threshold = if ($null -ne $ctx.Rule.min_uncovered_usd) { $ctx.Rule.min_uncovered_usd } else { $script:ReservationScopeMinNonOwnerUsd }

            # Pre-aggregate spend per subscription (bare IDs)
            $spendBySub = @{}
            foreach ($res in $ctx.Dataset.azure_resources) {
                if ($null -ne $res.subscription_id -and $null -ne $res.monthly_cost_usd) {
                    $bareSub = Get-FinOpsBareSubId -ArmOrBare $res.subscription_id
                    if (-not $spendBySub.ContainsKey($bareSub)) { $spendBySub[$bareSub] = 0.0 }
                    $spendBySub[$bareSub] += [double]$res.monthly_cost_usd
                }
            }
            if ($spendBySub.Count -eq 0) { return @() }

            foreach ($reservation in $ctx.Dataset.azure_reservations) {
                if (-not $reservation.scope) { continue }
                if ($reservation.scope.ToLowerInvariant() -ne 'single') { continue }
                if ($null -eq $reservation.applied_scope_subscription_ids) { continue }
                if ($reservation.applied_scope_subscription_ids.Count -eq 0) {
                    Write-Warning "AZ.RESERVATION_SCOPE_MISMATCH: $($reservation.reservation_id) is single-scope but applied_scope_subscription_ids is empty -- abstaining"
                    continue
                }

                # Normalise owner sub IDs to bare form
                $ownerBare = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
                foreach ($sid in $reservation.applied_scope_subscription_ids) {
                    [void] $ownerBare.Add((Get-FinOpsBareSubId -ArmOrBare $sid))
                }

                $siblingSubs = [System.Collections.Generic.List[string]]::new()
                $nonOwnerUsd = 0.0
                foreach ($subId in $spendBySub.Keys) {
                    if (-not $ownerBare.Contains($subId)) {
                        $siblingSubs.Add((Get-FinOpsRedactedPrincipal -Principal $subId -RedactPii $ctx.RedactPii -Salt $ctx.Salt))
                        $nonOwnerUsd += $spendBySub[$subId]
                    }
                }
                if ($siblingSubs.Count -eq 0) { continue }
                if ($nonOwnerUsd -lt $threshold) { continue }

                # Sort with redacted values for determinism (must match Python sorted())
                $ownerDisplay = @()
                foreach ($sid in $ownerBare) {
                    $ownerDisplay += (Get-FinOpsRedactedPrincipal -Principal $sid -RedactPii $ctx.RedactPii -Salt $ctx.Salt)
                }
                $ownerDisplay = Get-FinOpsOrdinalSorted -InputObject $ownerDisplay
                $siblingSubs = Get-FinOpsOrdinalSorted -InputObject $siblingSubs

                $principal = Get-FinOpsRedactedPrincipal -Principal $reservation.reservation_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal     = $principal
                    owner_subs    = $ownerDisplay -join ', '
                    sibling_subs  = $siblingSubs -join ', '
                    non_owner_usd = Format-FinOpsFloat ([math]::Round($nonOwnerUsd, 1))
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $reservation.sku `
                    -Savings (Get-FinOpsAzureSavingsValue -Price $nonOwnerUsd) `
                    -Evidence ([ordered]@{
                        reservation_name        = $reservation.reservation_name
                        sku                     = $reservation.sku
                        scope                   = $reservation.scope
                        owner_subscription_ids  = $ownerDisplay
                        sibling_subscription_ids = $siblingSubs
                        non_owner_monthly_usd   = [math]::Round($nonOwnerUsd, 2)
                        utilization_pct         = $reservation.utilization_pct
                        monthly_cost_usd        = $reservation.monthly_cost_usd
                    })
                ))
            }
            return $findings.ToArray()
        }

        # -----------------------------------------------------------------------
        # AZ.AHB_ELIGIBLE
        # -----------------------------------------------------------------------
        'AZ.AHB_ELIGIBLE' = {
            param($ctx)
            $findings = [System.Collections.Generic.List[object]]::new()

            foreach ($resource in $ctx.Dataset.azure_resources) {
                if ($resource.resource_type -cne 'virtualMachine') { continue }
                if ($resource.os_type -cne 'Windows') { continue }
                if ($script:AhbLicenceTypes.Contains($resource.license_type)) { continue }

                $principal = Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                $skuStr = if ($resource.sku) { $resource.sku } else { '(unknown)' }
                $locStr = if ($resource.location) { $resource.location } else { '(unknown)' }
                $licStr = if ($resource.license_type) { $resource.license_type } else { '(none)' }
                $rec = Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{
                    principal    = $principal
                    sku          = $skuStr
                    location     = $locStr
                    license_type = $licStr
                }
                $findings.Add((Build-FinOpsAzureFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity `
                    -Principal $principal -Recommendation $rec `
                    -CurrentSku $resource.sku `
                    -Savings $null `
                    -Confidence 'high' `
                    -Evidence ([ordered]@{
                        resource_id  = (Get-FinOpsRedactedPrincipal -Principal $resource.resource_id -RedactPii $ctx.RedactPii -Salt $ctx.Salt)
                        os_type      = $resource.os_type
                        license_type = $resource.license_type
                        sku          = $resource.sku
                        location     = $resource.location
                    })
                ))
            }
            return $findings.ToArray()
        }
    }
}
