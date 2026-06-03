Set-StrictMode -Version Latest

$script:FinOpsHtmlSeverityOrder = @{
    high   = 0
    medium = 1
    low    = 2
    info   = 3
}

$script:FinOpsHtmlSurfaceLabels = @(
    [pscustomobject] @{ Surface = 'm365'; Label = 'Microsoft 365' }
    [pscustomobject] @{ Surface = 'azure'; Label = 'Azure' }
    [pscustomobject] @{ Surface = 'github'; Label = 'GitHub' }
    [pscustomobject] @{ Surface = 'ado'; Label = 'Azure DevOps' }
)

function Get-FinOpsHtmlMemberValue {
    [CmdletBinding()]
    [OutputType([object])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter()] [AllowNull()] [object] $Default = $null
    )

    if ($null -eq $InputObject) { return $Default }
    if ($InputObject -is [System.Collections.IDictionary]) {
        if ($InputObject.Contains($Name)) { return $InputObject[$Name] }
        return $Default
    }
    $prop = $InputObject.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $Default
}

function Add-FinOpsHtmlLine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [System.Text.StringBuilder] $Builder,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Text
    )

    [void] $Builder.Append($Text)
    [void] $Builder.Append("`n")
}

function ConvertTo-FinOpsMarkupSafeEscaped {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return '' }
    $text = [string] $Value
    $text = $text.Replace('&', '&amp;')
    $text = $text.Replace('<', '&lt;')
    $text = $text.Replace('>', '&gt;')
    $text = $text.Replace('"', '&#34;')
    $text = $text.Replace("'", '&#39;')
    return $text
}

function ConvertTo-FinOpsJinjaJsonString {
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

function ConvertTo-FinOpsJinjaTojsonValue {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter(Mandatory)] [int] $Indent,
        [Parameter(Mandatory)] [int] $Level
    )

    if ($null -eq $InputObject) { return 'null' }
    if ($InputObject -is [bool]) { return ([bool] $InputObject) ? 'true' : 'false' }
    if (
        $InputObject -is [int] -or $InputObject -is [long] -or $InputObject -is [short] -or
        $InputObject -is [sbyte] -or $InputObject -is [uint16] -or $InputObject -is [uint32] -or
        $InputObject -is [byte] -or $InputObject -is [decimal] -or
        $InputObject -is [float] -or $InputObject -is [double]
    ) {
        return Format-FinOpsCanonicalJsonNumber -Value $InputObject
    }
    if ($InputObject -is [string]) {
        return ConvertTo-FinOpsJinjaJsonString -Value ([string] $InputObject)
    }

    $entries = [System.Collections.Generic.List[object]]::new()
    if ($InputObject -is [System.Collections.IDictionary]) {
        $keys = Get-FinOpsOrdinalSorted -InputObject @($InputObject.Keys | ForEach-Object { [string] $_ })
        foreach ($key in $keys) {
            [void] $entries.Add([pscustomobject] @{ Key = [string] $key; Value = $InputObject[$key] })
        }
    } elseif ($InputObject -is [pscustomobject]) {
        $propertyMap = @{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $propertyMap[[string] $property.Name] = $property.Value
        }
        $keys = Get-FinOpsOrdinalSorted -InputObject @($propertyMap.Keys)
        foreach ($key in $keys) {
            [void] $entries.Add([pscustomobject] @{ Key = [string] $key; Value = $propertyMap[$key] })
        }
    }
    if ($entries.Count -gt 0) {
        if ($entries.Count -eq 0) { return '{}' }
        $childIndent = ' ' * (($Level + 1) * $Indent)
        $selfIndent = ' ' * ($Level * $Indent)
        $parts = [System.Collections.Generic.List[string]]::new()
        foreach ($entry in $entries) {
            $key = ConvertTo-FinOpsJinjaJsonString -Value ([string] $entry.Key)
            $value = ConvertTo-FinOpsJinjaTojsonValue -InputObject $entry.Value -Indent $Indent -Level ($Level + 1)
            [void] $parts.Add($childIndent + $key + ': ' + $value)
        }
        return "{`n" + ($parts -join ",`n") + "`n" + $selfIndent + '}'
    }

    if ($InputObject -is [System.Collections.IEnumerable]) {
        $items = @()
        foreach ($item in $InputObject) { $items += , $item }
        if ($items.Count -eq 0) { return '[]' }
        $childIndent = ' ' * (($Level + 1) * $Indent)
        $selfIndent = ' ' * ($Level * $Indent)
        $parts = foreach ($item in $items) {
            $childIndent + (ConvertTo-FinOpsJinjaTojsonValue -InputObject $item -Indent $Indent -Level ($Level + 1))
        }
        return "[`n" + (@($parts) -join ",`n") + "`n" + $selfIndent + ']'
    }

    return ConvertTo-FinOpsJinjaJsonString -Value ([string] $InputObject)
}

function ConvertTo-FinOpsJinjaTojson {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()] [AllowNull()] [object] $InputObject,
        [Parameter()] [int] $Indent = 2
    )

    $json = ConvertTo-FinOpsJinjaTojsonValue -InputObject $InputObject -Indent $Indent -Level 0
    $json = $json.Replace('<', '\u003c')
    $json = $json.Replace('>', '\u003e')
    $json = $json.Replace('&', '\u0026')
    $json = $json.Replace("'", '\u0027')
    return $json
}

function Get-FinOpsHtmlFindingsBySurface {
    [CmdletBinding()]
    [OutputType([hashtable])]
    param([Parameter()] [AllowEmptyCollection()] [object[]] $Findings = @())

    $grouped = @{}
    foreach ($finding in $Findings) {
        $surface = [string] (Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'surface' -Default '')
        if (-not $grouped.ContainsKey($surface)) {
            $grouped[$surface] = [System.Collections.Generic.List[object]]::new()
        }
        [void] $grouped[$surface].Add($finding)
    }
    foreach ($surface in @($grouped.Keys)) {
        $grouped[$surface] = @(
            $grouped[$surface] | Sort-Object -Stable -Property `
                @{ Expression = {
                        $key = [string] (Get-FinOpsHtmlMemberValue -InputObject $_ -Name 'severity' -Default '')
                        if ($script:FinOpsHtmlSeverityOrder.ContainsKey($key)) {
                            $script:FinOpsHtmlSeverityOrder[$key]
                        } else {
                            99
                        }
                    }
                },
                @{ Expression = { [string] (Get-FinOpsHtmlMemberValue -InputObject $_ -Name 'rule_id' -Default '') } }
        )
    }
    return $grouped
}

function Format-FinOpsHtmlMoney {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [double] $Value)

    return '$' + $Value.ToString('F2', [System.Globalization.CultureInfo]::InvariantCulture)
}

function ConvertTo-FinOpsHtmlReport {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Report)

    $findings = @(Get-FinOpsHtmlMemberValue -InputObject $Report -Name 'findings' -Default @())
    $summary = Get-FinOpsHtmlMemberValue -InputObject $Report -Name 'summary' -Default ([ordered]@{})
    $run = Get-FinOpsHtmlMemberValue -InputObject $Report -Name 'run' -Default ([ordered]@{})

    $ruleCounts = Get-FinOpsHtmlMemberValue -InputObject $summary -Name 'rule_counts' -Default ([ordered]@{})
    $rulesFiredCount = 0
    if ($ruleCounts -is [System.Collections.IDictionary]) {
        foreach ($value in $ruleCounts.Values) {
            if ($value) { $rulesFiredCount++ }
        }
    } elseif ($ruleCounts -is [pscustomobject]) {
        foreach ($property in $ruleCounts.PSObject.Properties) {
            if ($property.Value) { $rulesFiredCount++ }
        }
    }

    $totalEstimatedSavings = 0.0
    foreach ($finding in $findings) {
        $savingsRaw = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'estimated_monthly_savings_usd'
        if ($null -ne $savingsRaw) {
            $totalEstimatedSavings += [double] $savingsRaw
        }
    }

    $personaDistribution = Get-FinOpsHtmlMemberValue -InputObject $summary -Name 'persona_distribution' -Default ([ordered]@{})
    $personaEntries = [System.Collections.Generic.List[object]]::new()
    $principals = 0
    if ($personaDistribution -is [System.Collections.IDictionary]) {
        foreach ($key in $personaDistribution.Keys) {
            $count = [int] $personaDistribution[$key]
            $principals += $count
            [void] $personaEntries.Add([pscustomobject] @{ Key = [string] $key; Count = $count })
        }
    } elseif ($personaDistribution -is [pscustomobject]) {
        foreach ($property in $personaDistribution.PSObject.Properties) {
            $count = [int] $property.Value
            $principals += $count
            [void] $personaEntries.Add([pscustomobject] @{ Key = [string] $property.Name; Count = $count })
        }
    }
    $personaKeys = Get-FinOpsOrdinalSorted -InputObject @($personaEntries | ForEach-Object { $_.Key })
    $personaByKey = @{}
    foreach ($entry in $personaEntries) { $personaByKey[$entry.Key] = $entry.Count }

    $rulesSkipped = @(Get-FinOpsHtmlMemberValue -InputObject $summary -Name 'rules_skipped_no_impl' -Default @())
    $findingsBySurface = Get-FinOpsHtmlFindingsBySurface -Findings $findings
    $practiceReviewHtml = Get-FinOpsPracticeReviewHtml -Report $Report

    $summaryFindingsCount = Get-FinOpsHtmlMemberValue -InputObject $summary -Name 'findings_count'
    if ($null -eq $summaryFindingsCount) {
        $summaryFindingsCount = $findings.Count
    }

    $sb = [System.Text.StringBuilder]::new()

    Add-FinOpsHtmlLine -Builder $sb -Text '<!DOCTYPE html>'
    Add-FinOpsHtmlLine -Builder $sb -Text '<html lang="en">'
    Add-FinOpsHtmlLine -Builder $sb -Text '<head>'
    Add-FinOpsHtmlLine -Builder $sb -Text '<meta charset="utf-8">'
    Add-FinOpsHtmlLine -Builder $sb -Text '<meta name="viewport" content="width=device-width, initial-scale=1">'
    Add-FinOpsHtmlLine -Builder $sb -Text ('<meta name="generator" content="finops-assess ' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'version' -Default '')) + '">')
    Add-FinOpsHtmlLine -Builder $sb -Text '<meta name="referrer" content="no-referrer">'
    $emdash = [string] [char] 0x2014
    Add-FinOpsHtmlLine -Builder $sb -Text ('<title>FinOps assessment report ' + $emdash + ' ' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'generated_at' -Default '')) + '</title>')
    Add-FinOpsHtmlLine -Builder $sb -Text '<style>'
    Add-FinOpsHtmlLine -Builder $sb -Text ('  /* Vendored, print-friendly CSS ' + $emdash + ' no remote assets, CSP-safe. */')
    Add-FinOpsHtmlLine -Builder $sb -Text '  :root {'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --fg: #1f2328;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --muted: #57606a;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --border: #d0d7de;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --bg: #ffffff;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --bg-alt: #f6f8fa;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --sev-info: #0969da;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --sev-low: #1a7f37;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --sev-medium: #bf8700;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    --sev-high: #cf222e;'
    Add-FinOpsHtmlLine -Builder $sb -Text '  }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  * { box-sizing: border-box; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  body {'
    Add-FinOpsHtmlLine -Builder $sb -Text '    font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    color: var(--fg);'
    Add-FinOpsHtmlLine -Builder $sb -Text '    background: var(--bg);'
    Add-FinOpsHtmlLine -Builder $sb -Text '    margin: 0;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    padding: 2rem;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    max-width: 1100px;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    margin-left: auto;'
    Add-FinOpsHtmlLine -Builder $sb -Text '    margin-right: auto;'
    Add-FinOpsHtmlLine -Builder $sb -Text '  }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  h1 { font-size: 1.6rem; margin: 0 0 0.25rem 0; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  h2 { font-size: 1.2rem; margin: 2rem 0 0.5rem 0; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  h3 { font-size: 1rem; margin: 1rem 0 0.5rem 0; color: var(--muted); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .meta code { background: var(--bg-alt); padding: 0 0.3rem; border-radius: 3px; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .cards { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .card { flex: 1 1 180px; border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem 1rem; background: var(--bg-alt); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .card .label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .card .value { font-size: 1.4rem; font-weight: 600; margin-top: 0.25rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  table { width: 100%; border-collapse: collapse; margin: 0.5rem 0 1.5rem 0; font-size: 0.9rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); vertical-align: top; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  th { background: var(--bg-alt); font-weight: 600; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  tr:hover { background: var(--bg-alt); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .sev { display: inline-block; padding: 0.05rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; color: white; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .sev-info    { background: var(--sev-info); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .sev-low     { background: var(--sev-low); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .sev-medium  { background: var(--sev-medium); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .sev-high    { background: var(--sev-high); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  details { margin: 0.25rem 0; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  summary { cursor: pointer; color: var(--muted); }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  pre { background: var(--bg-alt); border: 1px solid var(--border); border-radius: 4px; padding: 0.6rem; overflow-x: auto; font-size: 0.8rem; margin: 0.4rem 0 0 0; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .pill-list { display: flex; flex-wrap: wrap; gap: 0.4rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .pill { background: var(--bg-alt); border: 1px solid var(--border); border-radius: 12px; padding: 0.1rem 0.6rem; font-size: 0.8rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  .empty { color: var(--muted); font-style: italic; padding: 0.5rem 0; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.8rem; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  @media print {'
    Add-FinOpsHtmlLine -Builder $sb -Text '    body { padding: 0.5in; max-width: none; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '    details { page-break-inside: avoid; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '    .card { page-break-inside: avoid; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '    tr   { page-break-inside: avoid; }'
    Add-FinOpsHtmlLine -Builder $sb -Text '  }'
    Add-FinOpsHtmlLine -Builder $sb -Text '</style>'
    Add-FinOpsHtmlLine -Builder $sb -Text '</head>'
    Add-FinOpsHtmlLine -Builder $sb -Text '<body>'
    Add-FinOpsHtmlLine -Builder $sb -Text '  <header>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    <h1>FinOps assessment report</h1>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    <p class="meta">'
    Add-FinOpsHtmlLine -Builder $sb -Text ('      Generated <code>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'generated_at' -Default '')) + '</code> by')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      <code>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'tool' -Default '')) + ' ' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'version' -Default '')) + '</code>')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      &middot; mode <code>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'mode' -Default '')) + '</code>')
    $piiState = if ([bool] (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'pii_redaction' -Default $false)) { 'on' } else { 'off' }
    Add-FinOpsHtmlLine -Builder $sb -Text ('      &middot; PII redaction <code>' + $piiState + '</code>')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      &middot; input <code>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value (Get-FinOpsHtmlMemberValue -InputObject $run -Name 'input' -Default '')) + '</code>')
    Add-FinOpsHtmlLine -Builder $sb -Text '    </p>'
    Add-FinOpsHtmlLine -Builder $sb -Text '  </header>'
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    Add-FinOpsHtmlLine -Builder $sb -Text '  <section>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    <h2>Summary</h2>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    <div class="cards">'
    Add-FinOpsHtmlLine -Builder $sb -Text ('      <div class="card"><div class="label">Findings</div><div class="value">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $summaryFindingsCount) + '</div></div>')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      <div class="card"><div class="label">Rules fired</div><div class="value">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $rulesFiredCount) + '</div></div>')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      <div class="card"><div class="label">Estimated monthly savings</div><div class="value">' + (Format-FinOpsHtmlMoney -Value $totalEstimatedSavings) + '</div></div>')
    Add-FinOpsHtmlLine -Builder $sb -Text ('      <div class="card"><div class="label">Principals</div><div class="value">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $principals) + '</div></div>')
    Add-FinOpsHtmlLine -Builder $sb -Text '    </div>'
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    Add-FinOpsHtmlLine -Builder $sb -Text '    <h3>Persona distribution</h3>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    '
    if ($personaKeys.Count -gt 0) {
        Add-FinOpsHtmlLine -Builder $sb -Text '      <div class="pill-list">'
        foreach ($personaId in $personaKeys) {
            Add-FinOpsHtmlLine -Builder $sb -Text '        '
            $count = $personaByKey[$personaId]
            Add-FinOpsHtmlLine -Builder $sb -Text ('          <span class="pill"><span class="mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $personaId) + '</span> &middot; ' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $count) + '</span>')
        }
        Add-FinOpsHtmlLine -Builder $sb -Text '        '
        Add-FinOpsHtmlLine -Builder $sb -Text '      </div>'
    } else {
        Add-FinOpsHtmlLine -Builder $sb -Text '      <p class="empty">No persona assignments.</p>'
    }
    Add-FinOpsHtmlLine -Builder $sb -Text '    '
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    if ($rulesSkipped.Count -gt 0) {
        Add-FinOpsHtmlLine -Builder $sb -Text '      <h3>Rules in catalogue without an implementation</h3>'
        Add-FinOpsHtmlLine -Builder $sb -Text '      <div class="pill-list">'
        foreach ($ruleId in $rulesSkipped) {
            Add-FinOpsHtmlLine -Builder $sb -Text '        '
            Add-FinOpsHtmlLine -Builder $sb -Text ('          <span class="pill mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $ruleId) + '</span>')
        }
        Add-FinOpsHtmlLine -Builder $sb -Text '        '
        Add-FinOpsHtmlLine -Builder $sb -Text '      </div>'
    }
    Add-FinOpsHtmlLine -Builder $sb -Text '    '
    Add-FinOpsHtmlLine -Builder $sb -Text '  </section>'
    Add-FinOpsHtmlLine -Builder $sb -Text ''

    foreach ($surfaceLabel in $script:FinOpsHtmlSurfaceLabels) {
        $surface = $surfaceLabel.Surface
        $label = $surfaceLabel.Label
        $surfaceFindings = if ($findingsBySurface.ContainsKey($surface)) { @($findingsBySurface[$surface]) } else { @() }
        Add-FinOpsHtmlLine -Builder $sb -Text '  '
        Add-FinOpsHtmlLine -Builder $sb -Text '    <section>'
        Add-FinOpsHtmlLine -Builder $sb -Text ('      <h2>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $label) + '</h2>')
        Add-FinOpsHtmlLine -Builder $sb -Text '      '
        Add-FinOpsHtmlLine -Builder $sb -Text '      '
        if ($surfaceFindings.Count -gt 0) {
            Add-FinOpsHtmlLine -Builder $sb -Text '        <table>'
            Add-FinOpsHtmlLine -Builder $sb -Text '          <thead>'
            Add-FinOpsHtmlLine -Builder $sb -Text '            <tr>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Severity</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Rule</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Principal</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Current SKU</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Recommended SKU</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Est. savings / mo</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '              <th>Recommendation</th>'
            Add-FinOpsHtmlLine -Builder $sb -Text '            </tr>'
            Add-FinOpsHtmlLine -Builder $sb -Text '          </thead>'
            Add-FinOpsHtmlLine -Builder $sb -Text '          <tbody>'
            foreach ($finding in $surfaceFindings) {
                Add-FinOpsHtmlLine -Builder $sb -Text '            '
                $severity = [string] (Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'severity' -Default '')
                $ruleId = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'rule_id' -Default ''
                $principal = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'principal' -Default ''
                $currentSku = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'current_sku'
                $recommendedSku = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'recommended_sku'
                if ([string]::IsNullOrEmpty([string] $currentSku)) { $currentSku = [string] [char] 0x2014 }
                if ([string]::IsNullOrEmpty([string] $recommendedSku)) { $recommendedSku = [string] [char] 0x2014 }
                $savings = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'estimated_monthly_savings_usd'
                $recommendation = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'recommendation' -Default ''
                $evidence = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'evidence'
                $confidence = Get-FinOpsHtmlMemberValue -InputObject $finding -Name 'confidence' -Default ''
                $savingsText = if ($null -eq $savings) { [string] [char] 0x2014 } else { Format-FinOpsHtmlMoney -Value ([double] $savings) }

                Add-FinOpsHtmlLine -Builder $sb -Text '              <tr>'
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td><span class="sev sev-' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $severity) + '">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $severity) + '</span></td>')
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td class="mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $ruleId) + '</td>')
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td class="mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $principal) + '</td>')
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td class="mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $currentSku) + '</td>')
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td class="mono">' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $recommendedSku) + '</td>')
                Add-FinOpsHtmlLine -Builder $sb -Text ('                <td>' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $savingsText) + '</td>')
                Add-FinOpsHtmlLine -Builder $sb -Text '                <td>'
                Add-FinOpsHtmlLine -Builder $sb -Text ('                  ' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $recommendation))
                Add-FinOpsHtmlLine -Builder $sb -Text '                  '
                if ($null -ne $evidence) {
                    $evidenceJson = ConvertTo-FinOpsJinjaTojson -InputObject $evidence -Indent 2
                    Add-FinOpsHtmlLine -Builder $sb -Text '                    <details>'
                    Add-FinOpsHtmlLine -Builder $sb -Text ('                      <summary>Evidence (' + (ConvertTo-FinOpsMarkupSafeEscaped -Value $confidence) + ' confidence)</summary>')
                    Add-FinOpsHtmlLine -Builder $sb -Text ('                      <pre>' + $evidenceJson + '</pre>')
                    Add-FinOpsHtmlLine -Builder $sb -Text '                    </details>'
                }
                Add-FinOpsHtmlLine -Builder $sb -Text '                  '
                Add-FinOpsHtmlLine -Builder $sb -Text '                </td>'
                Add-FinOpsHtmlLine -Builder $sb -Text '              </tr>'
            }
            Add-FinOpsHtmlLine -Builder $sb -Text '            '
            Add-FinOpsHtmlLine -Builder $sb -Text '          </tbody>'
            Add-FinOpsHtmlLine -Builder $sb -Text '        </table>'
        } else {
            Add-FinOpsHtmlLine -Builder $sb -Text '        <p class="empty">No findings.</p>'
        }
        Add-FinOpsHtmlLine -Builder $sb -Text '      '
        Add-FinOpsHtmlLine -Builder $sb -Text '    </section>'
    }
    Add-FinOpsHtmlLine -Builder $sb -Text '  '
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    [void] $sb.Append('  ')
    [void] $sb.Append($practiceReviewHtml)
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    Add-FinOpsHtmlLine -Builder $sb -Text ''
    Add-FinOpsHtmlLine -Builder $sb -Text '  <footer>'
    Add-FinOpsHtmlLine -Builder $sb -Text '    <p>'
    Add-FinOpsHtmlLine -Builder $sb -Text '      <strong>finops-assess</strong> is a read-only auditing tool. This report'
    Add-FinOpsHtmlLine -Builder $sb -Text ('      contains advisory recommendations only ' + $emdash + ' no changes were made to any')
    Add-FinOpsHtmlLine -Builder $sb -Text '      system. See the'
    Add-FinOpsHtmlLine -Builder $sb -Text '      <a href="https://github.com/martinopedal/FinOps-assessment">project'
    Add-FinOpsHtmlLine -Builder $sb -Text '      repository</a> for the rule definitions and source code.'
    Add-FinOpsHtmlLine -Builder $sb -Text '    </p>'
    Add-FinOpsHtmlLine -Builder $sb -Text '  </footer>'
    Add-FinOpsHtmlLine -Builder $sb -Text '</body>'
    Add-FinOpsHtmlLine -Builder $sb -Text '</html>'

    return $sb.ToString()
}
