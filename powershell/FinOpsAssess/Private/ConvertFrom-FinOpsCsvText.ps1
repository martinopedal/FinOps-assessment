function ConvertFrom-FinOpsCsvText {
    <#
    .SYNOPSIS
        Parse CSV text into raw string-array rows (RFC 4180).

    .DESCRIPTION
        A self-contained, cross-platform CSV field parser used instead of
        ``Import-Csv``/``ConvertFrom-Csv`` so the strict-column contract
        (rows with cells beyond the header are an error) and exact field
        counts can be enforced the same way the Python ``csv.DictReader``
        path does. Handles quoted fields, embedded commas/newlines, and
        doubled-quote escaping. A UTF-8 BOM on the first field is stripped.

        Returns an array of rows; each row is a ``[string[]]`` of cells.
        The header row is included as the first element. Returns an empty
        array for empty input.
    #>
    [CmdletBinding()]
    [OutputType([object[]])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string] $Text
    )

    $rows = [System.Collections.Generic.List[object]]::new()
    $field = [System.Text.StringBuilder]::new()
    $record = [System.Collections.Generic.List[string]]::new()
    $inQuotes = $false
    $started = $false
    $i = 0
    $len = $Text.Length

    # Strip a leading UTF-8 BOM if Get-Content surfaced it as a character.
    if ($len -gt 0 -and $Text[0] -eq [char]0xFEFF) {
        $i = 1
    }

    $endField = {
        $record.Add($field.ToString())
        [void]$field.Clear()
    }

    while ($i -lt $len) {
        $ch = $Text[$i]
        if ($inQuotes) {
            if ($ch -eq '"') {
                if (($i + 1) -lt $len -and $Text[$i + 1] -eq '"') {
                    [void]$field.Append('"')
                    $i += 2
                    continue
                }
                $inQuotes = $false
                $i++
                continue
            }
            [void]$field.Append($ch)
            $i++
            continue
        }

        switch ($ch) {
            '"' { $inQuotes = $true; $started = $true; $i++ }
            ',' { & $endField; $started = $true; $i++ }
            "`r" {
                if (($i + 1) -lt $len -and $Text[$i + 1] -eq "`n") { $i++ }
                $record.Add($field.ToString()); [void]$field.Clear()
                $rows.Add($record.ToArray()); $record.Clear(); $started = $false
                $i++
            }
            "`n" {
                $record.Add($field.ToString()); [void]$field.Clear()
                $rows.Add($record.ToArray()); $record.Clear(); $started = $false
                $i++
            }
            default { [void]$field.Append($ch); $started = $true; $i++ }
        }
    }

    # Flush a trailing record that did not end with a newline.
    if ($started -or $field.Length -gt 0 -or $record.Count -gt 0) {
        $record.Add($field.ToString())
        $rows.Add($record.ToArray())
    }

    , $rows.ToArray()
}
