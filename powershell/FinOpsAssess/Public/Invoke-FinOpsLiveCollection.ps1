function Invoke-FinOpsLiveCollectionWorker {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet('Graph', 'Arm', 'GitHub', 'Ado')]
        [string] $Surface,

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter()]
        [string] $TenantId,

        [Parameter()]
        [string[]] $SubscriptionId,

        [Parameter()]
        [string] $GitHubEnterprise,

        [Parameter()]
        [string[]] $GitHubOrg,

        [Parameter()]
        [string] $AdoOrg,

        [switch] $SkipMetrics,
        [switch] $AcceptArmRbacRisk,
        [int] $PageLimit
    )

    switch ($Surface) {
        'Graph' {
            $collectorArgs = @{
                OutputPath = $OutputPath
                Auth       = $Auth
                TenantId   = $TenantId
                PageLimit  = $PageLimit
            }
            return Get-FinOpsGraphCollector @collectorArgs
        }
        default {
            $null = $Auth, $OutputPath, $TenantId, $SubscriptionId, $GitHubEnterprise, $GitHubOrg, $AdoOrg, $SkipMetrics, $AcceptArmRbacRisk, $PageLimit
            throw [System.NotImplementedException]::new("$Surface collector lands in Phase 6x")
        }
    }
}

function Invoke-FinOpsLiveCollection {
    <#
    .SYNOPSIS
        Collects live data for one surface (Phase 6a scaffold).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [ValidateSet('Graph', 'Arm', 'GitHub', 'Ado')]
        [string] $Surface,

        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter()]
        [string] $TenantId,

        [Parameter()]
        [string[]] $SubscriptionId,

        [Parameter()]
        [string] $GitHubEnterprise,

        [Parameter()]
        [string[]] $GitHubOrg,

        [Parameter()]
        [string] $AdoOrg,

        [Parameter()]
        [System.Security.SecureString] $Token,

        [Parameter()]
        [System.Security.SecureString] $Pat,

        [switch] $SkipMetrics,
        [switch] $AcceptArmRbacRisk,
        [switch] $AllowUnknownScopes,

        [Parameter()]
        [int] $PageLimit = 500
    )

    $tokenArgs = @{}
    if ($PSBoundParameters.ContainsKey('TenantId')) { $tokenArgs['TenantId'] = $TenantId }
    if ($PSBoundParameters.ContainsKey('Token')) { $tokenArgs['Token'] = $Token }
    if ($PSBoundParameters.ContainsKey('Pat')) { $tokenArgs['Pat'] = $Pat }

    if (-not $tokenArgs.ContainsKey('Token') -and -not $tokenArgs.ContainsKey('Pat')) {
        if ($Surface -ceq 'Graph') { $tokenArgs['Scope'] = 'graph' }
        elseif ($Surface -ceq 'Arm') { $tokenArgs['Scope'] = 'arm' }
        else {
            throw "Surface $Surface requires -Token or -Pat in Phase 6a."
        }
    }

    $auth = Get-FinOpsAccessToken @tokenArgs

    $guardArgs = @{}
    if ($AllowUnknownScopes) { $guardArgs['AllowUnknownScopes'] = $true }

    if ([string]$auth.Source -ceq 'caller-pat') {
        $guardSurface = if ($Surface -ceq 'Ado') { 'AzureDevOps' } else { 'GitHub' }
        $guardArgs['Scope'] = @()
        $guardArgs['Surface'] = $guardSurface
        Assert-FinOpsReadOnlyScope @guardArgs
    } else {
        $plainToken = $null
        try {
            $plainToken = [System.Net.NetworkCredential]::new('', $auth.AccessToken).Password
            $guardArgs['AccessToken'] = $plainToken
            Assert-FinOpsReadOnlyScope @guardArgs
        } finally {
            $plainToken = $null
        }
    }

    $workerResult = Invoke-FinOpsLiveCollectionWorker `
        -Surface $Surface `
        -Auth $auth `
        -OutputPath $OutputPath `
        -TenantId $TenantId `
        -SubscriptionId $SubscriptionId `
        -GitHubEnterprise $GitHubEnterprise `
        -GitHubOrg $GitHubOrg `
        -AdoOrg $AdoOrg `
        -SkipMetrics:$SkipMetrics `
        -AcceptArmRbacRisk:$AcceptArmRbacRisk `
        -PageLimit $PageLimit

    return [pscustomobject]@{
        Surface     = $Surface
        OutputPath  = $OutputPath
        FilesWritten = @($workerResult.FilesWritten)
        RowCounts   = if ($workerResult.RowCounts) { $workerResult.RowCounts } else { [ordered]@{} }
    }
}
