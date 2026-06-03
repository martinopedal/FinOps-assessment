function Write-FinOpsCollectorCsv {
    <#
    .SYNOPSIS
        Writes collector output as atomic UTF-8 no-BOM LF CSV.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string] $Path,

        [Parameter(Mandatory)]
        [string[]] $Header,

        [Parameter()]
        [AllowEmptyCollection()]
        [pscustomobject[]] $Row = @()
    )

    function ConvertTo-FinOpsCollectorCsvField {
        param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Value)
        if ($Value.IndexOfAny([char[]]@(',', '"', "`n", "`r")) -ge 0) {
            return '"' + $Value.Replace('"', '""') + '"'
        }
        return $Value
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    [void]$lines.Add(($Header | ForEach-Object { ConvertTo-FinOpsCollectorCsvField -Value $_ }) -join ',')

    foreach ($entry in $Row) {
        $cells = foreach ($name in $Header) {
            $value = $null
            if ($entry -and $entry.PSObject.Properties.Name -contains $name) {
                $value = $entry.$name
            }
            $text = if ($null -eq $value) { '' } else { [string]$value }
            ConvertTo-FinOpsCollectorCsvField -Value $text
        }
        [void]$lines.Add(($cells -join ','))
    }

    $csv = ($lines -join "`n") + "`n"
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $tempPath = "$Path.tmp"
    try {
        [System.IO.File]::WriteAllText($tempPath, $csv, (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $tempPath -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
    return $Path
}
