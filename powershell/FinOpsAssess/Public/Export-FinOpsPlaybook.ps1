function Export-FinOpsPlaybook {
    <#
    .SYNOPSIS
        Exports playbook ticket JSONL + manifest from an existing report JSON.
    .DESCRIPTION
        Reads an existing finops-assess report JSON and emits a playbook
        export: one newline-delimited JSON (JSONL) ticket per finding plus a
        sidecar manifest. This is the native PowerShell port of the Python
        playbook reporter and produces byte-identical output for the same
        report (cross-engine conformance is enforced in CI).

        Each JSONL row is a ready-to-triage ticket with a deterministic
        ``ticket_key``, the originating ``rule_id``/``surface``/``severity``,
        the rendered ``title``/``description``, ordered ``remediation_steps``
        and ``verification_checklist`` arrays, ``references``, and
        severity-derived ``adapter_hints``. Rows are emitted in a stable sort
        order (surface, severity, rule_id, then source order) so the file is
        diff-friendly and safe to commit.

        The manifest written to ``<OutputPath>.manifest.json`` records the
        row count, the SHA-256 and byte length of the JSONL payload, the set
        of surfaces present, and the PII-redaction posture inherited from the
        source report. This command is read-only with respect to the audited
        systems; it only reads the report JSON and writes the two output files.

    .PARAMETER InputReport
        Path to an existing finops-assess report JSON file.

    .PARAMETER OutputPath
        Destination path for the JSONL file. Manifest is written to
        "<OutputPath>.manifest.json".

    .OUTPUTS
        System.Collections.Specialized.OrderedDictionary. An ordered
        dictionary with the keys ``jsonl_path``, ``manifest_path``,
        ``row_count``, ``jsonl_sha256``, and ``jsonl_byte_count``.

    .EXAMPLE
        Export-FinOpsPlaybook -InputReport ./report.json -OutputPath ./playbook.jsonl

        Reads report.json and writes ./playbook.jsonl plus
        ./playbook.jsonl.manifest.json, returning the summary dictionary.

    .EXAMPLE
        $result = Export-FinOpsPlaybook -InputReport ./report.json -OutputPath ./out/playbook.jsonl
        "$($result.row_count) tickets, sha256=$($result.jsonl_sha256)"

        Captures the return value to report how many tickets were written and
        the content hash of the JSONL payload (useful for change detection in
        an automation pipeline).
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
