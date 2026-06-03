#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
    $script:AdoFixtureDir = Join-Path $script:RepoRoot 'tests' 'fixtures' 'live_collectors' 'ado'
    $script:AdoInputDir = Join-Path $script:AdoFixtureDir '_input'
    Import-Module $script:ModuleManifest -Force

    Set-Item -Path Function:global:New-TestSecureString -Value {
        param([Parameter(Mandatory)] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) { $secure.AppendChar($char) }
        $secure.MakeReadOnly()
        return $secure
    }

    Set-Item -Path Function:global:New-TestJwt -Value {
        param([hashtable] $Claims)
        $enc = {
            param($obj)
            $json = $obj | ConvertTo-Json -Compress -Depth 5
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

Describe 'Get-FinOpsAdoCollector + ADO dispatcher guard' {
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

    Describe 'dispatcher ADO scope guard paths' {
        It 'bearer with vso.code_write is refused by guard' {
            InModuleScope FinOpsAssess {
                $writeJwt = New-TestJwt -Claims @{ aud = '499b84ac-1321-427f-aa17-267ca6975798'; scp = 'vso.code_write' }
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value $writeJwt); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Get-FinOpsAdoCollector {}

                { Invoke-FinOpsLiveCollection -Surface Ado -OutputPath 'out' -AdoOrg 'contoso' -Token (New-TestSecureString -Value $writeJwt) } | Should -Throw -ExpectedMessage '*write/admin scope*'
                Assert-MockCalled Get-FinOpsAdoCollector -Times 0 -Exactly
            }
        }

        It 'bearer with vso.code proceeds' {
            InModuleScope FinOpsAssess {
                $readJwt = New-TestJwt -Claims @{ aud = '499b84ac-1321-427f-aa17-267ca6975798'; scp = 'vso.code' }
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value $readJwt); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Get-FinOpsAdoCollector {
                    [pscustomobject]@{ FilesWritten = @('ado_seats.csv', 'ado_orgs.csv'); RowCounts = [ordered]@{ ado_seats = 0; ado_orgs = 1 } }
                }

                { Invoke-FinOpsLiveCollection -Surface Ado -OutputPath 'out' -AdoOrg 'contoso' -Token (New-TestSecureString -Value $readJwt) } | Should -Not -Throw
                Assert-MockCalled Get-FinOpsAdoCollector -Times 1 -Exactly
            }
        }

        It 'PAT path is fail-closed without -AllowUnknownScopes' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'pat-token'); Source = 'caller-pat' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Get-FinOpsAdoCollector {}

                { Invoke-FinOpsLiveCollection -Surface Ado -OutputPath 'out' -AdoOrg 'contoso' -Pat (New-TestSecureString -Value 'pat-token') } | Should -Throw -ExpectedMessage '*fail-closed*'
                Assert-MockCalled Get-FinOpsAdoCollector -Times 0 -Exactly
            }
        }

        It 'PAT path proceeds with -AllowUnknownScopes' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'pat-token'); Source = 'caller-pat' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Get-FinOpsAdoCollector {
                    [pscustomobject]@{ FilesWritten = @('ado_seats.csv', 'ado_orgs.csv'); RowCounts = [ordered]@{ ado_seats = 0; ado_orgs = 1 } }
                }

                { Invoke-FinOpsLiveCollection -Surface Ado -OutputPath 'out' -AdoOrg 'contoso' -Pat (New-TestSecureString -Value 'pat-token') -AllowUnknownScopes } | Should -Not -Throw
                Assert-MockCalled Get-FinOpsAdoCollector -Times 1 -Exactly
            }
        }
    }

    It 'uses Basic auth header base64(":"+pat) for caller-pat' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $pat = 'fixture-pat'
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value $pat); Source = 'caller-pat' }
            $script:headersSeen = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod {
                param($Uri, $Headers)
                $script:headersSeen.Add([pscustomobject]@{ Uri = $Uri; Headers = $Headers }) | Out-Null
                if ($Uri -like '*userentitlements*') { return [pscustomobject]@{ members = @(); continuationToken = '' } }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 1 }) }
                if ($Uri -like '*_apis/projects*') { return [pscustomobject]@{ value = @() } }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso' | Out-Null
            $expected = 'Basic ' + [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes(":$pat"))
            ($script:headersSeen | ForEach-Object { $_.Headers.Authorization } | Select-Object -Unique) | Should -Be @($expected)
        }
    }

    It 'uses Bearer auth header for caller-bearer' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'fixture-bearer'); Source = 'caller-bearer' }
            $script:headersSeen = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod {
                param($Uri, $Headers)
                $script:headersSeen.Add([pscustomobject]@{ Uri = $Uri; Headers = $Headers }) | Out-Null
                if ($Uri -like '*userentitlements*') { return [pscustomobject]@{ members = @(); continuationToken = '' } }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 1 }) }
                if ($Uri -like '*_apis/projects*') { return [pscustomobject]@{ value = @() } }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso' | Out-Null
            ($script:headersSeen | ForEach-Object { $_.Headers.Authorization } | Select-Object -Unique) | Should -Be @('Bearer fixture-bearer')
        }
    }

    It 'paginates userentitlements via continuationToken in body (two pages)' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $script:uris = [System.Collections.Generic.List[string]]::new()
            Mock Invoke-RestMethod {
                param($Uri)
                $script:uris.Add([string]$Uri) | Out-Null
                if ($Uri -like '*userentitlements*continuationToken=page-2*') {
                    return [pscustomobject]@{
                        members = @([pscustomobject]@{ user = [pscustomobject]@{ mailAddress = 'two@contoso.test' }; accessLevel = [pscustomobject]@{ accessLevelName = 'Stakeholder' }; projectEntitlements = @() })
                        continuationToken = ''
                    }
                }
                if ($Uri -like '*userentitlements*') {
                    return [pscustomobject]@{
                        members = @([pscustomobject]@{ user = [pscustomobject]@{ mailAddress = 'one@contoso.test' }; accessLevel = [pscustomobject]@{ accessLevelName = 'Advanced' }; projectEntitlements = @() })
                        continuationToken = 'page-2'
                    }
                }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 1 }) }
                if ($Uri -like '*_apis/projects*') { return [pscustomobject]@{ value = @() } }
                throw "unexpected uri: $Uri"
            }

            $result = Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso'
            $result.RowCounts.ado_seats | Should -Be 2
            @($script:uris | Where-Object { $_ -like '*continuationToken=page-2*' }).Count | Should -BeGreaterThan 0
        }
    }

    It 'paginates via X-MS-ContinuationToken header branch' {
        InModuleScope FinOpsAssess {
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $script:uris = [System.Collections.Generic.List[string]]::new()
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable, $ErrorAction)
                $null = $Method, $Headers, $ResponseHeadersVariable, $ErrorAction
                $script:uris.Add([string]$Uri) | Out-Null
                if ($Uri -like '*continuationToken=header-2*') {
                    return [pscustomobject]@{
                        members = @([pscustomobject]@{ user = [pscustomobject]@{ mailAddress = 'header-two@contoso.test' } })
                        'x-ms-continuationtoken' = ''
                    }
                }
                return [pscustomobject]@{
                    members = @([pscustomobject]@{ user = [pscustomobject]@{ mailAddress = 'header-one@contoso.test' } })
                    'x-ms-continuationtoken' = 'header-2'
                }
            }

            $rows = @(
                Invoke-FinOpsRestRequest `
                    -Uri 'https://vsaex.dev.azure.com/contoso/_apis/userentitlements?api-version=7.1&top=100&select=Projects,Extensions' `
                    -Auth $auth `
                    -Paging AdoContinuation `
                    -ValueProperty 'members' `
                    -MaxPages 10
            )
            $rows.Count | Should -BeGreaterThan 0
        }
    }

    It 'maps access levels, test plans extension, stakeholder-only activity and org limits' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*userentitlements*') {
                    return @(
                        [pscustomobject]@{
                            user = [pscustomobject]@{ mailAddress = 'stake@contoso.test' }
                            accessLevel = [pscustomobject]@{ accessLevelName = 'Stakeholder'; lastAccessedDate = '2025-05-10T00:00:00Z' }
                            extensions = @()
                            projectEntitlements = @(
                                [pscustomobject]@{ projectPermissions = [pscustomobject]@{ hasRepoAccess = $false; hasBuildAccess = $false } }
                            )
                        },
                        [pscustomobject]@{
                            user = [pscustomobject]@{ mailAddress = 'basic@contoso.test' }
                            accessLevel = [pscustomobject]@{ accessLevelName = 'Advanced'; lastAccessedDate = '2025-05-20T00:00:00Z' }
                            extensions = @()
                            projectEntitlements = @(
                                [pscustomobject]@{ projectPermissions = [pscustomobject]@{ hasRepoAccess = $true; hasBuildAccess = $false } }
                            )
                        },
                        [pscustomobject]@{
                            user = [pscustomobject]@{ mailAddress = 'testplans@contoso.test' }
                            accessLevel = [pscustomobject]@{ accessLevelName = 'Express'; lastAccessedDate = '2025-05-25T00:00:00Z' }
                            extensions = @([pscustomobject]@{ id = 'ms.vss-test-web.testplans' })
                            projectEntitlements = @()
                        }
                    )
                }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 10 }) }
                if ($Uri -like '*_apis/projects*') { return @() }
                throw "unexpected uri: $Uri"
            }

            $result = Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso'
            $result.RowCounts.ado_seats | Should -Be 3
            $seatsRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'ado_seats.csv'), [System.Text.Encoding]::UTF8)
            $orgRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'ado_orgs.csv'), [System.Text.Encoding]::UTF8)
            $seatsRaw | Should -Match 'stake@contoso\.test,contoso,stakeholder,ADO\.STAKEHOLDER,22,true,'
            $seatsRaw | Should -Match 'basic@contoso\.test,contoso,basic,ADO\.BASIC,12,false,'
            $seatsRaw | Should -Match 'testplans@contoso\.test,contoso,basic_plus_test,ADO\.BASIC_TEST,7,false,'
            $orgRaw | Should -Match 'contoso,10,'
        }
    }

    It 'matches Python int() p95 index semantics for 25 samples (returns 24)' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $builds = @(1..25 | ForEach-Object {
                    $n = $_
                    $start = [datetime]'2025-05-15T00:00:00Z'
                    [pscustomobject]@{
                        startTime = $start.ToString('yyyy-MM-ddTHH:mm:ssZ')
                        finishTime = $start.AddMinutes($n).ToString('yyyy-MM-ddTHH:mm:ssZ')
                    }
                })
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*userentitlements*') { return @() }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 3 }) }
                if ($Uri -like '*_apis/projects*') { return @([pscustomobject]@{ id = 'project-1' }) }
                if ($Uri -like '*/project-1/_apis/build/builds*') { return @($builds) }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso' | Out-Null
            $orgRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'ado_orgs.csv'), [System.Text.Encoding]::UTF8)
            $orgRaw | Should -Match 'contoso,3,24'
        }
    }

    It 'matches committed Python ADO fixtures at normalized dataset level' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir; InputDir = $script:AdoInputDir; FixtureDir = $script:AdoFixtureDir } {
            param($OutDir, $InputDir, $FixtureDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $userentitlements = Get-Content -LiteralPath (Join-Path $InputDir 'userentitlements.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $projects = Get-Content -LiteralPath (Join-Path $InputDir 'projects.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $builds = Get-Content -LiteralPath (Join-Path $InputDir 'builds.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50

            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*userentitlements*continuationToken=page-2*') { return @($userentitlements.page_2.members) }
                if ($Uri -like '*userentitlements*') { return @($userentitlements.page_1.members + $userentitlements.page_2.members) }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 10 }) }
                if ($Uri -like '*_apis/projects*') { return @($projects.value) }
                if ($Uri -like '*/project-one/_apis/build/builds*') { return @($builds.'project-one'.value) }
                if ($Uri -like '*/project-two/_apis/build/builds*') { return @($builds.'project-two'.value) }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso' | Out-Null
            $actual = Get-FinOpsNormalizedDataset -InputDirectory $OutDir
            $expected = Get-FinOpsNormalizedDataset -InputDirectory $FixtureDir

            $actualSeats = @($actual.ado_seats | Sort-Object principal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal = $_.principal
                        org = $_.org
                        seat_type = $_.seat_type
                        sku_id = $_.sku_id
                        last_activity_days = $_.last_activity_days
                        only_stakeholder_activity = $_.only_stakeholder_activity
                        last_test_plan_days = $_.last_test_plan_days
                    }
                })
            $expectedSeats = @($expected.ado_seats | Sort-Object principal | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal = $_.principal
                        org = $_.org
                        seat_type = $_.seat_type
                        sku_id = $_.sku_id
                        last_activity_days = $_.last_activity_days
                        only_stakeholder_activity = $_.only_stakeholder_activity
                        last_test_plan_days = $_.last_test_plan_days
                    }
                })

            $actualOrgs = @($actual.ado_orgs | Sort-Object org | ForEach-Object {
                    [pscustomobject][ordered]@{
                        org = $_.org
                        purchased_parallel_jobs = $_.purchased_parallel_jobs
                        p95_concurrent_jobs = $_.p95_concurrent_jobs
                    }
                })
            $expectedOrgs = @($expected.ado_orgs | Sort-Object org | ForEach-Object {
                    [pscustomobject][ordered]@{
                        org = $_.org
                        purchased_parallel_jobs = $_.purchased_parallel_jobs
                        p95_concurrent_jobs = $_.p95_concurrent_jobs
                    }
                })

            ($actualSeats | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedSeats | ConvertTo-Json -Depth 8 -Compress)
            ($actualOrgs | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedOrgs | ConvertTo-Json -Depth 8 -Compress)
        }
    }

    It 'emits lowercase boolean literals for only_stakeholder_activity' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*userentitlements*') {
                    return @([pscustomobject]@{
                            user = [pscustomobject]@{ mailAddress = 'literal@contoso.test' }
                            accessLevel = [pscustomobject]@{ accessLevelName = 'Stakeholder' }
                            projectEntitlements = @(
                                [pscustomobject]@{ projectPermissions = [pscustomobject]@{ hasRepoAccess = $false; hasBuildAccess = $false } }
                            )
                        })
                }
                if ($Uri -like '*resourcelimits*') { return @([pscustomobject]@{ parallelSmallJobsCount = 1 }) }
                if ($Uri -like '*_apis/projects*') { return @() }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsAdoCollector -OutputPath $OutDir -Auth $auth -Org 'contoso' | Out-Null
            $raw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'ado_seats.csv'), [System.Text.Encoding]::UTF8)
            $raw | Should -Match ',true,'
            [regex]::IsMatch($raw, ',True,') | Should -BeFalse
            [regex]::IsMatch($raw, ',False,') | Should -BeFalse
        }
    }
}
