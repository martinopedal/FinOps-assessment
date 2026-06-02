function Invoke-FinOpsAssessment {
    <#
    .SYNOPSIS
        Runs the native FinOps assessment over a directory of normalised CSVs.

    .DESCRIPTION
        Native counterpart of the Python ``finops-assess run`` command. It
        normalises the input CSVs, assigns personas, and emits the canonical
        JSON report.

        PREVIEW / PARTIAL PARITY: the savings-rule engines are not ported yet
        (they arrive in later phases), so ``findings`` is always empty and the
        report's ``summary.rules_skipped_no_impl`` lists every rule id. What is
        already at parity: the read CSV contract, the normalised dataset, the
        persona engine (``summary.persona_distribution``), the run metadata,
        PII-redaction of the input path, and the deterministic timestamp. Do
        not treat this as a drop-in replacement for the Python assessment until
        the rule phases land.

    .PARAMETER InputDirectory
        Directory containing the normalised CSVs (and optional overrides.yaml).

    .PARAMETER OutputPath
        Optional path to write the JSON report to. When omitted, the report
        object is returned on the pipeline.

    .PARAMETER Format
        Output format. Only ``json`` is supported in this preview.

    .PARAMETER NoPiiRedaction
        Disables PII redaction (redaction is on by default).

    .PARAMETER PiiSalt
        When supplied, the report records ``salt_mode = tenant_stable`` (a
        caller-pinned, tenant-stable salt); otherwise ``per_run``. Finding-level
        salting is deferred until the rule phases produce findings to salt.

    .OUTPUTS
        [System.Collections.Specialized.OrderedDictionary] report object.

    .EXAMPLE
        Invoke-FinOpsAssessment -InputDirectory ./tenant -OutputPath ./report.json
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)]
        [string] $InputDirectory,

        [Parameter()]
        [string] $OutputPath,

        [Parameter()]
        [ValidateSet('json')]
        [string] $Format = 'json',

        [Parameter()]
        [switch] $NoPiiRedaction,

        [Parameter()]
        [string] $PiiSalt
    )

    if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
        throw "Input directory not found: $InputDirectory"
    }

    Write-Warning ('FinOpsAssess is in report-contract preview: no savings rules are ' +
        "implemented natively yet, so 'findings' is empty. Persona distribution, run " +
        'metadata, and the normalised dataset are produced natively. Use the Python ' +
        'engine for findings until the rule phases land.')

    $redactPii = -not $NoPiiRedaction.IsPresent
    $saltMode = if ($PSBoundParameters.ContainsKey('PiiSalt') -and $PiiSalt) { 'tenant_stable' } else { 'per_run' }

    $dataset = Get-FinOpsNormalizedDataset -InputDirectory $InputDirectory
    $assignments = Get-FinOpsPersonaAssignment -Dataset $dataset

    $report = Build-FinOpsReport `
        -Dataset $dataset `
        -PersonaAssignments $assignments `
        -InputPath $InputDirectory `
        -RedactPii $redactPii `
        -SaltMode $saltMode

    if ($OutputPath) {
        [void] (Write-FinOpsJsonReport -Report $report -OutputPath $OutputPath)
    }

    $report
}
