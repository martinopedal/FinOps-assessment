Set-StrictMode -Version Latest

$script:FinOpsFocusAlignedColumns = @(
    'ServiceProviderName',
    'HostProviderName',
    'ServiceName',
    'ServiceCategory',
    'ServiceSubcategory',
    'ChargeCategory',
    'ChargeClass',
    'ChargeFrequency',
    'ChargeDescription',
    'SkuId',
    'ResourceId',
    'ResourceType',
    'BillingPeriodStart',
    'BillingPeriodEnd',
    'PricingCurrency',
    'ListCost',
    'ContractedCost',
    'BilledCost',
    'EffectiveCost',
    'EstimatedMonthlySavingsUsd',
    'AdvisoryFindingKey',
    'RuleId',
    'Severity'
)

$script:FinOpsFocusAlignedAllSurfaces = @('ado', 'azure', 'github', 'm365')
$script:FinOpsFocusAlignedSurfaceMeta = @{
    azure  = @('Azure', 'Compute', '')
    m365   = @('Microsoft 365', 'Collaboration', 'user_license')
    github = @('GitHub', 'Developer Tools', 'seat')
    ado    = @('Azure DevOps', 'Developer Tools', 'seat')
}
$script:FinOpsFocusAlignedUnsupportedColumns = @(
    'BilledCost',
    'BillingAccountId',
    'BillingAccountName',
    'CommitmentDiscountId',
    'CommitmentDiscountName',
    'CommitmentDiscountType',
    'ContractedCost',
    'ContractedUnitPrice',
    'EffectiveCost',
    'ListCost',
    'ListUnitPrice',
    'PricingQuantity',
    'PricingUnit',
    'Region',
    'SkuPriceId',
    'UsageQuantity',
    'UsageUnit'
)
$script:FinOpsFocusAlignedConformanceRationale = (
    'Rows describe corrective recommendations, not billed consumption. ' +
    'Cost columns (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally ' +
    'empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. ' +
    'See docs/focus-export.md.'
)

function ConvertTo-FinOpsFocusJsonString {
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
                if ($code -lt 0x20) {
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

function ConvertTo-FinOpsFocusJsonValue {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $InputObject)

    if ($null -eq $InputObject) { return 'null' }
    if ($InputObject -is [bool]) { return ([bool] $InputObject) ? 'true' : 'false' }
    if (
        $InputObject -is [int] -or $InputObject -is [long] -or $InputObject -is [short] -or
        $InputObject -is [sbyte] -or $InputObject -is [uint16] -or $InputObject -is [uint32] -or
        $InputObject -is [byte]
    ) {
        return ([string] $InputObject)
    }
    if ($InputObject -is [string]) { return ConvertTo-FinOpsFocusJsonString -Value ([string] $InputObject) }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $keys = @($InputObject.Keys | ForEach-Object { [string] $_ })
        $sorted = Get-FinOpsOrdinalSorted -InputObject $keys
        $pairs = foreach ($key in $sorted) {
            (ConvertTo-FinOpsFocusJsonString -Value $key) + ':' + (ConvertTo-FinOpsFocusJsonValue -InputObject $InputObject[$key])
        }
        return '{' + ($pairs -join ',') + '}'
    }

    if ($InputObject -is [pscustomobject]) {
        $dictionary = [ordered]@{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $dictionary[$property.Name] = $property.Value
        }
        return ConvertTo-FinOpsFocusJsonValue -InputObject $dictionary
    }

    if ($InputObject -is [System.Collections.IEnumerable]) {
        $items = foreach ($item in $InputObject) {
            ConvertTo-FinOpsFocusJsonValue -InputObject $item
        }
        return '[' + (@($items) -join ',') + ']'
    }

    return ConvertTo-FinOpsFocusJsonString -Value ([string] $InputObject)
}

function ConvertTo-FinOpsFocusEvidenceCanonical {
    [CmdletBinding()]
    [OutputType([object])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return '' }
    if ($Value -is [bool]) { return [bool] $Value }
    if (
        $Value -is [int] -or $Value -is [long] -or $Value -is [short] -or
        $Value -is [sbyte] -or $Value -is [uint16] -or $Value -is [uint32] -or
        $Value -is [byte]
    ) {
        return $Value
    }
    if ($Value -is [float] -or $Value -is [double] -or $Value -is [decimal]) {
        return (Format-FinOpsCanonicalJsonNumber -Value $Value)
    }
    if ($Value -is [string]) { return [string] $Value }

    if ($Value -is [pscustomobject]) {
        $asDict = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $asDict[$property.Name] = $property.Value
        }
        return ConvertTo-FinOpsFocusEvidenceCanonical -Value $asDict
    }

    if ($Value -is [System.Collections.IDictionary]) {
        $result = [ordered]@{}
        $keys = @($Value.Keys | ForEach-Object { [string] $_ })
        foreach ($key in (Get-FinOpsOrdinalSorted -InputObject $keys)) {
            $result[$key] = ConvertTo-FinOpsFocusEvidenceCanonical -Value $Value[$key]
        }
        return $result
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $items = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) {
            [void] $items.Add((ConvertTo-FinOpsFocusEvidenceCanonical -Value $item))
        }
        return , ([object[]] $items.ToArray())
    }

    throw "unhashable evidence value type: $($Value.GetType().Name)"
}

function Get-FinOpsFocusAdvisoryFindingKey {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Finding)

    $ruleId = if ($null -eq $Finding.rule_id) { '' } else { [string] $Finding.rule_id }
    $resourceId = if ($null -eq $Finding.principal) { '' } else { [string] $Finding.principal }
    $evidence = $Finding.evidence
    if ($null -eq $evidence) {
        $evidence = [ordered]@{}
    }
    $canonical = ConvertTo-FinOpsFocusEvidenceCanonical -Value $evidence
    $normalized = ConvertTo-FinOpsFocusJsonValue -InputObject $canonical
    $envelope = ConvertTo-FinOpsFocusJsonValue -InputObject @($ruleId, $resourceId, $normalized)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($envelope))
    } finally {
        $sha.Dispose()
    }
    return [System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
}

function Get-FinOpsNowUtc {
    [CmdletBinding()]
    [OutputType([System.DateTimeOffset])]
    param()

    $epoch = $env:SOURCE_DATE_EPOCH
    if ($epoch) {
        [long] $seconds = 0
        if ([long]::TryParse($epoch, [ref] $seconds)) {
            try {
                return [System.DateTimeOffset]::FromUnixTimeSeconds($seconds).ToUniversalTime()
            } catch {
                Write-Verbose "Ignoring out-of-range SOURCE_DATE_EPOCH '$epoch'"
            }
        }
    }
    return [System.DateTimeOffset]::UtcNow
}

function Get-FinOpsFocusBillingPeriod {
    [CmdletBinding()]
    [OutputType([string[]])]
    param([Parameter(Mandatory)] [object] $Finding)

    $raw = $null
    if ($null -ne $Finding.evidence -and $null -ne $Finding.evidence.PSObject.Properties['observation_window_end']) {
        $raw = $Finding.evidence.observation_window_end
    }

    $dt = $null
    if (-not [string]::IsNullOrWhiteSpace([string] $raw)) {
        $text = [string] $raw
        $inv = [System.Globalization.CultureInfo]::InvariantCulture
        $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal
        $formats = @('yyyy-MM-ddTHH:mm:ssK', "yyyy-MM-ddTHH:mm:ss'Z'")
        foreach ($format in $formats) {
            $parsed = [System.DateTimeOffset]::MinValue
            if ([System.DateTimeOffset]::TryParseExact($text, $format, $inv, $styles, [ref] $parsed)) {
                $dt = $parsed.ToUniversalTime()
                break
            }
        }
        if ($null -eq $dt) {
            $dateOnly = [datetime]::MinValue
            if ([datetime]::TryParseExact($text, 'yyyy-MM-dd', $inv, [System.Globalization.DateTimeStyles]::None, [ref] $dateOnly)) {
                $dt = [System.DateTimeOffset]::new(
                    $dateOnly.Year,
                    $dateOnly.Month,
                    $dateOnly.Day,
                    0,
                    0,
                    0,
                    [System.TimeSpan]::Zero
                )
            }
        }
    }

    if ($null -eq $dt) {
        $dt = Get-FinOpsNowUtc
    }

    $start = [System.DateTimeOffset]::new($dt.Year, $dt.Month, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    if ($start.Month -eq 12) {
        $end = [System.DateTimeOffset]::new($start.Year + 1, 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    } else {
        $end = [System.DateTimeOffset]::new($start.Year, $start.Month + 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    }
    $fmt = "yyyy-MM-ddTHH:mm:ss'Z'"
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    return @($start.ToString($fmt, $inv), $end.ToString($fmt, $inv))
}

function ConvertTo-FinOpsFocusSavingsString {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return '' }
    if (
        $Value -is [int] -or $Value -is [long] -or $Value -is [short] -or
        $Value -is [sbyte] -or $Value -is [uint16] -or $Value -is [uint32] -or
        $Value -is [byte]
    ) {
        return ([string] $Value)
    }
    if ($Value -is [float] -or $Value -is [double] -or $Value -is [decimal]) {
        return Format-FinOpsCanonicalJsonNumber -Value $Value
    }
    return [string] $Value
}

function Get-FinOpsFocusAlignedRow {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [object] $Finding)

    $surface = if ($null -eq $Finding.surface) { 'azure' } else { [string] $Finding.surface }
    $meta = $script:FinOpsFocusAlignedSurfaceMeta[$surface]
    if ($null -eq $meta) {
        $serviceName = 'Unknown'
        $serviceCategory = 'Unknown'
        $resourceType = ''
    } else {
        $serviceName = [string] $meta[0]
        $serviceCategory = [string] $meta[1]
        $resourceType = [string] $meta[2]
    }

    $period = Get-FinOpsFocusBillingPeriod -Finding $Finding

    return [ordered]@{
        ServiceProviderName         = 'Microsoft'
        HostProviderName            = 'Microsoft'
        ServiceName                 = $serviceName
        ServiceCategory             = $serviceCategory
        ServiceSubcategory          = ''
        ChargeCategory              = 'Advisory'
        ChargeClass                 = 'Optimization'
        ChargeFrequency             = 'Monthly'
        ChargeDescription           = if ($null -eq $Finding.recommendation) { '' } else { [string] $Finding.recommendation }
        SkuId                       = if ([string]::IsNullOrEmpty([string] $Finding.current_sku)) { '' } else { [string] $Finding.current_sku }
        ResourceId                  = if ($null -eq $Finding.principal) { '' } else { [string] $Finding.principal }
        ResourceType                = $resourceType
        BillingPeriodStart          = [string] $period[0]
        BillingPeriodEnd            = [string] $period[1]
        PricingCurrency             = 'USD'
        ListCost                    = ''
        ContractedCost              = ''
        BilledCost                  = ''
        EffectiveCost               = ''
        EstimatedMonthlySavingsUsd  = ConvertTo-FinOpsFocusSavingsString -Value $Finding.estimated_monthly_savings_usd
        AdvisoryFindingKey          = Get-FinOpsFocusAdvisoryFindingKey -Finding $Finding
        RuleId                      = if ($null -eq $Finding.rule_id) { '' } else { [string] $Finding.rule_id }
        Severity                    = if ($null -eq $Finding.severity) { '' } else { [string] $Finding.severity }
    }
}

function Split-FinOpsFocusAlignedFindingSet {
    [CmdletBinding()]
    [OutputType([object[]])]
    param(
        [Parameter(Mandatory)] [object[]] $Findings,
        [Parameter(Mandatory)] [string[]] $Surfaces
    )

    $surfaceSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($surface in $Surfaces) {
        [void] $surfaceSet.Add([string] $surface)
    }

    $included = [System.Collections.Generic.List[object]]::new()
    $skipped = @{}
    foreach ($finding in $Findings) {
        $surface = if ($null -eq $finding.surface) { '' } else { [string] $finding.surface }
        if ($surfaceSet.Contains($surface)) {
            [void] $included.Add($finding)
        } else {
            if (-not $skipped.ContainsKey($surface)) {
                $skipped[$surface] = 0
            }
            $skipped[$surface] = [int] $skipped[$surface] + 1
        }
    }

    $orderedSkipped = [ordered]@{}
    foreach ($surface in (Get-FinOpsOrdinalSorted -InputObject @($skipped.Keys | ForEach-Object { [string] $_ }))) {
        $orderedSkipped[$surface] = [int] $skipped[$surface]
    }

    return @($included.ToArray(), $orderedSkipped)
}

function Get-FinOpsFocusPiiModeName {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [bool] $PiiRedaction,
        [Parameter(Mandatory)] [string] $SaltMode,
        [Parameter(Mandatory)] [string[]] $SurfacesIncluded
    )

    $hasNonAzure = $false
    foreach ($surface in $SurfacesIncluded) {
        if ($surface -cne 'azure') {
            $hasNonAzure = $true
            break
        }
    }

    if (-not $PiiRedaction) {
        return $hasNonAzure ? 'principal_cleartext' : 'azure_resource_id_cleartext'
    }
    if ($SaltMode -ceq 'tenant_stable') {
        return $hasNonAzure ? 'principal_tenant_stable_salted_hash' : 'azure_resource_id_tenant_stable_salted_hash'
    }
    return $hasNonAzure ? 'principal_per_run_salted_hash' : 'azure_resource_id_per_run_salted_hash'
}

function Build-FinOpsFocusAlignedManifest {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [Parameter(Mandatory)] [object[]] $IncludedRows,
        [Parameter(Mandatory)] [System.Collections.IDictionary] $Skipped,
        [Parameter(Mandatory)] [string[]] $SurfacesRequested
    )

    $null = $SurfacesRequested

    $run = $Report.run
    if ($null -eq $run) { $run = [ordered]@{} }
    $piiRedaction = $true
    if ($null -ne $run.pii_redaction) {
        $piiRedaction = [bool] $run.pii_redaction
    }
    $saltMode = if ([string]::IsNullOrWhiteSpace([string] $run.salt_mode)) { 'per_run' } else { [string] $run.salt_mode }

    $surfaceSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($row in $IncludedRows) {
        $surface = if ($null -eq $row.surface) { '' } else { [string] $row.surface }
        if (-not [string]::IsNullOrEmpty($surface)) {
            [void] $surfaceSet.Add($surface)
        }
    }
    $actualSurfaces = Get-FinOpsOrdinalSorted -InputObject @($surfaceSet)
    $mode = Get-FinOpsFocusPiiModeName -PiiRedaction $piiRedaction -SaltMode $saltMode -SurfacesIncluded $actualSurfaces

    if ($mode -in @('azure_resource_id_tenant_stable_salted_hash', 'principal_tenant_stable_salted_hash')) {
        $piiHandling = [ordered]@{
            mode             = $mode
            salt_mode        = 'tenant_stable'
            known_limitation = $null
        }
        $resourceIdStability = 'stable'
        $advisoryKeyStability = 'stable'
        $advisoryKeyNotes = 'Stable across runs for the same (rule_id, resource_id, evidence) with tenant-stable salt. Not a FOCUS column.'
    } elseif ($mode -in @('azure_resource_id_per_run_salted_hash', 'principal_per_run_salted_hash')) {
        $piiHandling = [ordered]@{
            mode             = $mode
            salt_mode        = 'per_run'
            known_limitation = (
                'ResourceId is the engine''s salted hash of the cleartext principal ' +
                'under default redaction; AdvisoryFindingKey rotates ' +
                'with the per-run salt and is unsafe for cross-run joins. ' +
                'Re-runs will produce duplicate advisory rows. Engine ' +
                'tenant-stable salting is available via #73; until then, run ' +
                'with --no-pii-redaction or accept the per-run instability.'
            )
        }
        $resourceIdStability = 'per_run'
        $advisoryKeyStability = 'per_run'
        $advisoryKeyNotes = (
            'Stable across runs for the same (rule_id, resource_id, evidence) ' +
            'ONLY when --no-pii-redaction is set; otherwise rotates with the ' +
            'per-run salt. Not a FOCUS column.'
        )
    } else {
        $piiHandling = [ordered]@{
            mode             = $mode
            salt_mode        = 'disabled'
            known_limitation = $null
        }
        $resourceIdStability = 'stable'
        $advisoryKeyStability = 'stable'
        $advisoryKeyNotes = 'Stable across runs for the same (rule_id, resource_id, evidence). Not a FOCUS column.'
    }

    $skippedOrdered = [ordered]@{}
    foreach ($key in (Get-FinOpsOrdinalSorted -InputObject @($Skipped.Keys | ForEach-Object { [string] $_ }))) {
        $skippedOrdered[$key] = [int] $Skipped[$key]
    }

    return [ordered]@{
        manifest_schema_version = '0.1'
        tool                    = [ordered]@{
            name    = 'finops-assess'
            version = Get-FinOpsPackageVersion
        }
        generated_at            = Get-FinOpsGeneratedAt
        source_report           = [ordered]@{
            path           = if ($null -eq $run.input) { '' } else { [string] $run.input }
            schema_version = if ([string]::IsNullOrWhiteSpace([string] $run.schema_version)) { '1.0' } else { [string] $run.schema_version }
            pii_redaction  = $piiRedaction
        }
        dataset_type            = 'advisory'
        focus_version           = '1.3'
        conformance_level       = 'non-conformant'
        conformance_rationale   = $script:FinOpsFocusAlignedConformanceRationale
        surfaces_included       = @($actualSurfaces)
        surfaces_skipped        = $skippedOrdered
        row_count               = @($IncludedRows).Count
        unsupported_columns     = @($script:FinOpsFocusAlignedUnsupportedColumns)
        join_keys               = @(
            [ordered]@{
                column    = 'ResourceId'
                joins_to  = 'FOCUS.ResourceId'
                stability = $resourceIdStability
            },
            [ordered]@{
                column    = 'AdvisoryFindingKey'
                joins_to  = $null
                stability = $advisoryKeyStability
                notes     = $advisoryKeyNotes
            }
        )
        pii_handling            = $piiHandling
        non_additive_warning    = $true
        column_order            = @($script:FinOpsFocusAlignedColumns)
        evidence_key_fields     = @('rule_id', 'resource_id', 'normalized_evidence')
        evidence_key_algorithm  = 'sha256(json_envelope([rule_id, resource_id, normalized_evidence_json]))'
    }
}

function ConvertTo-FinOpsFocusAlignedCsv {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object[]] $Findings)

    $lines = [System.Collections.Generic.List[string]]::new()
    $header = ($script:FinOpsFocusAlignedColumns | ForEach-Object { ConvertTo-FinOpsCsvField -Value $_ }) -join ','
    [void] $lines.Add($header)

    foreach ($finding in $Findings) {
        $row = Get-FinOpsFocusAlignedRow -Finding $finding
        $cells = foreach ($column in $script:FinOpsFocusAlignedColumns) {
            $value = if ($row.Contains($column)) { [string] $row[$column] } else { '' }
            ConvertTo-FinOpsCsvField -Value $value
        }
        [void] $lines.Add(($cells -join ','))
    }
    return ($lines -join "`n") + "`n"
}

function Write-FinOpsFocusAlignedExport {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [Parameter(Mandatory)] [string] $OutputPath,
        [Parameter()] [string[]] $Surface = $script:FinOpsFocusAlignedAllSurfaces
    )

    $outPath = [System.IO.Path]::GetFullPath($OutputPath)
    $outDir = Split-Path -Parent $outPath
    if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    $sourceFindings = @($Report.findings)
    $split = Split-FinOpsFocusAlignedFindingSet -Findings $sourceFindings -Surfaces $Surface
    $included = @($split[0])
    $skipped = $split[1]

    $ordinal = [System.StringComparer]::Ordinal
    $orderedRows = [System.Linq.Enumerable]::OrderBy(
        [object[]] $included,
        [System.Func[object, string]] {
            param($f)
            if ($null -eq $f.surface) { return '' }
            return [string] $f.surface
        },
        $ordinal
    )
    $orderedRows = [System.Linq.Enumerable]::ThenBy(
        $orderedRows,
        [System.Func[object, string]] {
            param($f)
            if ($null -eq $f.rule_id) { return '' }
            return [string] $f.rule_id
        },
        $ordinal
    )
    $orderedRows = [System.Linq.Enumerable]::ThenBy(
        $orderedRows,
        [System.Func[object, string]] {
            param($f)
            if ($null -eq $f.principal) { return '' }
            return [string] $f.principal
        },
        $ordinal
    )
    $sorted = @($orderedRows)

    $csv = ConvertTo-FinOpsFocusAlignedCsv -Findings $sorted
    [System.IO.File]::WriteAllText($outPath, ($csv -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))

    $manifest = Build-FinOpsFocusAlignedManifest -Report $Report -IncludedRows $sorted -Skipped $skipped -SurfacesRequested $Surface
    $manifestPath = $outPath + '.manifest.json'
    $manifestJson = $manifest | ConvertTo-Json -Depth 64
    [System.IO.File]::WriteAllText(
        $manifestPath,
        (($manifestJson -replace "`r`n", "`n") + "`n"),
        (New-Object System.Text.UTF8Encoding($false))
    )

    return [ordered]@{
        csv_path      = $outPath
        manifest_path = $manifestPath
    }
}