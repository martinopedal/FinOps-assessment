Set-StrictMode -Version Latest

$script:FinOpsPracticeReviewAdvisoryDisclaimer = 'This section is advisory only. It summarises operator-facing posture cues derived from the canonical report and does not constitute a maturity assessment, grade, or compliance verdict.'
$script:FinOpsPracticeReviewAdvisoryHeader = 'Advisory'
$script:FinOpsPracticeReviewSectionHeading = 'FinOps practice review'
$script:FinOpsPracticeReviewEmDash = [string] [char] 0x2014

function Get-FinOpsPracticeReviewMemberValue {
    [CmdletBinding()]
    [OutputType([object])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter()] [AllowNull()] [object] $Default = $null
    )

    if ($null -eq $InputObject) {
        return $Default
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        if ($InputObject.Contains($Name)) {
            return $InputObject[$Name]
        }
        return $Default
    }

    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -ne $property) {
        return $property.Value
    }
    return $Default
}

function Test-FinOpsPracticeReviewDictionaryPayload {
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [System.Collections.IDictionary]) {
        return $Value.Count -gt 0
    }
    if ($Value -is [pscustomobject]) {
        return $Value.PSObject.Properties.Count -gt 0
    }
    return $false
}

function Get-FinOpsPracticeReviewPricingAssumptionContext {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [object] $Report)

    $findings = @(Get-FinOpsPracticeReviewMemberValue -InputObject $Report -Name 'findings' -Default @())
    $withSavings = [System.Collections.Generic.List[object]]::new()
    $total = 0.0
    foreach ($finding in $findings) {
        $savings = Get-FinOpsPracticeReviewMemberValue -InputObject $finding -Name 'estimated_monthly_savings_usd'
        if ($null -ne $savings) {
            [void] $withSavings.Add($finding)
            $total += [double] $savings
        }
    }

    return [ordered]@{
        findings_with_estimated_savings      = $withSavings.Count
        total_estimated_monthly_savings_usd  = $total
        basis                                = 'Estimated savings are derived from public list-price catalogue defaults bundled with this tool. Customer-negotiated pricing is not distinguished in the current report schema; treat the totals as an order-of-magnitude advisory figure, not a quote.'
    }
}

function Get-FinOpsPracticeReviewDataQualityWarningList {
    [CmdletBinding()]
    [OutputType([object[]])]
    param([Parameter(Mandatory)] [object] $Report)

    $summary = Get-FinOpsPracticeReviewMemberValue -InputObject $Report -Name 'summary' -Default ([ordered]@{})
    $warnings = [System.Collections.Generic.List[string]]::new()

    $principals = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'principals_evaluated' -Default 0)
    $assignments = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'assignments_evaluated' -Default 0)
    $azureResources = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'azure_resources_evaluated' -Default 0)

    if ($principals -eq 0) {
        [void] $warnings.Add("Input snapshot contains no principals $($script:FinOpsPracticeReviewEmDash) the M365 surface evaluated against an empty dataset. Verify the user-export collector ran successfully before relying on this report.")
    }
    if ($assignments -eq 0) {
        [void] $warnings.Add("Input snapshot contains no licence assignments $($script:FinOpsPracticeReviewEmDash) the assignment dataset is empty or was not collected for this run.")
    }
    if ($azureResources -eq 0) {
        [void] $warnings.Add("Input snapshot contains no Azure resources $($script:FinOpsPracticeReviewEmDash) the Azure surface evaluated against an empty dataset; Azure findings in this report (if any) reflect catalogue defaults only.")
    }

    $skipped = @(Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'rules_skipped_no_impl' -Default @())
    if ($skipped.Count -gt 0) {
        [void] $warnings.Add("Catalogue declares $($skipped.Count) rule(s) without a runnable implementation in this build $($script:FinOpsPracticeReviewEmDash) rule coverage for this snapshot is partial. The skipped rule IDs are listed in the Summary section above.")
    }

    if (([string] (Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'pii_redaction' -Default '')) -ceq 'disabled') {
        [void] $warnings.Add("PII redaction is disabled for this run $($script:FinOpsPracticeReviewEmDash) principal identifiers in the findings table are not salted-hashed.")
    }

    return , ([object[]] $warnings.ToArray())
}

function Get-FinOpsPracticeReviewCommitmentPosture {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [object] $Report)

    $summary = Get-FinOpsPracticeReviewMemberValue -InputObject $Report -Name 'summary' -Default ([ordered]@{})
    $payload = Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'commitment_coverage'
    if (-not (Test-FinOpsPracticeReviewDictionaryPayload -Value $payload)) {
        return [ordered]@{
            available = $false
            message   = 'Commitment-coverage data is not yet surfaced in the canonical report schema. This sub-section will populate once the upstream commitment-posture contract lands.'
        }
    }
    return [ordered]@{
        available = $true
        payload   = $payload
    }
}

function Get-FinOpsPracticeReviewSkuMixPosture {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [object] $Report)

    $summary = Get-FinOpsPracticeReviewMemberValue -InputObject $Report -Name 'summary' -Default ([ordered]@{})
    $families = Get-FinOpsPracticeReviewMemberValue -InputObject $summary -Name 'm365_family_summaries'
    if ($families -is [string] -or $null -eq $families) {
        return [ordered]@{
            available = $false
            message   = 'M365 family-level SKU-mix summaries are not yet surfaced in the canonical report schema. This sub-section will populate once family summaries land in the report contract.'
            families  = @()
        }
    }

    $familyList = @($families)
    if ($familyList.Count -eq 0) {
        return [ordered]@{
            available = $false
            message   = 'M365 family-level SKU-mix summaries are not yet surfaced in the canonical report schema. This sub-section will populate once family summaries land in the report contract.'
            families  = @()
        }
    }

    $normalised = [System.Collections.Generic.List[object]]::new()
    foreach ($family in $familyList) {
        if (-not (Test-FinOpsPracticeReviewDictionaryPayload -Value $family)) {
            continue
        }
        [void] $normalised.Add([ordered]@{
                family_name                     = [string] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'family_name' -Default '')
                total_assigned                  = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'total_assigned' -Default 0)
                distinct_users_with_assignment  = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_users_with_assignment' -Default 0)
                distinct_active_users           = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_active_users' -Default 0)
                distinct_inactive_users         = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_inactive_users' -Default 0)
                coverage_note                   = Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'coverage_note'
            })
    }

    return [ordered]@{
        available = $true
        message   = $null
        families  = , ([object[]] $normalised.ToArray())
    }
}

function Get-FinOpsPracticeReview {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [object] $Report)

    return [ordered]@{
        header                = $script:FinOpsPracticeReviewAdvisoryHeader
        heading               = $script:FinOpsPracticeReviewSectionHeading
        disclaimer            = $script:FinOpsPracticeReviewAdvisoryDisclaimer
        pricing_assumptions   = Get-FinOpsPracticeReviewPricingAssumptionContext -Report $Report
        data_quality_warnings = Get-FinOpsPracticeReviewDataQualityWarningList -Report $Report
        commitment_posture    = Get-FinOpsPracticeReviewCommitmentPosture -Report $Report
        sku_mix_posture       = Get-FinOpsPracticeReviewSkuMixPosture -Report $Report
    }
}

function ConvertTo-FinOpsHtmlEscaped {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [AllowEmptyString()] [string] $Value)

    if ($null -eq $Value) {
        return ''
    }

    $escaped = [string] $Value
    $escaped = $escaped.Replace('&', '&amp;')
    $escaped = $escaped.Replace('<', '&lt;')
    $escaped = $escaped.Replace('>', '&gt;')
    $escaped = $escaped.Replace('"', '&quot;')
    $escaped = $escaped.Replace("'", '&#x27;')
    return $escaped
}

function Get-FinOpsPracticeReviewPricingHtml {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $PricingAssumptions)

    $n = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $PricingAssumptions -Name 'findings_with_estimated_savings' -Default 0)
    $total = [double] (Get-FinOpsPracticeReviewMemberValue -InputObject $PricingAssumptions -Name 'total_estimated_monthly_savings_usd' -Default 0.0)
    $basis = [string] (Get-FinOpsPracticeReviewMemberValue -InputObject $PricingAssumptions -Name 'basis' -Default '')
    $formattedTotal = $total.ToString('F2', [System.Globalization.CultureInfo]::InvariantCulture)
    return "<h3>Pricing assumptions</h3>`n<p>$(ConvertTo-FinOpsHtmlEscaped -Value $basis)</p>`n<ul>`n  <li>Findings carrying an estimated monthly saving: <strong>$n</strong></li>`n  <li>Sum of estimated monthly savings across those findings: <strong>$" + $formattedTotal + "</strong></li>`n</ul>`n"
}

function Get-FinOpsPracticeReviewDataQualityHtml {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowEmptyCollection()] [object[]] $Warnings = @())

    if ($Warnings.Count -eq 0) {
        return '<h3>Data-quality warnings</h3>' + "`n" + '<p class="empty">No data-quality warnings derived from this snapshot. Dataset coverage and rule implementation are complete for the surfaces evaluated.</p>' + "`n"
    }

    $items = @(
        foreach ($warning in $Warnings) {
            "  <li>$(ConvertTo-FinOpsHtmlEscaped -Value ([string] $warning))</li>"
        }
    ) -join "`n"
    return "<h3>Data-quality warnings</h3>`n<ul>`n$items`n</ul>`n"
}

function Get-FinOpsPracticeReviewCommitmentHtml {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $CommitmentPosture)

    if (-not [bool] (Get-FinOpsPracticeReviewMemberValue -InputObject $CommitmentPosture -Name 'available' -Default $false)) {
        $message = [string] (Get-FinOpsPracticeReviewMemberValue -InputObject $CommitmentPosture -Name 'message' -Default '')
        return "<h3>Commitment posture</h3>`n<p class=`"empty`">$(ConvertTo-FinOpsHtmlEscaped -Value $message)</p>`n"
    }

    $payload = Get-FinOpsPracticeReviewMemberValue -InputObject $CommitmentPosture -Name 'payload' -Default ([ordered]@{})
    $rows = [System.Collections.Generic.List[string]]::new()
    if ($payload -is [System.Collections.IDictionary]) {
        foreach ($key in $payload.Keys) {
            $keyText = ConvertTo-FinOpsHtmlEscaped -Value ([string] $key)
            $valueText = ConvertTo-FinOpsHtmlEscaped -Value ([string] $payload[$key])
            [void] $rows.Add("  <li><span class=`"mono`">$keyText</span>: $valueText</li>")
        }
    } elseif ($payload -is [pscustomobject]) {
        foreach ($property in $payload.PSObject.Properties) {
            $keyText = ConvertTo-FinOpsHtmlEscaped -Value ([string] $property.Name)
            $valueText = ConvertTo-FinOpsHtmlEscaped -Value ([string] $property.Value)
            [void] $rows.Add("  <li><span class=`"mono`">$keyText</span>: $valueText</li>")
        }
    }
    $rowsText = @($rows.ToArray()) -join "`n"
    return "<h3>Commitment posture</h3>`n<p>Coverage and utilisation cues derived from upstream commitment-coverage data. Posture cues only $($script:FinOpsPracticeReviewEmDash) this section does not recommend purchase actions.</p>`n<ul>`n$rowsText`n</ul>`n"
}

function Get-FinOpsPracticeReviewSkuMixHtml {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $SkuMixPosture)

    if (-not [bool] (Get-FinOpsPracticeReviewMemberValue -InputObject $SkuMixPosture -Name 'available' -Default $false)) {
        $message = [string] (Get-FinOpsPracticeReviewMemberValue -InputObject $SkuMixPosture -Name 'message' -Default '')
        return "<h3>SKU-mix posture</h3>`n<p class=`"empty`">$(ConvertTo-FinOpsHtmlEscaped -Value $message)</p>`n"
    }

    $rows = [System.Collections.Generic.List[string]]::new()
    $families = @(Get-FinOpsPracticeReviewMemberValue -InputObject $SkuMixPosture -Name 'families' -Default @())
    foreach ($family in $families) {
        $familyName = ConvertTo-FinOpsHtmlEscaped -Value ([string] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'family_name' -Default ''))
        $totalAssigned = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'total_assigned' -Default 0)
        $distinctUsers = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_users_with_assignment' -Default 0)
        $activeUsers = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_active_users' -Default 0)
        $inactiveUsers = [int] (Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'distinct_inactive_users' -Default 0)
        $coverageRaw = Get-FinOpsPracticeReviewMemberValue -InputObject $family -Name 'coverage_note'
        $coverageNote = if ($null -eq $coverageRaw) { '' } else { [string] $coverageRaw }
        $coverageEscaped = ConvertTo-FinOpsHtmlEscaped -Value $coverageNote
        [void] $rows.Add("  <tr><td class=`"mono`">$familyName</td><td>$totalAssigned</td><td>$distinctUsers</td><td>$activeUsers</td><td>$inactiveUsers</td><td>$coverageEscaped</td></tr>")
    }
    $body = @($rows.ToArray()) -join "`n"
    return "<h3>SKU-mix posture</h3>`n<p>Per-family assigned-vs-active coverage cues. Vendor-neutral and presented without ranking $($script:FinOpsPracticeReviewEmDash) no SKU family is named as preferred or recommended over another.</p>`n<table>`n  <thead><tr><th>Family</th><th>Total assigned</th><th>Distinct users</th><th>Active users</th><th>Inactive users</th><th>Note</th></tr></thead>`n  <tbody>`n$body`n  </tbody>`n</table>`n"
}

function Get-FinOpsPracticeReviewHtml {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Report)

    $context = Get-FinOpsPracticeReview -Report $Report
    $heading = ConvertTo-FinOpsHtmlEscaped -Value ([string] (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'heading' -Default ''))
    $header = ConvertTo-FinOpsHtmlEscaped -Value ([string] (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'header' -Default ''))
    $disclaimer = ConvertTo-FinOpsHtmlEscaped -Value ([string] (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'disclaimer' -Default ''))
    $pricing = Get-FinOpsPracticeReviewPricingHtml -PricingAssumptions (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'pricing_assumptions' -Default ([ordered]@{}))
    $warnings = @(Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'data_quality_warnings' -Default @())
    $dataQuality = Get-FinOpsPracticeReviewDataQualityHtml -Warnings $warnings
    $commitment = Get-FinOpsPracticeReviewCommitmentHtml -CommitmentPosture (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'commitment_posture' -Default ([ordered]@{}))
    $skuMix = Get-FinOpsPracticeReviewSkuMixHtml -SkuMixPosture (Get-FinOpsPracticeReviewMemberValue -InputObject $context -Name 'sku_mix_posture' -Default ([ordered]@{}))
    return "<section class=`"practice-review`">`n  <h2>$heading <span class=`"pill`">$header</span></h2>`n  <p class=`"disclaimer`"><em>$disclaimer</em></p>`n  $pricing  $dataQuality  $commitment  $skuMix</section>`n"
}
