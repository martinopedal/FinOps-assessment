Set-StrictMode -Version Latest

# Native port of finops_assess.reporters.csv_reporter. One row per finding,
# fixed column order, evidence serialised as compact JSON, with OWASP
# CSV-formula-injection mitigation. The CSV is a *final* artefact (it is
# not re-canonicalised), so the PowerShell writer must match Python's
# csv.QUOTE_MINIMAL bytes and json.dumps formatting exactly.

# Public, stable column order (csv_reporter.COLUMNS).
$script:FinOpsCsvColumns = @(
    'rule_id', 'surface', 'severity', 'confidence', 'principal',
    'current_sku', 'recommended_sku', 'estimated_monthly_savings_usd',
    'recommendation', 'evidence_ref', 'evidence_json'
)

# Leading characters a spreadsheet treats as a formula start (csv_reporter
# _FORMULA_PREFIXES): '=', '+', '-', '@', TAB, CR.
$script:FinOpsFormulaPrefixes = @([char]'=', [char]'+', [char]'-', [char]'@', [char]"`t", [char]"`r")

function Format-FinOpsPyFloat {
    <#
    .SYNOPSIS
        Render a double the way Python ``repr``/``json.dumps`` does:
        shortest round-trip, always with a decimal point (e.g. ``30.0``).
    #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)] [double] $Value)
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $text = $Value.ToString('R', $inv)
    if ($text -notmatch '[.eEnN]') { $text += '.0' }
    return $text
}

function ConvertTo-FinOpsCompactJson {
    <#
    .SYNOPSIS
        Serialise a value to compact JSON byte-compatible with Python
        ``json.dumps(..., sort_keys=True)`` (separators ', '/': ',
        ensure_ascii=True, lowercase true/false/null).

    .DESCRIPTION
        Used for the CSV ``evidence_json`` column, which must byte-match the
        Python reporter. Supports the value types that appear in finding
        evidence: null, bool, integer, double, string, array, and
        dictionary ([ordered]/hashtable/pscustomobject).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $InputObject)

    if ($null -eq $InputObject) { return 'null' }

    if ($InputObject -is [bool]) { return ([bool] $InputObject) ? 'true' : 'false' }
    if ($InputObject -is [int] -or $InputObject -is [long] -or $InputObject -is [int16] -or $InputObject -is [byte]) {
        return ([long] $InputObject).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    if ($InputObject -is [double] -or $InputObject -is [single] -or $InputObject -is [decimal]) {
        return Format-FinOpsPyFloat -Value ([double] $InputObject)
    }
    if ($InputObject -is [string]) {
        return ConvertTo-FinOpsJsonString -Value ([string] $InputObject)
    }

    # Dictionary-like: [ordered] (OrderedDictionary), hashtable, IDictionary.
    if ($InputObject -is [System.Collections.IDictionary]) {
        $keys = @($InputObject.Keys | ForEach-Object { [string] $_ })
        $sortedKeys = Get-FinOpsOrdinalSorted -InputObject $keys
        $parts = foreach ($k in $sortedKeys) {
            (ConvertTo-FinOpsJsonString -Value $k) + ': ' + (ConvertTo-FinOpsCompactJson -InputObject $InputObject[$k])
        }
        return '{' + ($parts -join ', ') + '}'
    }

    # Array / enumerable (but not string, handled above).
    if ($InputObject -is [System.Collections.IEnumerable]) {
        $parts = foreach ($item in $InputObject) { ConvertTo-FinOpsCompactJson -InputObject $item }
        return '[' + (@($parts) -join ', ') + ']'
    }

    # Fallback: treat as string (json.dumps default=str).
    return ConvertTo-FinOpsJsonString -Value ([string] $InputObject)
}

function ConvertTo-FinOpsJsonString {
    <#
    .SYNOPSIS
        Escape a string as a JSON string literal with ensure_ascii=True
        (non-ASCII -> \uXXXX), matching Python json.dumps.
    #>
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

function Get-FinOpsCsvCell {
    <#
    .SYNOPSIS
        Render a finding field as a CSV cell, neutralising formula-injection
        prefixes (csv_reporter._sanitize_cell).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return '' }
    if ($Value -is [bool]) { return ([bool] $Value) ? 'True' : 'False' }
    if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
        return Format-FinOpsPyFloat -Value ([double] $Value)
    }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [int16] -or $Value -is [byte]) {
        return ([long] $Value).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    $text = [string] $Value
    if ($text.Length -gt 0 -and $script:FinOpsFormulaPrefixes -contains $text[0]) {
        return "'" + $text
    }
    return $text
}

function ConvertTo-FinOpsCsvField {
    <#
    .SYNOPSIS
        Quote a field per csv.QUOTE_MINIMAL: quote only when it contains the
        delimiter, a quote, CR, or LF; double interior quotes.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Value)

    if ($Value.IndexOfAny([char[]]@(',', '"', "`r", "`n")) -ge 0) {
        return '"' + $Value.Replace('"', '""') + '"'
    }
    return $Value
}

function ConvertTo-FinOpsCsvReport {
    <#
    .SYNOPSIS
        Render findings as a flat CSV string (csv_reporter.write_csv_report).

    .DESCRIPTION
        One row per finding in the fixed column order, LF line terminator,
        QUOTE_MINIMAL quoting. ``evidence`` is serialised to the
        ``evidence_json`` column as compact JSON (sort_keys parity). The
        returned string ends with a trailing LF after the last row, matching
        Python's csv writer.

    .PARAMETER Finding
        Array of finding dictionaries (from the rule engine / report).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowEmptyCollection()] [object[]] $Finding = @())

    $lines = [System.Collections.Generic.List[string]]::new()
    $header = ($script:FinOpsCsvColumns | ForEach-Object { ConvertTo-FinOpsCsvField -Value $_ }) -join ','
    [void] $lines.Add($header)

    foreach ($f in $Finding) {
        $cells = foreach ($column in $script:FinOpsCsvColumns) {
            if ($column -ceq 'evidence_json') {
                $evidence = if ($f.Contains('evidence') -and $null -ne $f['evidence']) { $f['evidence'] } else { [ordered]@{} }
                $raw = ConvertTo-FinOpsCompactJson -InputObject $evidence
            } else {
                $value = if ($f.Contains($column)) { $f[$column] } else { $null }
                $raw = Get-FinOpsCsvCell -Value $value
            }
            ConvertTo-FinOpsCsvField -Value $raw
        }
        [void] $lines.Add(($cells -join ','))
    }

    return ($lines -join "`n") + "`n"
}

function Write-FinOpsCsvReport {
    <#
    .SYNOPSIS
        Writes the findings CSV to a file (UTF-8 no BOM, LF newlines).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $Finding,
        [Parameter(Mandatory)] [string] $OutputPath
    )

    $csv = ConvertTo-FinOpsCsvReport -Finding $Finding
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($OutputPath, $csv, (New-Object System.Text.UTF8Encoding($false)))
    return $OutputPath
}
