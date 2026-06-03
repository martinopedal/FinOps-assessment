function Invoke-FinOpsAssessment {
    <#
    .SYNOPSIS
        Runs the native FinOps assessment over a directory of normalised CSVs.

    .DESCRIPTION
        Native counterpart of the Python ``finops-assess run`` command. It
        normalises the input CSVs, assigns personas, runs the rule engine,
        and emits the report (JSON) or the flat findings CSV.

        All four rule surfaces are ported natively and run by default:
        ``M365.*`` (Phase 2), ``AZURE.*`` (Phase 3), and ``GITHUB.*`` /
        ``ADO.*`` (Phase 4), so ``summary.rules_skipped_no_impl`` is empty
        for the bundled catalogue. The read CSV contract, the normalised
        dataset, the persona engine, run metadata, deterministic PII
        redaction, and the JSON, CSV, and HTML (``-Format html``) reporters
        are at cross-engine conformance parity. Companion cmdlets cover the
        advisory triage (``Invoke-FinOpsTriage``) and FOCUS-aligned advisory
        export (``Export-FinOpsFocusAligned``). The playbook/ticket reporter
        is not yet ported; use the Python engine for that output.

    .PARAMETER InputDirectory
        Directory containing the normalised CSVs (and optional overrides.yaml).

    .PARAMETER OutputPath
        Optional path to write the report to. When omitted, the report
        object is returned on the pipeline (``json``) or the CSV text is
        emitted as a string (``csv``).

    .PARAMETER Format
        Output format: ``json`` (default), ``csv`` (flat findings table), or
        ``html`` (full report document).

    .PARAMETER NoPiiRedaction
        Disables PII redaction (redaction is on by default).

    .PARAMETER PiiSalt
        When supplied, principals are salted with this caller-pinned,
        tenant-stable salt and the report records ``salt_mode =
        tenant_stable``; otherwise a per-run random salt is used and
        ``salt_mode = per_run``.

    .OUTPUTS
        [System.Collections.Specialized.OrderedDictionary] report object
        (``json``) or [string] CSV (``csv``).

    .EXAMPLE
        Invoke-FinOpsAssessment -InputDirectory ./tenant -OutputPath ./report.json

    .EXAMPLE
        Invoke-FinOpsAssessment -InputDirectory ./tenant -Format csv -OutputPath ./findings.csv
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [string] $InputDirectory,

        [Parameter()]
        [string] $OutputPath,

        [Parameter()]
        [ValidateSet('json', 'csv', 'html')]
        [string] $Format = 'json',

        [Parameter()]
        [switch] $NoPiiRedaction,

        [Parameter()]
        [string] $PiiSalt
    )

    if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
        throw "Input directory not found: $InputDirectory"
    }

    $redactPii = -not $NoPiiRedaction.IsPresent

    $dataset = Get-FinOpsNormalizedDataset -InputDirectory $InputDirectory
    $assignments = Get-FinOpsPersonaAssignment -Dataset $dataset

    $engineArgs = @{
        Dataset            = $dataset
        PersonaAssignments = $assignments
        RedactPii          = $redactPii
    }
    if ($PSBoundParameters.ContainsKey('PiiSalt') -and $PiiSalt) {
        $engineArgs['Salt'] = $PiiSalt
    }
    $engine = Invoke-FinOpsRuleEngine @engineArgs

    $report = Build-FinOpsReport `
        -Dataset $dataset `
        -PersonaAssignments $assignments `
        -InputPath $InputDirectory `
        -RedactPii $redactPii `
        -SaltMode $engine.SaltMode `
        -Findings $engine.Findings `
        -RuleCounts $engine.RuleCounts `
        -RulesSkipped $engine.RulesSkipped

    if ($Format -ceq 'csv') {
        if ($OutputPath) {
            [void] (Write-FinOpsCsvReport -Finding $engine.Findings -OutputPath $OutputPath)
            return
        }
        return (ConvertTo-FinOpsCsvReport -Finding $engine.Findings)
    }

    if ($Format -ceq 'html') {
        $html = ConvertTo-FinOpsHtmlReport -Report $report
        if ($OutputPath) {
            $dir = Split-Path -Parent $OutputPath
            if ($dir -and -not (Test-Path -LiteralPath $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }
            [System.IO.File]::WriteAllText(
                $OutputPath,
                ($html -replace "`r`n", "`n"),
                (New-Object System.Text.UTF8Encoding($false))
            )
            return
        }
        return $html
    }

    if ($OutputPath) {
        [void] (Write-FinOpsJsonReport -Report $report -OutputPath $OutputPath)
    }

    $report
}
