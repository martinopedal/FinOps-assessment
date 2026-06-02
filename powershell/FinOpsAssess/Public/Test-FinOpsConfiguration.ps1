function Test-FinOpsConfiguration {
    <#
    .SYNOPSIS
        Self-tests the module's structural integrity and version lock.

    .DESCRIPTION
        The Phase-0 counterpart of the Python ``finops-assess validate``
        subcommand. In Phase 0 this validates only what the scaffold can
        honestly guarantee:

          * the module manifest is importable,
          * the Public/ and Private/ layout is intact,
          * the module version is locked to the Python package version.

        Full catalogue + personas + rules schema validation is
        DEFERRED to Phase 1 (when the shared data projection lands). This
        cmdlet does not yet assert schema parity and says so.

        Emits an error and throws when any check fails, so it is safe to
        use as a CI gate. Use -PassThru to obtain the structured result
        object without throwing.

    .OUTPUTS
        [pscustomobject] with Success ([bool]) and Checks (per-check
        Check/Status/Detail records). Status is one of pass/fail/skipped.

    .EXAMPLE
        Test-FinOpsConfiguration

    .EXAMPLE
        $r = Test-FinOpsConfiguration -PassThru; $r.Checks
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [switch] $PassThru
    )

    $checks = [System.Collections.Generic.List[object]]::new()
    $record = {
        param([string] $Name, [string] $Status, [string] $Detail)
        $checks.Add([pscustomobject]@{ Check = $Name; Status = $Status; Detail = $Detail })
    }

    # 1. Manifest importable.
    $manifestPath = Join-Path $script:ModuleRoot 'FinOpsAssess.psd1'
    $manifest = $null
    try {
        $manifest = Import-PowerShellDataFile -Path $manifestPath
        & $record 'manifest-importable' 'pass' "Imported $manifestPath"
    } catch {
        & $record 'manifest-importable' 'fail' $_.Exception.Message
    }

    # 2. Module structure.
    foreach ($dir in @('Public', 'Private')) {
        $path = Join-Path $script:ModuleRoot $dir
        if (Test-Path -LiteralPath $path) {
            & $record "structure-$dir" 'pass' "$path exists"
        } else {
            & $record "structure-$dir" 'fail' "Missing directory $path"
        }
    }

    # 3. Version lock vs the Python package.
    if ($null -ne $manifest) {
        try {
            $packageVersion = Get-FinOpsPackageVersion
            if ($packageVersion -eq $manifest.ModuleVersion) {
                & $record 'version-lock' 'pass' "Module $($manifest.ModuleVersion) == package $packageVersion"
            } else {
                & $record 'version-lock' 'fail' "Module $($manifest.ModuleVersion) != package $packageVersion"
            }
        } catch {
            & $record 'version-lock' 'skipped' "Python package source not available: $($_.Exception.Message)"
        }
    }

    $failed = @($checks | Where-Object { $_.Status -eq 'fail' })
    $result = [pscustomobject]@{
        Success = ($failed.Count -eq 0)
        Checks  = $checks.ToArray()
    }

    if ($PassThru) {
        return $result
    }

    foreach ($check in $checks) {
        Write-Verbose ("[{0}] {1}: {2}" -f $check.Status.ToUpperInvariant(), $check.Check, $check.Detail)
    }

    if (-not $result.Success) {
        $detail = ($failed | ForEach-Object { "$($_.Check): $($_.Detail)" }) -join '; '
        throw "Test-FinOpsConfiguration failed ($($failed.Count) check(s)): $detail"
    }

    return $result
}
