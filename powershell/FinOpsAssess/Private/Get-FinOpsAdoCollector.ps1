function Get-FinOpsAdoCollector {
    <#
    .SYNOPSIS
        Collects Azure DevOps seats and org usage snapshots to normalized CSVs.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter(Mandatory)]
        [string] $Org,

        [Parameter()]
        [int] $PageLimit = 200
    )

    $null = $Auth
    $adoBase = 'https://dev.azure.com'
    $vsaexBase = 'https://vsaex.dev.azure.com'
    $maxPages = if ($PageLimit -gt 0) { $PageLimit } else { 200 }
    $now = Get-FinOpsNow
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $accessLevelMap = @{
        express     = 'basic'
        advanced    = 'basic'
        stakeholder = 'stakeholder'
        vssubscriber = 'basic_plus_test'
        eligible    = 'stakeholder'
        none        = 'stakeholder'
        extendedmem = 'basic_plus_test'
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

    function ConvertTo-FinOpsBoolLiteral {
        param([Parameter()] [AllowNull()] [object] $Value)
        if ($Value -eq $true) { return 'true' }
        if ($Value -eq $false) { return 'false' }
        return ''
    }

    function Get-FinOpsAdoPercentile95 {
        param([Parameter()] [int[]] $Values)
        if (-not $Values -or $Values.Count -eq 0) { return $null }
        $sorted = @($Values | Sort-Object)
        $idx = [int][Math]::Floor($sorted.Count * 0.95)
        return $sorted[[Math]::Min($idx, $sorted.Count - 1)]
    }

    function Invoke-FinOpsAdoPagedMember {
        $uri = "$vsaexBase/$Org/_apis/userentitlements?api-version=7.1&top=100&select=Projects,Extensions"
        $rows = Invoke-FinOpsRestRequest -Uri $uri -Auth $Auth -Paging AdoContinuation -ValueProperty 'members' -MaxPages $maxPages
        return @($rows)
    }

    function Invoke-FinOpsAdoPagedProject {
        $uri = "$adoBase/$Org/_apis/projects?api-version=7.1&`$top=200"
        $rows = Invoke-FinOpsRestRequest -Uri $uri -Auth $Auth -Paging AdoContinuation -ValueProperty 'value' -MaxPages $maxPages
        return @($rows)
    }

    function Get-FinOpsAdoP95ConcurrentJob {
        $projects = @(Invoke-FinOpsAdoPagedProject)
        $windows = [System.Collections.Generic.List[object]]::new()
        foreach ($project in $projects) {
            $projectId = [string](Get-FinOpsPropertyValue -InputObject $project -Name 'id' -Default '')
            if (-not $projectId) { continue }
            $buildsUri = "$adoBase/$Org/$projectId/_apis/build/builds?api-version=7.1&`$top=200&queryOrder=startTimeDescending&statusFilter=completed"
            $buildRows = @()
            try {
                $buildRows = @(
                    Invoke-FinOpsRestRequest -Uri $buildsUri -Auth $Auth -Paging AdoContinuation -ValueProperty 'value' -MaxPages $maxPages
                )
            } catch {
                continue
            }

            foreach ($build in $buildRows) {
                $startText = [string](Get-FinOpsPropertyValue -InputObject $build -Name 'startTime' -Default '')
                $finishText = [string](Get-FinOpsPropertyValue -InputObject $build -Name 'finishTime' -Default '')
                if (-not $startText -or -not $finishText) { continue }
                try {
                    $start = [System.DateTimeOffset]::Parse($startText, $inv, [System.Globalization.DateTimeStyles]::AssumeUniversal)
                    $finish = [System.DateTimeOffset]::Parse($finishText, $inv, [System.Globalization.DateTimeStyles]::AssumeUniversal)
                    [void]$windows.Add([pscustomobject]@{
                            Start  = $start.ToUniversalTime()
                            Finish = $finish.ToUniversalTime()
                        })
                } catch {
                    continue
                }
            }
        }

        if ($windows.Count -eq 0) { return $null }
        $sortedWindows = @($windows.ToArray() | Sort-Object Start)
        $concurrencies = [System.Collections.Generic.List[int]]::new()
        for ($i = 0; $i -lt $sortedWindows.Count; $i++) {
            $start = $sortedWindows[$i].Start
            $concurrent = 0
            for ($j = 0; $j -le $i; $j++) {
                $window = $sortedWindows[$j]
                if ($window.Start -le $start -and $start -le $window.Finish) {
                    $concurrent++
                }
            }
            [void]$concurrencies.Add($concurrent)
        }
        return Get-FinOpsAdoPercentile95 -Values @($concurrencies.ToArray())
    }

    $seatRows = [System.Collections.Generic.List[object]]::new()
    foreach ($member in @(Invoke-FinOpsAdoPagedMember)) {
        $user = Get-FinOpsPropertyValue -InputObject $member -Name 'user' -Default $null
        $principal = [string](Get-FinOpsPropertyValue -InputObject $user -Name 'mailAddress' -Default '')
        if (-not $principal) {
            $principal = [string](Get-FinOpsPropertyValue -InputObject $user -Name 'uniqueName' -Default '')
        }
        if (-not $principal) {
            $principal = [string](Get-FinOpsPropertyValue -InputObject $user -Name 'displayName' -Default '')
        }
        if (-not $principal) { continue }

        $accessLevel = Get-FinOpsPropertyValue -InputObject $member -Name 'accessLevel' -Default $null
        $levelName = ([string](Get-FinOpsPropertyValue -InputObject $accessLevel -Name 'accessLevelName' -Default '')).ToLowerInvariant()
        $seatType = if ($accessLevelMap.ContainsKey($levelName)) { [string]$accessLevelMap[$levelName] } else { 'basic' }
        $skuId = switch ($seatType) {
            'stakeholder' { 'ADO.STAKEHOLDER'; break }
            'basic_plus_test' { 'ADO.BASIC_TEST'; break }
            default { 'ADO.BASIC' }
        }

        $lastAccessed = [string](Get-FinOpsPropertyValue -InputObject $member -Name 'lastAccessedDate' -Default '')
        if (-not $lastAccessed) {
            $lastAccessed = [string](Get-FinOpsPropertyValue -InputObject $accessLevel -Name 'lastAccessedDate' -Default '')
        }
        $lastActivityDays = Get-FinOpsDaysSinceIso -DateText $lastAccessed

        $extensions = @(Get-FinOpsPropertyValue -InputObject $member -Name 'extensions' -Default @())
        $hasTestPlans = $false
        foreach ($extension in $extensions) {
            $extensionId = ([string](Get-FinOpsPropertyValue -InputObject $extension -Name 'id' -Default '')).ToLowerInvariant()
            $extensionName = ([string](Get-FinOpsPropertyValue -InputObject $extension -Name 'name' -Default '')).ToLowerInvariant()
            if ($extensionId.Contains('testplans') -or $extensionName.Contains('test plans')) {
                $hasTestPlans = $true
                break
            }
        }
        if ($hasTestPlans -and $seatType -ceq 'basic') {
            $seatType = 'basic_plus_test'
            $skuId = 'ADO.BASIC_TEST'
        }

        $projectEntitlements = @(Get-FinOpsPropertyValue -InputObject $member -Name 'projectEntitlements' -Default @())
        $nonBoardActivity = $false
        foreach ($projectEntitlement in $projectEntitlements) {
            $permissions = Get-FinOpsPropertyValue -InputObject $projectEntitlement -Name 'projectPermissions' -Default $null
            if ((Get-FinOpsPropertyValue -InputObject $permissions -Name 'hasRepoAccess' -Default $false) -or
                (Get-FinOpsPropertyValue -InputObject $permissions -Name 'hasBuildAccess' -Default $false)) {
                $nonBoardActivity = $true
                break
            }
        }
        $onlyStakeholderActivity = ($projectEntitlements.Count -gt 0) -and (-not $nonBoardActivity)

        [void]$seatRows.Add([pscustomobject][ordered]@{
                principal                 = $principal
                org                       = $Org
                seat_type                 = $seatType
                sku_id                    = $skuId
                last_activity_days        = if ($null -eq $lastActivityDays) { '' } else { [string]$lastActivityDays }
                only_stakeholder_activity = ConvertTo-FinOpsBoolLiteral -Value $onlyStakeholderActivity
                last_test_plan_days       = ''
            })
    }

    $limitsUri = "$adoBase/$Org/_apis/distributedtask/resourcelimits?api-version=7.1"
    $resourceLimits = $null
    try {
        $resourceLimits = Invoke-FinOpsRestRequest -Uri $limitsUri -Auth $Auth -MaxPages $maxPages
    } catch {
        $resourceLimits = $null
    }

    $purchasedParallel = $null
    if ($null -ne $resourceLimits) {
        $items = @()
        if ($resourceLimits -is [System.Collections.IEnumerable] -and -not ($resourceLimits -is [string])) {
            $items = @($resourceLimits)
        } else {
            $valueRows = @(Get-FinOpsPropertyValue -InputObject $resourceLimits -Name 'value' -Default @())
            if ($valueRows.Count -gt 0) {
                $items = $valueRows
            } else {
                $items = @($resourceLimits)
            }
        }
        foreach ($item in $items) {
            if ($null -eq $item) { continue }
            $hosted = Get-FinOpsPropertyValue -InputObject $item -Name 'parallelSmallJobsCount' -Default $null
            if ($null -eq $hosted) {
                $hosted = Get-FinOpsPropertyValue -InputObject $item -Name 'totalCount' -Default $null
            }
            if ($null -ne $hosted -and -not [string]::IsNullOrWhiteSpace([string]$hosted)) {
                try {
                    $purchasedParallel = [int][string]$hosted
                    break
                } catch {
                    continue
                }
            }
        }
    }

    $p95Concurrent = Get-FinOpsAdoP95ConcurrentJob
    $orgRows = @(
        [pscustomobject][ordered]@{
            org                     = $Org
            purchased_parallel_jobs = if ($null -eq $purchasedParallel) { '' } else { [string]$purchasedParallel }
            p95_concurrent_jobs     = if ($null -eq $p95Concurrent) { '' } else { [string]$p95Concurrent }
        }
    )

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'ado_seats.csv') -Header @(
        'principal',
        'org',
        'seat_type',
        'sku_id',
        'last_activity_days',
        'only_stakeholder_activity',
        'last_test_plan_days'
    ) -Row @($seatRows.ToArray()) | Out-Null

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'ado_orgs.csv') -Header @(
        'org',
        'purchased_parallel_jobs',
        'p95_concurrent_jobs'
    ) -Row $orgRows | Out-Null

    return [pscustomobject]@{
        FilesWritten = @('ado_seats.csv', 'ado_orgs.csv')
        RowCounts    = [ordered]@{
            ado_seats = @($seatRows.ToArray()).Count
            ado_orgs  = @($orgRows).Count
        }
    }
}
