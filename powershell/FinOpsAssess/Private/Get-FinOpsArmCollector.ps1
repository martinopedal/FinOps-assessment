function Get-FinOpsArmCollector {
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [pscustomobject] $Auth,

        [Parameter()]
        [string[]] $SubscriptionId,

        [switch] $SkipMetrics,

        [Parameter()]
        [int] $PageLimit = 500,

        [switch] $AcceptArmRbacRisk
    )

    $null = $AcceptArmRbacRisk, $Auth, $SkipMetrics
    $armBase = 'https://management.azure.com'
    $retailBase = 'https://prices.azure.com/api/retail/prices'
    $api = @{
        subscriptions = '2022-12-01'
        virtualMachines = '2023-09-01'
        disks = '2023-10-02'
        publicIPAddresses = '2023-11-01'
        reservations = '2022-11-01'
        benefitRecommendations = '2022-10-01'
        workspaces = '2023-09-01'
        workspaceUsages = '2020-08-01'
        metrics = '2023-10-01'
    }
    $maxPages = if ($PageLimit -gt 0) { $PageLimit } else { 500 }
    $now = Get-FinOpsNow
    $inv = [System.Globalization.CultureInfo]::InvariantCulture

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

    function ConvertTo-FinOpsRounded {
        param(
            [Parameter()] [AllowNull()] [object] $Value,
            [Parameter(Mandatory)] [int] $Digits
        )
        if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return '' }
        try {
            $number = [double]::Parse([string]$Value, $inv)
            return ([Math]::Round($number, $Digits, [System.MidpointRounding]::ToEven)).ToString($inv)
        } catch {
            return ''
        }
    }

    function ConvertTo-FinOpsBoolLiteral {
        param([Parameter()] [AllowNull()] [object] $Value)
        if ($Value -eq $true) { return 'true' }
        if ($Value -eq $false) { return 'false' }
        return ''
    }

    function Get-FinOpsMetricsPercentile95 {
        param([Parameter()] [double[]] $Values)
        if (-not $Values -or $Values.Count -eq 0) { return $null }
        $sorted = @($Values | Sort-Object)
        $idx = [int]($sorted.Count * 0.95)
        return $sorted[[Math]::Min($idx, $sorted.Count - 1)]
    }

    function Get-FinOpsMetricsAverage {
        param([Parameter()] [double[]] $Values)
        if (-not $Values -or $Values.Count -eq 0) { return $null }
        $sum = 0.0
        foreach ($v in $Values) { $sum += [double]$v }
        return ($sum / $Values.Count)
    }

    function Get-FinOpsArmDataset {
        param([Parameter(Mandatory)] [string] $Uri)
        $rows = Invoke-FinOpsRestRequest -Uri $Uri -Auth $Auth -Paging ArmNextLink -ValueProperty 'value' -MaxPages $maxPages
        return @($rows)
    }

    function Get-FinOpsArmBody {
        param([Parameter(Mandatory)] [string] $Uri)
        return Invoke-FinOpsRestRequest -Uri $Uri -Auth $Auth -MaxPages $maxPages
    }

    function Get-FinOpsMetricWindow {
        $end = $now
        $start = $now.AddDays(-14)
        return [pscustomobject]@{
            Start = $start.ToString('yyyy-MM-ddTHH:mm:ssZ', $inv)
            End = $end.ToString('yyyy-MM-ddTHH:mm:ssZ', $inv)
        }
    }

    function Get-FinOpsVmMetric {
        param([Parameter(Mandatory)] [string] $ResourceId)
        if ($SkipMetrics) {
            return @{ avg_cpu_pct = $null; p95_cpu_pct = $null; p95_mem_pct = $null; avg_net_kbps = $null }
        }

        $window = Get-FinOpsMetricWindow
        $metricNames = [System.Uri]::EscapeDataString('Percentage CPU,Network In Total,Network Out Total')
        $aggregation = [System.Uri]::EscapeDataString('Average,Percentile')
        $timespan = [System.Uri]::EscapeDataString("$($window.Start)/$($window.End)")
        $uri = "$armBase$ResourceId/providers/microsoft.insights/metrics?api-version=$($api.metrics)&timespan=$timespan&interval=PT1H&metricnames=$metricNames&aggregation=$aggregation&percentile=95&`$top=3"

        try {
            $body = Get-FinOpsArmBody -Uri $uri
        } catch {
            return @{ avg_cpu_pct = $null; p95_cpu_pct = $null; p95_mem_pct = $null; avg_net_kbps = $null }
        }

        $metricMap = @{}
        foreach ($metric in @((Get-FinOpsPropertyValue -InputObject $body -Name 'value' -Default @()))) {
            $metricNameRaw = [string](Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $metric -Name 'name' -Default $null) -Name 'value' -Default '')
            $metricName = $metricNameRaw.ToLowerInvariant().Replace(' ', '')
            $points = [System.Collections.Generic.List[double]]::new()
            foreach ($series in @((Get-FinOpsPropertyValue -InputObject $metric -Name 'timeseries' -Default @()))) {
                foreach ($dp in @((Get-FinOpsPropertyValue -InputObject $series -Name 'data' -Default @()))) {
                    $avg = Get-FinOpsPropertyValue -InputObject $dp -Name 'average'
                    if ($null -ne $avg) {
                        try {
                            [void]$points.Add([double]::Parse([string]$avg, $inv))
                        } catch {
                            Write-Verbose "Skipping non-numeric metric value '$avg' for $ResourceId."
                        }
                    }
                }
            }
            if ($points.Count -gt 0) {
                $metricMap[$metricName] = @($points.ToArray())
            }
        }

        $cpu = if ($metricMap.ContainsKey('percentagecpu')) { @($metricMap['percentagecpu']) } else { @() }
        $netIn = if ($metricMap.ContainsKey('networkingtotal')) { @($metricMap['networkingtotal']) } elseif ($metricMap.ContainsKey('networkintotal')) { @($metricMap['networkintotal']) } else { @() }
        $netOut = if ($metricMap.ContainsKey('networkouttotal')) { @($metricMap['networkouttotal']) } else { @() }

        $netCombined = [System.Collections.Generic.List[double]]::new()
        if ($netIn.Count -gt 0 -and $netOut.Count -gt 0) {
            $limit = [Math]::Min($netIn.Count, $netOut.Count)
            for ($i = 0; $i -lt $limit; $i++) {
                [void]$netCombined.Add(([double]$netIn[$i] + [double]$netOut[$i]))
            }
        } elseif ($netIn.Count -gt 0) {
            foreach ($v in $netIn) { [void]$netCombined.Add([double]$v) }
        } else {
            foreach ($v in $netOut) { [void]$netCombined.Add([double]$v) }
        }

        $netKbps = @($netCombined.ToArray() | ForEach-Object { ([double]$_ / 3600 / 1024) })
        return @{
            avg_cpu_pct = Get-FinOpsMetricsAverage -Values $cpu
            p95_cpu_pct = Get-FinOpsMetricsPercentile95 -Values $cpu
            p95_mem_pct = $null
            avg_net_kbps = Get-FinOpsMetricsAverage -Values $netKbps
        }
    }

    function Get-FinOpsWorkspaceUsage {
        param([Parameter(Mandatory)] [string] $WorkspaceId)
        $uri = "$armBase$WorkspaceId/usages?api-version=$($api.workspaceUsages)"
        try {
            $body = Get-FinOpsArmBody -Uri $uri
            foreach ($item in @((Get-FinOpsPropertyValue -InputObject $body -Name 'value' -Default @()))) {
                $nameValue = [string](Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $item -Name 'name' -Default $null) -Name 'value' -Default '')
                if ($nameValue.ToLowerInvariant() -ceq 'dataingestion') {
                    $currentValue = Get-FinOpsPropertyValue -InputObject $item -Name 'currentValue'
                    if ($null -ne $currentValue) {
                        $gb = [Math]::Round(([double]::Parse([string]$currentValue, $inv) / 1024), 3, [System.MidpointRounding]::ToEven)
                        return $gb
                    }
                }
            }
        } catch {
            return $null
        }
        return $null
    }

    function Get-FinOpsRecommendedLaTier {
        param([Parameter(Mandatory)] [double] $DailyGb)
        if ($DailyGb -lt 10.0) {
            return [pscustomobject]@{ Tier = $null; SavingsPct = $null }
        }
        $tiers = @(
            @{ Threshold = 100.0; Tier = '100gb_per_day_commitment' },
            @{ Threshold = 200.0; Tier = '200gb_per_day_commitment' },
            @{ Threshold = 300.0; Tier = '300gb_per_day_commitment' },
            @{ Threshold = 400.0; Tier = '400gb_per_day_commitment' },
            @{ Threshold = 500.0; Tier = '500gb_per_day_commitment' }
        )
        foreach ($entry in $tiers) {
            if ($DailyGb -le $entry.Threshold) {
                return [pscustomobject]@{ Tier = $entry.Tier; SavingsPct = 15.0 }
            }
        }
        return [pscustomobject]@{ Tier = '500gb_per_day_commitment'; SavingsPct = 15.0 }
    }

    function Get-FinOpsRetailPrice {
        param(
            [Parameter(Mandatory)] [string] $ServiceName,
            [Parameter()] [string] $ArmRegionName,
            [Parameter()] [string] $SkuName
        )
        $filterParts = [System.Collections.Generic.List[string]]::new()
        [void]$filterParts.Add("serviceName eq '$ServiceName'")
        if ($ArmRegionName) { [void]$filterParts.Add("armRegionName eq '$ArmRegionName'") }
        if ($SkuName) { [void]$filterParts.Add("skuName eq '$SkuName'") }
        $filter = [string]::Join(' and ', @($filterParts.ToArray()))
        $uri = "${retailBase}?`$filter=$([System.Uri]::EscapeDataString($filter))"
        try {
            # Retail Prices API is public metadata and intentionally called without Authorization.
            $body = Invoke-RestMethod -Method Get -Uri $uri -ErrorAction Stop
            foreach ($item in @((Get-FinOpsPropertyValue -InputObject $body -Name 'Items' -Default @()))) {
                $price = Get-FinOpsPropertyValue -InputObject $item -Name 'retailPrice'
                if ($null -ne $price) {
                    return [double]::Parse([string]$price, $inv)
                }
            }
        } catch {
            return $null
        }
        return $null
    }

    function Get-FinOpsBenefitScopeArn {
        param(
            [Parameter(Mandatory)] [object] $Recommendation,
            [Parameter(Mandatory)] [string] $SubId
        )
        $props = Get-FinOpsPropertyValue -InputObject $Recommendation -Name 'properties' -Default $null
        $discriminator = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'scope' -Default '')
        if ($discriminator -ceq 'Single') {
            $subFromProps = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'subscriptionId' -Default $SubId)
            $rg = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'resourceGroup' -Default '')
            if ($rg) { return "/subscriptions/$subFromProps/resourceGroups/$rg" }
            return "/subscriptions/$subFromProps"
        }
        if ($discriminator -ceq 'Shared') {
            $rid = [string](Get-FinOpsPropertyValue -InputObject $Recommendation -Name 'id' -Default '')
            $marker = '/providers/Microsoft.CostManagement/'
            if ($rid.Contains($marker)) { return $rid.Split($marker)[0] }
            return "/subscriptions/$SubId"
        }
        return "/subscriptions/$SubId"
    }

    $benefitScopeKinds = [System.Collections.Generic.HashSet[string]]::new([string[]]@('Single', 'Shared'), [System.StringComparer]::Ordinal)
    $benefitTerms = [System.Collections.Generic.HashSet[string]]::new([string[]]@('P1Y', 'P3Y'), [System.StringComparer]::Ordinal)
    $benefitLookbacks = [System.Collections.Generic.HashSet[string]]::new([string[]]@('Last7Days', 'Last30Days', 'Last60Days'), [System.StringComparer]::Ordinal)
    $benefitKinds = [System.Collections.Generic.HashSet[string]]::new([string[]]@('SavingsPlan', 'Reservation'), [System.StringComparer]::Ordinal)

    function ConvertTo-FinOpsBenefitRow {
        param(
            [Parameter(Mandatory)] [object] $Recommendation,
            [Parameter(Mandatory)] [string] $SubId
        )
        $rid = [string](Get-FinOpsPropertyValue -InputObject $Recommendation -Name 'id' -Default '')
        $props = Get-FinOpsPropertyValue -InputObject $Recommendation -Name 'properties' -Default $null
        $scopeKind = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'scope' -Default '')
        $term = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'term' -Default '')
        $lookback = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'lookBackPeriod' -Default '')
        $kind = [string](Get-FinOpsPropertyValue -InputObject $Recommendation -Name 'kind' -Default '')

        if ($scopeKind -and -not $benefitScopeKinds.Contains($scopeKind)) { return $null }
        if ($term -and -not $benefitTerms.Contains($term)) { return $null }
        if ($lookback -and -not $benefitLookbacks.Contains($lookback)) { return $null }
        if ($kind -and -not $benefitKinds.Contains($kind)) { return $null }

        $details = Get-FinOpsPropertyValue -InputObject $props -Name 'recommendationDetails' -Default $null
        return [pscustomobject][ordered]@{
            recommendation_id = $rid
            scope = Get-FinOpsBenefitScopeArn -Recommendation $Recommendation -SubId $SubId
            scope_kind = $scopeKind
            term = $term
            lookback_period = $lookback
            arm_sku_name = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'armSkuName' -Default '')
            cost_without_benefit_usd = [string](Get-FinOpsPropertyValue -InputObject $details -Name 'costWithoutBenefit' -Default '')
            recommended_hourly_commit_usd = [string](Get-FinOpsPropertyValue -InputObject $details -Name 'recommendedQuantity' -Default '')
            net_savings_usd = [string](Get-FinOpsPropertyValue -InputObject $details -Name 'netSavings' -Default '')
            wastage_usd = [string](Get-FinOpsPropertyValue -InputObject $details -Name 'wastage' -Default '')
            benefit_kind = if ($kind) { $kind } else { 'SavingsPlan' }
        }
    }

    $subIds = @($SubscriptionId | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($subIds.Count -eq 0) {
        $subscriptionsUri = "$armBase/subscriptions?api-version=$($api.subscriptions)"
        foreach ($subscription in @(Get-FinOpsArmDataset -Uri $subscriptionsUri)) {
            $state = [string](Get-FinOpsPropertyValue -InputObject $subscription -Name 'state' -Default '')
            $sid = [string](Get-FinOpsPropertyValue -InputObject $subscription -Name 'subscriptionId' -Default '')
            if ($state -ceq 'Enabled' -and $sid) {
                $subIds += $sid
            }
        }
    }

    $resourceRows = [System.Collections.Generic.List[object]]::new()
    $workspaceRows = [System.Collections.Generic.List[object]]::new()
    $reservationRows = [System.Collections.Generic.List[object]]::new()
    $benefitRowsByKey = @{}
    $lookbackPriority = @{ Last60Days = 3; Last30Days = 2; Last7Days = 1 }

    foreach ($subId in $subIds) {
        $vmsUri = "$armBase/subscriptions/$subId/providers/Microsoft.Compute/virtualMachines?api-version=$($api.virtualMachines)"
        foreach ($vm in @(Get-FinOpsArmDataset -Uri $vmsUri)) {
            $rid = [string](Get-FinOpsPropertyValue -InputObject $vm -Name 'id' -Default '')
            $props = Get-FinOpsPropertyValue -InputObject $vm -Name 'properties' -Default $null
            $hw = Get-FinOpsPropertyValue -InputObject $props -Name 'hardwareProfile' -Default $null
            $storageProfile = Get-FinOpsPropertyValue -InputObject $props -Name 'storageProfile' -Default $null
            $osDisk = Get-FinOpsPropertyValue -InputObject $storageProfile -Name 'osDisk' -Default $null
            $tags = Get-FinOpsPropertyValue -InputObject $vm -Name 'tags' -Default $null
            $envTag = [string](Get-FinOpsPropertyValue -InputObject $tags -Name 'env' -Default '')
            if (-not $envTag) { $envTag = [string](Get-FinOpsPropertyValue -InputObject $tags -Name 'environment' -Default '') }
            if (-not $envTag) { $envTag = [string](Get-FinOpsPropertyValue -InputObject $tags -Name 'Environment' -Default '') }

            $metrics = Get-FinOpsVmMetric -ResourceId $rid

            [void]$resourceRows.Add([pscustomobject][ordered]@{
                    resource_id = $rid
                    resource_type = 'virtualMachine'
                    sku = [string](Get-FinOpsPropertyValue -InputObject $hw -Name 'vmSize' -Default '')
                    location = [string](Get-FinOpsPropertyValue -InputObject $vm -Name 'location' -Default '')
                    avg_cpu_pct = ConvertTo-FinOpsRounded -Value (Get-FinOpsPropertyValue -InputObject $metrics -Name 'avg_cpu_pct') -Digits 2
                    p95_cpu_pct = ConvertTo-FinOpsRounded -Value (Get-FinOpsPropertyValue -InputObject $metrics -Name 'p95_cpu_pct') -Digits 2
                    p95_mem_pct = ConvertTo-FinOpsRounded -Value (Get-FinOpsPropertyValue -InputObject $metrics -Name 'p95_mem_pct') -Digits 2
                    avg_net_kbps = ConvertTo-FinOpsRounded -Value (Get-FinOpsPropertyValue -InputObject $metrics -Name 'avg_net_kbps') -Digits 2
                    days_inactive = ''
                    attached = ''
                    associated = ''
                    monthly_cost_usd = ''
                    recommended_sku = ''
                    subscription_id = $subId
                    subscription_offer = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'subscriptionOffer' -Default '')
                    env_tag = $envTag
                    os_type = [string](Get-FinOpsPropertyValue -InputObject $osDisk -Name 'osType' -Default '')
                    license_type = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'licenseType' -Default '')
                })
        }

        $disksUri = "$armBase/subscriptions/$subId/providers/Microsoft.Compute/disks?api-version=$($api.disks)"
        foreach ($disk in @(Get-FinOpsArmDataset -Uri $disksUri)) {
            $props = Get-FinOpsPropertyValue -InputObject $disk -Name 'properties' -Default $null
            $managedBy = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'managedBy' -Default '')
            $attached = -not [string]::IsNullOrWhiteSpace($managedBy)
            $diskState = ([string](Get-FinOpsPropertyValue -InputObject $props -Name 'diskState' -Default '')).ToLowerInvariant()
            if (-not $attached -or $diskState -ceq 'unattached') {
                $daysInactive = ''
                $timeCreated = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'timeCreated' -Default '')
                if ($timeCreated) {
                    try {
                        $created = [System.DateTimeOffset]::Parse($timeCreated, $inv, [System.Globalization.DateTimeStyles]::AssumeUniversal)
                        $daysInactive = [string][Math]::Max(0, ($now - $created.ToUniversalTime()).Days)
                    } catch {
                        Write-Verbose "Failed to parse disk timeCreated '$timeCreated' for $subId."
                    }
                }
                $sku = Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $disk -Name 'sku' -Default $null) -Name 'name' -Default ''
                [void]$resourceRows.Add([pscustomobject][ordered]@{
                        resource_id = [string](Get-FinOpsPropertyValue -InputObject $disk -Name 'id' -Default '')
                        resource_type = 'managedDisk'
                        sku = [string]$sku
                        location = [string](Get-FinOpsPropertyValue -InputObject $disk -Name 'location' -Default '')
                        avg_cpu_pct = ''
                        p95_cpu_pct = ''
                        p95_mem_pct = ''
                        avg_net_kbps = ''
                        days_inactive = $daysInactive
                        attached = 'false'
                        associated = ''
                        monthly_cost_usd = ''
                        recommended_sku = ''
                        subscription_id = $subId
                        subscription_offer = ''
                        env_tag = ''
                        os_type = ''
                        license_type = ''
                    })
            }
        }

        $pipUri = "$armBase/subscriptions/$subId/providers/Microsoft.Network/publicIPAddresses?api-version=$($api.publicIPAddresses)"
        foreach ($pip in @(Get-FinOpsArmDataset -Uri $pipUri)) {
            $props = Get-FinOpsPropertyValue -InputObject $pip -Name 'properties' -Default $null
            $associated = $null -ne (Get-FinOpsPropertyValue -InputObject $props -Name 'ipConfiguration') -or $null -ne (Get-FinOpsPropertyValue -InputObject $props -Name 'natGateway')
            $sku = Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $pip -Name 'sku' -Default $null) -Name 'name' -Default ''
            [void]$resourceRows.Add([pscustomobject][ordered]@{
                    resource_id = [string](Get-FinOpsPropertyValue -InputObject $pip -Name 'id' -Default '')
                    resource_type = 'publicIp'
                    sku = [string]$sku
                    location = [string](Get-FinOpsPropertyValue -InputObject $pip -Name 'location' -Default '')
                    avg_cpu_pct = ''
                    p95_cpu_pct = ''
                    p95_mem_pct = ''
                    avg_net_kbps = ''
                    days_inactive = ''
                    attached = ''
                    associated = if ($associated) { 'true' } else { 'false' }
                    monthly_cost_usd = ''
                    recommended_sku = ''
                    subscription_id = $subId
                    subscription_offer = ''
                    env_tag = ''
                    os_type = ''
                    license_type = ''
                })
        }

        $workspacesUri = "$armBase/subscriptions/$subId/providers/Microsoft.OperationalInsights/workspaces?api-version=$($api.workspaces)"
        foreach ($workspace in @(Get-FinOpsArmDataset -Uri $workspacesUri)) {
            $workspaceId = [string](Get-FinOpsPropertyValue -InputObject $workspace -Name 'id' -Default '')
            $dailyGb = Get-FinOpsWorkspaceUsage -WorkspaceId $workspaceId
            $recommendation = if ($null -ne $dailyGb) { Get-FinOpsRecommendedLaTier -DailyGb ([double]$dailyGb) } else { [pscustomobject]@{ Tier = $null; SavingsPct = $null } }
            $location = [string](Get-FinOpsPropertyValue -InputObject $workspace -Name 'location' -Default '')
            $skuName = [string](Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $workspace -Name 'properties' -Default $null) -Name 'sku' -Default $null) -Name 'name' -Default '')
            $null = Get-FinOpsRetailPrice -ServiceName 'Azure Monitor' -ArmRegionName $location -SkuName $skuName
            [void]$workspaceRows.Add([pscustomobject][ordered]@{
                    workspace_id = $workspaceId
                    workspace_name = [string](Get-FinOpsPropertyValue -InputObject $workspace -Name 'name' -Default '')
                    daily_gb = if ($null -eq $dailyGb) { '' } else { ([double]$dailyGb).ToString($inv) }
                    commitment_tier_gb = ''
                    recommended_tier = [string](Get-FinOpsPropertyValue -InputObject $recommendation -Name 'Tier' -Default '')
                    est_savings_pct = if ($null -eq (Get-FinOpsPropertyValue -InputObject $recommendation -Name 'SavingsPct')) { '' } else { ([double](Get-FinOpsPropertyValue -InputObject $recommendation -Name 'SavingsPct')).ToString($inv) }
                    monthly_cost_usd = ''
                })
        }

        $benefitsUri = "$armBase/subscriptions/$subId/providers/Microsoft.CostManagement/benefitRecommendations?api-version=$($api.benefitRecommendations)"
        foreach ($rec in @(Get-FinOpsArmDataset -Uri $benefitsUri)) {
            $row = ConvertTo-FinOpsBenefitRow -Recommendation $rec -SubId $subId
            if ($null -eq $row) { continue }
            $scopeVal = [string]$row.scope
            $termVal = [string]$row.term
            $lookback = [string]$row.lookback_period
            $key = "$scopeVal||$termVal"
            $priority = if ($lookbackPriority.ContainsKey($lookback)) { [int]$lookbackPriority[$lookback] } else { 0 }
            if ($benefitRowsByKey.ContainsKey($key)) {
                $existing = $benefitRowsByKey[$key]
                $existingLookback = [string](Get-FinOpsPropertyValue -InputObject $existing -Name 'lookback_period' -Default '')
                $existingPriority = if ($lookbackPriority.ContainsKey($existingLookback)) { [int]$lookbackPriority[$existingLookback] } else { 0 }
                if ($priority -lt $existingPriority) { continue }
                if ($priority -eq $existingPriority) {
                    $existingSavings = 0.0
                    $newSavings = 0.0
                    [double]::TryParse([string](Get-FinOpsPropertyValue -InputObject $existing -Name 'net_savings_usd' -Default '0'), [ref]$existingSavings) | Out-Null
                    [double]::TryParse([string](Get-FinOpsPropertyValue -InputObject $row -Name 'net_savings_usd' -Default '0'), [ref]$newSavings) | Out-Null
                    if ($newSavings -le $existingSavings) { continue }
                }
            }
            $benefitRowsByKey[$key] = $row
        }
    }

    $reservationsUri = "$armBase/providers/Microsoft.Capacity/reservations?api-version=$($api.reservations)"
    foreach ($reservation in @(Get-FinOpsArmDataset -Uri $reservationsUri)) {
        $props = Get-FinOpsPropertyValue -InputObject $reservation -Name 'properties' -Default $null
        $displayState = ([string](Get-FinOpsPropertyValue -InputObject $props -Name 'displayProvisioningState' -Default '')).ToLowerInvariant()
        if ($displayState -and $displayState -cne 'succeeded') { continue }

        $utilizationValue = $null
        $utilization = Get-FinOpsPropertyValue -InputObject $props -Name 'utilization' -Default $null
        foreach ($agg in @((Get-FinOpsPropertyValue -InputObject $utilization -Name 'aggregates' -Default @()))) {
            $grain = ([string](Get-FinOpsPropertyValue -InputObject $agg -Name 'grain' -Default '')).ToLowerInvariant()
            if ($grain -in @('30days', '30d', 'monthly')) {
                $utilizationValue = Get-FinOpsPropertyValue -InputObject $agg -Name 'value'
            }
        }
        if ($null -eq $utilizationValue) {
            $utilizationValue = Get-FinOpsPropertyValue -InputObject $utilization -Name 'onDemandUtilizationPercentage'
        }

        $appliedScopes = Get-FinOpsPropertyValue -InputObject $props -Name 'appliedScopes' -Default $null
        $scopeCell = ''
        if ($appliedScopes -is [System.Collections.IEnumerable] -and -not ($appliedScopes -is [string])) {
            $trimmed = [System.Collections.Generic.List[string]]::new()
            foreach ($s in @($appliedScopes)) {
                $text = [string]$s
                if ($text.Trim()) { [void]$trimmed.Add($text.Trim()) }
            }
            $scopeCell = [string]::Join('|', @($trimmed.ToArray()))
        }
        if (-not $scopeCell -and $subIds.Count -eq 1 -and $subIds[0]) {
            $scopeCell = "/subscriptions/$($subIds[0])"
        }

        [void]$reservationRows.Add([pscustomobject][ordered]@{
                reservation_id = [string](Get-FinOpsPropertyValue -InputObject $reservation -Name 'id' -Default '')
                reservation_name = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'displayName' -Default '')
                sku = [string](Get-FinOpsPropertyValue -InputObject (Get-FinOpsPropertyValue -InputObject $reservation -Name 'sku' -Default $null) -Name 'name' -Default '')
                scope = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'appliedScopeType' -Default '')
                utilization_pct = ConvertTo-FinOpsRounded -Value $utilizationValue -Digits 2
                monthly_cost_usd = ''
                expiry_date = [string](Get-FinOpsPropertyValue -InputObject $props -Name 'expiryDate' -Default '')
                auto_renew = ConvertTo-FinOpsBoolLiteral -Value (Get-FinOpsPropertyValue -InputObject $props -Name 'renew')
                applied_scope_subscription_ids = $scopeCell
            })
    }

    $benefitRows = @($benefitRowsByKey.Values)

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'azure_resources.csv') -Header @(
        'resource_id',
        'resource_type',
        'sku',
        'location',
        'avg_cpu_pct',
        'p95_cpu_pct',
        'p95_mem_pct',
        'avg_net_kbps',
        'days_inactive',
        'attached',
        'associated',
        'monthly_cost_usd',
        'recommended_sku',
        'subscription_id',
        'subscription_offer',
        'env_tag',
        'os_type',
        'license_type'
    ) -Row @($resourceRows.ToArray()) | Out-Null

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'azure_reservations.csv') -Header @(
        'reservation_id',
        'reservation_name',
        'sku',
        'scope',
        'utilization_pct',
        'monthly_cost_usd',
        'expiry_date',
        'auto_renew',
        'applied_scope_subscription_ids'
    ) -Row @($reservationRows.ToArray()) | Out-Null

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'azure_log_workspaces.csv') -Header @(
        'workspace_id',
        'workspace_name',
        'daily_gb',
        'commitment_tier_gb',
        'recommended_tier',
        'est_savings_pct',
        'monthly_cost_usd'
    ) -Row @($workspaceRows.ToArray()) | Out-Null

    Write-FinOpsCollectorCsv -Path (Join-Path $OutputPath 'azure_benefit_recommendations.csv') -Header @(
        'recommendation_id',
        'scope',
        'scope_kind',
        'term',
        'lookback_period',
        'arm_sku_name',
        'cost_without_benefit_usd',
        'recommended_hourly_commit_usd',
        'net_savings_usd',
        'wastage_usd',
        'benefit_kind'
    ) -Row @($benefitRows) | Out-Null

    return [pscustomobject]@{
        FilesWritten = @(
            'azure_resources.csv',
            'azure_reservations.csv',
            'azure_log_workspaces.csv',
            'azure_benefit_recommendations.csv'
        )
        RowCounts = [ordered]@{
            azure_resources = @($resourceRows.ToArray()).Count
            azure_reservations = @($reservationRows.ToArray()).Count
            azure_log_workspaces = @($workspaceRows.ToArray()).Count
            azure_benefit_recommendations = @($benefitRows).Count
        }
    }
}

