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
        'GitHub' {
            $collectorArgs = @{
                OutputPath = $OutputPath
                Auth       = $Auth
                Enterprise = $GitHubEnterprise
                Org        = $GitHubOrg
                PageLimit  = $PageLimit
            }
            return Get-FinOpsGitHubCollector @collectorArgs
        }
        'Ado' {
            $collectorArgs = @{
                OutputPath = $OutputPath
                Auth       = $Auth
                Org        = $AdoOrg
                PageLimit  = $PageLimit
            }
            return Get-FinOpsAdoCollector @collectorArgs
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
        Collects live, read-only data for one Microsoft-ecosystem surface and
        writes normalized CSVs to disk.

    .DESCRIPTION
        Runs the read-only live collector for exactly one of four surfaces:
        Microsoft 365 (Graph), Azure (ARM), GitHub, or Azure DevOps (Ado).
        The cmdlet acquires an access token for the selected surface, then
        enforces the read-only posture by calling Assert-FinOpsReadOnlyScope
        BEFORE any data is read - if the credential carries a write or admin
        scope the run is refused.

        Azure (ARM) collection is gated behind an explicit two-key consent
        because ARM read-only cannot be proven from token claims (RBAC is not
        introspectable): the caller must pass -AcceptArmRbacRisk AND set the
        environment variable FINOPS_ACCEPT_ARM_RBAC_RISK=1, otherwise the run
        is refused. GitHub accepts bearer tokens only (-Token or GITHUB_TOKEN;
        a -Pat is rejected). Azure DevOps accepts -Pat/-Token or the
        AZURE_DEVOPS_PAT/AZURE_DEVOPS_TOKEN environment variables and requires
        -AdoOrg. The collected rows are written as CSV files under -OutputPath;
        nothing in the audited systems is mutated.

    .PARAMETER Surface
        The surface to collect: Graph, Arm, GitHub, or Ado.

    .PARAMETER OutputPath
        Directory where the collector writes its normalized CSV files.

    .PARAMETER TenantId
        Optional Entra tenant ID for Graph/ARM token acquisition.

    .PARAMETER SubscriptionId
        One or more Azure subscription IDs to scope ARM collection.

    .PARAMETER GitHubEnterprise
        Optional GitHub Enterprise slug to scope GitHub collection.

    .PARAMETER GitHubOrg
        One or more GitHub organization logins to scope GitHub collection.

    .PARAMETER AdoOrg
        Azure DevOps organization name (required for the Ado surface).

    .PARAMETER Token
        Bearer access token (SecureString) for Graph/ARM/GitHub.

    .PARAMETER Pat
        Personal access token (SecureString) for Azure DevOps.

    .PARAMETER SkipMetrics
        Skip optional metric collection (ARM).

    .PARAMETER AcceptArmRbacRisk
        Operator attestation half of the ARM two-key read-only consent.

    .PARAMETER AllowUnknownScopes
        Permit tokens whose scopes cannot be classified (advisory).

    .PARAMETER PageLimit
        Maximum number of pages to fetch per collection (default 500).

    .OUTPUTS
        System.Management.Automation.PSCustomObject with properties
        ``Surface``, ``OutputPath``, ``FilesWritten`` (string[] of CSV files
        written), and ``RowCounts`` (ordered map of file -> row count).

    .EXAMPLE
        Invoke-FinOpsLiveCollection -Surface Graph -OutputPath ./out -TenantId $tid

        Collects Microsoft 365 licensing/identity data via Microsoft Graph
        after the read-only scope guard passes.

    .EXAMPLE
        $env:FINOPS_ACCEPT_ARM_RBAC_RISK = '1'
        Invoke-FinOpsLiveCollection -Surface Arm -OutputPath ./out `
            -SubscriptionId $sub -AcceptArmRbacRisk

        Collects Azure (ARM) data. Both consent keys are supplied, so the
        ARM read-only attestation gate is satisfied.

    .EXAMPLE
        Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath ./out -GitHubOrg contoso

        Collects GitHub seat/usage data using GITHUB_TOKEN (bearer). The token
        is probed for scopes and rejected if it carries write access.

    .EXAMPLE
        Invoke-FinOpsLiveCollection -Surface Ado -OutputPath ./out -AdoOrg contoso

        Collects Azure DevOps data for the 'contoso' organization using
        AZURE_DEVOPS_PAT / AZURE_DEVOPS_TOKEN.
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

    function ConvertTo-FinOpsSecureString {
        param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) {
            $secure.AppendChar($char)
        }
        $secure.MakeReadOnly()
        return $secure
    }

    function Get-FinOpsHeaderValue {
        param(
            [Parameter()] [object] $Headers,
            [Parameter(Mandatory)] [string] $Name
        )

        if ($null -eq $Headers) { return $null }

        if ($Headers -is [System.Collections.IDictionary]) {
            foreach ($key in @($Headers.Keys)) {
                if ([string]::Equals([string]$key, $Name, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $rawValue = $Headers[$key]
                    if ($rawValue -is [System.Collections.IEnumerable] -and $rawValue -isnot [string]) {
                        return (@($rawValue | ForEach-Object { [string]$_ }) -join ', ')
                    }
                    return [string]$rawValue
                }
            }
            return $null
        }

        if ($Headers -is [System.Net.Http.Headers.HttpHeaders]) {
            $typedValues = $null
            if ($Headers.TryGetValues($Name, [ref]$typedValues)) {
                return (@($typedValues | ForEach-Object { [string]$_ }) -join ', ')
            }
            return $null
        }

        if ($Headers -is [System.Net.WebHeaderCollection]) {
            $headerValues = $Headers.GetValues($Name)
            if ($null -ne $headerValues) {
                return (@($headerValues | ForEach-Object { [string]$_ }) -join ', ')
            }
            return $null
        }

        $headerValues = $null
        if ($Headers.PSObject.Methods.Name -contains 'TryGetValues') {
            $typedValues = $null
            if ($Headers.TryGetValues($Name, [ref]$typedValues)) {
                return (@($typedValues | ForEach-Object { [string]$_ }) -join ', ')
            }
            return $null
        }

        if ($Headers.PSObject.Methods.Name -contains 'GetValues') {
            try {
                $headerValues = $Headers.GetValues($Name)
            } catch {
                $headerValues = $null
            }
            if ($null -ne $headerValues) {
                return (@($headerValues | ForEach-Object { [string]$_ }) -join ', ')
            }
        }

        try {
            $indexed = $Headers[$Name]
            if ($null -ne $indexed) {
                if ($indexed -is [System.Collections.IEnumerable] -and $indexed -isnot [string]) {
                    return (@($indexed | ForEach-Object { [string]$_ }) -join ', ')
                }
                return [string]$indexed
            }
        } catch {
            Write-Verbose (
                "Header indexer lookup for '{0}' failed on type '{1}' with exception type '{2}'." -f
                $Name,
                $Headers.GetType().FullName,
                $_.Exception.GetType().FullName
            )
        }

        $matchedProperty = @($Headers.PSObject.Properties | Where-Object {
                [string]::Equals($_.Name, $Name, [System.StringComparison]::OrdinalIgnoreCase)
            } | Select-Object -First 1)
        if ($matchedProperty.Count -gt 0) {
            $value = $matchedProperty[0].Value
            if ($value -is [System.Collections.IEnumerable] -and $value -isnot [string]) {
                return (@($value | ForEach-Object { [string]$_ }) -join ', ')
            }
            return [string]$value
        }

        return $null
    }

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

    if ($Surface -ceq 'GitHub') {
        if ($tokenArgs.ContainsKey('Pat')) {
            throw 'GitHub live collection accepts bearer tokens only. Use -Token (SecureString) or set GITHUB_TOKEN.'
        }
        if (-not $tokenArgs.ContainsKey('Token')) {
            $githubToken = [string]$env:GITHUB_TOKEN
            if ([string]::IsNullOrWhiteSpace($githubToken)) {
                throw 'GitHub live collection requires -Token or GITHUB_TOKEN.'
            }
            $tokenArgs['Token'] = ConvertTo-FinOpsSecureString -Value $githubToken
        }
    } elseif ($Surface -ceq 'Ado') {
        if ($tokenArgs.ContainsKey('Pat')) {
            if ($tokenArgs.ContainsKey('Token')) { $tokenArgs.Remove('Token') }
        } elseif (-not $tokenArgs.ContainsKey('Token')) {
            $adoPat = [string]$env:AZURE_DEVOPS_PAT
            $adoToken = [string]$env:AZURE_DEVOPS_TOKEN
            if (-not [string]::IsNullOrWhiteSpace($adoPat)) {
                $tokenArgs['Pat'] = ConvertTo-FinOpsSecureString -Value $adoPat
            } elseif (-not [string]::IsNullOrWhiteSpace($adoToken)) {
                $tokenArgs['Token'] = ConvertTo-FinOpsSecureString -Value $adoToken
            } else {
                throw 'Azure DevOps live collection requires -Pat/-Token or AZURE_DEVOPS_PAT/AZURE_DEVOPS_TOKEN.'
            }
        }

        if ([string]::IsNullOrWhiteSpace([string]$AdoOrg)) {
            throw 'Azure DevOps live collection requires -AdoOrg.'
        }
    } elseif (-not $tokenArgs.ContainsKey('Token') -and -not $tokenArgs.ContainsKey('Pat')) {
        if ($Surface -ceq 'Graph') { $tokenArgs['Scope'] = 'graph' }
        elseif ($Surface -ceq 'Arm') { $tokenArgs['Scope'] = 'arm' }
        else { throw "Surface $Surface requires -Token or -Pat in Phase 6a." }
    }

    $auth = Get-FinOpsAccessToken @tokenArgs

    $guardArgs = @{}
    if ($AllowUnknownScopes) { $guardArgs['AllowUnknownScopes'] = $true }

    if ($Surface -ceq 'GitHub') {
        $plainToken = $null
        try {
            $plainToken = [System.Net.NetworkCredential]::new('', $auth.AccessToken).Password
            $probeHeaders = @{
                Accept                 = 'application/vnd.github+json'
                'X-GitHub-Api-Version' = '2022-11-28'
                Authorization          = "Bearer $plainToken"
            }
            $response = Invoke-WebRequest -Method Get -Uri 'https://api.github.com/' -Headers $probeHeaders -ErrorAction Stop
            $probeResponseHeaders = if ($response -and $response.PSObject.Properties.Name -contains 'Headers') {
                $response.Headers
            } else {
                $null
            }
            $scopeHeader = Get-FinOpsHeaderValue -Headers $probeResponseHeaders -Name 'X-OAuth-Scopes'
            $scopes = @()
            if (-not [string]::IsNullOrWhiteSpace($scopeHeader)) {
                $scopes = @(
                    $scopeHeader -split ',' |
                    ForEach-Object { [string]$_ } |
                    ForEach-Object { $_.Trim() } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
                )
            }
            $guardArgs['Scope'] = $scopes
            $guardArgs['Surface'] = 'GitHub'
            Assert-FinOpsReadOnlyScope @guardArgs
        } finally {
            $plainToken = $null
        }
    } elseif ([string]$auth.Source -ceq 'caller-pat') {
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
