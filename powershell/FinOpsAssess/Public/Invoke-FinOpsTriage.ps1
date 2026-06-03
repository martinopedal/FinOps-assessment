function Invoke-FinOpsTriage {
    <#
    .SYNOPSIS
        Builds advisory triage JSON/CSV artefacts from an existing report JSON.

    .DESCRIPTION
        Native port of the Python ``finops-assess triage`` subcommand.
        Reads an existing finops-assess report file and emits deterministic,
        read-only advisory triage artefacts.

    .PARAMETER InputReport
        Path to an existing finops-assess report JSON file.

    .PARAMETER OutputDirectory
        Output directory for triage artefacts. Defaults to ``./triage-output``.

    .PARAMETER Format
        Artefact format to write: ``json``, ``csv``, or ``both``.
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [string] $InputReport,

        [Parameter()]
        [string] $OutputDirectory = '.\triage-output',

        [Parameter()]
        [ValidateSet('json', 'csv', 'both')]
        [string] $Format = 'both'
    )

    if (-not (Test-Path -LiteralPath $InputReport -PathType Leaf)) {
        throw "Input report not found: $InputReport"
    }

    if (-not (Test-Path -LiteralPath $OutputDirectory)) {
        New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    }

    $inputReportPath = (Resolve-Path -LiteralPath $InputReport).Path
    $outputDirectoryPath = (Resolve-Path -LiteralPath $OutputDirectory).Path

    $rawReport = Get-Content -LiteralPath $inputReportPath -Raw -Encoding utf8
    $source = ConvertFrom-FinOpsReportJson -Json $rawReport
    $triage = Build-FinOpsTriage -Report $source -SourcePath $inputReportPath -CopilotHelper 'disabled'

    if ($Format -in @('json', 'both')) {
        [void] (Write-FinOpsTriageJson -Triage $triage -OutputPath (Join-Path $outputDirectoryPath 'triage.json'))
    }
    if ($Format -in @('csv', 'both')) {
        [void] (Write-FinOpsTriageCsv -Triage $triage -OutputPath (Join-Path $outputDirectoryPath 'triage.csv'))
    }

    return $triage
}
