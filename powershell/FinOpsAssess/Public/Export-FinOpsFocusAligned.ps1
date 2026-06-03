function Export-FinOpsFocusAligned {
    <#
    .SYNOPSIS
        Exports a FOCUS-aligned advisory CSV + manifest from a report JSON.

    .DESCRIPTION
        Native port of Python ``write_focus_aligned_export``. Reads an existing
        finops-assess report JSON and writes ``<output>.csv`` plus
        ``<output>.csv.manifest.json``.

    .PARAMETER InputReport
        Path to an existing finops-assess report JSON file.

    .PARAMETER OutputPath
        Destination path for the advisory CSV output file.

    .PARAMETER Surface
        Optional surface filter. Defaults to all four surfaces: m365, azure,
        github, and ado.

    .OUTPUTS
        System.Collections.Specialized.OrderedDictionary. An ordered
        dictionary with the keys ``csv_path`` and ``manifest_path``.

    .EXAMPLE
        Export-FinOpsFocusAligned -InputReport ./report.json -OutputPath ./focus.csv

        Writes a FOCUS-aligned advisory CSV for all four surfaces plus
        ./focus.csv.manifest.json.

    .EXAMPLE
        Export-FinOpsFocusAligned -InputReport ./report.json -OutputPath ./azure-focus.csv -Surface azure

        Writes a FOCUS-aligned advisory export filtered to the Azure surface
        only.
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [string] $InputReport,

        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter()]
        [ValidateSet('m365', 'azure', 'github', 'ado')]
        [string[]] $Surface = @('m365', 'azure', 'github', 'ado')
    )

    if (-not (Test-Path -LiteralPath $InputReport -PathType Leaf)) {
        throw "Input report not found: $InputReport"
    }

    $inputReportPath = (Resolve-Path -LiteralPath $InputReport).Path
    $rawReport = Get-Content -LiteralPath $inputReportPath -Raw -Encoding utf8
    $report = ConvertFrom-FinOpsReportJson -Json $rawReport

    return Write-FinOpsFocusAlignedExport -Report $report -OutputPath $OutputPath -Surface $Surface
}