function Invoke-FinOpsRestRequest {
    <#
    .SYNOPSIS
        Performs authenticated GET requests with paging and retry support.
    #>
    [CmdletBinding()]
    [OutputType([object])]
    param(
        [Parameter(Mandatory)]
        [string] $Uri,

        [Parameter()]
        [ValidateSet('Get')]
        [string] $Method = 'Get',

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter()]
        [hashtable] $Headers = @{},

        [Parameter()]
        [ValidateSet('None', 'GraphODataNext', 'ArmNextLink', 'GitHubLink', 'AdoContinuation')]
        [string] $Paging = 'None',

        [Parameter()]
        [string] $ValueProperty,

        [Parameter()]
        [ValidateRange(1, 10000)]
        [int] $MaxPages = 500,

        [switch] $Accept404AsNull
    )

    function Get-FinOpsStatusCodeFromError {
        param([Parameter(Mandatory)] [System.Management.Automation.ErrorRecord] $ErrorRecord)
        if ($null -eq $ErrorRecord.Exception) {
            return $null
        }
        if (-not ($ErrorRecord.Exception.PSObject.Properties.Name -contains 'Response')) {
            return $null
        }

        $response = $ErrorRecord.Exception.Response
        if ($null -eq $response) {
            return $null
        }
        if ($response.PSObject.Properties.Name -contains 'StatusCode') {
            if ($response.StatusCode -is [int]) { return [int]$response.StatusCode }
            return [int]$response.StatusCode.value__
        }
        return $null
    }

    function Get-FinOpsRetryAfterFromHeader {
        param([Parameter()] [object] $HeaderObject)
        if ($null -eq $HeaderObject) { return $null }
        if ($HeaderObject -is [System.Collections.IDictionary]) {
            if ($HeaderObject.Contains('Retry-After')) {
                return [int]$HeaderObject['Retry-After']
            }
            if ($HeaderObject.Contains('retry-after')) {
                return [int]$HeaderObject['retry-after']
            }
        }
        return $null
    }

    function Get-FinOpsNextLink {
        param(
            [Parameter(Mandatory)] [string] $PagingMode,
            [Parameter()] [AllowNull()] [object] $Body,
            [Parameter(Mandatory)] [string] $CurrentUri,
            [Parameter()] [AllowNull()] [object] $ResponseHeaders
        )

        switch ($PagingMode) {
            'GraphODataNext' {
                if ($Body -and $Body.PSObject.Properties.Name -contains '@odata.nextLink') {
                    return [string]$Body.'@odata.nextLink'
                }
                return $null
            }
            'ArmNextLink' {
                if ($Body -and $Body.PSObject.Properties.Name -contains 'nextLink') {
                    return [string]$Body.nextLink
                }
                return $null
            }
            'GitHubLink' {
                if ($null -eq $ResponseHeaders) { return $null }
                $linkHeader = $null
                if ($ResponseHeaders -is [System.Collections.IDictionary]) {
                    if ($ResponseHeaders.Contains('Link')) { $linkHeader = [string]$ResponseHeaders['Link'] }
                    elseif ($ResponseHeaders.Contains('link')) { $linkHeader = [string]$ResponseHeaders['link'] }
                }
                if (-not $linkHeader) { return $null }
                $match = [regex]::Match($linkHeader, '<([^>]+)>;\s*rel="?next"?')
                if ($match.Success) { return $match.Groups[1].Value }
                return $null
            }
            'AdoContinuation' {
                $continuationToken = $null
                if ($Body -and $Body.PSObject.Properties.Name -contains 'continuationToken' -and $Body.continuationToken) {
                    $continuationToken = [string]$Body.continuationToken
                }
                if (-not $continuationToken -and $ResponseHeaders -is [System.Collections.IDictionary]) {
                    if ($ResponseHeaders.Contains('X-MS-ContinuationToken')) { $continuationToken = [string]$ResponseHeaders['X-MS-ContinuationToken'] }
                    elseif ($ResponseHeaders.Contains('x-ms-continuationtoken')) { $continuationToken = [string]$ResponseHeaders['x-ms-continuationtoken'] }
                }

                if (-not $continuationToken) { return $null }
                $withoutToken = $CurrentUri -replace '([?&])continuationToken=[^&]*', '$1'
                $withoutToken = $withoutToken.TrimEnd('?', '&')
                $separator = if ($withoutToken -match '\?') { '&' } else { '?' }
                return "$withoutToken${separator}continuationToken=$([System.Uri]::EscapeDataString($continuationToken))"
            }
            default { return $null }
        }
    }

    $rawToken = $null
    try {
        $rawToken = [System.Net.NetworkCredential]::new('', $Auth.AccessToken).Password
        $authHeaderValue = switch ([string]$Auth.Source) {
            'caller-pat' {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(":$rawToken")
                'Basic ' + [Convert]::ToBase64String($bytes)
            }
            default { "Bearer $rawToken" }
        }

        $currentUri = $Uri
        $page = 0
        $items = [System.Collections.Generic.List[object]]::new()

        while ($currentUri -and $page -lt $MaxPages) {
            $page++
            $attempt = 0
            $body = $null
            $responseHeaders = $null

            while ($true) {
                $attempt++
                $requestHeaders = @{}
                foreach ($kv in $Headers.GetEnumerator()) { $requestHeaders[$kv.Key] = $kv.Value }
                $requestHeaders['Authorization'] = $authHeaderValue

                try {
                    if ($Paging -ceq 'GitHubLink') {
                        $webResponse = Invoke-WebRequest -Method $Method -Uri $currentUri -Headers $requestHeaders -ResponseHeadersVariable responseHeaders -ErrorAction Stop
                        if ($null -eq $responseHeaders -and $webResponse -and $webResponse.PSObject.Properties.Name -contains 'Headers') {
                            $responseHeaders = $webResponse.Headers
                        }
                        $body = if ($webResponse.Content) { $webResponse.Content | ConvertFrom-Json -Depth 100 } else { $null }
                    } else {
                        $body = Invoke-RestMethod -Method $Method -Uri $currentUri -Headers $requestHeaders -ResponseHeadersVariable responseHeaders -ErrorAction Stop
                    }
                    break
                } catch {
                    $statusCode = Get-FinOpsStatusCodeFromError -ErrorRecord $_
                    if ($Accept404AsNull -and $statusCode -eq 404) {
                        return $null
                    }

                    if (($statusCode -eq 429 -or $statusCode -eq 503) -and $attempt -lt 5) {
                        $retryAfter = Get-FinOpsRetryAfterFromHeader -HeaderObject $responseHeaders
                        if ($null -eq $retryAfter) {
                            $exp = [Math]::Pow(2, ($attempt - 1))
                            $retryAfter = [Math]::Min([int]$exp, 16)
                        }
                        Start-Sleep -Seconds ([Math]::Max($retryAfter, 1))
                        continue
                    }

                    Write-Verbose "Invoke-FinOpsRestRequest failed status=$statusCode uri=$currentUri"
                    throw "Request failed with status=$statusCode uri=$currentUri"
                }
            }

            if ($Paging -ceq 'None') {
                return $body
            }

            if ($ValueProperty) {
                if ($body -and $body.PSObject.Properties.Name -contains $ValueProperty -and $null -ne $body.$ValueProperty) {
                    foreach ($entry in @($body.$ValueProperty)) { [void]$items.Add($entry) }
                }
            } elseif ($body -is [System.Collections.IEnumerable] -and -not ($body -is [string])) {
                foreach ($entry in @($body)) { [void]$items.Add($entry) }
            } else {
                [void]$items.Add($body)
            }

            $currentUri = Get-FinOpsNextLink -PagingMode $Paging -Body $body -CurrentUri $currentUri -ResponseHeaders $responseHeaders
        }

        return , $items.ToArray()
    } finally {
        $rawToken = $null
    }
}
