function Get-FinOpsGeneratedAt {
    <#
    .SYNOPSIS
        Returns the report timestamp, honouring ``SOURCE_DATE_EPOCH``.

    .DESCRIPTION
        Native port of ``finops_assess.reporters._determinism.generated_at_iso``.
        When ``SOURCE_DATE_EPOCH`` is set to a valid integer, the timestamp is
        derived from that epoch (UTC), making report output byte-deterministic
        across runs -- this is what the cross-engine conformance compare relies
        on. Malformed or unset values fall through to the wall-clock UTC time,
        exactly like the Python helper (which silently ignores a bad epoch).

        The ``zzz`` format specifier renders the offset as ``+00:00`` (with the
        colon), matching Python's ``datetime.isoformat``. ``InvariantCulture``
        guards against locale-specific digit/separator rendering.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param()

    $format = 'yyyy-MM-ddTHH:mm:sszzz'
    $invariant = [System.Globalization.CultureInfo]::InvariantCulture
    $epoch = $env:SOURCE_DATE_EPOCH
    if ($epoch) {
        [long] $seconds = 0
        if ([long]::TryParse($epoch, [ref] $seconds)) {
            try {
                return [System.DateTimeOffset]::FromUnixTimeSeconds($seconds).ToUniversalTime().ToString($format, $invariant)
            } catch {
                # Out-of-range epoch -> fall through to wall-clock, like Python.
                Write-Verbose "Ignoring out-of-range SOURCE_DATE_EPOCH '$epoch': $($_.Exception.Message)"
            }
        }
    }
    return [System.DateTimeOffset]::UtcNow.ToString($format, $invariant)
}

function ConvertTo-FinOpsRedactedInput {
    <#
    .SYNOPSIS
        Reduces an input path to its leaf when PII redaction is on.

    .DESCRIPTION
        Native port of ``json_reporter._redact_input_path``. With redaction
        enabled the directory portion is dropped (operator workstation paths
        leak user / customer / engagement names), recording only
        ``<redacted>/<leaf>``. With redaction off the path is returned as-is.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $InputPath,
        [Parameter(Mandatory)] [bool] $RedactPii
    )

    if (-not $RedactPii) {
        return $InputPath
    }
    $leaf = [System.IO.Path]::GetFileName($InputPath.TrimEnd('/', '\'))
    return "<redacted>/$leaf"
}

function Get-FinOpsModuleVersion {
    <#
    .SYNOPSIS
        Returns this module's version from its manifest.

    .DESCRIPTION
        The report ``run.version`` is the producing engine's version. The
        manifest ``ModuleVersion`` is kept in lockstep with the Python
        package version; the conformance compare (which includes the whole
        ``run`` block) mechanically fails if the two ever drift.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [string] $ManifestPath = (Join-Path $script:ModuleRoot 'FinOpsAssess.psd1')
    )

    $manifest = Import-PowerShellDataFile -Path $ManifestPath
    return [string] $manifest.ModuleVersion
}

function Build-FinOpsReport {
    <#
    .SYNOPSIS
        Builds the canonical report object for a normalised dataset.

    .DESCRIPTION
        Native port of ``json_reporter.build_report`` plus the dataset-derived
        portions of ``engine.run_rules``'s summary. Until the rule engines are
        ported, this produces a structurally complete report with an empty
        ``findings`` array and ``rules_skipped_no_impl`` listing every rule id
        (so the report is self-documenting about the absent rule logic). The
        cross-engine conformance compare uses the ``report-structural-v1``
        canonical profile, which masks those rule-dependent fields.

    .PARAMETER Dataset
        Normalised dataset from ``Get-FinOpsNormalizedDataset``.

    .PARAMETER PersonaAssignments
        Persona assignment map from ``Get-FinOpsPersonaAssignment``.

    .PARAMETER InputPath
        The input directory the dataset came from (recorded, redacted, in
        ``run.input``).

    .PARAMETER RedactPii
        Whether PII redaction is on (default ``$true``).

    .PARAMETER SaltMode
        ``per_run`` (default) or ``tenant_stable``.

    .PARAMETER Findings
        Findings to embed (default empty until rule phases land).

    .PARAMETER Rules
        Rule definitions, used to populate ``rules_skipped_no_impl``.

    .PARAMETER RuleCounts
        Optional per-rule finding counts (``summary.rule_counts``). When the
        rule engine has run, the caller passes the counts it produced; when
        omitted the report records an empty map (Phase-1c structural mode).

    .PARAMETER RulesSkipped
        Optional explicit ``rules_skipped_no_impl`` list. When the rule
        engine has run it passes the rules it could not implement; when
        omitted every rule id is listed (Phase-1c structural mode, where the
        whole rule layer is absent).

    .OUTPUTS
        [System.Collections.Specialized.OrderedDictionary] mirroring the
        Python report envelope (run / summary / findings).
    #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [object] $Dataset,
        [Parameter(Mandatory)] [System.Collections.Specialized.OrderedDictionary] $PersonaAssignments,
        [Parameter(Mandatory)] [string] $InputPath,
        [bool] $RedactPii = $true,
        [ValidateSet('per_run', 'tenant_stable')]
        [string] $SaltMode = 'per_run',
        [object[]] $Findings = @(),
        [object[]] $Rules = (Get-FinOpsDataProjection).Rules,
        [System.Collections.Specialized.OrderedDictionary] $RuleCounts,
        [string[]] $RulesSkipped
    )

    $personaDistribution = [ordered]@{}
    foreach ($assignment in $PersonaAssignments.Values) {
        $id = $assignment.persona_id
        if ($personaDistribution.Contains($id)) {
            $personaDistribution[$id] = $personaDistribution[$id] + 1
        } else {
            $personaDistribution[$id] = 1
        }
    }

    if ($PSBoundParameters.ContainsKey('RulesSkipped')) {
        $skippedRules = @($RulesSkipped)
    } else {
        $skippedRules = @($Rules | ForEach-Object { $_.id } | Sort-Object)
    }
    $ruleCountsValue = if ($PSBoundParameters.ContainsKey('RuleCounts')) { $RuleCounts } else { [ordered]@{} }

    $summary = [ordered]@{
        rule_counts               = $ruleCountsValue
        rules_skipped_no_impl     = $skippedRules
        total_findings            = @($Findings).Count
        principals_evaluated      = @($Dataset.users).Count
        assignments_evaluated     = @($Dataset.assignments).Count
        azure_resources_evaluated = @($Dataset.azure_resources).Count
        salt_mode                 = $SaltMode
    }
    if (-not $RedactPii) {
        $summary['pii_redaction'] = 'disabled'
    }
    $summary['persona_distribution'] = $personaDistribution

    $run = [ordered]@{
        tool           = 'finops-assess'
        version        = Get-FinOpsModuleVersion
        schema_version = '1.0'
        generated_at   = Get-FinOpsGeneratedAt
        input          = ConvertTo-FinOpsRedactedInput -InputPath $InputPath -RedactPii $RedactPii
        pii_redaction  = $RedactPii
        salt_mode      = $SaltMode
        mode           = 'read-only'
    }

    [ordered]@{
        run      = $run
        summary  = $summary
        findings = @($Findings)
    }
}

function Write-FinOpsJsonReport {
    <#
    .SYNOPSIS
        Serialises a report object to canonical-friendly JSON.

    .DESCRIPTION
        Writes the report as UTF-8 JSON with LF newlines. Raw key order is
        cosmetic: the cross-engine conformance compare runs the output through
        the shared ``scripts/canonicalize_report.py`` profile, which sorts
        keys. When ``OutputPath`` is omitted the JSON string is returned.

    .PARAMETER Report
        The report object from ``Build-FinOpsReport``.

    .PARAMETER OutputPath
        Optional destination file.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $Report,
        [string] $OutputPath
    )

    $json = $Report | ConvertTo-Json -Depth 32

    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # Explicit UTF-8 (no BOM) + LF so bytes are identical on every OS.
        $normalised = $json -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($OutputPath, $normalised + "`n", (New-Object System.Text.UTF8Encoding($false)))
    }

    return $json
}
