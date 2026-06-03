function Get-FinOpsGitHubCollector {
    <#
    .SYNOPSIS
        Collects GitHub seats and org billing snapshots to normalized CSVs.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter()]
        [string] $Enterprise,

        [Parameter()]
        [string[]] $Org,

        [Parameter()]
        [int] $PageLimit = 200
    )

    $base = 'https://api.github.com'
    $maxPages = if ($PageLimit -gt 0) { $PageLimit } else { 200 }
    $now = Get-FinOpsNow
    $headers = @{
        Accept                 = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }

    function Get-FinOpsPropertyValue {
        param(
            [Parameter()] [AllowNull()] [object] $InputObject,
            [Parameter(Mandatory)] [string] $Name,
            [Parameter()] [AllowNull()] [object] $Default = $null
        )
        if ($null -eq $InputObject) { return $Default }
        if ($InputObject -is [System.Collections.IDictionary]) {
            if (-not $InputObject.Contains($Name)) { return $Default }
            return $InputObject[$Name]
        }
        $propertyNames = @($InputObject.PSObject.Properties | ForEach-Object { $_.Name })
        if ($propertyNames -notcontains $Name) { return $Default }
        return $InputObject.$Name
    }

    function Get-FinOpsDaysSinceIso {
        param([Parameter()] [AllowNull()] [string] $DateText)
        if ([string]::IsNullOrWhiteSpace($DateText)) { return $null }
        try {
            $parsed = [System.DateTimeOffset]::Parse(
                $DateText,
                [System.Globalization.CultureInfo]::InvariantCulture,
                [System.Globalization.DateTimeStyles]::AssumeUniversal
            )
            return [Math]::Max(0, ($now - $parsed.ToUniversalTime()).Days)
        } catch {
            return $null
        }
    }

    function Expand-FinOpsGitHubBatch {
        param([Parameter()] [AllowNull()] [object] $Batch)
        if ($null -eq $Batch) { return @() }
        if ($Batch -is [System.Collections.IDictionary]) {
            foreach ($name in @('seats', 'users', 'runners', 'organizations')) {
                if ($Batch.Contains($name) -and $Batch[$name]) {
                    return @($Batch[$name])
                }
            }
            return @($Batch)
        }
        $nameList = @($Batch.PSObject.Properties | ForEach-Object { $_.Name })
        foreach ($name in @('seats', 'users', 'runners', 'organizations')) {
            if ($nameList -contains $name -and $Batch.$name) {
                return @($Batch.$name)
            }
        }
        if ($Batch -is [System.Collections.IEnumerable] -and -not ($Batch -is [string])) {
            return @($Batch)
        }
        return @($Batch)
    }

    function Invoke-FinOpsGitHubPaged {
        param([Parameter(Mandatory)] [string] $Uri)
        $rows = [System.Collections.Generic.List[object]]::new()
        $response = @(Invoke-FinOpsRestRequest -Uri $Uri -Auth $Auth -Headers $headers -Paging GitHubLink -MaxPages $maxPages)
        foreach ($chunk in $response) {
            foreach ($row in @(Expand-FinOpsGitHubBatch -Batch $chunk)) {
                [void]$rows.Add($row)
            }
        }
        return @($rows.ToArray())
    }

    function ConvertTo-FinOpsRunnerTier {
        param([Parameter()] [AllowNull()] [object] $IncludedMinutes)
        if ($null -eq $IncludedMinutes -or [string]::IsNullOrWhiteSpace([string]$IncludedMinutes)) { return '' }
        try {
            $value = [int][string]$IncludedMinutes
            if ($value -ge 50000) { return 'enterprise' }
            if ($value -ge 3000) { return 'team' }
            return 'free'
        } catch {
            return ''
        }
    }

    $seatRows = [System.Collections.Generic.List[object]]::new()
    $orgRows = [System.Collections.Generic.List[object]]::new()

    if ($Enterprise) {
        $consumedUri = "$base/enterprises/$Enterprise/consumed-licenses?per_page=100&page=1"
        foreach ($seat in @(Invoke-FinOpsGitHubPaged -Uri $consumedUri)) {
            $githubCom = Get-FinOpsPropertyValue -InputObject $seat -Name 'github_com_user' -Default $null
            $principal = [string](Get-FinOpsPropertyValue -InputObject $githubCom -Name 'login' -Default '')
            if (-not $principal) {
                $principal = [string](Get-FinOpsPropertyValue -InputObject $seat -Name 'login' -Default '')
            }
            if (-not $principal) { continue }
            $lastActivityRaw = [string](Get-FinOpsPropertyValue -InputObject $githubCom -Name 'updated_at' -Default '')
            if (-not $lastActivityRaw) {
                $lastActivityRaw = [string](Get-FinOpsPropertyValue -InputObject $githubCom -Name 'created_at' -Default '')
            }
            $lastActivityDays = Get-FinOpsDaysSinceIso -DateText $lastActivityRaw
            [void]$seatRows.Add([pscustomobject][ordered]@{
                    principal               = $principal
                    org                     = $Enterprise
                    seat_type               = 'enterprise'
                    sku_id                  = 'GH.ENTERPRISE'
                    last_activity_days      = if ($null -eq $lastActivityDays) { '' } else { [string]$lastActivityDays }
                    copilot_acceptances_30d = ''
                })
        }

        $copilotUri = "$base/enterprises/$Enterprise/copilot/billing/seats?per_page=100&page=1"
        foreach ($seat in @(Invoke-FinOpsGitHubPaged -Uri $copilotUri)) {
            $assignee = Get-FinOpsPropertyValue -InputObject $seat -Name 'assignee' -Default $null
            $principal = [string](Get-FinOpsPropertyValue -InputObject $assignee -Name 'login' -Default '')
            if (-not $principal) { continue }
            $planType = ([string](Get-FinOpsPropertyValue -InputObject $seat -Name 'plan_type' -Default '')).ToLowerInvariant()
            $isEnterprisePlan = $planType.Contains('enterprise')
            $seatType = if ($isEnterprisePlan) { 'copilot_enterprise' } else { 'copilot_business' }
            $skuId = if ($isEnterprisePlan) { 'GH.COPILOT_ENTERPRISE' } else { 'GH.COPILOT_BUSINESS' }
            $lastActivityDays = Get-FinOpsDaysSinceIso -DateText ([string](Get-FinOpsPropertyValue -InputObject $seat -Name 'last_activity_at' -Default ''))
            [void]$seatRows.Add([pscustomobject][ordered]@{
                    principal               = $principal
                    org                     = $Enterprise
                    seat_type               = $seatType
                    sku_id                  = $skuId
                    last_activity_days      = if ($null -eq $lastActivityDays) { '' } else { [string]$lastActivityDays }
                    copilot_acceptances_30d = if ($null -ne $lastActivityDays -and $lastActivityDays -ge 30) { '0' } else { '' }
                })
        }
    }

    foreach ($name in @($Org | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })) {
        $ghas = Invoke-FinOpsRestRequest `
            -Uri "$base/orgs/$name/settings/billing/advanced-security" `
            -Auth $Auth `
            -Headers $headers `
            -Accept404AsNull `
            -MaxPages $maxPages
        $actions = Invoke-FinOpsRestRequest `
            -Uri "$base/orgs/$name/settings/billing/actions" `
            -Auth $Auth `
            -Headers $headers `
            -Accept404AsNull `
            -MaxPages $maxPages

        $ghasRepoCount = $null
        $activelyScanned = $null
        $activeCommitters = $null
        if ($ghas) {
            $repos = @(Get-FinOpsPropertyValue -InputObject $ghas -Name 'repos' -Default @())
            $ghasRepoCount = $repos.Count
            $scannedCount = 0
            foreach ($repo in $repos) {
                $breakdown = @(Get-FinOpsPropertyValue -InputObject $repo -Name 'advanced_security_committers_breakdown' -Default @())
                $hasResults = $false
                foreach ($entry in $breakdown) {
                    $resultsCount = Get-FinOpsPropertyValue -InputObject $entry -Name 'results_count'
                    try {
                        if ($null -ne $resultsCount -and [int][string]$resultsCount -gt 0) {
                            $hasResults = $true
                            break
                        }
                    } catch {
                        continue
                    }
                }
                if ($hasResults) { $scannedCount++ }
            }
            $activelyScanned = $scannedCount
            $activeCommitters = Get-FinOpsPropertyValue -InputObject $ghas -Name 'total_advanced_security_committers'
        }

        $runnerMinutesUsed = $null
        $runnerMinutesIncluded = $null
        $runnerTier = ''
        if ($actions) {
            $runnerMinutesUsed = Get-FinOpsPropertyValue -InputObject $actions -Name 'total_minutes_used'
            $runnerMinutesIncluded = Get-FinOpsPropertyValue -InputObject $actions -Name 'included_minutes'
            $runnerTier = ConvertTo-FinOpsRunnerTier -IncludedMinutes $runnerMinutesIncluded
        }

        [void]$orgRows.Add([pscustomobject][ordered]@{
                org                     = $name
                ghas_repo_count         = if ($null -eq $ghasRepoCount) { '' } else { [string]$ghasRepoCount }
                actively_scanned_repos  = if ($null -eq $activelyScanned) { '' } else { [string]$activelyScanned }
                active_committers       = if ($null -eq $activeCommitters -or [string]::IsNullOrWhiteSpace([string]$activeCommitters)) { '' } else { [string]$activeCommitters }
                runner_tier             = $runnerTier
                runner_minutes_used     = if ($null -eq $runnerMinutesUsed -or [string]::IsNullOrWhiteSpace([string]$runnerMinutesUsed)) { '' } else { [string]$runnerMinutesUsed }
                runner_minutes_included = if ($null -eq $runnerMinutesIncluded -or [string]::IsNullOrWhiteSpace([string]$runnerMinutesIncluded)) { '' } else { [string]$runnerMinutesIncluded }
            })
    }

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'github_seats.csv') -Header @(
        'principal',
        'org',
        'seat_type',
        'sku_id',
        'last_activity_days',
        'copilot_acceptances_30d'
    ) -Row @($seatRows.ToArray()) | Out-Null

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'github_orgs.csv') -Header @(
        'org',
        'ghas_repo_count',
        'actively_scanned_repos',
        'active_committers',
        'runner_tier',
        'runner_minutes_used',
        'runner_minutes_included'
    ) -Row @($orgRows.ToArray()) | Out-Null

    return [pscustomobject]@{
        FilesWritten = @('github_seats.csv', 'github_orgs.csv')
        RowCounts    = [ordered]@{
            github_seats = @($seatRows.ToArray()).Count
            github_orgs  = @($orgRows.ToArray()).Count
        }
    }
}
