Set-StrictMode -Version Latest

$script:FinOpsTriageSchemaVersion = '1.0'
$script:FinOpsTriageAdvisoryBanner = 'Template-based advisory triage only. Verify findings before action; no remediation, write scopes, or de-redaction are performed.'
$script:FinOpsTriageOwnerBySurface = @{
    m365   = 'license-admin'
    azure  = 'azure-owner'
    github = 'github-org-admin'
    ado    = 'ado-org-admin'
}
$script:FinOpsTriageChecklistBySurface = @{
    m365   = @(
        'Confirm the assigned persona and business exception with the license owner.',
        'Review recent sign-in and workload activity before changing any license.',
        'Verify compliance, mailbox, guest, or break-glass exceptions are not present.'
    )
    azure  = @(
        'Confirm the resource is still owned and in scope for optimisation.',
        'Review recent metrics, tags, and change windows before resizing or stopping.',
        'Verify reservations, commitments, or environment tags with the FinOps owner.'
    )
    github = @(
        'Confirm the seat, org, or repository ownership before changing entitlements.',
        'Review recent contribution, Copilot, GHAS, and runner usage signals.',
        'Verify security or release-engineering exceptions with the GitHub admin.'
    )
    ado    = @(
        'Confirm the Azure DevOps organisation and project ownership.',
        'Review work-item, code, pipeline, and Test Plans activity before changing access.',
        'Verify stakeholder eligibility or parallel-job needs with the ADO admin.'
    )
}
$script:FinOpsTriageQuestionsBySurface = @{
    m365   = @(
        'Is the principal covered by a legal hold, eDiscovery, shared-mailbox, or service-account exception?',
        "Does the persona assignment match the user's current role?"
    )
    azure  = @(
        'Is this workload seasonal, recently deployed, or intentionally kept warm?',
        'Would a right-size or commitment change affect availability targets?'
    )
    github = @(
        'Is the seat required for a pending project, compliance control, or release window?',
        'Are repository or runner signals delayed by billing-period timing?'
    )
    ado    = @(
        'Is the access level needed for upcoming sprint, test, or release work?',
        'Are project-level permissions or stakeholder limitations acceptable?'
    )
}

function ConvertTo-FinOpsCanonicalJsonString {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Value)

    $sb = [System.Text.StringBuilder]::new()
    [void] $sb.Append('"')
    foreach ($ch in $Value.ToCharArray()) {
        $code = [int] $ch
        switch ($ch) {
            '"' { [void] $sb.Append('\"'); continue }
            '\' { [void] $sb.Append('\\'); continue }
            "`b" { [void] $sb.Append('\b'); continue }
            "`f" { [void] $sb.Append('\f'); continue }
            "`n" { [void] $sb.Append('\n'); continue }
            "`r" { [void] $sb.Append('\r'); continue }
            "`t" { [void] $sb.Append('\t'); continue }
            default {
                if ($code -lt 0x20 -or $code -gt 0x7E) {
                    [void] $sb.Append('\u')
                    [void] $sb.Append($code.ToString('x4', [System.Globalization.CultureInfo]::InvariantCulture))
                } else {
                    [void] $sb.Append($ch)
                }
            }
        }
    }
    [void] $sb.Append('"')
    return $sb.ToString()
}

function Format-FinOpsCanonicalJsonNumber {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Value)

    if (
        $Value -is [int] -or
        $Value -is [long] -or
        $Value -is [short] -or
        $Value -is [sbyte] -or
        $Value -is [uint16] -or
        $Value -is [uint32] -or
        $Value -is [byte]
    ) {
        return ([string] $Value)
    }
    if ($Value -is [decimal]) {
        return ([decimal] $Value).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }

    $text = ([double] $Value).ToString('R', [System.Globalization.CultureInfo]::InvariantCulture)
    $text = $text.Replace('E', 'e')
    if ($text -notmatch '[.eN]') {
        $text += '.0'
    }
    return $text
}

function ConvertTo-FinOpsCanonicalJsonValue {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $InputObject)

    if ($null -eq $InputObject) { return 'null' }
    if ($InputObject -is [bool]) { return ([bool] $InputObject) ? 'true' : 'false' }
    if (
        $InputObject -is [int] -or $InputObject -is [long] -or $InputObject -is [short] -or
        $InputObject -is [sbyte] -or $InputObject -is [uint16] -or $InputObject -is [uint32] -or
        $InputObject -is [byte] -or $InputObject -is [float] -or $InputObject -is [double] -or
        $InputObject -is [decimal]
    ) {
        return Format-FinOpsCanonicalJsonNumber -Value $InputObject
    }
    if ($InputObject -is [string]) {
        return ConvertTo-FinOpsCanonicalJsonString -Value ([string] $InputObject)
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $keys = @($InputObject.Keys | ForEach-Object { [string] $_ })
        $sorted = Get-FinOpsOrdinalSorted -InputObject $keys
        $pairs = foreach ($key in $sorted) {
            (ConvertTo-FinOpsCanonicalJsonString -Value $key) + ':' + (ConvertTo-FinOpsCanonicalJsonValue -InputObject $InputObject[$key])
        }
        return '{' + ($pairs -join ',') + '}'
    }
    if ($InputObject -is [pscustomobject]) {
        $dictionary = [ordered]@{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $dictionary[$property.Name] = $property.Value
        }
        return ConvertTo-FinOpsCanonicalJsonValue -InputObject $dictionary
    }
    if ($InputObject -is [System.Collections.IEnumerable]) {
        $items = foreach ($item in $InputObject) {
            ConvertTo-FinOpsCanonicalJsonValue -InputObject $item
        }
        return '[' + (@($items) -join ',') + ']'
    }
    return ConvertTo-FinOpsCanonicalJsonString -Value ([string] $InputObject)
}

function ConvertTo-FinOpsCanonicalJson {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $InputObject)

    return ConvertTo-FinOpsCanonicalJsonValue -InputObject $InputObject
}

function Get-FinOpsTriageFindingRef {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Finding)

    $evidence = $Finding.evidence
    if ($null -eq $evidence) {
        $evidence = [ordered]@{}
    }
    $stable = [ordered]@{
        rule_id         = $Finding.rule_id
        surface         = $Finding.surface
        principal       = $Finding.principal
        current_sku     = $Finding.current_sku
        recommended_sku = $Finding.recommended_sku
        evidence        = $evidence
    }
    $payload = ConvertTo-FinOpsCanonicalJson -InputObject $stable
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($payload))
    } finally {
        $sha.Dispose()
    }
    $hex = [System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
    return 'finding:' + $hex.Substring(0, 16)
}

function Get-FinOpsTriageSourceReportPath {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()] [AllowNull()] [string] $SourcePath,
        [Parameter(Mandatory)] [bool] $RedactPii
    )

    if ([string]::IsNullOrWhiteSpace($SourcePath)) {
        return $null
    }
    if ($RedactPii) {
        return "<redacted>/$(Split-Path -Leaf $SourcePath)"
    }
    return $SourcePath
}

function Get-FinOpsTriagePriorityBucket {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Severity,
        [Parameter(Mandatory)] [string] $Confidence,
        [Parameter()] [AllowNull()] [object] $Savings
    )

    $numericSavings = if ($null -eq $Savings) { 0.0 } else { [double] $Savings }
    if ($Severity -ceq 'high' -and $Confidence -ceq 'high') { return 'p1' }
    if ($Severity -ceq 'high' -or ($Severity -ceq 'medium' -and $numericSavings -ge 100.0)) { return 'p2' }
    if ($Severity -ceq 'medium' -or $Confidence -ceq 'medium') { return 'p3' }
    return 'p4'
}

function Get-FinOpsTriageOwnerRole {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Surface,
        [Parameter(Mandatory)] [string] $RuleId
    )

    if ($RuleId.StartsWith('M365.GUEST', [System.StringComparison]::Ordinal) -or $RuleId.StartsWith('M365.DISABLED', [System.StringComparison]::Ordinal)) {
        return 'identity-admin'
    }
    if ($RuleId.StartsWith('AZ.RESERVATION', [System.StringComparison]::Ordinal) -or $RuleId.StartsWith('AZ.LOG', [System.StringComparison]::Ordinal)) {
        return 'finops-analyst'
    }
    if ($script:FinOpsTriageOwnerBySurface.ContainsKey($Surface)) {
        return $script:FinOpsTriageOwnerBySurface[$Surface]
    }
    return 'finops-analyst'
}

function Get-FinOpsTriageRationale {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Severity,
        [Parameter(Mandatory)] [string] $Confidence,
        [Parameter()] [AllowNull()] [object] $Savings,
        [Parameter(Mandatory)] [string] $Priority
    )

    $savingsText = if ($null -eq $Savings) {
        'unknown savings'
    } else {
        '$' + ([double] $Savings).ToString('F2', [System.Globalization.CultureInfo]::InvariantCulture) + '/mo estimated savings'
    }
    return "$($Priority.ToUpperInvariant()) because severity is $Severity, confidence is $Confidence, and the finding has $savingsText."
}

function Build-FinOpsTriage {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [Parameter()] [AllowNull()] [string] $SourcePath,
        [Parameter()] [ValidateSet('disabled', 'sdk', 'cli', 'unavailable')] [string] $CopilotHelper = 'disabled'
    )

    $run = $Report.run
    if ($null -eq $run) { $run = [ordered]@{} }
    $sourceFindings = @($Report.findings)
    $items = [System.Collections.Generic.List[object]]::new()
    for ($i = 0; $i -lt $sourceFindings.Count; $i++) {
        $finding = $sourceFindings[$i]
        $surface = [string] $finding.surface
        $severity = [string] $finding.severity
        $confidence = if ($null -eq $finding.confidence) { 'high' } else { [string] $finding.confidence }
        $savings = $finding.estimated_monthly_savings_usd
        $priority = Get-FinOpsTriagePriorityBucket -Severity $severity -Confidence $confidence -Savings $savings
        $item = [ordered]@{
            finding_ref                    = Get-FinOpsTriageFindingRef -Finding $finding
            source_finding_index           = $i
            rule_id                        = [string] $finding.rule_id
            surface                        = $surface
            severity                       = $severity
            confidence                     = $confidence
            principal                      = [string] $finding.principal
            current_sku                    = $finding.current_sku
            recommended_sku                = $finding.recommended_sku
            estimated_monthly_savings_usd  = $savings
            evidence_ref                   = $finding.evidence_ref
            priority_bucket                = $priority
            priority_rationale             = Get-FinOpsTriageRationale -Severity $severity -Confidence $confidence -Savings $savings -Priority $priority
            suggested_owner_role           = Get-FinOpsTriageOwnerRole -Surface $surface -RuleId ([string] $finding.rule_id)
            verification_checklist         = @($script:FinOpsTriageChecklistBySurface[$surface])
            followup_questions             = @($script:FinOpsTriageQuestionsBySurface[$surface])
            advisory                       = $true
        }
        [void] $items.Add($item)
    }

    $priorityCounts = [ordered]@{ p1 = 0; p2 = 0; p3 = 0; p4 = 0 }
    foreach ($item in $items) {
        $bucket = [string] $item.priority_bucket
        $priorityCounts[$bucket] = [int] $priorityCounts[$bucket] + 1
    }

    $piiRedaction = $true
    if ($null -ne $run.pii_redaction) {
        $piiRedaction = [bool] $run.pii_redaction
    }

    return [ordered]@{
        run     = [ordered]@{
            tool            = 'finops-assess-triage'
            version         = $run.version
            schema_version  = $script:FinOpsTriageSchemaVersion
            generated_at    = $run.generated_at
            mode            = 'advisory'
            pii_redaction   = $piiRedaction
            advisory        = $true
            advisory_banner = $script:FinOpsTriageAdvisoryBanner
            copilot_helper  = $CopilotHelper
        }
        source  = [ordered]@{
            tool                = $run.tool
            mode                = $run.mode
            schema_version      = if ($null -eq $run.schema_version) { '1.0' } else { $run.schema_version }
            report_path         = Get-FinOpsTriageSourceReportPath -SourcePath $SourcePath -RedactPii $piiRedaction
            findings_count      = $sourceFindings.Count
            input_pii_redaction = $piiRedaction
        }
        summary = [ordered]@{
            total_items     = $items.Count
            priority_counts = $priorityCounts
        }
        items   = $items.ToArray()
    }
}
