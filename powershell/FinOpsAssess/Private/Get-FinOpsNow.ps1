function Get-FinOpsNow {
    <#
    .SYNOPSIS
        Returns the current UTC instant with deterministic override support.
    #>
    [CmdletBinding()]
    [OutputType([System.DateTimeOffset])]
    param()

    if ($env:FINOPS_NOW_OVERRIDE) {
        return [System.DateTimeOffset]::ParseExact(
            $env:FINOPS_NOW_OVERRIDE,
            'yyyy-MM-dd',
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::AssumeUniversal
        )
    }

    return [System.DateTimeOffset]::UtcNow
}
