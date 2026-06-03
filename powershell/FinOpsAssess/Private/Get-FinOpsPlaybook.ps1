Set-StrictMode -Version Latest

$script:FinOpsPlaybookSchemaVersion = '0.1'
$script:FinOpsPlaybookFindingRevision = 1
$script:FinOpsPlaybookEmDash = [string] [char] 0x2014
$script:FinOpsPlaybookKnownLimitationPerRun = "ticket_key is per_run for ALL surfaces when PII redaction is on (the engine salts every principal $($script:FinOpsPlaybookEmDash) including Azure resource IDs $($script:FinOpsPlaybookEmDash) with a per-run secret).  Cross-run deduplication is unsafe under this mode.  Engine tenant-stable salting is deferred to #73; until then, run with --no-pii-redaction or accept that re-runs will produce duplicate tickets."
$script:FinOpsPlaybookStableSurfaces = @('ado', 'azure', 'github', 'm365')
$script:FinOpsPlaybookSectionMarkers = [ordered]@{
    '[TITLE]'                  = 'title'
    '[DESCRIPTION]'            = 'description'
    '[REMEDIATION_STEPS]'      = 'remediation_steps'
    '[VERIFICATION_CHECKLIST]' = 'verification_checklist'
    '[REFERENCES]'             = 'references'
}
$script:FinOpsPlaybookSeverityAdapter = [ordered]@{
    high   = [ordered]@{
        servicenow = [ordered]@{ category = 'Cloud Cost Optimisation'; urgency = 1; priority = 1 }
        jira       = [ordered]@{ issuetype = 'Task'; priority = 'High'; labels = @('finops', 'severity:high') }
        github     = [ordered]@{ labels = @('finops', 'severity:high') }
    }
    medium = [ordered]@{
        servicenow = [ordered]@{ category = 'Cloud Cost Optimisation'; urgency = 2; priority = 2 }
        jira       = [ordered]@{ issuetype = 'Task'; priority = 'Medium'; labels = @('finops', 'severity:medium') }
        github     = [ordered]@{ labels = @('finops', 'severity:medium') }
    }
    low    = [ordered]@{
        servicenow = [ordered]@{ category = 'Cloud Cost Optimisation'; urgency = 3; priority = 3 }
        jira       = [ordered]@{ issuetype = 'Task'; priority = 'Low'; labels = @('finops', 'severity:low') }
        github     = [ordered]@{ labels = @('finops', 'severity:low') }
    }
    info   = [ordered]@{
        servicenow = [ordered]@{ category = 'Cloud Cost Optimisation'; urgency = 4; priority = 4 }
        jira       = [ordered]@{ issuetype = 'Task'; priority = 'Lowest'; labels = @('finops', 'severity:info') }
        github     = [ordered]@{ labels = @('finops', 'severity:info') }
    }
}

function Get-FinOpsPlaybookField {
    [CmdletBinding()]
    [OutputType([object])]
    param(
        [Parameter(Mandatory)] [AllowNull()] [object] $Object,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter()] [AllowNull()] [object] $Default = $null
    )

    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $Default
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $Default
}

function ConvertTo-FinOpsPlaybookJsonString {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Value,
        [Parameter()] [bool] $EnsureAscii = $false
    )

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
                if ($code -lt 0x20 -or ($EnsureAscii -and $code -gt 0x7E)) {
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

function ConvertTo-FinOpsPlaybookJsonValue {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter()] [bool] $SortKeys = $false,
        [Parameter()] [bool] $Compact = $false,
        [Parameter()] [bool] $EnsureAscii = $false
    )

    if ($null -eq $InputObject) { return 'null' }
    if ($InputObject -is [bool]) { return ([bool] $InputObject) ? 'true' : 'false' }

    if (
        $InputObject -is [int] -or $InputObject -is [long] -or $InputObject -is [short] -or
        $InputObject -is [sbyte] -or $InputObject -is [uint16] -or $InputObject -is [uint32] -or
        $InputObject -is [byte]
    ) {
        return ([string] $InputObject)
    }

    if ($InputObject -is [double] -or $InputObject -is [single] -or $InputObject -is [decimal]) {
        return (Format-FinOpsPyFloat -Value ([double] $InputObject)).Replace('E', 'e')
    }

    if ($InputObject -is [string]) {
        return ConvertTo-FinOpsPlaybookJsonString -Value ([string] $InputObject) -EnsureAscii $EnsureAscii
    }

    if ($InputObject -is [pscustomobject]) {
        $asMap = [ordered]@{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $asMap[$property.Name] = $property.Value
        }
        return ConvertTo-FinOpsPlaybookJsonValue -InputObject $asMap -SortKeys $SortKeys -Compact $Compact -EnsureAscii $EnsureAscii
    }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $keys = @($InputObject.Keys | ForEach-Object { [string] $_ })
        if ($SortKeys) {
            $keys = Get-FinOpsOrdinalSorted -InputObject $keys
        }
        $pairSeparator = if ($Compact) { ',' } else { ', ' }
        $valueSeparator = if ($Compact) { ':' } else { ': ' }
        $pairs = foreach ($key in $keys) {
            (ConvertTo-FinOpsPlaybookJsonString -Value $key -EnsureAscii $EnsureAscii) +
            $valueSeparator +
            (ConvertTo-FinOpsPlaybookJsonValue -InputObject $InputObject[$key] -SortKeys $SortKeys -Compact $Compact -EnsureAscii $EnsureAscii)
        }
        return '{' + (@($pairs) -join $pairSeparator) + '}'
    }

    if ($InputObject -is [System.Collections.IEnumerable]) {
        $itemSeparator = if ($Compact) { ',' } else { ', ' }
        $items = foreach ($item in $InputObject) {
            ConvertTo-FinOpsPlaybookJsonValue -InputObject $item -SortKeys $SortKeys -Compact $Compact -EnsureAscii $EnsureAscii
        }
        return '[' + (@($items) -join $itemSeparator) + ']'
    }

    return ConvertTo-FinOpsPlaybookJsonString -Value ([string] $InputObject) -EnsureAscii $EnsureAscii
}

function ConvertTo-FinOpsPlaybookJson {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter()] [bool] $SortKeys = $false,
        [Parameter()] [bool] $Compact = $false,
        [Parameter()] [bool] $EnsureAscii = $false
    )

    return ConvertTo-FinOpsPlaybookJsonValue -InputObject $InputObject -SortKeys $SortKeys -Compact $Compact -EnsureAscii $EnsureAscii
}

function ConvertTo-FinOpsJinjaScalarString {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return 'None' }
    if ($Value -is [bool]) { return ([bool] $Value) ? 'True' : 'False' }
    if (
        $Value -is [int] -or $Value -is [long] -or $Value -is [short] -or
        $Value -is [sbyte] -or $Value -is [uint16] -or $Value -is [uint32] -or
        $Value -is [byte]
    ) {
        return ([string] $Value)
    }
    if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
        return (Format-FinOpsPyFloat -Value ([double] $Value)).Replace('E', 'e')
    }
    return [string] $Value
}

function Test-FinOpsJinjaTruthy {
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [bool]) { return [bool] $Value }
    if ($Value -is [string]) { return ([string] $Value).Length -gt 0 }
    if (
        $Value -is [int] -or $Value -is [long] -or $Value -is [short] -or
        $Value -is [sbyte] -or $Value -is [uint16] -or $Value -is [uint32] -or
        $Value -is [byte] -or $Value -is [double] -or $Value -is [single] -or
        $Value -is [decimal]
    ) {
        return ([double] $Value) -ne 0.0
    }
    if ($Value -is [System.Collections.IDictionary]) { return $Value.Count -gt 0 }
    if ($Value -is [System.Collections.IEnumerable]) {
        foreach ($item in $Value) { return $true }
        return $false
    }
    return $true
}

function Resolve-FinOpsPlaybookExpression {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Expression,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string, object]] $Context
    )

    $expr = $Expression.Trim()

    $match = [regex]::Match($expr, "^([A-Za-z_][A-Za-z0-9_]*)\s+if\s+\1\s+is\s+defined\s+else\s+'([^']*)'$")
    if ($match.Success) {
        $name = $match.Groups[1].Value
        if ($Context.ContainsKey($name)) {
            return ConvertTo-FinOpsJinjaScalarString -Value $Context[$name]
        }
        return $match.Groups[2].Value
    }

    $match = [regex]::Match($expr, "^([A-Za-z_][A-Za-z0-9_]*)\s+if\s+\1\s+else\s+'([^']*)'$")
    if ($match.Success) {
        $name = $match.Groups[1].Value
        if (-not $Context.ContainsKey($name)) {
            throw "Jinja StrictUndefined: '$name' is undefined in template expression '$expr'."
        }
        $value = $Context[$name]
        if (Test-FinOpsJinjaTruthy -Value $value) {
            return ConvertTo-FinOpsJinjaScalarString -Value $value
        }
        return $match.Groups[2].Value
    }

    $match = [regex]::Match($expr, "^([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*default\('([^']*)'\)$")
    if ($match.Success) {
        $name = $match.Groups[1].Value
        if ($Context.ContainsKey($name)) {
            return ConvertTo-FinOpsJinjaScalarString -Value $Context[$name]
        }
        return $match.Groups[2].Value
    }

    $match = [regex]::Match($expr, "^([A-Za-z_][A-Za-z0-9_]*)$")
    if ($match.Success) {
        $name = $match.Groups[1].Value
        if (-not $Context.ContainsKey($name)) {
            throw "Jinja StrictUndefined: '$name' is undefined in template expression '$expr'."
        }
        return ConvertTo-FinOpsJinjaScalarString -Value $Context[$name]
    }

    throw "Unsupported playbook template expression: $expr"
}

function ConvertTo-FinOpsPlaybookTemplate {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Template,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string, object]] $Context
    )

    $regex = [regex]::new('\{\{\s*(.*?)\s*\}\}', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $sb = [System.Text.StringBuilder]::new()
    $cursor = 0
    foreach ($match in $regex.Matches($Template)) {
        [void] $sb.Append($Template.Substring($cursor, $match.Index - $cursor))
        $replacement = Resolve-FinOpsPlaybookExpression -Expression $match.Groups[1].Value -Context $Context
        [void] $sb.Append($replacement)
        $cursor = $match.Index + $match.Length
    }
    [void] $sb.Append($Template.Substring($cursor))
    return $sb.ToString()
}

function ConvertFrom-FinOpsPlaybookTemplateOutput {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [string] $Rendered)

    $sections = [ordered]@{
        '[TITLE]'                  = [System.Collections.Generic.List[string]]::new()
        '[DESCRIPTION]'            = [System.Collections.Generic.List[string]]::new()
        '[REMEDIATION_STEPS]'      = [System.Collections.Generic.List[string]]::new()
        '[VERIFICATION_CHECKLIST]' = [System.Collections.Generic.List[string]]::new()
        '[REFERENCES]'             = [System.Collections.Generic.List[string]]::new()
    }

    $current = $null
    $lines = ($Rendered -replace "`r`n", "`n" -replace "`r", "`n").Split("`n")
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($sections.Contains($trimmed)) {
            $current = $trimmed
            continue
        }
        if ($null -ne $current) {
            [void] $sections[$current].Add($line)
        }
    }

    $listFromSection = {
        param([string] $Section)
        $items = [System.Collections.Generic.List[string]]::new()
        foreach ($raw in $sections[$Section]) {
            $text = $raw.Trim()
            if (-not [string]::IsNullOrEmpty($text)) {
                [void] $items.Add($text)
            }
        }
        return $items.ToArray()
    }

    return [ordered]@{
        title                  = (@($sections['[TITLE]']) -join "`n").Trim()
        description            = (@($sections['[DESCRIPTION]']) -join "`n").Trim()
        remediation_steps      = & $listFromSection '[REMEDIATION_STEPS]'
        verification_checklist = & $listFromSection '[VERIFICATION_CHECKLIST]'
        references             = & $listFromSection '[REFERENCES]'
    }
}

function ConvertTo-FinOpsPlaybookCanonicalEvidence {
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
    if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
        return (Format-FinOpsPyFloat -Value ([double] $Value)).Replace('E', 'e')
    }
    if ($Value -is [string]) { return [string] $Value }

    if ($Value -is [pscustomobject]) {
        $dict = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $dict[$property.Name] = $property.Value
        }
        return ConvertTo-FinOpsPlaybookCanonicalEvidence -Value $dict
    }

    if ($Value -is [System.Collections.IDictionary]) {
        $out = [ordered]@{}
        $keys = Get-FinOpsOrdinalSorted -InputObject @($Value.Keys | ForEach-Object { [string] $_ })
        foreach ($key in $keys) {
            $out[$key] = ConvertTo-FinOpsPlaybookCanonicalEvidence -Value $Value[$key]
        }
        return $out
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $items = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) {
            [void] $items.Add((ConvertTo-FinOpsPlaybookCanonicalEvidence -Value $item))
        }
        return , ($items.ToArray())
    }

    throw "unhashable evidence value type: $($Value.GetType().Name)"
}

function Get-FinOpsPlaybookTicketKey {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Finding)

    $ruleId = [string] (Get-FinOpsPlaybookField -Object $Finding -Name 'rule_id' -Default '')
    $principal = [string] (Get-FinOpsPlaybookField -Object $Finding -Name 'principal' -Default '')
    $evidence = Get-FinOpsPlaybookField -Object $Finding -Name 'evidence' -Default ([ordered]@{})
    $norm = ConvertTo-FinOpsPlaybookJson -InputObject (ConvertTo-FinOpsPlaybookCanonicalEvidence -Value $evidence) -SortKeys $true -Compact $true -EnsureAscii $false
    $envelope = ConvertTo-FinOpsPlaybookJson -InputObject @($ruleId, $principal, $norm) -Compact $true -EnsureAscii $false

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($envelope)
        $hash = $sha.ComputeHash($bytes)
    } finally {
        $sha.Dispose()
    }
    $hex = [System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
    return "sha256:$hex"
}

function Get-FinOpsPlaybookAdapterHintMap {
    [CmdletBinding()]
    [OutputType([object])]
    param([Parameter(Mandatory)] [string] $Severity)

    if ($script:FinOpsPlaybookSeverityAdapter.Contains($Severity)) {
        return $script:FinOpsPlaybookSeverityAdapter[$Severity]
    }
    return $script:FinOpsPlaybookSeverityAdapter['info']
}

function Get-FinOpsPlaybookSortTuple {
    [CmdletBinding()]
    [OutputType([string[]])]
    param([Parameter(Mandatory)] [object] $Row)

    $evidenceRef = Get-FinOpsPlaybookField -Object $Row -Name 'evidence_ref' -Default ''
    if ($null -eq $evidenceRef) { $evidenceRef = '' }

    return @(
        [string] (Get-FinOpsPlaybookField -Object $Row -Name 'surface' -Default ''),
        [string] (Get-FinOpsPlaybookField -Object $Row -Name 'rule_id' -Default ''),
        [string] (Get-FinOpsPlaybookField -Object $Row -Name 'ticket_key' -Default ''),
        [string] $evidenceRef
    )
}

function Write-FinOpsPlaybookAtomicText {
    [CmdletBinding()]
    [OutputType([void])]
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $Text
    )

    $directory = Split-Path -Parent $Path
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $leaf = [System.IO.Path]::GetFileName($Path)
    $tmpPath = Join-Path $directory ('.tmp-{0}-{1}' -f $leaf, [System.IO.Path]::GetRandomFileName())
    try {
        [System.IO.File]::WriteAllText($tmpPath, ($Text -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $tmpPath -Destination $Path -Force
    } catch {
        if (Test-Path -LiteralPath $tmpPath) {
            Remove-Item -LiteralPath $tmpPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Get-FinOpsPlaybookManifest {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [Parameter(Mandatory)] [int] $RowCount,
        [Parameter(Mandatory)] [string] $JsonlSha256,
        [Parameter(Mandatory)] [int] $JsonlByteCount,
        [Parameter(Mandatory)] [string[]] $Surfaces,
        [Parameter(Mandatory)] [bool] $PiiRedaction
    )

    $run = Get-FinOpsPlaybookField -Object $Report -Name 'run' -Default ([ordered]@{})
    $saltMode = [string] (Get-FinOpsPlaybookField -Object $run -Name 'salt_mode' -Default 'per_run')

    if ($PiiRedaction -and $saltMode -ceq 'tenant_stable') {
        $stability = [ordered]@{ ado = 'stable'; azure = 'stable'; github = 'stable'; m365 = 'stable' }
        $knownLimitation = $null
    } elseif ($PiiRedaction) {
        $stability = [ordered]@{ ado = 'per_run'; azure = 'per_run'; github = 'per_run'; m365 = 'per_run' }
        $knownLimitation = $script:FinOpsPlaybookKnownLimitationPerRun
    } else {
        $stability = [ordered]@{ ado = 'stable'; azure = 'stable'; github = 'stable'; m365 = 'stable' }
        $knownLimitation = $null
    }

    return [ordered]@{
        playbook_schema_version = $script:FinOpsPlaybookSchemaVersion
        tool                    = [ordered]@{
            name    = 'finops-assess'
            version = Get-FinOpsModuleVersion
        }
        generated_at            = Get-FinOpsGeneratedAt
        source_report           = [ordered]@{
            path          = [string] (Get-FinOpsPlaybookField -Object $run -Name 'input' -Default '')
            schema_version = [string] (Get-FinOpsPlaybookField -Object $run -Name 'schema_version' -Default '1.0')
            pii_redaction = Get-FinOpsPlaybookField -Object $run -Name 'pii_redaction' -Default $PiiRedaction
        }
        row_count               = $RowCount
        output_artifacts        = [ordered]@{
            jsonl_sha256     = $JsonlSha256
            jsonl_byte_count = $JsonlByteCount
        }
        pii_handling            = [ordered]@{
            mode                           = if ($PiiRedaction) { 'salted_hash' } else { 'cleartext' }
            salt_mode                      = if ($PiiRedaction) { $saltMode } else { 'disabled' }
            ticket_key_stability_by_surface = $stability
            known_limitation               = $knownLimitation
        }
        surfaces               = @($Surfaces)
        sort_key               = '(surface, rule_id, ticket_key, evidence_ref)'
        templates_source       = 'importlib.resources:finops_assess.data.playbooks'
    }
}

function Write-FinOpsPlaybookExport {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [Parameter(Mandatory)] [string] $OutputPath
    )

    $projection = Get-FinOpsDataProjection
    $playbooks = Get-FinOpsPlaybookField -Object $projection -Name 'Playbooks'
    $ruleAdapterMap = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
    foreach ($rule in @($projection.Rules)) {
        $ruleId = [string] (Get-FinOpsPlaybookField -Object $rule -Name 'id' -Default '')
        if ([string]::IsNullOrEmpty($ruleId)) { continue }
        $adapter = [string] (Get-FinOpsPlaybookField -Object $rule -Name 'adapter_class' -Default 'generic')
        $ruleAdapterMap[$ruleId] = $adapter
    }

    $rows = [System.Collections.Generic.List[object]]::new()
    $sourceIndex = 0
    foreach ($finding in @(Get-FinOpsPlaybookField -Object $Report -Name 'findings' -Default @())) {
        $ruleId = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'rule_id' -Default '')
        $templateRecord = Get-FinOpsPlaybookField -Object $playbooks -Name $ruleId -Default $null
        if ($null -eq $templateRecord) {
            throw "Playbook template not found for rule '$ruleId' in powershell/FinOpsAssess/data/playbooks.json."
        }

        $evidence = Get-FinOpsPlaybookField -Object $finding -Name 'evidence' -Default ([ordered]@{})
        $ctx = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
        if ($evidence -is [pscustomobject]) {
            foreach ($property in $evidence.PSObject.Properties) {
                $ctx[$property.Name] = $property.Value
            }
        } elseif ($evidence -is [System.Collections.IDictionary]) {
            foreach ($key in $evidence.Keys) {
                $ctx[[string] $key] = $evidence[$key]
            }
        }

        $severity = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'severity' -Default 'info')
        $ctx['rule_id'] = $ruleId
        $ctx['surface'] = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'surface' -Default '')
        $ctx['severity'] = $severity
        $ctx['principal'] = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'principal' -Default '')
        $ctx['current_sku'] = Get-FinOpsPlaybookField -Object $finding -Name 'current_sku'
        $ctx['recommended_sku'] = Get-FinOpsPlaybookField -Object $finding -Name 'recommended_sku'
        $ctx['estimated_monthly_savings_usd'] = Get-FinOpsPlaybookField -Object $finding -Name 'estimated_monthly_savings_usd'
        $ctx['recommendation'] = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'recommendation' -Default '')
        $ctx['evidence_ref'] = Get-FinOpsPlaybookField -Object $finding -Name 'evidence_ref'
        $ctx['confidence'] = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'confidence' -Default 'high')

        $rendered = ConvertTo-FinOpsPlaybookTemplate -Template ([string] $templateRecord.template) -Context $ctx
        $parsed = ConvertFrom-FinOpsPlaybookTemplateOutput -Rendered $rendered
        $adapterClass = if ($ruleAdapterMap.ContainsKey($ruleId)) { $ruleAdapterMap[$ruleId] } else { 'generic' }
        $row = [ordered]@{
            playbook_schema_version      = $script:FinOpsPlaybookSchemaVersion
            ticket_key                   = Get-FinOpsPlaybookTicketKey -Finding $finding
            finding_revision             = $script:FinOpsPlaybookFindingRevision
            rule_id                      = $ruleId
            surface                      = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'surface' -Default '')
            severity                     = $severity
            adapter_class                = $adapterClass
            principal                    = [string] (Get-FinOpsPlaybookField -Object $finding -Name 'principal' -Default '')
            current_sku                  = Get-FinOpsPlaybookField -Object $finding -Name 'current_sku'
            recommended_sku              = Get-FinOpsPlaybookField -Object $finding -Name 'recommended_sku'
            estimated_monthly_savings_usd = Get-FinOpsPlaybookField -Object $finding -Name 'estimated_monthly_savings_usd'
            evidence_ref                 = Get-FinOpsPlaybookField -Object $finding -Name 'evidence_ref'
            template_render_inputs       = @($templateRecord.render_inputs)
            title                        = $parsed.title
            description                  = $parsed.description
            remediation_steps            = @($parsed.remediation_steps)
            verification_checklist       = @($parsed.verification_checklist)
            references                   = @($parsed.references)
            adapter_hints                = Get-FinOpsPlaybookAdapterHintMap -Severity $severity
        }
        [void] $rows.Add([pscustomobject]@{ index = $sourceIndex; row = $row })
        $sourceIndex += 1
    }

    $rowArray = @($rows.ToArray())
    [Array]::Sort(
        $rowArray,
        [System.Comparison[object]]{
            param($left, $right)
            $a = Get-FinOpsPlaybookSortTuple -Row $left.row
            $b = Get-FinOpsPlaybookSortTuple -Row $right.row
            for ($i = 0; $i -lt 4; $i++) {
                $cmp = [System.StringComparer]::Ordinal.Compare($a[$i], $b[$i])
                if ($cmp -ne 0) { return $cmp }
            }
            return [int] $left.index - [int] $right.index
        }
    )

    $jsonlLines = foreach ($row in $rowArray) {
        ConvertTo-FinOpsPlaybookJson -InputObject $row.row -SortKeys $false -Compact $false -EnsureAscii $false
    }
    $jsonlText = ''
    if ($jsonlLines.Count -gt 0) {
        $jsonlText = ($jsonlLines -join "`n") + "`n"
    }

    $outputAbs = [System.IO.Path]::GetFullPath($OutputPath)
    Write-FinOpsPlaybookAtomicText -Path $outputAbs -Text $jsonlText

    $jsonlBytes = [System.IO.File]::ReadAllBytes($outputAbs)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($jsonlBytes)
    } finally {
        $sha.Dispose()
    }
    $jsonlSha256 = [System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
    $jsonlByteCount = $jsonlBytes.Length

    $surfaceSet = Build-FinOpsOrdinalSet
    foreach ($row in $rowArray) {
        [void] $surfaceSet.Add([string] (Get-FinOpsPlaybookField -Object $row.row -Name 'surface' -Default ''))
    }
    $surfaces = Get-FinOpsOrdinalSorted -InputObject @($surfaceSet | Where-Object { -not [string]::IsNullOrEmpty($_) })
    $piiRedaction = [bool] (Get-FinOpsPlaybookField -Object (Get-FinOpsPlaybookField -Object $Report -Name 'run' -Default ([ordered]@{})) -Name 'pii_redaction' -Default $true)
    $manifest = Get-FinOpsPlaybookManifest -Report $Report -RowCount $rowArray.Count -JsonlSha256 $jsonlSha256 -JsonlByteCount $jsonlByteCount -Surfaces $surfaces -PiiRedaction $piiRedaction
    $manifestText = ($manifest | ConvertTo-Json -Depth 64) + "`n"

    $manifestPath = "$outputAbs.manifest.json"
    Write-FinOpsPlaybookAtomicText -Path $manifestPath -Text $manifestText

    return [ordered]@{
        jsonl_path     = $outputAbs
        manifest_path  = $manifestPath
        row_count      = $rowArray.Count
        jsonl_sha256   = $jsonlSha256
        jsonl_byte_count = $jsonlByteCount
    }
}
