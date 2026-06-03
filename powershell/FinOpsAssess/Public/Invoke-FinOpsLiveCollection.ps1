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
        'Arm' {
            $collectorArgs = @{
                OutputPath         = $OutputPath
                Auth               = $Auth
                SubscriptionId     = $SubscriptionId
                SkipMetrics        = $SkipMetrics
                PageLimit          = $PageLimit
                AcceptArmRbacRisk  = $AcceptArmRbacRisk
            }
            return Get-FinOpsArmCollector @collectorArgs
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

    $armConsentMessage = 'ARM live collection requires explicit two-key consent: pass -AcceptArmRbacRisk AND set FINOPS_ACCEPT_ARM_RBAC_RISK=1. ARM read-only is operator-attested because RBAC cannot be proven from token claims.'
    if ($Surface -ceq 'Arm') {
        $envConsent = [string]$env:FINOPS_ACCEPT_ARM_RBAC_RISK
        $hasEnvConsent = $envConsent -ceq '1'
        if (-not ($AcceptArmRbacRisk -and $hasEnvConsent)) {
            throw $armConsentMessage
        }
    }

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
            if ($Surface -ceq 'Arm') {
                $guardArgs['AllowUnknownScopes'] = $true
                $consentMessage = 'ARM read-only is OPERATOR-ATTESTED. RBAC introspection deferred. Consent: -AcceptArmRbacRisk + FINOPS_ACCEPT_ARM_RBAC_RISK=1'
                Write-Warning $consentMessage
                Write-Information $consentMessage -InformationAction Continue
            }
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

