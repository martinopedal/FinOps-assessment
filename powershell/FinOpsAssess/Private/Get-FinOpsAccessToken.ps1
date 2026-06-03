function Get-FinOpsAccessToken {
    <#
    .SYNOPSIS
        Resolves a read-only access token or PAT for live collection.
    #>
    [CmdletBinding(DefaultParameterSetName = 'Scope')]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Scope')]
        [ValidateSet('graph', 'arm')]
        [string] $Scope,

        [Parameter(ParameterSetName = 'Scope')]
        [string] $TenantId,

        [Parameter(ParameterSetName = 'Scope')]
        [string] $ClientId,

        [Parameter(Mandatory, ParameterSetName = 'Token')]
        [System.Security.SecureString] $Token,

        [Parameter(Mandatory, ParameterSetName = 'Pat')]
        [System.Security.SecureString] $Pat
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

    if ($PSCmdlet.ParameterSetName -eq 'Token') {
        return [pscustomobject]@{
            AccessToken = $Token
            Surface     = 'CallerBearer'
            ExpiresOn   = $null
            Source      = 'caller-bearer'
        }
    }

    if ($PSCmdlet.ParameterSetName -eq 'Pat') {
        return [pscustomobject]@{
            AccessToken = $Pat
            Surface     = 'CallerPat'
            ExpiresOn   = $null
            Source      = 'caller-pat'
        }
    }

    $surface = if ($Scope -ceq 'graph') { 'Graph' } else { 'AzureResourceManager' }
    $resourceUrl = if ($Scope -ceq 'graph') { 'https://graph.microsoft.com' } else { 'https://management.azure.com' }
    $resourceScope = "$resourceUrl/.default"

    if (Get-Module -ListAvailable -Name Az.Accounts) {
        try {
            $azToken = Get-AzAccessToken -ResourceUrl $resourceUrl -ErrorAction Stop
            if ($azToken -and $azToken.Token) {
                Write-Verbose "Get-FinOpsAccessToken source=az.accounts surface=$surface expires=$($azToken.ExpiresOn)"
                return [pscustomobject]@{
                    AccessToken = ConvertTo-FinOpsSecureString -Value ([string]$azToken.Token)
                    Surface     = $surface
                    ExpiresOn   = $azToken.ExpiresOn
                    Source      = 'az.accounts'
                }
            }
        } catch {
            Write-Verbose "Get-FinOpsAccessToken source=az.accounts surface=$surface status=unavailable"
        }
    }

    $resolvedTenantId = if ($TenantId) { $TenantId } elseif ($env:AZURE_TENANT_ID) { $env:AZURE_TENANT_ID } else { $null }
    $resolvedClientId = if ($ClientId) { $ClientId } elseif ($env:AZURE_CLIENT_ID) { $env:AZURE_CLIENT_ID } else { $null }

    if ($resolvedTenantId -and $resolvedClientId -and $env:AZURE_FEDERATED_TOKEN_FILE) {
        $federatedToken = Get-Content -LiteralPath $env:AZURE_FEDERATED_TOKEN_FILE -Raw -ErrorAction Stop
        $tokenEndpoint = "https://login.microsoftonline.com/$resolvedTenantId/oauth2/v2.0/token"
        $body = @{
            client_id             = $resolvedClientId
            scope                 = $resourceScope
            grant_type            = 'client_credentials'
            client_assertion_type = 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer'
            client_assertion      = $federatedToken
        }
        $request = @{
            Method      = 'Post'
            Uri         = $tokenEndpoint
            Body        = $body
            ContentType = 'application/x-www-form-urlencoded'
            ErrorAction = 'Stop'
        }
        try {
            $response = Invoke-RestMethod @request
        } catch {
            throw "Token acquisition failed for $surface from workload identity at $tokenEndpoint."
        }

        Write-Verbose "Get-FinOpsAccessToken source=workload-identity surface=$surface expires=$($response.expires_in)"
        return [pscustomobject]@{
            AccessToken = ConvertTo-FinOpsSecureString -Value ([string]$response.access_token)
            Surface     = $surface
            ExpiresOn   = if ($response.expires_in) { [System.DateTimeOffset]::UtcNow.AddSeconds([int]$response.expires_in) } else { $null }
            Source      = 'workload-identity'
        }
    }

    if ($resolvedTenantId -and $resolvedClientId -and $env:AZURE_CLIENT_SECRET) {
        $tokenEndpoint = "https://login.microsoftonline.com/$resolvedTenantId/oauth2/v2.0/token"
        $body = @{
            client_id     = $resolvedClientId
            client_secret = $env:AZURE_CLIENT_SECRET
            scope         = $resourceScope
            grant_type    = 'client_credentials'
        }
        $request = @{
            Method      = 'Post'
            Uri         = $tokenEndpoint
            Body        = $body
            ContentType = 'application/x-www-form-urlencoded'
            ErrorAction = 'Stop'
        }
        try {
            $response = Invoke-RestMethod @request
        } catch {
            throw "Token acquisition failed for $surface from client secret at $tokenEndpoint."
        }

        Write-Verbose "Get-FinOpsAccessToken source=client-secret surface=$surface expires=$($response.expires_in)"
        return [pscustomobject]@{
            AccessToken = ConvertTo-FinOpsSecureString -Value ([string]$response.access_token)
            Surface     = $surface
            ExpiresOn   = if ($response.expires_in) { [System.DateTimeOffset]::UtcNow.AddSeconds([int]$response.expires_in) } else { $null }
            Source      = 'client-secret'
        }
    }

    throw "Token acquisition failed for ${surface}: no supported credential source resolved."
}
