Set-StrictMode -Version Latest

# Native port of finops_assess.rules_impl.m365_rules -- the eight M365 /
# Entra savings rules. Each rule is a scriptblock in the registry returned
# by Get-FinOpsM365RuleRegistry, keyed by the YAML rule id (kept in
# lockstep with data/rules/m365.yaml). Ordinal / case-sensitive semantics
# throughout for Python parity.

# Feature tag -> usage signal(s) (m365_rules.py _FEATURE_TO_SIGNALS).
$script:FinOpsFeatureToSignals = @{
    'mailbox.50gb'     = @('exchange')
    'mailbox.100gb'    = @('exchange')
    'mailbox.2gb'      = @('exchange')
    'office.desktop'   = @('office')
    'office.web'       = @('office')
    'teams.full'       = @('teams')
    'teams.basic'      = @('teams')
    'sharepoint.full'  = @('sharepoint')
    'sharepoint.read'  = @('sharepoint')
    'intune.mdm'       = @('intune')
    'intune.mam'       = @('intune')
    'entra.p1'         = @('entra')
    'entra.p2'         = @('entra_p2')
    'defender.o365.p1' = @('defender_o365')
    'defender.o365.p2' = @('defender_o365')
    'purview.dlp'      = @('purview_dlp')
    'purview.records'  = @('purview')
    'powerbi.pro'      = @('powerbi')
    'copilot.m365'     = @('copilot')
}

# E5-tier signals (FIXED order -- emitted verbatim as evidence.checked_signals).
$script:FinOpsE5Signals = @('defender_o365', 'purview_dlp', 'entra_p2')
# Feature tags that together define an E5-tier SKU.
$script:FinOpsE5DefiningFeatures = @('entra.p2', 'defender.o365.p2', 'purview.dlp')

function Get-FinOpsSavingsValue {
    [CmdletBinding()] [OutputType([object])]
    param([Parameter()] [AllowNull()] [object] $Price)
    if ($null -eq $Price) { return $null }
    return [math]::Round([double] $Price, 2)
}

function Get-FinOpsDelta {
    [CmdletBinding()] [OutputType([object])]
    param(
        [Parameter()] [AllowNull()] [object] $Current,
        [Parameter()] [AllowNull()] [object] $Recommended
    )
    if ($null -eq $Current -or $null -eq $Recommended) { return $null }
    return [math]::Round([math]::Max(0.0, [double] $Current - [double] $Recommended), 2)
}

function Build-FinOpsFinding {
    <#
    .SYNOPSIS
        Builds a finding dictionary mirroring the Finding pydantic model
        (defaults: current_sku/recommended_sku/savings/evidence_ref null,
        confidence 'high', evidence {}).
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
        surface                       = 'm365'
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

function Get-FinOpsUsageValue {
    <#
    .SYNOPSIS
        usage.get(signal) -- returns the stored last_activity_days or $null.
    #>
    [CmdletBinding()] [OutputType([object])]
    param([object] $Usage, [string] $Signal)
    if ($null -ne $Usage -and $Usage.ContainsKey($Signal)) { return $Usage[$Signal] }
    return $null
}

function Get-FinOpsSkuSignalSet {
    [CmdletBinding()] [OutputType([System.Collections.Generic.HashSet[string]])]
    param([object] $Context, [string] $SkuId)
    $signals = Build-FinOpsOrdinalSet
    foreach ($feat in (Get-FinOpsEffectiveFeatureSet -SkuId $SkuId -Catalog $Context.Catalog)) {
        if ($script:FinOpsFeatureToSignals.ContainsKey($feat)) {
            foreach ($s in $script:FinOpsFeatureToSignals[$feat]) { [void] $signals.Add($s) }
        }
    }
    return , $signals
}

function Get-FinOpsM365RuleRegistry {
    <#
    .SYNOPSIS
        Returns a hashtable of rule-id -> scriptblock for the eight M365
        rules. Each scriptblock takes the rule context and returns an array
        of finding dictionaries.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param()

    $registry = @{}

    $registry['M365.UNUSED_LICENSE_30D'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 30 }
        $users = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        foreach ($u in @($ctx.Dataset.users)) { $users[$u.principal] = $u }
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($assignment in @($ctx.Dataset.assignments)) {
            $sku = if ($ctx.Catalog.ContainsKey($assignment.sku_id)) { $ctx.Catalog[$assignment.sku_id] } else { $null }
            if ($null -eq $sku -or $sku.cloud -cne 'm365') { continue }
            $signals = Get-FinOpsSkuSignalSet -Context $ctx -SkuId $assignment.sku_id
            if ($signals.Count -eq 0) { continue }
            $usage = if ($ctx.UsageByPrincipal.ContainsKey($assignment.principal)) { $ctx.UsageByPrincipal[$assignment.principal] } else { $null }
            $isActive = $false
            foreach ($sig in $signals) {
                $last = Get-FinOpsUsageValue -Usage $usage -Signal $sig
                if ($null -ne $last -and $last -le $days) { $isActive = $true; break }
            }
            if ($isActive) { continue }
            if (-not $users.ContainsKey($assignment.principal)) { continue }
            $user = $users[$assignment.principal]
            if (@('shared_mailbox', 'service') -ccontains $user.user_type) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal $assignment.principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $sortedSignals = Get-FinOpsOrdinalSorted -InputObject @($signals)
            $lastMap = [ordered]@{}
            foreach ($s in $sortedSignals) { $lastMap[$s] = Get-FinOpsUsageValue -Usage $usage -Signal $s }
            [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                        -CurrentSku $assignment.sku_id -Savings (Get-FinOpsSavingsValue -Price $sku.list_price_usd_month) `
                        -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; current_sku = $assignment.sku_id }) `
                        -Evidence ([ordered]@{
                            inactivity_window_days = $days
                            checked_signals        = $sortedSignals
                            last_activity_days     = $lastMap
                        })))
        }
        return $out.ToArray()
    }

    $registry['M365.OVER_LICENSED_VS_PERSONA'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        $excludeFamilies = @('m365_addon', 'voice', 'windows', 'windows_365')
        foreach ($assignment in @($ctx.Dataset.assignments)) {
            $sku = if ($ctx.Catalog.ContainsKey($assignment.sku_id)) { $ctx.Catalog[$assignment.sku_id] } else { $null }
            if ($null -eq $sku -or $sku.cloud -cne 'm365' -or $null -eq $sku.list_price_usd_month) { continue }
            if ($excludeFamilies -ccontains $sku.family) { continue }
            if (-not $ctx.PersonaAssignments.Contains($assignment.principal)) { continue }
            $personaAssn = $ctx.PersonaAssignments[$assignment.principal]
            if (-not $ctx.Personas.ContainsKey($personaAssn.persona_id)) { continue }
            $persona = $ctx.Personas[$personaAssn.persona_id]
            if (@($persona.required_features).Count -eq 0) { continue }
            $required = Get-FinOpsSurfaceFeatureSet -Feature @($persona.required_features) -Surface 'm365'
            if ($required.Count -eq 0) { continue }
            $currentFeatures = Get-FinOpsEffectiveFeatureSet -SkuId $assignment.sku_id -Catalog $ctx.Catalog
            if (-not (Test-FinOpsSubset -Required $required -Candidate $currentFeatures)) { continue }
            $cheaper = Get-FinOpsCheapestCoveringSku -Required $required -CatalogList $ctx.CatalogList -Catalog $ctx.Catalog -Cloud 'm365'
            if ($null -eq $cheaper -or $cheaper.id -ceq $assignment.sku_id) { continue }
            if ($null -eq $cheaper.list_price_usd_month -or $cheaper.list_price_usd_month -ge $sku.list_price_usd_month) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal $assignment.principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                        -CurrentSku $assignment.sku_id -RecommendedSku $cheaper.id `
                        -Savings (Get-FinOpsDelta -Current $sku.list_price_usd_month -Recommended $cheaper.list_price_usd_month) `
                        -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; persona = $persona.id; current_sku = $assignment.sku_id; recommended_sku = $cheaper.id }) `
                        -Confidence $personaAssn.confidence `
                        -Evidence ([ordered]@{
                            persona                   = $persona.id
                            persona_required_features = (Get-FinOpsOrdinalSorted -InputObject @($required))
                            current_features          = (Get-FinOpsOrdinalSorted -InputObject @($currentFeatures))
                        })))
        }
        return $out.ToArray()
    }

    $registry['M365.DUPLICATE_BUNDLE'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($principal in $ctx.AssignmentOrder) {
            $skuIds = @($ctx.AssignmentsByPrincipal[$principal])
            $m365Skus = @($skuIds | Where-Object { $ctx.Catalog.ContainsKey($_) -and $ctx.Catalog[$_].cloud -ceq 'm365' })
            if ($m365Skus.Count -lt 2) { continue }
            $sortedAssignments = Get-FinOpsOrdinalSorted -InputObject $skuIds
            foreach ($outer in $m365Skus) {
                $included = Get-FinOpsTransitiveIncludeSet -SkuId $outer -Catalog $ctx.Catalog
                foreach ($other in $m365Skus) {
                    if ($other -ceq $outer) { continue }
                    if ($included.Contains($other)) {
                        $duplicate = $ctx.Catalog[$other]
                        $redacted = Get-FinOpsRedactedPrincipal -Principal $principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                        [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                                    -CurrentSku $outer -Savings (Get-FinOpsSavingsValue -Price $duplicate.list_price_usd_month) `
                                    -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; current_sku = $outer; duplicate_sku = $other }) `
                                    -Evidence ([ordered]@{
                                        bundle          = $outer
                                        duplicate_sku   = $other
                                        all_assignments = $sortedAssignments
                                    })))
                    }
                }
            }
        }
        return $out.ToArray()
    }

    $registry['M365.DISABLED_USER_LICENSED'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        $users = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        foreach ($u in @($ctx.Dataset.users)) { $users[$u.principal] = $u }
        foreach ($principal in $ctx.AssignmentOrder) {
            if (-not $users.ContainsKey($principal)) { continue }
            $user = $users[$principal]
            if ($user.account_enabled) { continue }
            foreach ($skuId in @($ctx.AssignmentsByPrincipal[$principal])) {
                $sku = if ($ctx.Catalog.ContainsKey($skuId)) { $ctx.Catalog[$skuId] } else { $null }
                if ($null -eq $sku -or $sku.cloud -cne 'm365') { continue }
                $redacted = Get-FinOpsRedactedPrincipal -Principal $principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                            -CurrentSku $skuId -Savings (Get-FinOpsSavingsValue -Price $sku.list_price_usd_month) `
                            -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; current_sku = $skuId }) `
                            -Evidence ([ordered]@{ account_enabled = $false })))
            }
        }
        return $out.ToArray()
    }

    $registry['M365.SHARED_MAILBOX_LICENSED'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        $users = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        foreach ($u in @($ctx.Dataset.users)) { $users[$u.principal] = $u }
        foreach ($principal in $ctx.AssignmentOrder) {
            if (-not $users.ContainsKey($principal)) { continue }
            $user = $users[$principal]
            if ($user.user_type -cne 'shared_mailbox') { continue }
            $size = if ($null -ne $user.mailbox_size_gb) { [double] $user.mailbox_size_gb } else { 0.0 }
            if ($size -ge 50.0) { continue }
            foreach ($skuId in @($ctx.AssignmentsByPrincipal[$principal])) {
                $sku = if ($ctx.Catalog.ContainsKey($skuId)) { $ctx.Catalog[$skuId] } else { $null }
                if ($null -eq $sku -or $sku.cloud -cne 'm365') { continue }
                $hasMailbox = $false
                foreach ($f in (Get-FinOpsEffectiveFeatureSet -SkuId $skuId -Catalog $ctx.Catalog)) {
                    if ($f.StartsWith('mailbox.', [System.StringComparison]::Ordinal)) { $hasMailbox = $true; break }
                }
                if (-not $hasMailbox) { continue }
                $redacted = Get-FinOpsRedactedPrincipal -Principal $principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                            -CurrentSku $skuId -Savings (Get-FinOpsSavingsValue -Price $sku.list_price_usd_month) `
                            -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; current_sku = $skuId; mailbox_size_gb = [math]::Round($size, 1) }) `
                            -Evidence ([ordered]@{ mailbox_size_gb = $size; user_type = 'shared_mailbox' })))
            }
        }
        return $out.ToArray()
    }

    $registry['M365.GUEST_PREMIUM_LICENSED'] = {
        param($ctx)
        $out = [System.Collections.Generic.List[object]]::new()
        $users = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        foreach ($u in @($ctx.Dataset.users)) { $users[$u.principal] = $u }
        foreach ($principal in $ctx.AssignmentOrder) {
            if (-not $users.ContainsKey($principal)) { continue }
            $user = $users[$principal]
            if ($user.user_type -cne 'guest') { continue }
            foreach ($skuId in @($ctx.AssignmentsByPrincipal[$principal])) {
                $sku = if ($ctx.Catalog.ContainsKey($skuId)) { $ctx.Catalog[$skuId] } else { $null }
                if ($null -eq $sku -or $sku.cloud -cne 'm365') { continue }
                $redacted = Get-FinOpsRedactedPrincipal -Principal $principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
                [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                            -CurrentSku $skuId -Savings (Get-FinOpsSavingsValue -Price $sku.list_price_usd_month) `
                            -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted; current_sku = $skuId }) `
                            -Evidence ([ordered]@{ user_type = 'guest' })))
            }
        }
        return $out.ToArray()
    }

    $registry['M365.COPILOT_INACTIVE_60D'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 60 }
        $copilotSkus = Build-FinOpsOrdinalSet
        foreach ($sku in $ctx.CatalogList) {
            if ($sku.cloud -ceq 'm365' -and (@($sku.features) -ccontains 'copilot.m365')) { [void] $copilotSkus.Add($sku.id) }
        }
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($assignment in @($ctx.Dataset.assignments)) {
            if (-not $copilotSkus.Contains($assignment.sku_id)) { continue }
            $sku = if ($ctx.Catalog.ContainsKey($assignment.sku_id)) { $ctx.Catalog[$assignment.sku_id] } else { $null }
            if ($null -eq $sku) { continue }
            $usage = if ($ctx.UsageByPrincipal.ContainsKey($assignment.principal)) { $ctx.UsageByPrincipal[$assignment.principal] } else { $null }
            $last = Get-FinOpsUsageValue -Usage $usage -Signal 'copilot'
            if ($null -ne $last -and $last -le $days) { continue }
            $redacted = Get-FinOpsRedactedPrincipal -Principal $assignment.principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                        -CurrentSku $assignment.sku_id -Savings (Get-FinOpsSavingsValue -Price $sku.list_price_usd_month) `
                        -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted }) `
                        -Evidence ([ordered]@{ copilot_last_activity_days = $last; window_days = $days })))
        }
        return $out.ToArray()
    }

    $registry['M365.E5_FEATURES_UNUSED'] = {
        param($ctx)
        $days = if ($ctx.Rule.inactivity_days) { [int] $ctx.Rule.inactivity_days } else { 90 }
        $e5Skus = Build-FinOpsOrdinalSet
        foreach ($sku in $ctx.CatalogList) {
            if ($sku.cloud -cne 'm365') { continue }
            $featureSet = Build-FinOpsOrdinalSet
            foreach ($f in @($sku.features)) { [void] $featureSet.Add($f) }
            $covers = $true
            foreach ($needed in $script:FinOpsE5DefiningFeatures) {
                if (-not $featureSet.Contains($needed)) { $covers = $false; break }
            }
            if ($covers) { [void] $e5Skus.Add($sku.id) }
        }
        $out = [System.Collections.Generic.List[object]]::new()
        foreach ($assignment in @($ctx.Dataset.assignments)) {
            if (-not $e5Skus.Contains($assignment.sku_id)) { continue }
            $sku = if ($ctx.Catalog.ContainsKey($assignment.sku_id)) { $ctx.Catalog[$assignment.sku_id] } else { $null }
            if ($null -eq $sku) { continue }
            $usage = if ($ctx.UsageByPrincipal.ContainsKey($assignment.principal)) { $ctx.UsageByPrincipal[$assignment.principal] } else { $null }
            $anyActive = $false
            foreach ($sig in $script:FinOpsE5Signals) {
                $last = Get-FinOpsUsageValue -Usage $usage -Signal $sig
                if ($null -ne $last -and $last -le $days) { $anyActive = $true; break }
            }
            if ($anyActive) { continue }
            # _stepdown_sku: first successor_of id present in the catalog.
            $recommended = $null
            foreach ($predecessor in @($sku.successor_of)) {
                if ($ctx.Catalog.ContainsKey($predecessor)) { $recommended = $predecessor; break }
            }
            $recommendedEntry = if ($recommended -and $ctx.Catalog.ContainsKey($recommended)) { $ctx.Catalog[$recommended] } else { $null }
            $recPrice = if ($null -ne $recommendedEntry) { $recommendedEntry.list_price_usd_month } else { $null }
            $redacted = Get-FinOpsRedactedPrincipal -Principal $assignment.principal -RedactPii $ctx.RedactPii -Salt $ctx.Salt
            $lastMap = [ordered]@{}
            foreach ($sig in $script:FinOpsE5Signals) { $lastMap[$sig] = Get-FinOpsUsageValue -Usage $usage -Signal $sig }
            [void] $out.Add((Build-FinOpsFinding -RuleId $ctx.Rule.id -Severity $ctx.Rule.severity -Principal $redacted `
                        -CurrentSku $assignment.sku_id -RecommendedSku $recommended `
                        -Savings (Get-FinOpsDelta -Current $sku.list_price_usd_month -Recommended $recPrice) `
                        -Recommendation (Format-FinOpsRecommendation -Template $ctx.Rule.recommendation_template -Values @{ principal = $redacted }) `
                        -Evidence ([ordered]@{
                            checked_signals    = @($script:FinOpsE5Signals)
                            last_activity_days = $lastMap
                            window_days        = $days
                        })))
        }
        return $out.ToArray()
    }

    return $registry
}
