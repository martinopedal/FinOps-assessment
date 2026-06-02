function Get-FinOpsDataProjection {
    <#
    .SYNOPSIS
        Loads the shared catalogue/personas/rules data projection.

    .DESCRIPTION
        The native PowerShell engine reads the *same* catalogue, persona,
        and rule data as the Python tool. To avoid a second YAML parser
        (and the drift risk that carries), the shared YAML is projected to
        canonical JSON at build time by
        ``scripts/generate_ps_data_projection.py`` and shipped alongside
        the module under ``data/``. At runtime this loader only needs the
        built-in ``ConvertFrom-Json``.

        The projection carries fully resolved pydantic shapes (defaults
        already applied), so the PowerShell engine never re-implements
        validation or defaulting. List order is the Python loader iteration
        order, preserved exactly so order-sensitive behaviour stays in
        parity.

        Each list is materialised as an array even when it contains a
        single element, so callers never have to guard against
        ``ConvertFrom-Json`` unwrapping a one-item array into a scalar.

    .OUTPUTS
        [pscustomobject] with Catalog, Personas, and Rules properties, each
        an array of [pscustomobject] entries.

    .EXAMPLE
        $data = Get-FinOpsDataProjection
        $data.Rules.Count   # 28
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter()]
        [string] $DataRoot = (Join-Path $script:ModuleRoot 'data')
    )

    $files = [ordered]@{
        Catalog  = 'catalog.json'
        Personas = 'personas.json'
        Rules    = 'rules.json'
        Schema   = 'schema.json'
    }

    $result = [ordered]@{}
    foreach ($key in $files.Keys) {
        $path = Join-Path $DataRoot $files[$key]
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "FinOps data projection file is missing: $path. Run 'python scripts/generate_ps_data_projection.py' to regenerate it."
        }

        # Read as UTF-8 (the projection is UTF-8 no-BOM); ConvertFrom-Json
        # in PowerShell 7 handles UTF-8 content. Be explicit so non-ASCII
        # recommendation/display text round-trips on every OS.
        try {
            $raw = Get-Content -LiteralPath $path -Raw -Encoding utf8
        } catch {
            throw "Failed to read FinOps data projection '$path': $($_.Exception.Message)"
        }

        try {
            $parsed = $raw | ConvertFrom-Json
        } catch {
            throw "FinOps data projection '$path' is not valid JSON: $($_.Exception.Message)"
        }

        # Force an array even for a single-element projection so downstream
        # code can always rely on .Count and pipeline-array semantics. The
        # schema projection is a single object, not a list, so keep it as-is.
        if ($key -eq 'Schema') {
            $result[$key] = $parsed
        } else {
            $result[$key] = @($parsed)
        }
    }

    [pscustomobject] $result
}
