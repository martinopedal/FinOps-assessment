function Test-FinOpsCatalogCoverage {
    <#
    .SYNOPSIS
        Compares the Microsoft upstream M365 SKU catalogue against the local data projection.

    .DESCRIPTION
        PowerShell parity for `finops-assess catalog coverage`. Fetches the
        Microsoft-published M365 service-plan CSV (Product names and service plan identifiers
        for licensing) and compares the upstream String_Id set against the curated M365 entries
        in the local data projection.

        Auto-generated stub entries (cloud == 'm365', family == 'm365_uncategorized', written
        by `finops-assess catalog refresh --write`) are excluded from the local count, exactly
        matching the Python behaviour. This ensures the drift gate only fires for SKUs the
        project has deliberately modelled.

        By default, a terminating error is raised when upstream contains SKUs absent from the
        local catalogue -- equivalent to Python's --fail-on-gap. The result object is always
        emitted to the success stream before the error is raised. Use -NoFailOnGap to suppress
        the error.

        -Source accepts HTTP(S) URLs, file:// URIs, and native filesystem paths. HTTP(S) calls
        are read-only GET with no authentication, no cookies, and no secrets; a descriptive
        User-Agent is sent. Local path support is required for offline use and CI tests.

    .PARAMETER Source
        URL or local path to the Microsoft upstream SKU CSV.
        Defaults to the stable Microsoft download URL referenced from
        https://learn.microsoft.com/en-us/entra/identity/users/licensing-service-plan-reference.
        Accepts http://, https://, file://, and native filesystem paths (including Windows
        drive-letter paths such as C:\data\skus.csv).

    .PARAMETER NoFailOnGap
        Suppresses the terminating error when upstream SKUs are absent from the local
        catalogue. Equivalent to Python's --no-fail-on-gap. The result object is always
        emitted to the pipeline regardless of this switch.

    .PARAMETER PassThru
        Returns the result as a structured [pscustomobject] instead of JSON text.
        Recommended for automation and testing. Use with -NoFailOnGap to receive the object
        without triggering the gap error.

    .OUTPUTS
        [pscustomobject] with properties:
          source          (string)  - the -Source value used
          upstream_count  (int)     - unique String_Id entries in the upstream CSV
          catalog_count   (int)     - curated local M365 entries (excl. autogen stubs)
          coverage_pct    (float)   - rounded percentage of upstream covered locally
          missing         (array)   - upstream SKUs not in the local catalogue; each item
                                      has id (string) and display_name (string)
          extra_local_ids (array)   - local M365 IDs absent from the upstream CSV

    .EXAMPLE
        Test-FinOpsCatalogCoverage -NoFailOnGap

        Fetches the live upstream CSV and emits a JSON coverage report without failing on gaps.

    .EXAMPLE
        Test-FinOpsCatalogCoverage -Source 'file:///C:/data/skus.csv' -NoFailOnGap

        Reads a local copy of the upstream CSV and emits a JSON coverage report.

    .EXAMPLE
        $r = Test-FinOpsCatalogCoverage -NoFailOnGap -PassThru
        $r.missing | Format-Table id, display_name

        Returns the coverage result as a structured object and shows missing SKUs.

    .EXAMPLE
        Test-FinOpsCatalogCoverage -NoFailOnGap | ConvertTo-Json -Depth 5

        Equivalent to the default output; explicitly pipes to ConvertTo-Json.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter()]
        [string] $Source = (
            'https://download.microsoft.com/download/e/3/e/e3e9faf2-f28b-490a-9ada-c6089a1fc5b0/' +
            'Product%20names%20and%20service%20plan%20identifiers%20for%20licensing.csv'
        ),

        [switch] $NoFailOnGap,

        # When present, emits the result as a [pscustomobject] to the pipeline.
        # When absent, the result is serialised to JSON text via ConvertTo-Json -Depth 5.
        [switch] $PassThru
    )

    # --- 1. Fetch the upstream CSV text ---
    $parsedUri = $null
    $uriValid = [System.Uri]::TryCreate($Source, [System.UriKind]::Absolute, [ref]$parsedUri)

    $csvText = $null

    if ($uriValid -and $parsedUri.Scheme -in @('http', 'https')) {
        # Read-only GET; no auth, no cookies, no secrets.
        $headers = @{ 'User-Agent' = 'finops-assess/catalog-coverage (read-only)' }
        $wr = Invoke-WebRequest -Uri $Source -Method GET -UseBasicParsing -Headers $headers
        # RawContentStream gives raw bytes regardless of Content-Type charset so BOM handling
        # is always correct.
        $bytes = $wr.RawContentStream.ToArray()
        $csvText = [System.Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)
    } elseif ($uriValid -and $parsedUri.Scheme -eq 'file') {
        # file:// URI: LocalPath handles percent-decoding and platform path differences.
        $localPath = $parsedUri.LocalPath
        $csvText = Get-Content -LiteralPath $localPath -Raw -Encoding utf8
    } else {
        # Native filesystem path (also covers Windows drive-letter paths such as C:\... that
        # Uri parses with a single-letter scheme).
        $csvText = Get-Content -LiteralPath $Source -Raw -Encoding utf8
    }

    # Belt-and-suspenders BOM strip for any path that returns the mark.
    if ($csvText.Length -gt 0 -and $csvText[0] -eq [char]0xFEFF) {
        $csvText = $csvText.Substring(1)
    }

    # --- 2. Parse CSV, validate columns, deduplicate by String_Id ---
    $csvRows = @($csvText | ConvertFrom-Csv)
    if ($csvRows.Count -eq 0) {
        throw 'Upstream CSV produced no rows; the file may be empty or not a valid CSV.'
    }

    $columnNames = @($csvRows[0].PSObject.Properties.Name)
    foreach ($required in @('Product_Display_Name', 'String_Id', 'GUID')) {
        if ($required -notin $columnNames) {
            throw "Upstream CSV is missing required column: '$required'."
        }
    }

    # Insertion-ordered map String_Id -> display_name; first occurrence wins (matching Python).
    $upstreamById = [ordered]@{}
    foreach ($row in $csvRows) {
        $sid = if ($null -ne $row.String_Id) { $row.String_Id.Trim() } else { '' }
        if ($sid -and -not $upstreamById.Contains($sid)) {
            $raw = if ($null -ne $row.Product_Display_Name) { $row.Product_Display_Name.Trim() } else { '' }
            $upstreamById[$sid] = if ($raw) { $raw } else { $sid }
        }
    }

    # --- 3. Load local M365 catalogue from data projection (autogen stubs excluded) ---
    $projection = Get-FinOpsDataProjection
    $localM365Ids = @(
        $projection.Catalog |
            Where-Object { $_.cloud -eq 'm365' -and $_.family -ne 'm365_uncategorized' } |
            ForEach-Object { $_.id }
    )

    # --- 4. Compute coverage (case-sensitive, matching Python set semantics) ---
    $upstreamIdSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($k in $upstreamById.Keys) { [void]$upstreamIdSet.Add($k) }

    $localIdSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($id in $localM365Ids) { [void]$localIdSet.Add($id) }

    $upstreamCount = $upstreamIdSet.Count
    $catalogCount  = $localIdSet.Count

    $missingIds = @($upstreamIdSet | Where-Object { -not $localIdSet.Contains($_) } | Sort-Object)
    $extraIds   = @($localIdSet | Where-Object { -not $upstreamIdSet.Contains($_) } | Sort-Object)

    $coveragePct = if ($upstreamCount -eq 0) {
        100.0
    } else {
        [math]::Round(100.0 * ($upstreamCount - $missingIds.Count) / $upstreamCount, 2)
    }

    $missingObjs = @($missingIds | ForEach-Object {
        [pscustomobject]@{
            id           = $_
            display_name = $upstreamById[$_]
        }
    })

    $result = [pscustomobject]@{
        source          = $Source
        upstream_count  = $upstreamCount
        catalog_count   = $catalogCount
        coverage_pct    = $coveragePct
        missing         = $missingObjs
        extra_local_ids = $extraIds
    }

    # --- 5. Emit result to pipeline (always before any error, matching Python behaviour) ---
    if ($PassThru) {
        $result
    } else {
        $result | ConvertTo-Json -Depth 5
    }

    # Terminating error raised AFTER emitting the result so callers see the evidence.
    if (-not $NoFailOnGap -and $missingObjs.Count -gt 0) {
        $msg = 'Catalog coverage gap: {0} upstream SKU(s) not modelled locally. Use -NoFailOnGap to suppress.' -f $missingObjs.Count
        Write-Error -Message $msg -ErrorAction Stop
    }
}
