function Get-FinOpsPackageVersion {
    <#
    .SYNOPSIS
        Returns the Python package version that this module is pinned to.

    .DESCRIPTION
        Parses ``__version__`` from the repo's
        ``src/finops_assess/__init__.py``. Used to assert that the
        PowerShell module version never drifts from the Python package
        version. Throws if the source file is unavailable (e.g. when the
        module is installed standalone without the repo tree).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [string] $InitPath = (Join-Path $script:RepoRoot 'src' 'finops_assess' '__init__.py')
    )

    if (-not (Test-Path -LiteralPath $InitPath)) {
        throw "Cannot locate the Python package source at '$InitPath'."
    }

    $content = Get-Content -LiteralPath $InitPath -Raw
    $match = [regex]::Match($content, '(?m)^__version__\s*=\s*["'']([^"'']+)["'']')
    if (-not $match.Success) {
        throw "Could not parse __version__ from '$InitPath'."
    }

    return $match.Groups[1].Value
}
