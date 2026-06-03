#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
    $script:GraphFixtureDir = Join-Path $script:RepoRoot 'tests' 'fixtures' 'live_collectors' 'graph'
    $script:GraphInputDir = Join-Path $script:GraphFixtureDir '_input'
    Import-Module $script:ModuleManifest -Force

    Set-Item -Path Function:global:New-TestSecureString -Value {
        param([Parameter(Mandatory)] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) { $secure.AppendChar($char) }
        $secure.MakeReadOnly()
        return $secure
    }

    Set-Item -Path Function:global:New-TestJwt -Value {
        param([Parameter(Mandatory)] [hashtable] $Claims)
        $enc = {
            param($obj)
            $json = $obj | ConvertTo-Json -Compress -Depth 10
            $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
            $b64.TrimEnd('=').Replace('+', '-').Replace('/', '_')
        }
        $header = & $enc @{ alg = 'none'; typ = 'JWT' }
        $payload = & $enc $Claims
        "$header.$payload.sig"
    }
}

AfterAll {
    Remove-Item -Path Function:global:New-TestSecureString -ErrorAction SilentlyContinue
    Remove-Item -Path Function:global:New-TestJwt -ErrorAction SilentlyContinue
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsGraphCollector' {
    BeforeEach {
        $script:prevNow = $env:FINOPS_NOW_OVERRIDE
        $env:FINOPS_NOW_OVERRIDE = '2025-06-01'
        $script:OutDir = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $script:OutDir -Force | Out-Null
    }

    AfterEach {
        if ($null -eq $script:prevNow) { Remove-Item Env:FINOPS_NOW_OVERRIDE -ErrorAction SilentlyContinue }
        else { $env:FINOPS_NOW_OVERRIDE = $script:prevNow }
    }

    It 'requests users with Graph paging and ConsistencyLevel eventual and merges mapped rows' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-FinOpsRestRequest {
                param($Uri, $Method, $Auth, $Headers, $Paging, $ValueProperty, $MaxPages)
                $null = $Method, $Auth
                $calls.Add([pscustomobject]@{
                        Uri           = $Uri
                        Paging        = $Paging
                        ValueProperty = $ValueProperty
                        Headers       = $Headers
                        MaxPages      = $MaxPages
                    }) | Out-Null
                if ($Uri -like '*users?*') {
                    return @(
                        [pscustomobject]@{
                            userPrincipalName = 'alice@contoso.test'
                            displayName       = 'Alice'
                            userType          = 'Member'
                            accountEnabled    = $true
                            jobTitle          = 'Engineer'
                            department        = 'Engineering'
                            assignedLicenses  = @([pscustomobject]@{ skuId = '6fd2c87f-b296-42f0-b197-1e91e994b900' })
                            signInActivity    = [pscustomobject]@{ lastSignInDateTime = '2025-05-30T00:00:00Z' }
                        },
                        [pscustomobject]@{
                            userPrincipalName = 'guest@contoso.test'
                            displayName       = 'Guest'
                            userType          = 'Guest'
                            accountEnabled    = $false
                            assignedLicenses  = @()
                            signInActivity    = [pscustomobject]@{ lastSignInDateTime = '2025-05-10T00:00:00Z' }
                        }
                    )
                }
                if ($Uri -like '*getMailboxUsageDetail*') {
                    return "User Principal Name,Storage Used (Byte)`nalice@contoso.test,2147483648`n"
                }
                if ($Uri -like '*getOffice365ActiveUserDetail*') {
                    return "User Principal Name,Exchange,SharePoint,Teams`nalice@contoso.test,Yes,No,Yes`n"
                }
                if ($Uri -like '*getMicrosoft365CopilotUsageSummary*') {
                    return "User Principal Name,Copilot Active`nalice@contoso.test,1`nguest@contoso.test,0`n"
                }
                throw "unexpected uri: $Uri"
            }

            $result = Get-FinOpsGraphCollector -OutputPath $OutDir -Auth $auth -PageLimit 321
            $result.RowCounts.users | Should -Be 2
            $result.RowCounts.license_assignments | Should -Be 1
            $result.RowCounts.usage | Should -Be 8

            $usersCall = @($calls.ToArray() | Where-Object { $_.Uri -like '*users?*' })[0]
            $usersCall.Paging | Should -Be 'GraphODataNext'
            $usersCall.ValueProperty | Should -Be 'value'
            $usersCall.Headers.ConsistencyLevel | Should -Be 'eventual'
            $usersCall.MaxPages | Should -Be 321

            $usersCsv = Get-Content -LiteralPath (Join-Path $OutDir 'users.csv') -Raw -Encoding utf8
            $usersCsv | Should -Match 'alice@contoso\.test,Alice,member,true,Engineer,Engineering,2,2'
            $usersCsv | Should -Match 'guest@contoso\.test,Guest,guest,false,,,.*,22'

            $assignCsv = Get-Content -LiteralPath (Join-Path $OutDir 'license_assignments.csv') -Raw -Encoding utf8
            $assignCsv | Should -Match 'alice@contoso\.test,6FD2C87F-B296-42F0-B197-1E91E994B900'

            $usageCsv = Get-Content -LiteralPath (Join-Path $OutDir 'usage.csv') -Raw -Encoding utf8
            $usageCsv | Should -Match 'alice@contoso\.test,exchange,0'
            $usageCsv | Should -Match 'guest@contoso\.test,exchange,22'
            $usageCsv | Should -Match 'guest@contoso\.test,copilot,61'
        }
    }

    It 'falls back safely when optional report endpoints fail' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*users?*') {
                    return @(
                        [pscustomobject]@{
                            userPrincipalName = 'svc@contoso.test'
                            displayName       = 'Svc'
                            userType          = 'UnknownType'
                            accountEnabled    = $false
                            assignedLicenses  = @()
                            signInActivity    = [pscustomobject]@{ lastSignInDateTime = '2025-05-31T00:00:00Z' }
                        }
                    )
                }
                throw '404'
            }

            { Get-FinOpsGraphCollector -OutputPath $OutDir -Auth $auth } | Should -Not -Throw
            $usersCsv = Get-Content -LiteralPath (Join-Path $OutDir 'users.csv') -Raw -Encoding utf8
            $usersCsv | Should -Match 'svc@contoso\.test,Svc,service,false,,,,1'
            $usageCsv = Get-Content -LiteralPath (Join-Path $OutDir 'usage.csv') -Raw -Encoding utf8
            $usageCsv | Should -Match 'svc@contoso\.test,exchange,1'
            $usageCsv | Should -Match 'svc@contoso\.test,sharepoint,1'
            $usageCsv | Should -Match 'svc@contoso\.test,teams,1'
        }
    }

    It 'enforces scope guard before dispatcher invokes any Graph API call' {
        InModuleScope FinOpsAssess {
            $writeJwt = New-TestJwt -Claims @{
                aud = 'https://graph.microsoft.com'
                scp = 'User.ReadWrite.All'
            }
            $secure = New-TestSecureString -Value $writeJwt
            Mock Get-FinOpsGraphCollector {}
            { Invoke-FinOpsLiveCollection -Surface Graph -OutputPath 'out' -Token $secure } | Should -Throw
            Assert-MockCalled Get-FinOpsGraphCollector -Times 0 -Exactly
        }
    }

    It 'matches Python Graph fixtures at normalized dataset level using recorded inputs' {
        InModuleScope FinOpsAssess -Parameters @{
            OutDir       = $script:OutDir
            InputDir     = $script:GraphInputDir
            FixtureDir   = $script:GraphFixtureDir
        } {
            param($OutDir, $InputDir, $FixtureDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $usersJson = Get-Content -LiteralPath (Join-Path $InputDir 'users.json') -Raw -Encoding utf8 | ConvertFrom-Json
            $mailboxCsv = [System.IO.File]::ReadAllText((Join-Path $InputDir 'mailbox_usage.csv'), [System.Text.Encoding]::UTF8)
            $activeCsv = [System.IO.File]::ReadAllText((Join-Path $InputDir 'active_users.csv'), [System.Text.Encoding]::UTF8)
            $copilotCsv = [System.IO.File]::ReadAllText((Join-Path $InputDir 'copilot_usage.csv'), [System.Text.Encoding]::UTF8)

            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*users?*') { return @($usersJson.value) }
                if ($Uri -like '*getMailboxUsageDetail*') { return $mailboxCsv }
                if ($Uri -like '*getOffice365ActiveUserDetail*') { return $activeCsv }
                if ($Uri -like '*getMicrosoft365CopilotUsageSummary*') { return $copilotCsv }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsGraphCollector -OutputPath $OutDir -Auth $auth | Out-Null
            $actual = Get-FinOpsNormalizedDataset -InputDirectory $OutDir
            $expected = Get-FinOpsNormalizedDataset -InputDirectory $FixtureDir

            $actualUsers = @($actual.users | Sort-Object principal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal         = $_.principal
                        display_name      = $_.display_name
                        user_type         = $_.user_type
                        account_enabled   = $_.account_enabled
                        job_title         = $_.job_title
                        department        = $_.department
                        mailbox_size_gb   = $_.mailbox_size_gb
                        last_sign_in_days = $_.last_sign_in_days
                    }
                })
            $expectedUsers = @($expected.users | Sort-Object principal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal         = $_.principal
                        display_name      = $_.display_name
                        user_type         = $_.user_type
                        account_enabled   = $_.account_enabled
                        job_title         = $_.job_title
                        department        = $_.department
                        mailbox_size_gb   = $_.mailbox_size_gb
                        last_sign_in_days = $_.last_sign_in_days
                    }
                })
            $actualAssignments = @($actual.assignments | Sort-Object principal, sku_id | ForEach-Object {
                    [pscustomobject][ordered]@{ principal = $_.principal; sku_id = $_.sku_id }
                })
            $expectedAssignments = @($expected.assignments | Sort-Object principal, sku_id | ForEach-Object {
                    [pscustomobject][ordered]@{ principal = $_.principal; sku_id = $_.sku_id }
                })
            $actualUsage = @($actual.usage | Sort-Object principal, signal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal          = $_.principal
                        signal             = $_.signal
                        last_activity_days = $_.last_activity_days
                    }
                })
            $expectedUsage = @($expected.usage | Sort-Object principal, signal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal          = $_.principal
                        signal             = $_.signal
                        last_activity_days = $_.last_activity_days
                    }
                })

            ($actualUsers | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedUsers | ConvertTo-Json -Depth 8 -Compress)
            ($actualAssignments | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedAssignments | ConvertTo-Json -Depth 8 -Compress)
            ($actualUsage | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedUsage | ConvertTo-Json -Depth 8 -Compress)
        }
    }

    It 'emits lowercase true/false account_enabled literals in users.csv bytes' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*users?*') {
                    return @(
                        [pscustomobject]@{
                            userPrincipalName = 'truecase@contoso.test'
                            displayName       = 'True Case'
                            userType          = 'Member'
                            accountEnabled    = $true
                            assignedLicenses  = @()
                            signInActivity    = [pscustomobject]@{}
                        },
                        [pscustomobject]@{
                            userPrincipalName = 'falsecase@contoso.test'
                            displayName       = 'False Case'
                            userType          = 'Member'
                            accountEnabled    = $false
                            assignedLicenses  = @()
                            signInActivity    = [pscustomobject]@{}
                        }
                    )
                }
                throw 'optional'
            }

            Get-FinOpsGraphCollector -OutputPath $OutDir -Auth $auth | Out-Null
            $raw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'users.csv'), [System.Text.Encoding]::UTF8)
            $raw | Should -Match ',member,true,'
            $raw | Should -Match ',member,false,'
            [regex]::IsMatch($raw, ',member,True,', [System.Text.RegularExpressions.RegexOptions]::None) | Should -BeFalse
            [regex]::IsMatch($raw, ',member,False,', [System.Text.RegularExpressions.RegexOptions]::None) | Should -BeFalse
        }
    }
}
