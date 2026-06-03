function Export-FinOpsPlaybook {
    <#
    .SYNOPSIS
        Exports playbook ticket JSONL + manifest from an existing report JSON.

    .PARAMETER InputReport
        Path to an existing finops-assess report JSON file.

    .PARAMETER OutputPath
        Destination path for the JSONL file. Manifest is written to
        "<OutputPath>.manifest.json".
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [string] $InputReport,

        [Parameter(Mandatory)]
        [string] $OutputPath
    )

    if (-not (Test-Path -LiteralPath $InputReport -PathType Leaf)) {
        throw "Input report not found: $InputReport"
    }

    $inputPath = (Resolve-Path -LiteralPath $InputReport).Path
    $rawReport = Get-Content -LiteralPath $inputPath -Raw -Encoding utf8
    $report = ConvertFrom-FinOpsReportJson -Json $rawReport

    return Write-FinOpsPlaybookExport -Report $report -OutputPath $OutputPath
}
