#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
    $script:ArmFixtureDir = Join-Path $script:RepoRoot 'tests' 'fixtures' 'live_collectors' 'arm'
    $script:ArmInputDir = Join-Path $script:ArmFixtureDir '_input'
    Import-Module $script:ModuleManifest -Force

    Set-Item -Path Function:global:New-TestSecureString -Value {
        param([Parameter(Mandatory)] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) { $secure.AppendChar($char) }
        $secure.MakeReadOnly()
        return $secure
    }

    function script:Get-JsonFixture {
        param([Parameter(Mandatory)] [string] $Name)
        Get-Content -LiteralPath (Join-Path $script:ArmInputDir $Name) -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
    }
}

AfterAll {
    Remove-Item -Path Function:global:New-TestSecureString -ErrorAction SilentlyContinue
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsArmCollector' {
    BeforeEach {
        $script:prevNow = $env:FINOPS_NOW_OVERRIDE
        $env:FINOPS_NOW_OVERRIDE = '2025-06-01'
        $script:OutDir = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $script:OutDir -Force | Out-Null
    }

    Describe 'ARM two-key consent (dispatcher)' {
        It 'without either key it throws the documented consent message' {
            InModuleScope FinOpsAssess {
                { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' } | Should -Throw -ExpectedMessage '*explicit two-key consent*'
            }
        }

        It 'with switch only it throws (env missing)' {
            InModuleScope FinOpsAssess {
                { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' -AcceptArmRbacRisk } | Should -Throw -ExpectedMessage '*FINOPS_ACCEPT_ARM_RBAC_RISK=1*'
            }
        }

        It 'with env only it throws (switch missing)' {
            InModuleScope FinOpsAssess {
                $previous = $env:FINOPS_ACCEPT_ARM_RBAC_RISK
                $env:FINOPS_ACCEPT_ARM_RBAC_RISK = '1'
                try {
                    { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' } | Should -Throw -ExpectedMessage '*pass -AcceptArmRbacRisk*'
                } finally {
                    if ($null -eq $previous) { Remove-Item Env:FINOPS_ACCEPT_ARM_RBAC_RISK -ErrorAction SilentlyContinue }
                    else { $env:FINOPS_ACCEPT_ARM_RBAC_RISK = $previous }
                }
            }
        }
    }

    AfterEach {
        if ($null -eq $script:prevNow) { Remove-Item Env:FINOPS_NOW_OVERRIDE -ErrorAction SilentlyContinue }
        else { $env:FINOPS_NOW_OVERRIDE = $script:prevNow }
    }

    It 'enumerates subscriptions and maps VM/disk/public-IP rows' {
        $subscriptions = script:Get-JsonFixture -Name 'subscriptions.json'
        $vms = script:Get-JsonFixture -Name 'vms.json'
        $disks = script:Get-JsonFixture -Name 'disks.json'
        $publicIps = script:Get-JsonFixture -Name 'public_ips.json'
        $workspace = script:Get-JsonFixture -Name 'workspaces.json'
        $workspaceUsage = script:Get-JsonFixture -Name 'workspace_usages.json'
        $metricsCpu = script:Get-JsonFixture -Name 'metrics-cpu.json'
        $metricsNet = script:Get-JsonFixture -Name 'metrics-net.json'
        $reservations = script:Get-JsonFixture -Name 'reservations.json'
        $benefits = script:Get-JsonFixture -Name 'benefit_recommendations.json'

        InModuleScope FinOpsAssess -Parameters @{
            OutDir = $script:OutDir
            Subscriptions = $subscriptions
            Vms = $vms
            Disks = $disks
            PublicIps = $publicIps
            Workspace = $workspace
            WorkspaceUsage = $workspaceUsage
            MetricsCpu = $metricsCpu
            MetricsNet = $metricsNet
            Reservations = $reservations
            Benefits = $benefits
        } {
            param($OutDir, $Subscriptions, $Vms, $Disks, $PublicIps, $Workspace, $WorkspaceUsage, $MetricsCpu, $MetricsNet, $Reservations, $Benefits)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $null = $Subscriptions, $Vms, $Disks, $PublicIps, $Workspace, $WorkspaceUsage, $MetricsCpu, $MetricsNet, $Reservations, $Benefits
            $restCalls = [System.Collections.Generic.List[object]]::new()

            Mock Invoke-FinOpsRestRequest {
                param($Uri, $Auth, $Paging, $ValueProperty, $MaxPages)
                $null = $Auth
                $restCalls.Add([pscustomobject]@{
                        Uri = $Uri
                        Paging = $Paging
                        ValueProperty = $ValueProperty
                        MaxPages = $MaxPages
                    }) | Out-Null
                if ($Uri -like '*subscriptions?api-version=*') { return @($Subscriptions.value) }
                if ($Uri -like '*virtualMachines?api-version=*') { return @($Vms.value) }
                if ($Uri -like '*disks?api-version=*') { return @($Disks.value) }
                if ($Uri -like '*publicIPAddresses?api-version=*') { return @($PublicIps.value) }
                if ($Uri -like '*workspaces?api-version=*') { return @($Workspace.value) }
                if ($Uri -like '*workspaces/*/usages?api-version=*') { return $WorkspaceUsage }
                if ($Uri -like '*providers/microsoft.insights/metrics*') {
                    return [pscustomobject]@{ value = @($MetricsCpu.value + $MetricsNet.value) }
                }
                if ($Uri -like '*providers/Microsoft.Capacity/reservations*') { return @($Reservations.value) }
                if ($Uri -like '*benefitRecommendations?api-version=*') { return @($Benefits.value) }
                throw "unexpected uri: $Uri"
            }
            Mock Invoke-RestMethod { [pscustomobject]@{ Items = @() } }

            $result = Get-FinOpsArmCollector -OutputPath $OutDir -Auth $auth -PageLimit 321
            $result.RowCounts.azure_resources | Should -Be 3
            $result.RowCounts.azure_reservations | Should -Be 1
            $result.RowCounts.azure_log_workspaces | Should -Be 1
            $result.RowCounts.azure_benefit_recommendations | Should -Be 1

            ($restCalls | Where-Object { $_.Uri -like '*subscriptions?*' })[0].Paging | Should -Be 'ArmNextLink'
            ($restCalls | Where-Object { $_.Uri -like '*subscriptions?*' })[0].ValueProperty | Should -Be 'value'
            ($restCalls | Where-Object { $_.Uri -like '*subscriptions?*' })[0].MaxPages | Should -Be 321

            $resourcesCsv = Get-Content -LiteralPath (Join-Path $OutDir 'azure_resources.csv') -Raw -Encoding utf8
            $resourcesCsv | Should -Match 'virtualMachine,Standard_D4s_v5,eastus,25,40,,0'
            $resourcesCsv | Should -Match 'managedDisk,Premium_LRS,eastus,,,,,517,false,'
            $resourcesCsv | Should -Match 'publicIp,Standard,eastus,,,,,,,false'
        }
    }

    It 'supports -SkipMetrics by leaving metric columns blank' {
        $vms = script:Get-JsonFixture -Name 'vms.json'
        $disks = script:Get-JsonFixture -Name 'disks.json'
        $publicIps = script:Get-JsonFixture -Name 'public_ips.json'
        $workspaces = script:Get-JsonFixture -Name 'workspaces.json'
        $workspaceUsage = script:Get-JsonFixture -Name 'workspace_usages.json'
        $reservations = script:Get-JsonFixture -Name 'reservations.json'
        $benefits = script:Get-JsonFixture -Name 'benefit_recommendations.json'
        InModuleScope FinOpsAssess -Parameters @{
            OutDir = $script:OutDir
            Vms = $vms
            Disks = $disks
            PublicIps = $publicIps
            Workspaces = $workspaces
            WorkspaceUsage = $workspaceUsage
            Reservations = $reservations
            Benefits = $benefits
        } {
            param($OutDir, $Vms, $Disks, $PublicIps, $Workspaces, $WorkspaceUsage, $Reservations, $Benefits)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $null = $Vms, $Disks, $PublicIps, $Workspaces, $WorkspaceUsage, $Reservations, $Benefits
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*virtualMachines?api-version=*') { return @($Vms.value) }
                if ($Uri -like '*disks?api-version=*') { return @($Disks.value) }
                if ($Uri -like '*publicIPAddresses?api-version=*') { return @($PublicIps.value) }
                if ($Uri -like '*workspaces?api-version=*') { return @($Workspaces.value) }
                if ($Uri -like '*workspaces/*/usages?api-version=*') { return $WorkspaceUsage }
                if ($Uri -like '*providers/Microsoft.Capacity/reservations*') { return @($Reservations.value) }
                if ($Uri -like '*benefitRecommendations?api-version=*') { return @($Benefits.value) }
                if ($Uri -like '*providers/microsoft.insights/metrics*') { throw 'metrics should be skipped' }
                return @([pscustomobject]@{ subscriptionId = 'sub-1'; state = 'Enabled' })
            }
            Mock Invoke-RestMethod { [pscustomobject]@{ Items = @() } }

            Get-FinOpsArmCollector -OutputPath $OutDir -Auth $auth -SkipMetrics | Out-Null
            $resourcesCsv = Get-Content -LiteralPath (Join-Path $OutDir 'azure_resources.csv') -Raw -Encoding utf8
            $resourcesCsv | Should -Match 'virtualMachine,Standard_D4s_v5,eastus,,,,,,,,,,sub-1'
        }
    }

    It 'writes lowercase boolean literals for attached/associated/auto_renew' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*subscriptions?api-version=*') { return @([pscustomobject]@{ subscriptionId = 'sub-1'; state = 'Enabled' }) }
                if ($Uri -like '*virtualMachines?api-version=*') { return @() }
                if ($Uri -like '*disks?api-version=*') {
                    return @([pscustomobject]@{
                            id = '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk1'
                            location = 'eastus'
                            sku = [pscustomobject]@{ name = 'Premium_LRS' }
                            properties = [pscustomobject]@{ diskState = 'Unattached'; timeCreated = '2024-01-01T00:00:00Z' }
                        })
                }
                if ($Uri -like '*publicIPAddresses?api-version=*') {
                    return @([pscustomobject]@{
                            id = '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/p1'
                            location = 'eastus'
                            sku = [pscustomobject]@{ name = 'Standard' }
                            properties = [pscustomobject]@{}
                        })
                }
                if ($Uri -like '*workspaces?api-version=*') { return @() }
                if ($Uri -like '*benefitRecommendations?api-version=*') { return @() }
                if ($Uri -like '*providers/Microsoft.Capacity/reservations*') {
                    return @([pscustomobject]@{
                            id = '/providers/Microsoft.Capacity/reservations/res-1'
                            sku = [pscustomobject]@{ name = 's' }
                            properties = [pscustomobject]@{ displayProvisioningState = 'Succeeded'; renew = $true }
                        })
                }
                return [pscustomobject]@{ value = @() }
            }
            Mock Invoke-RestMethod { [pscustomobject]@{ Items = @() } }

            Get-FinOpsArmCollector -OutputPath $OutDir -Auth $auth -SkipMetrics | Out-Null
            $resourcesRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'azure_resources.csv'), [System.Text.Encoding]::UTF8)
            $reservationsRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'azure_reservations.csv'), [System.Text.Encoding]::UTF8)
            $resourcesRaw | Should -Match ',false,'
            $resourcesRaw | Should -Match ',publicIp,.*,(true|false),'
            [regex]::IsMatch($resourcesRaw, ',False,') | Should -BeFalse
            [regex]::IsMatch($resourcesRaw, ',True,') | Should -BeFalse
            $reservationsRaw | Should -Match ',true,'
            [regex]::IsMatch($reservationsRaw, ',True,') | Should -BeFalse
        }
    }

    It 'calls Retail Prices anonymously (no Authorization header)' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $script:headersSeen = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*subscriptions?api-version=*') { return @([pscustomobject]@{ subscriptionId = 'sub-1'; state = 'Enabled' }) }
                if ($Uri -like '*workspaces?api-version=*') {
                    return @([pscustomobject]@{
                            id = '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.OperationalInsights/workspaces/ws1'
                            name = 'ws1'
                            location = 'eastus'
                            properties = [pscustomobject]@{ sku = [pscustomobject]@{ name = 'PerGB2018' } }
                        })
                }
                if ($Uri -like '*workspaces/*/usages?api-version=*') {
                    return [pscustomobject]@{
                        value = @([pscustomobject]@{ name = [pscustomobject]@{ value = 'DataIngestion' }; currentValue = 122880 })
                    }
                }
                if ($Uri -like '*providers/Microsoft.Capacity/reservations*') { return @() }
                return @()
            }
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers)
                $null = $Method, $Uri
                $script:headersSeen.Add($Headers) | Out-Null
                [pscustomobject]@{ Items = @() }
            }

            Get-FinOpsArmCollector -OutputPath $OutDir -Auth $auth -SkipMetrics | Out-Null
            $script:headersSeen.Count | Should -BeGreaterThan 0
            foreach ($h in $script:headersSeen) {
                if ($h -is [System.Collections.IDictionary]) {
                    $h.Contains('Authorization') | Should -BeFalse
                } else {
                    $h | Should -BeNullOrEmpty
                }
            }
        }
    }

    It 'matches Python ARM fixtures at normalized dataset level with recorded inputs' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir; InputDir = $script:ArmInputDir; FixtureDir = $script:ArmFixtureDir } {
            param($OutDir, $InputDir, $FixtureDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $subscriptions = Get-Content -LiteralPath (Join-Path $InputDir 'subscriptions.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $vms = Get-Content -LiteralPath (Join-Path $InputDir 'vms.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $disks = Get-Content -LiteralPath (Join-Path $InputDir 'disks.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $publicIps = Get-Content -LiteralPath (Join-Path $InputDir 'public_ips.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $reservations = Get-Content -LiteralPath (Join-Path $InputDir 'reservations.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $benefits = Get-Content -LiteralPath (Join-Path $InputDir 'benefit_recommendations.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $workspaces = Get-Content -LiteralPath (Join-Path $InputDir 'workspaces.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $workspaceUsages = Get-Content -LiteralPath (Join-Path $InputDir 'workspace_usages.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $metricsCpu = Get-Content -LiteralPath (Join-Path $InputDir 'metrics-cpu.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $metricsNet = Get-Content -LiteralPath (Join-Path $InputDir 'metrics-net.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $retail = Get-Content -LiteralPath (Join-Path $InputDir 'retail-prices.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50

            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*subscriptions?api-version=*') { return @($subscriptions.value) }
                if ($Uri -like '*virtualMachines?api-version=*') { return @($vms.value) }
                if ($Uri -like '*disks?api-version=*') { return @($disks.value) }
                if ($Uri -like '*publicIPAddresses?api-version=*') { return @($publicIps.value) }
                if ($Uri -like '*providers/Microsoft.Capacity/reservations*') { return @($reservations.value) }
                if ($Uri -like '*benefitRecommendations?api-version=*') { return @($benefits.value) }
                if ($Uri -like '*workspaces?api-version=*') { return @($workspaces.value) }
                if ($Uri -like '*workspaces/*/usages?api-version=*') { return $workspaceUsages }
                if ($Uri -like '*providers/microsoft.insights/metrics*') {
                    return [pscustomobject]@{ value = @($metricsCpu.value + $metricsNet.value) }
                }
                throw "unexpected uri: $Uri"
            }
            Mock Invoke-RestMethod { $retail }

            Get-FinOpsArmCollector -OutputPath $OutDir -Auth $auth | Out-Null
            $actual = Get-FinOpsNormalizedDataset -InputDirectory $OutDir
            $expected = Get-FinOpsNormalizedDataset -InputDirectory $FixtureDir

            $actualResources = @($actual.azure_resources | Sort-Object resource_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        resource_id = $_.resource_id
                        resource_type = $_.resource_type
                        sku = $_.sku
                        location = $_.location
                        avg_cpu_pct = $_.avg_cpu_pct
                        p95_cpu_pct = $_.p95_cpu_pct
                        p95_mem_pct = $_.p95_mem_pct
                        avg_net_kbps = $_.avg_net_kbps
                        days_inactive = $_.days_inactive
                        attached = $_.attached
                        associated = $_.associated
                        monthly_cost_usd = $_.monthly_cost_usd
                        recommended_sku = $_.recommended_sku
                        subscription_id = $_.subscription_id
                        subscription_offer = $_.subscription_offer
                        env_tag = $_.env_tag
                        os_type = $_.os_type
                        license_type = $_.license_type
                    }
                })
            $expectedResources = @($expected.azure_resources | Sort-Object resource_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        resource_id = $_.resource_id
                        resource_type = $_.resource_type
                        sku = $_.sku
                        location = $_.location
                        avg_cpu_pct = $_.avg_cpu_pct
                        p95_cpu_pct = $_.p95_cpu_pct
                        p95_mem_pct = $_.p95_mem_pct
                        avg_net_kbps = $_.avg_net_kbps
                        days_inactive = $_.days_inactive
                        attached = $_.attached
                        associated = $_.associated
                        monthly_cost_usd = $_.monthly_cost_usd
                        recommended_sku = $_.recommended_sku
                        subscription_id = $_.subscription_id
                        subscription_offer = $_.subscription_offer
                        env_tag = $_.env_tag
                        os_type = $_.os_type
                        license_type = $_.license_type
                    }
                })

            $actualReservations = @($actual.azure_reservations | Sort-Object reservation_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        reservation_id = $_.reservation_id
                        reservation_name = $_.reservation_name
                        sku = $_.sku
                        scope = $_.scope
                        utilization_pct = $_.utilization_pct
                        monthly_cost_usd = $_.monthly_cost_usd
                        expiry_date = $_.expiry_date
                        auto_renew = $_.auto_renew
                        applied_scope_subscription_ids = $_.applied_scope_subscription_ids
                    }
                })
            $expectedReservations = @($expected.azure_reservations | Sort-Object reservation_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        reservation_id = $_.reservation_id
                        reservation_name = $_.reservation_name
                        sku = $_.sku
                        scope = $_.scope
                        utilization_pct = $_.utilization_pct
                        monthly_cost_usd = $_.monthly_cost_usd
                        expiry_date = $_.expiry_date
                        auto_renew = $_.auto_renew
                        applied_scope_subscription_ids = $_.applied_scope_subscription_ids
                    }
                })

            $actualWorkspaces = @($actual.azure_log_workspaces | Sort-Object workspace_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        workspace_id = $_.workspace_id
                        workspace_name = $_.workspace_name
                        daily_gb = $_.daily_gb
                        commitment_tier_gb = $_.commitment_tier_gb
                        recommended_tier = $_.recommended_tier
                        est_savings_pct = $_.est_savings_pct
                        monthly_cost_usd = $_.monthly_cost_usd
                    }
                })
            $expectedWorkspaces = @($expected.azure_log_workspaces | Sort-Object workspace_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        workspace_id = $_.workspace_id
                        workspace_name = $_.workspace_name
                        daily_gb = $_.daily_gb
                        commitment_tier_gb = $_.commitment_tier_gb
                        recommended_tier = $_.recommended_tier
                        est_savings_pct = $_.est_savings_pct
                        monthly_cost_usd = $_.monthly_cost_usd
                    }
                })

            $actualBenefits = @($actual.azure_benefit_recommendations | Sort-Object recommendation_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        recommendation_id = $_.recommendation_id
                        scope = $_.scope
                        scope_kind = $_.scope_kind
                        term = $_.term
                        lookback_period = $_.lookback_period
                        arm_sku_name = $_.arm_sku_name
                        cost_without_benefit_usd = $_.cost_without_benefit_usd
                        recommended_hourly_commit_usd = $_.recommended_hourly_commit_usd
                        net_savings_usd = $_.net_savings_usd
                        wastage_usd = $_.wastage_usd
                        benefit_kind = $_.benefit_kind
                    }
                })
            $expectedBenefits = @($expected.azure_benefit_recommendations | Sort-Object recommendation_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        recommendation_id = $_.recommendation_id
                        scope = $_.scope
                        scope_kind = $_.scope_kind
                        term = $_.term
                        lookback_period = $_.lookback_period
                        arm_sku_name = $_.arm_sku_name
                        cost_without_benefit_usd = $_.cost_without_benefit_usd
                        recommended_hourly_commit_usd = $_.recommended_hourly_commit_usd
                        net_savings_usd = $_.net_savings_usd
                        wastage_usd = $_.wastage_usd
                        benefit_kind = $_.benefit_kind
                    }
                })

            ($actualResources | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedResources | ConvertTo-Json -Depth 8 -Compress)
            ($actualReservations | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedReservations | ConvertTo-Json -Depth 8 -Compress)
            ($actualWorkspaces | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedWorkspaces | ConvertTo-Json -Depth 8 -Compress)
            ($actualBenefits | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedBenefits | ConvertTo-Json -Depth 8 -Compress)
        }
    }
}
