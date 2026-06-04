#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
    $script:GitHubFixtureDir = Join-Path $script:RepoRoot 'tests' 'fixtures' 'live_collectors' 'github'
    $script:GitHubInputDir = Join-Path $script:GitHubFixtureDir '_input'
    Import-Module $script:ModuleManifest -Force

    Set-Item -Path Function:global:New-TestSecureString -Value {
        param([Parameter(Mandatory)] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) { $secure.AppendChar($char) }
        $secure.MakeReadOnly()
        return $secure
    }

    function script:Get-GitHubFixture {
        param([Parameter(Mandatory)] [string] $Name)
        Get-Content -LiteralPath (Join-Path $script:GitHubInputDir $Name) -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
    }
}

AfterAll {
    Remove-Item -Path Function:global:New-TestSecureString -ErrorAction SilentlyContinue
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsGitHubCollector + GitHub dispatcher guard' {
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

    Describe 'dispatcher X-OAuth-Scopes guard path' {
        It 'parses X-OAuth-Scopes and calls guard with Surface GitHub' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'ghp_readonly'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    [pscustomobject]@{
                        Headers = @{ 'X-OAuth-Scopes' = 'read:org, read:enterprise, read:packages' }
                        Content = '{}'
                    }
                }
                Mock Assert-FinOpsReadOnlyScope {}
                Mock Get-FinOpsGitHubCollector {
                    [pscustomobject]@{ FilesWritten = @('github_seats.csv', 'github_orgs.csv'); RowCounts = [ordered]@{ github_seats = 0; github_orgs = 0 } }
                }

                Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_readonly') | Out-Null
                Assert-MockCalled Assert-FinOpsReadOnlyScope -Times 1 -Exactly -ParameterFilter {
                    $Surface -ceq 'GitHub' -and $Scope.Count -eq 3 -and $Scope[0] -ceq 'read:org' -and $Scope[1] -ceq 'read:enterprise'
                }
            }
        }

        It 'reads X-OAuth-Scopes from WebHeaderCollection-like headers without Contains overload errors' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'ghp_readonly'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    $headers = [System.Net.WebHeaderCollection]::new()
                    $headers.Add('X-OAuth-Scopes', 'read:org')
                    $headers.Add('X-OAuth-Scopes', 'read:enterprise')
                    [pscustomobject]@{
                        Headers = $headers
                        Content = '{}'
                    }
                }
                Mock Assert-FinOpsReadOnlyScope {}
                Mock Get-FinOpsGitHubCollector {
                    [pscustomobject]@{ FilesWritten = @('github_seats.csv', 'github_orgs.csv'); RowCounts = [ordered]@{ github_seats = 0; github_orgs = 0 } }
                }

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_readonly') } | Should -Not -Throw
                Assert-MockCalled Assert-FinOpsReadOnlyScope -Times 1 -Exactly
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 1 -Exactly
            }
        }

        It 'Dictionary[string,IEnumerable[string]] header shape (PS7 live type) does not crash on Contains and extracts scopes' {
            # Regression for: "Cannot find an overload for Contains and the argument count: 1"
            # Dictionary<string,IEnumerable<string>> implements IDictionary but exposes
            # Contains(object) only as an explicit interface member; PowerShell's dynamic
            # dispatch cannot resolve it from the concrete type reference.
            # Get-FinOpsHeaderValue avoids .Contains() entirely by iterating .Keys.
            # This test pins that fix and ensures the IEnumerable join path is exercised.
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'ghp_readonly'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    $headers = [System.Collections.Generic.Dictionary[string, System.Collections.Generic.IEnumerable[string]]]::new(
                        [System.StringComparer]::OrdinalIgnoreCase)
                    $headers['X-OAuth-Scopes'] = [string[]]@('read:org, read:enterprise, read:packages')
                    [pscustomobject]@{ Headers = $headers; Content = '{}' }
                }
                Mock Assert-FinOpsReadOnlyScope {}
                Mock Get-FinOpsGitHubCollector {
                    [pscustomobject]@{ FilesWritten = @('github_seats.csv', 'github_orgs.csv'); RowCounts = [ordered]@{ github_seats = 0; github_orgs = 0 } }
                }

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_readonly') } | Should -Not -Throw
                Assert-MockCalled Assert-FinOpsReadOnlyScope -Times 1 -Exactly -ParameterFilter {
                    $Surface -ceq 'GitHub' -and $Scope.Count -eq 3
                }
            }
        }

        It 'Dictionary[string,IEnumerable[string]] without X-OAuth-Scopes key does not crash and guard fails closed' {
            # Ensures the IDictionary branch in Get-FinOpsHeaderValue returns $null cleanly
            # (no MethodException) when the key is absent, and that the real scope guard
            # correctly refuses with a fail-closed error for the empty-scope case.
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'github_pat_fg_dict'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    $headers = [System.Collections.Generic.Dictionary[string, System.Collections.Generic.IEnumerable[string]]]::new(
                        [System.StringComparer]::OrdinalIgnoreCase)
                    $headers['Content-Type'] = [string[]]@('application/json')
                    [pscustomobject]@{ Headers = $headers; Content = '{}' }
                }
                Mock Get-FinOpsGitHubCollector {}

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'github_pat_fg_dict') } |
                    Should -Throw -ExpectedMessage '*fail-closed*'
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 0 -Exactly
            }
        }

        It 'WebHeaderCollection without X-OAuth-Scopes header does not crash and guard fails closed' {
            # Complements the success-path WebHeaderCollection test above.
            # When the header is absent, GetValues returns $null; Get-FinOpsHeaderValue
            # returns $null; scopes is empty; the real guard throws fail-closed.
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'ghp_ps51_noscopehdr'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    $headers = [System.Net.WebHeaderCollection]::new()
                    $headers.Add('Content-Type', 'application/json')
                    [pscustomobject]@{ Headers = $headers; Content = '{}' }
                }
                Mock Get-FinOpsGitHubCollector {}

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_ps51_noscopehdr') } |
                    Should -Throw -ExpectedMessage '*fail-closed*'
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 0 -Exactly
            }
        }

        It 'refuses write-shaped classic scopes and does not invoke worker' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'ghp_write'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    [pscustomobject]@{
                        Headers = @{ 'X-OAuth-Scopes' = 'read:org, repo, admin:org' }
                        Content = '{}'
                    }
                }
                Mock Get-FinOpsGitHubCollector {}

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_write') } | Should -Throw -ExpectedMessage '*write/admin scope*'
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 0 -Exactly
            }
        }

        It 'allows read-only classic scopes and threads the same auth object into worker' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{
                    AccessToken = (New-TestSecureString -Value 'ghp_read')
                    Source      = 'caller-bearer'
                    Marker      = [guid]::NewGuid().ToString()
                }
                $script:seenAuth = $null
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    [pscustomobject]@{
                        Headers = @{ 'X-OAuth-Scopes' = 'read:org, read:enterprise, read:packages' }
                        Content = '{}'
                    }
                }
                Mock Get-FinOpsGitHubCollector {
                    $script:seenAuth = $Auth
                    [pscustomobject]@{ FilesWritten = @('github_seats.csv', 'github_orgs.csv'); RowCounts = [ordered]@{ github_seats = 1; github_orgs = 1 } }
                }

                $result = Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'ghp_read')
                $result.RowCounts.github_seats | Should -Be 1
                [object]::ReferenceEquals($auth, $script:seenAuth) | Should -BeTrue
            }
        }

        It 'fails closed for fine-grained PAT with no scope header unless -AllowUnknownScopes is used' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'github_pat_fg_only'); Source = 'caller-bearer' }
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    [pscustomobject]@{
                        Headers = @{}
                        Content = '{}'
                    }
                }
                Mock Get-FinOpsGitHubCollector {}

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'github_pat_fg_only') } | Should -Throw -ExpectedMessage '*fail-closed*'
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 0 -Exactly
            }
        }

        It 'with -AllowUnknownScopes fine-grained PAT path downgrades to warning and proceeds' {
            InModuleScope FinOpsAssess {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'github_pat_fg_only'); Source = 'caller-bearer' }
                $script:warningCount = 0
                Mock Get-FinOpsAccessToken { $auth }
                Mock Invoke-WebRequest {
                    [pscustomobject]@{
                        Headers = @{}
                        Content = '{}'
                    }
                }
                Mock Write-Warning { $script:warningCount++ }
                Mock Get-FinOpsGitHubCollector {
                    [pscustomobject]@{ FilesWritten = @('github_seats.csv', 'github_orgs.csv'); RowCounts = [ordered]@{ github_seats = 0; github_orgs = 0 } }
                }

                { Invoke-FinOpsLiveCollection -Surface GitHub -OutputPath 'out' -Token (New-TestSecureString -Value 'github_pat_fg_only') -AllowUnknownScopes } | Should -Not -Throw
                $script:warningCount | Should -BeGreaterThan 0
                Assert-MockCalled Get-FinOpsGitHubCollector -Times 1 -Exactly
            }
        }
    }

    It 'uses GitHubLink pagination and maps consumed/copilot seats with day math' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-FinOpsRestRequest {
                param($Uri, $Paging, $Headers, $MaxPages, $Accept404AsNull)
                $calls.Add([pscustomobject]@{
                        Uri = $Uri
                        Paging = $Paging
                        Headers = $Headers
                        MaxPages = $MaxPages
                        Accept404AsNull = [bool]$Accept404AsNull
                    }) | Out-Null
                if ($Uri -like '*consumed-licenses*') {
                    return @(
                        [pscustomobject]@{ github_com_user = [pscustomobject]@{ login = 'alice'; updated_at = '2025-05-30T00:00:00Z' } },
                        [pscustomobject]@{ github_com_user = [pscustomobject]@{ login = 'bob'; created_at = '2025-05-01T00:00:00Z' } }
                    )
                }
                if ($Uri -like '*copilot/billing/seats*') {
                    return @(
                        [pscustomobject]@{
                            seats = @(
                                [pscustomobject]@{
                                    assignee = [pscustomobject]@{ login = 'copilot-a' }
                                    last_activity_at = '2025-05-25T00:00:00Z'
                                    plan_type = 'business'
                                },
                                [pscustomobject]@{
                                    assignee = [pscustomobject]@{ login = 'copilot-b' }
                                    last_activity_at = '2025-04-01T00:00:00Z'
                                    plan_type = 'enterprise'
                                }
                            )
                        }
                    )
                }
                if ($Uri -like '*advanced-security*') {
                    return [pscustomobject]@{
                        total_advanced_security_committers = 5
                        repos = @(
                            [pscustomobject]@{ advanced_security_committers_breakdown = @([pscustomobject]@{ results_count = 3 }) },
                            [pscustomobject]@{ advanced_security_committers_breakdown = @([pscustomobject]@{ results_count = 0 }) }
                        )
                    }
                }
                if ($Uri -like '*billing/actions*') {
                    return [pscustomobject]@{ total_minutes_used = 12000; included_minutes = 50000 }
                }
                if ($Accept404AsNull) { return $null }
                throw "unexpected uri: $Uri"
            }

            $result = Get-FinOpsGitHubCollector -OutputPath $OutDir -Auth $auth -Enterprise 'contoso' -Org @('contoso') -PageLimit 321
            $result.RowCounts.github_seats | Should -Be 4
            $result.RowCounts.github_orgs | Should -Be 1

            $consumedCall = @($calls.ToArray() | Where-Object { $_.Uri -like '*consumed-licenses*' })[0]
            $consumedCall.Paging | Should -Be 'GitHubLink'
            $consumedCall.MaxPages | Should -Be 321
            $consumedCall.Headers.Accept | Should -Be 'application/vnd.github+json'
            $consumedCall.Headers.'X-GitHub-Api-Version' | Should -Be '2022-11-28'

            $seatsRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'github_seats.csv'), [System.Text.Encoding]::UTF8)
            $seatsRaw | Should -Match 'alice,contoso,enterprise,GH\.ENTERPRISE,2,'
            $seatsRaw | Should -Match 'bob,contoso,enterprise,GH\.ENTERPRISE,31,'
            $seatsRaw | Should -Match 'copilot-a,contoso,copilot_business,GH\.COPILOT_BUSINESS,7,'
            $seatsRaw | Should -Match 'copilot-b,contoso,copilot_enterprise,GH\.COPILOT_ENTERPRISE,61,0'
        }
    }

    It 'maps org billing 404 responses to blank cells' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri, $Accept404AsNull)
                if ($Uri -like '*consumed-licenses*') { return @() }
                if ($Uri -like '*copilot/billing/seats*') { return @() }
                if ($Uri -like '*advanced-security*' -and $Accept404AsNull) { return $null }
                if ($Uri -like '*billing/actions*' -and $Accept404AsNull) { return $null }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsGitHubCollector -OutputPath $OutDir -Auth $auth -Org @('missing-org') | Out-Null
            $orgRaw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'github_orgs.csv'), [System.Text.Encoding]::UTF8)
            $orgRaw | Should -Match "missing-org,,,,,,"
        }
    }

    It 'derives runner_tier thresholds exactly at 2999/3000/49999/50000' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*consumed-licenses*') { return @() }
                if ($Uri -like '*copilot/billing/seats*') { return @() }
                if ($Uri -like '*advanced-security*') { return [pscustomobject]@{ total_advanced_security_committers = 0; repos = @() } }
                if ($Uri -like '*/orgs/free-org/*actions') { return [pscustomobject]@{ total_minutes_used = 10; included_minutes = 2999 } }
                if ($Uri -like '*/orgs/team-org/*actions') { return [pscustomobject]@{ total_minutes_used = 20; included_minutes = 3000 } }
                if ($Uri -like '*/orgs/team-max-org/*actions') { return [pscustomobject]@{ total_minutes_used = 30; included_minutes = 49999 } }
                if ($Uri -like '*/orgs/ent-org/*actions') { return [pscustomobject]@{ total_minutes_used = 40; included_minutes = 50000 } }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsGitHubCollector -OutputPath $OutDir -Auth $auth -Org @('free-org', 'team-org', 'team-max-org', 'ent-org') | Out-Null
            $dataset = Get-FinOpsNormalizedDataset -InputDirectory $OutDir
            $tierByOrg = @{}
            foreach ($row in $dataset.github_orgs) { $tierByOrg[$row.org] = $row.runner_tier }
            $tierByOrg['free-org'] | Should -Be 'free'
            $tierByOrg['team-org'] | Should -Be 'team'
            $tierByOrg['team-max-org'] | Should -Be 'team'
            $tierByOrg['ent-org'] | Should -Be 'enterprise'
        }
    }

    It 'matches committed Python GitHub fixtures at normalized dataset level' {
        InModuleScope FinOpsAssess -Parameters @{
            OutDir     = $script:OutDir
            InputDir   = $script:GitHubInputDir
            FixtureDir = $script:GitHubFixtureDir
        } {
            param($OutDir, $InputDir, $FixtureDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            $consumed = Get-Content -LiteralPath (Join-Path $InputDir 'consumed_licenses.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $copilot = Get-Content -LiteralPath (Join-Path $InputDir 'copilot_seats.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $ghas = Get-Content -LiteralPath (Join-Path $InputDir 'advanced_security.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50
            $actions = Get-Content -LiteralPath (Join-Path $InputDir 'actions_billing.json') -Raw -Encoding utf8 | ConvertFrom-Json -Depth 50

            Mock Invoke-FinOpsRestRequest {
                param($Uri, $Accept404AsNull)
                if ($Uri -like '*consumed-licenses*') { return @($consumed) }
                if ($Uri -like '*copilot/billing/seats*') { return @($copilot) }
                if ($Uri -like '*advanced-security*') { return (Get-Member -InputObject $ghas -Name 'contoso' -ErrorAction SilentlyContinue) ? $ghas.contoso : $null }
                if ($Uri -like '*billing/actions*') { return (Get-Member -InputObject $actions -Name 'contoso' -ErrorAction SilentlyContinue) ? $actions.contoso : $null }
                if ($Accept404AsNull) { return $null }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsGitHubCollector -OutputPath $OutDir -Auth $auth -Enterprise 'contoso' -Org @('contoso') | Out-Null
            $actual = Get-FinOpsNormalizedDataset -InputDirectory $OutDir
            $expected = Get-FinOpsNormalizedDataset -InputDirectory $FixtureDir

            $actualSeats = @($actual.github_seats | Sort-Object principal, seat_type, sku_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal = $_.principal
                        org = $_.org
                        seat_type = $_.seat_type
                        sku_id = $_.sku_id
                        last_activity_days = $_.last_activity_days
                        copilot_acceptances_30d = $_.copilot_acceptances_30d
                    }
                })
            $expectedSeats = @($expected.github_seats | Sort-Object principal, seat_type, sku_id | ForEach-Object {
                    [pscustomobject][ordered]@{
                        principal = $_.principal
                        org = $_.org
                        seat_type = $_.seat_type
                        sku_id = $_.sku_id
                        last_activity_days = $_.last_activity_days
                        copilot_acceptances_30d = $_.copilot_acceptances_30d
                    }
                })

            $actualOrgs = @($actual.github_orgs | Sort-Object org | ForEach-Object {
                    [pscustomobject][ordered]@{
                        org = $_.org
                        ghas_repo_count = $_.ghas_repo_count
                        actively_scanned_repos = $_.actively_scanned_repos
                        active_committers = $_.active_committers
                        runner_tier = $_.runner_tier
                        runner_minutes_used = $_.runner_minutes_used
                        runner_minutes_included = $_.runner_minutes_included
                    }
                })
            $expectedOrgs = @($expected.github_orgs | Sort-Object org | ForEach-Object {
                    [pscustomobject][ordered]@{
                        org = $_.org
                        ghas_repo_count = $_.ghas_repo_count
                        actively_scanned_repos = $_.actively_scanned_repos
                        active_committers = $_.active_committers
                        runner_tier = $_.runner_tier
                        runner_minutes_used = $_.runner_minutes_used
                        runner_minutes_included = $_.runner_minutes_included
                    }
                })

            ($actualSeats | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedSeats | ConvertTo-Json -Depth 8 -Compress)
            ($actualOrgs | ConvertTo-Json -Depth 8 -Compress) | Should -Be ($expectedOrgs | ConvertTo-Json -Depth 8 -Compress)
        }
    }

    It 'emits lowercase copilot seat_type literals in github_seats.csv bytes' {
        InModuleScope FinOpsAssess -Parameters @{ OutDir = $script:OutDir } {
            param($OutDir)
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'token'); Source = 'caller-bearer' }
            Mock Invoke-FinOpsRestRequest {
                param($Uri)
                if ($Uri -like '*consumed-licenses*') { return @() }
                if ($Uri -like '*copilot/billing/seats*') {
                    return @([pscustomobject]@{
                            assignee = [pscustomobject]@{ login = 'literalcase' }
                            last_activity_at = '2025-05-20T00:00:00Z'
                            plan_type = 'Enterprise'
                        })
                }
                if ($Uri -like '*advanced-security*') { return $null }
                if ($Uri -like '*billing/actions*') { return $null }
                throw "unexpected uri: $Uri"
            }

            Get-FinOpsGitHubCollector -OutputPath $OutDir -Auth $auth -Enterprise 'contoso' | Out-Null
            $raw = [System.IO.File]::ReadAllText((Join-Path $OutDir 'github_seats.csv'), [System.Text.Encoding]::UTF8)
            $raw | Should -Match ',copilot_enterprise,'
            [regex]::IsMatch($raw, ',COPILOT_ENTERPRISE,', [System.Text.RegularExpressions.RegexOptions]::None) | Should -BeFalse
        }
    }
}
