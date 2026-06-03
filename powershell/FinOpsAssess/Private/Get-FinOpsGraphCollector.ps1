function Get-FinOpsGraphCollector {
    <#
    .SYNOPSIS
        Collects Microsoft Graph users, assignments, and usage signals to CSV.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter()]
        [string] $TenantId,

        [Parameter()]
        [int] $PageLimit = 200
    )

    $null = $TenantId
    $graphBase = 'https://graph.microsoft.com/v1.0'
    $maxPages = if ($PageLimit -gt 0) { $PageLimit } else { 10000 }
    $now = Get-FinOpsNow

    function ConvertTo-FinOpsLowerMap {
        param([Parameter(Mandatory)] [pscustomobject] $Row)
        $map = @{}
        foreach ($prop in $Row.PSObject.Properties) {
            $map[[string]$prop.Name.ToLowerInvariant()] = $prop.Value
        }
        return $map
    }

    function ConvertFrom-FinOpsCsvBlob {
        param([Parameter(Mandatory)] [AllowNull()] [object] $Blob)
        if ($null -eq $Blob) { return @() }
        $text = if ($Blob -is [byte[]]) {
            [System.Text.Encoding]::UTF8.GetString($Blob)
        } else {
            [string]$Blob
        }
        $rows = ConvertFrom-FinOpsCsvText -Text $text
        if ($rows.Count -eq 0) { return @() }
        $header = @($rows[0] | ForEach-Object { [string]$_ })
        $result = [System.Collections.Generic.List[object]]::new()
        for ($i = 1; $i -lt $rows.Count; $i++) {
            $cells = @($rows[$i])
            if ($cells.Count -eq 1 -and [string]::IsNullOrEmpty([string]$cells[0])) {
                continue
            }
            $entry = [ordered]@{}
            for ($c = 0; $c -lt $header.Count; $c++) {
                $value = if ($c -lt $cells.Count) { [string]$cells[$c] } else { '' }
                $entry[$header[$c]] = $value
            }
            [void]$result.Add([pscustomobject]$entry)
        }
        return $result.ToArray()
    }

    function Get-FinOpsDaysSince {
        param([Parameter()] [AllowNull()] [string] $DateText)
        if ([string]::IsNullOrWhiteSpace($DateText)) {
            return $null
        }
        try {
            $parsed = [System.DateTimeOffset]::Parse($DateText, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal)
            $days = ($now - $parsed.ToUniversalTime()).Days
            return [Math]::Max(0, [int]$days)
        } catch {
            return $null
        }
    }

    function Get-FinOpsPropertyValue {
        param(
            [Parameter(Mandatory)] [object] $InputObject,
            [Parameter(Mandatory)] [string] $Name,
            [Parameter()] [AllowNull()] [object] $Default = $null
        )
        if ($null -eq $InputObject) {
            return $Default
        }
        if ($InputObject -is [System.Collections.IDictionary]) {
            if (-not $InputObject.Contains($Name)) { return $Default }
            return $InputObject[$Name]
        }
        $propNames = @($InputObject.PSObject.Properties | ForEach-Object { $_.Name })
        if ($propNames -notcontains $Name) { return $Default }
        return $InputObject.$Name
    }

    $select = 'id,userPrincipalName,displayName,userType,accountEnabled,jobTitle,department,assignedLicenses,signInActivity'
    $usersUri = "$graphBase/users?`$select=$select&`$top=999&`$count=true"
    $rawUsers = @(Invoke-FinOpsRestRequest `
            -Uri $usersUri `
            -Auth $Auth `
            -Headers @{ ConsistencyLevel = 'eventual' } `
            -Paging GraphODataNext `
            -ValueProperty 'value' `
            -MaxPages $maxPages)

    $mailboxSizes = @{}
    try {
        $mailboxBlob = Invoke-FinOpsRestRequest -Uri "$graphBase/reports/getMailboxUsageDetail(period='D30')" -Auth $Auth
        foreach ($row in @(ConvertFrom-FinOpsCsvBlob -Blob $mailboxBlob)) {
            $upn = ''
            $quota = ''
            foreach ($prop in $row.PSObject.Properties) {
                $name = ([string]$prop.Name).ToLowerInvariant()
                if ($name -ceq 'user principal name') {
                    $upn = ([string]$prop.Value).Trim().ToLowerInvariant()
                } elseif (($name -ceq 'storage used (byte)' -or $name -ceq 'used (byte)') -and -not $quota) {
                    $quota = [string]$prop.Value
                }
            }
            if ($upn -and -not [string]::IsNullOrWhiteSpace($quota)) {
                $bytes = 0L
                if ([long]::TryParse($quota.Trim(), [ref]$bytes)) {
                    $mailboxSizes[$upn] = [Math]::Round($bytes / 1073741824.0, 3)
                }
            }
        }
    } catch {
        Write-Warning "getMailboxUsageDetail failed ($($_.Exception.Message)); skipping mailbox sizes."
    }

    $activeServices = @{}
    try {
        $activeBlob = Invoke-FinOpsRestRequest -Uri "$graphBase/reports/getOffice365ActiveUserDetail(period='D30')" -Auth $Auth
        foreach ($row in @(ConvertFrom-FinOpsCsvBlob -Blob $activeBlob)) {
            $low = ConvertTo-FinOpsLowerMap -Row $row
            $upn = ([string]$low['user principal name']).Trim().ToLowerInvariant()
            if (-not $upn) { continue }
            $signals = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
            foreach ($k in $low.Keys) {
                $v = ([string]$low[$k]).Trim().ToLowerInvariant()
                if ($v -notin @('yes', 'true', '1')) { continue }
                if ($k.Contains('exchange')) { [void]$signals.Add('exchange') }
                elseif ($k.Contains('sharepoint')) { [void]$signals.Add('sharepoint') }
                elseif ($k.Contains('teams')) { [void]$signals.Add('teams') }
                elseif ($k.Contains('yammer')) { [void]$signals.Add('yammer') }
                elseif ($k.Contains('skype')) { [void]$signals.Add('skype') }
            }
            $activeServices[$upn] = $signals
        }
    } catch {
        Write-Warning "getOffice365ActiveUserDetail failed ($($_.Exception.Message)); skipping activity signals."
    }

    $copilotActive = @{}
    try {
        $copilotBlob = Invoke-FinOpsRestRequest -Uri "$graphBase/reports/getMicrosoft365CopilotUsageSummary(period='D30')" -Auth $Auth
        foreach ($row in @(ConvertFrom-FinOpsCsvBlob -Blob $copilotBlob)) {
            $low = ConvertTo-FinOpsLowerMap -Row $row
            $upn = ([string]$low['user principal name']).Trim().ToLowerInvariant()
            if (-not $upn) { continue }
            $active = $false
            foreach ($k in $low.Keys) {
                if (($k.Contains('active') -or $k.Contains('used') -or $k.Contains('activity')) -and -not $k.Contains('user')) {
                    $value = ([string]$low[$k]).Trim().ToLowerInvariant()
                    if ($value -notin @('0', '', 'false', 'no')) {
                        $active = $true
                        break
                    }
                }
            }
            $copilotActive[$upn] = $active
        }
    } catch {
        $copilotActive = @{}
    }

    $usersRows = [System.Collections.Generic.List[object]]::new()
    $assignmentRows = [System.Collections.Generic.List[object]]::new()
    $usageRows = [System.Collections.Generic.List[object]]::new()

    foreach ($u in $rawUsers) {
        $upn = [string](Get-FinOpsPropertyValue -InputObject $u -Name 'userPrincipalName' -Default '')
        $upnLower = $upn.ToLowerInvariant()
        $userTypeRaw = ([string](Get-FinOpsPropertyValue -InputObject $u -Name 'userType' -Default 'member')).ToLowerInvariant()
        $userType = if ($userTypeRaw -ceq 'guest') { 'guest' } elseif ($userTypeRaw -ceq 'member') { 'member' } else { 'service' }

        $accountEnabled = if ($u.PSObject.Properties.Name -contains 'accountEnabled') { [bool]$u.accountEnabled } else { $true }
        $lastSignInDays = $null
        $signInActivity = Get-FinOpsPropertyValue -InputObject $u -Name 'signInActivity'
        if ($signInActivity) {
            $lastSignInRaw = Get-FinOpsPropertyValue -InputObject $signInActivity -Name 'lastSignInDateTime'
            $lastSignInDays = Get-FinOpsDaysSince -DateText ([string]$lastSignInRaw)
        }

        $mailboxSize = if ($mailboxSizes.ContainsKey($upnLower)) { $mailboxSizes[$upnLower] } else { $null }
        $mailboxSizeText = if ($null -eq $mailboxSize) { '' } else { ([double]$mailboxSize).ToString([System.Globalization.CultureInfo]::InvariantCulture) }

        [void]$usersRows.Add([pscustomobject][ordered]@{
                principal         = $upn
                display_name      = [string](Get-FinOpsPropertyValue -InputObject $u -Name 'displayName' -Default '')
                user_type         = $userType
                account_enabled   = if ($accountEnabled) { 'true' } else { 'false' }
                job_title         = [string](Get-FinOpsPropertyValue -InputObject $u -Name 'jobTitle' -Default '')
                department        = [string](Get-FinOpsPropertyValue -InputObject $u -Name 'department' -Default '')
                mailbox_size_gb   = $mailboxSizeText
                last_sign_in_days = if ($null -eq $lastSignInDays) { '' } else { [string]$lastSignInDays }
            })

        foreach ($lic in @(Get-FinOpsPropertyValue -InputObject $u -Name 'assignedLicenses' -Default @())) {
            $sku = ([string]$lic.skuId).ToUpperInvariant()
            if ($sku) {
                [void]$assignmentRows.Add([pscustomobject][ordered]@{
                        principal = $upn
                        sku_id    = $sku
                    })
            }
        }

        $services = if ($activeServices.ContainsKey($upnLower)) { $activeServices[$upnLower] } else { $null }
        if ($null -eq $services) {
            $services = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
        }
        foreach ($pair in @(
                @{ Key = 'exchange'; Signal = 'exchange' },
                @{ Key = 'sharepoint'; Signal = 'sharepoint' },
                @{ Key = 'teams'; Signal = 'teams' }
            )) {
            if ($services.Contains($pair.Key)) {
                [void]$usageRows.Add([pscustomobject][ordered]@{
                        principal          = $upn
                        signal             = $pair.Signal
                        last_activity_days = '0'
                    })
            } elseif ($null -ne $lastSignInDays) {
                [void]$usageRows.Add([pscustomobject][ordered]@{
                        principal          = $upn
                        signal             = $pair.Signal
                        last_activity_days = [string]$lastSignInDays
                    })
            }
        }

        if ($copilotActive.ContainsKey($upnLower)) {
            [void]$usageRows.Add([pscustomobject][ordered]@{
                    principal          = $upn
                    signal             = 'copilot'
                    last_activity_days = if ($copilotActive[$upnLower]) { '0' } else { '61' }
                })
        }
    }

    $usersPath = Join-Path $OutputPath 'users.csv'
    $assignmentsPath = Join-Path $OutputPath 'license_assignments.csv'
    $usagePath = Join-Path $OutputPath 'usage.csv'

    Write-FinOpsCollectorCsv -Path $usersPath -Header @(
        'principal', 'display_name', 'user_type', 'account_enabled',
        'job_title', 'department', 'mailbox_size_gb', 'last_sign_in_days'
    ) -Row @($usersRows.ToArray()) | Out-Null
    Write-FinOpsCollectorCsv -Path $assignmentsPath -Header @('principal', 'sku_id') -Row @($assignmentRows.ToArray()) | Out-Null
    Write-FinOpsCollectorCsv -Path $usagePath -Header @('principal', 'signal', 'last_activity_days') -Row @($usageRows.ToArray()) | Out-Null

    return [pscustomobject]@{
        FilesWritten = @('users.csv', 'license_assignments.csv', 'usage.csv')
        RowCounts    = [ordered]@{
            users               = @($usersRows.ToArray()).Count
            license_assignments = @($assignmentRows.ToArray()).Count
            usage               = @($usageRows.ToArray()).Count
        }
    }
}
