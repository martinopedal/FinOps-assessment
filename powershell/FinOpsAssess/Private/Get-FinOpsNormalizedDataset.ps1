function Get-FinOpsNormalizedDataset {
    <#
    .SYNOPSIS
        Build a normalised dataset from a directory of CSV files.

    .DESCRIPTION
        The PowerShell counterpart of the Python
        ``finops_assess.collectors.csv_collector.collect_from_directory``.
        Reads the per-surface CSV files in ``InputDirectory`` and coerces
        + validates every cell against the schema projection
        (``schema.json``) so the result matches the Python
        ``NormalizedDataset`` shape exactly.

        Coercion / validation rules (mirrored from the Python collector):

          * Missing CSV file -> empty list.
          * Header is the authoritative column set. An unknown column is an
            error. A row with non-empty cells beyond the header is an error
            (the strict-column contract). Rows with fewer cells than the
            header treat the missing cells as empty.
          * An empty cell is omitted so the schema default applies.
          * ``bool`` cells parse from a fixed true/false token set.
          * ``list`` cells split on ``|`` (pipe), trimmed, empties dropped.
          * ``int``/``float`` cells are parsed with invariant culture.
          * ``literal`` cells must be a member of the enum.
          * Numeric ``ge``/``le`` and string ``min_length``/``max_length``
            bounds are enforced; required fields must be present.

        ``overrides.yaml`` is read as a strict flat ``key: value`` mapping
        (a documented subset of YAML, NOT full PyYAML parity -- see
        docs/powershell.md). ``m365_family_summaries`` has no CSV and is
        always emitted as an empty list, matching the Python collector.

    .OUTPUTS
        [pscustomobject] mirroring NormalizedDataset: one array property
        per dataset field plus an ``overrides`` ordered hashtable.

    .EXAMPLE
        $ds = Get-FinOpsNormalizedDataset -InputDirectory ./demo
        $ds.users.Count
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $InputDirectory,

        [Parameter()]
        [pscustomobject] $Schema = (Get-FinOpsDataProjection).Schema
    )

    if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
        throw "input directory not found: $InputDirectory"
    }

    $boolTrue = [System.Collections.Generic.HashSet[string]]::new(
        [string[]]$Schema.bool_true, [System.StringComparer]::Ordinal)
    $boolFalse = [System.Collections.Generic.HashSet[string]]::new(
        [string[]]$Schema.bool_false, [System.StringComparer]::Ordinal)
    $listSep = [string]$Schema.list_separator

    $result = [ordered]@{}
    foreach ($dataset in $Schema.dataset_fields) {
        $fieldName = $dataset.field
        if ($null -eq $dataset.csv) {
            # Non-CSV-backed dataset field (m365_family_summaries): emit [].
            $result[$fieldName] = @()
            continue
        }
        $modelSpec = $Schema.models.($dataset.model)
        $path = Join-Path $InputDirectory $dataset.csv
        $result[$fieldName] = @(
            ConvertTo-FinOpsRecord -Path $path -ModelName $dataset.model `
                -FieldSpecs $modelSpec -BoolTrue $boolTrue -BoolFalse $boolFalse `
                -ListSeparator $listSep
        )
    }

    $result['overrides'] = Read-FinOpsOverride -Path (Join-Path $InputDirectory 'overrides.yaml')

    [pscustomobject] $result
}


function ConvertTo-FinOpsRecord {
    <#
    .SYNOPSIS
        Read + coerce + validate one CSV file into record objects.
    #>
    [CmdletBinding()]
    [OutputType([object[]])]
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $ModelName,
        [Parameter(Mandatory)] [object[]] $FieldSpecs,
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $BoolTrue,
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $BoolFalse,
        [Parameter(Mandatory)] [string] $ListSeparator
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    $specByName = @{}
    foreach ($spec in $FieldSpecs) { $specByName[$spec.name] = $spec }

    $text = Get-Content -LiteralPath $Path -Raw -Encoding utf8
    if ($null -eq $text) { return }
    $rows = ConvertFrom-FinOpsCsvText -Text $text
    if ($rows.Count -eq 0) { return }

    $header = @($rows[0] | ForEach-Object { $_.Trim() })
    foreach ($col in $header) {
        if (-not $specByName.ContainsKey($col)) {
            throw "${Path}: ${ModelName}: unknown CSV column '$col'"
        }
    }

    $records = [System.Collections.Generic.List[object]]::new()
    for ($r = 1; $r -lt $rows.Count; $r++) {
        $cells = $rows[$r]
        $lineNo = $r + 1

        # A wholly empty trailing line (single empty cell) is skipped, the
        # same way csv.DictReader ignores a blank final line.
        if ($cells.Count -eq 1 -and [string]::IsNullOrEmpty($cells[0])) {
            continue
        }

        # Strict-column contract: any non-empty cell beyond the header.
        if ($cells.Count -gt $header.Count) {
            $extra = @()
            for ($c = $header.Count; $c -lt $cells.Count; $c++) {
                $v = ($cells[$c]).Trim()
                if ($v -ne '') { $extra += $v }
            }
            if ($extra.Count -gt 0) {
                throw "${Path}:${lineNo}: ${ModelName}: row has $($extra.Count) cell(s) beyond the declared header columns: $($extra -join ', ')"
            }
        }

        $obj = [ordered]@{}
        foreach ($spec in $FieldSpecs) {
            $idx = $header.IndexOf($spec.name)
            $raw = ''
            if ($idx -ge 0 -and $idx -lt $cells.Count) { $raw = [string]$cells[$idx] }
            $value = $raw.Trim()

            if ($value -eq '') {
                if ($spec.required) {
                    throw "${Path}:${lineNo}: ${ModelName}.$($spec.name): required value is missing"
                }
                # Omit -> schema default applies (null for nullable fields,
                # [] for list, declared default otherwise).
                $obj[$spec.name] = Get-FinOpsFieldDefault -Spec $spec
                continue
            }

            $obj[$spec.name] = ConvertTo-FinOpsFieldValue -Spec $spec -Value $value `
                -ModelName $ModelName -Path $Path -LineNo $lineNo `
                -BoolTrue $BoolTrue -BoolFalse $BoolFalse -ListSeparator $ListSeparator
        }
        $records.Add([pscustomobject] $obj)
    }

    $records.ToArray()
}


function Get-FinOpsFieldDefault {
    <#
    .SYNOPSIS
        The value to use for an absent (empty/missing) optional cell.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [pscustomobject] $Spec)

    if ($Spec.kind -eq 'list') {
        if ($Spec.nullable) { return $null }
        return , @()
    }
    # bool with a non-null default (e.g. account_enabled = True) keeps it;
    # everything else defaults to null when the cell is blank.
    $hasDefault = $Spec.PSObject.Properties.Name -contains 'default'
    if ($hasDefault -and $null -ne $Spec.default) {
        return $Spec.default
    }
    return $null
}


function ConvertTo-FinOpsFieldValue {
    <#
    .SYNOPSIS
        Coerce + validate one non-empty cell value per its field spec.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Spec,
        [Parameter(Mandatory)] [string] $Value,
        [Parameter(Mandatory)] [string] $ModelName,
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [int] $LineNo,
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $BoolTrue,
        [Parameter(Mandatory)] [System.Collections.Generic.HashSet[string]] $BoolFalse,
        [Parameter(Mandatory)] [string] $ListSeparator
    )

    $where = "${Path}:${LineNo}: ${ModelName}.$($Spec.name)"
    $inv = [System.Globalization.CultureInfo]::InvariantCulture

    switch ($Spec.kind) {
        'bool' {
            $lowered = $Value.ToLowerInvariant()
            if ($BoolTrue.Contains($lowered)) { return $true }
            if ($BoolFalse.Contains($lowered)) { return $false }
            throw "${where}: cannot parse bool '$Value'"
        }
        'list' {
            $items = @()
            foreach ($part in $Value.Split($ListSeparator)) {
                $t = $part.Trim()
                if ($t -ne '') { $items += $t }
            }
            return , $items
        }
        'int' {
            [int] $parsed = 0
            if (-not [int]::TryParse($Value, [System.Globalization.NumberStyles]::Integer, $inv, [ref] $parsed)) {
                throw "${where}: cannot parse int '$Value'"
            }
            Test-FinOpsNumericBound -Spec $Spec -Number $parsed -Where $where
            return $parsed
        }
        'float' {
            [double] $parsed = 0
            $styles = [System.Globalization.NumberStyles]::Float
            if (-not [double]::TryParse($Value, $styles, $inv, [ref] $parsed)) {
                throw "${where}: cannot parse number '$Value'"
            }
            Test-FinOpsNumericBound -Spec $Spec -Number $parsed -Where $where
            return $parsed
        }
        'literal' {
            # pydantic Literal matching is case-sensitive, so use -cnotcontains
            # (the default -notcontains is case-insensitive and would accept
            # mis-cased values the Python engine rejects).
            if ($Spec.enum -cnotcontains $Value) {
                throw "${where}: '$Value' is not one of: $($Spec.enum -join ', ')"
            }
            return $Value
        }
        default {
            # string
            $minProp = $Spec.PSObject.Properties.Name -contains 'min_length'
            if ($minProp -and $Value.Length -lt [int]$Spec.min_length) {
                throw "${where}: value shorter than min_length $($Spec.min_length)"
            }
            $maxProp = $Spec.PSObject.Properties.Name -contains 'max_length'
            if ($maxProp -and $Value.Length -gt [int]$Spec.max_length) {
                throw "${where}: value longer than max_length $($Spec.max_length)"
            }
            return $Value
        }
    }
}


function Test-FinOpsNumericBound {
    <#
    .SYNOPSIS
        Enforce ge/le bounds from the schema spec, throwing on violation.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Spec,
        [Parameter(Mandatory)] [double] $Number,
        [Parameter(Mandatory)] [string] $Where
    )

    if (($Spec.PSObject.Properties.Name -contains 'ge') -and $Number -lt [double]$Spec.ge) {
        throw "${Where}: value $Number is less than minimum $($Spec.ge)"
    }
    if (($Spec.PSObject.Properties.Name -contains 'le') -and $Number -gt [double]$Spec.le) {
        throw "${Where}: value $Number is greater than maximum $($Spec.le)"
    }
}


function Read-FinOpsOverride {
    <#
    .SYNOPSIS
        Read overrides.yaml as a strict flat key:value mapping.

    .DESCRIPTION
        Supports only the documented subset: blank lines, ``#`` comments,
        and ``key: value`` pairs (optionally quoted). Nested structures,
        anchors, tags, and flow collections are rejected. This is NOT full
        PyYAML parity -- see docs/powershell.md. Returns an ordered
        hashtable (empty when the file is absent).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)] [string] $Path)

    $map = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $map
    }

    $lineNo = 0
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding utf8)) {
        $lineNo++
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $colon = $trimmed.IndexOf(':')
        if ($colon -lt 1) {
            throw "${Path}:${lineNo}: expected 'key: value', got '$trimmed'"
        }
        $key = $trimmed.Substring(0, $colon).Trim()
        $val = $trimmed.Substring($colon + 1).Trim()
        # Strip a trailing inline comment only when unquoted.
        if ($val.StartsWith('"') -and $val.EndsWith('"') -and $val.Length -ge 2) {
            $val = $val.Substring(1, $val.Length - 2)
        } elseif ($val.StartsWith("'") -and $val.EndsWith("'") -and $val.Length -ge 2) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($val -eq '' -or $key.StartsWith('-') -or $val.StartsWith('{') -or $val.StartsWith('[') -or $val.StartsWith('&') -or $val.StartsWith('*')) {
            throw "${Path}:${lineNo}: only flat 'key: value' string mappings are supported (got '$trimmed')"
        }
        $map[$key] = $val
    }
    $map
}
