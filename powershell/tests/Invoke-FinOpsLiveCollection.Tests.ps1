#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    Import-Module $script:ModuleManifest -Force
    Set-Item -Path Function:global:New-TestSecureString -Value {
        param([Parameter(Mandatory)] [string] $Value)
        $secure = [System.Security.SecureString]::new()
        foreach ($char in $Value.ToCharArray()) { $secure.AppendChar($char) }
        $secure.MakeReadOnly()
        return $secure
    }
}

AfterAll {
    Remove-Item -Path Function:global:New-TestSecureString -ErrorAction SilentlyContinue
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Invoke-FinOpsLiveCollection' {
    It 'throws NotImplementedException for GitHub and Ado after guard passes' {
        $jwt = 'eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJhdWQiOiJodHRwczovL2dyYXBoLm1pY3Jvc29mdC5jb20iLCJzY3AiOiJVc2VyLlJlYWQuQWxsIn0.sig'
        $secure = New-TestSecureString -Value $jwt
        foreach ($surface in @('GitHub', 'Ado')) {
            { Invoke-FinOpsLiveCollection -Surface $surface -OutputPath 'out' -Token $secure -AllowUnknownScopes } |
                Should -Throw -ExceptionType ([System.NotImplementedException])
        }
    }

    It 'calls Get-FinOpsAccessToken then Assert-FinOpsReadOnlyScope before any API request' {
        InModuleScope FinOpsAssess {
            $order = [System.Collections.Generic.List[string]]::new()
            Mock Get-FinOpsAccessToken {
                $order.Add('token')
                [pscustomobject]@{
                    AccessToken = (New-TestSecureString -Value 'token')
                    Source      = 'scope'
                }
            }
            Mock Assert-FinOpsReadOnlyScope { $order.Add('guard') }
            Mock Invoke-FinOpsRestRequest { $order.Add('api') }
            Mock Invoke-FinOpsLiveCollectionWorker {
                throw [System.NotImplementedException]::new('Graph collector lands in Phase 6x')
            }

            { Invoke-FinOpsLiveCollection -Surface Graph -OutputPath 'out' } | Should -Throw -ExceptionType ([System.NotImplementedException])
            $order | Should -Be @('token', 'guard')
            Assert-MockCalled Invoke-FinOpsRestRequest -Times 0 -Exactly
        }
    }

    It 'refuses when scope guard throws' {
        InModuleScope FinOpsAssess {
            Mock Get-FinOpsAccessToken {
                [pscustomobject]@{
                    AccessToken = (New-TestSecureString -Value 'token')
                    Source      = 'scope'
                }
            }
            Mock Assert-FinOpsReadOnlyScope { throw 'write-capable token refused' }
            Mock Invoke-FinOpsLiveCollectionWorker {}

            { Invoke-FinOpsLiveCollection -Surface Graph -OutputPath 'out' } | Should -Throw -ExpectedMessage '*write-capable*'
            Assert-MockCalled Invoke-FinOpsLiveCollectionWorker -Times 0 -Exactly
        }
    }

    It 'passes the exact guarded auth object to downstream worker' {
        InModuleScope FinOpsAssess {
            $auth = [pscustomobject]@{
                AccessToken = (New-TestSecureString -Value 'token')
                Source      = 'scope'
                Marker      = [guid]::NewGuid().ToString()
            }
            $captured = $null

            Mock Get-FinOpsAccessToken { $auth }
            Mock Assert-FinOpsReadOnlyScope {}
            Mock Invoke-FinOpsLiveCollectionWorker {
                $script:captured = $Auth
                throw [System.NotImplementedException]::new("$Surface collector lands in Phase 6x")
            }

            { Invoke-FinOpsLiveCollection -Surface Graph -OutputPath 'out' -AllowUnknownScopes } | Should -Throw
            [object]::ReferenceEquals($auth, $script:captured) | Should -BeTrue
        }
    }

    It 'requires two-key ARM consent before token acquisition (missing both)' {
        InModuleScope FinOpsAssess {
            Mock Get-FinOpsAccessToken {}
            { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' } | Should -Throw -ExpectedMessage '*requires explicit two-key consent*'
            Assert-MockCalled Get-FinOpsAccessToken -Times 0 -Exactly
        }
    }

    It 'requires two-key ARM consent (switch only)' {
        InModuleScope FinOpsAssess {
            Mock Get-FinOpsAccessToken {}
            { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' -AcceptArmRbacRisk } | Should -Throw -ExpectedMessage '*FINOPS_ACCEPT_ARM_RBAC_RISK=1*'
            Assert-MockCalled Get-FinOpsAccessToken -Times 0 -Exactly
        }
    }

    It 'requires two-key ARM consent (env only)' {
        InModuleScope FinOpsAssess {
            $previous = $env:FINOPS_ACCEPT_ARM_RBAC_RISK
            $env:FINOPS_ACCEPT_ARM_RBAC_RISK = '1'
            try {
                Mock Get-FinOpsAccessToken {}
                { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' } | Should -Throw -ExpectedMessage '*pass -AcceptArmRbacRisk*'
                Assert-MockCalled Get-FinOpsAccessToken -Times 0 -Exactly
            } finally {
                if ($null -eq $previous) { Remove-Item Env:FINOPS_ACCEPT_ARM_RBAC_RISK -ErrorAction SilentlyContinue }
                else { $env:FINOPS_ACCEPT_ARM_RBAC_RISK = $previous }
            }
        }
    }

    It 'with both ARM consent keys it runs scope guard with -AllowUnknownScopes and warns' {
        InModuleScope FinOpsAssess {
            $previous = $env:FINOPS_ACCEPT_ARM_RBAC_RISK
            $env:FINOPS_ACCEPT_ARM_RBAC_RISK = '1'
            try {
                $auth = [pscustomobject]@{
                    AccessToken = (New-TestSecureString -Value 'token')
                    Source      = 'scope'
                }
                $script:guardArgs = $null
                $script:warnCount = 0
                $script:infoCount = 0
                Mock Get-FinOpsAccessToken { $auth }
                Mock Assert-FinOpsReadOnlyScope {
                    $script:guardArgs = $PSBoundParameters
                }
                Mock Write-Warning { $script:warnCount++ }
                Mock Write-Information { $script:infoCount++ }
                Mock Get-FinOpsArmCollector {
                    [pscustomobject]@{
                        FilesWritten = @('azure_resources.csv')
                        RowCounts    = [ordered]@{ azure_resources = 1 }
                    }
                }

                $result = Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' -AcceptArmRbacRisk
                $result.FilesWritten | Should -Be @('azure_resources.csv')
                Assert-MockCalled Assert-FinOpsReadOnlyScope -Times 1 -Exactly -ParameterFilter { $AllowUnknownScopes }
                $script:warnCount | Should -BeGreaterThan 0
                $script:infoCount | Should -BeGreaterThan 0
            } finally {
                if ($null -eq $previous) { Remove-Item Env:FINOPS_ACCEPT_ARM_RBAC_RISK -ErrorAction SilentlyContinue }
                else { $env:FINOPS_ACCEPT_ARM_RBAC_RISK = $previous }
            }
        }
    }

    It 'with both ARM keys a write-scoped token is still refused by the guard' {
        InModuleScope FinOpsAssess {
            $previous = $env:FINOPS_ACCEPT_ARM_RBAC_RISK
            $env:FINOPS_ACCEPT_ARM_RBAC_RISK = '1'
            try {
                $writeJwt = New-TestSecureString -Value 'eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJhdWQiOiJodHRwczovL21hbmFnZW1lbnQuYXp1cmUuY29tIiwic2NwIjoidXNlcl9pbXBlcnNvbmF0aW9uIiwicm9sZXMiOlsiRGlyZWN0b3J5LlJlYWRXcml0ZS5BbGwiXX0.sig'
                Mock Assert-FinOpsReadOnlyScope { throw 'write/admin scope refused' }
                Mock Get-FinOpsArmCollector {}
                { Invoke-FinOpsLiveCollection -Surface Arm -OutputPath 'out' -Token $writeJwt -AcceptArmRbacRisk } | Should -Throw -ExpectedMessage '*write/admin scope refused*'
                Assert-MockCalled Get-FinOpsArmCollector -Times 0 -Exactly
            } finally {
                if ($null -eq $previous) { Remove-Item Env:FINOPS_ACCEPT_ARM_RBAC_RISK -ErrorAction SilentlyContinue }
                else { $env:FINOPS_ACCEPT_ARM_RBAC_RISK = $previous }
            }
        }
    }

    It 'dispatches Graph to Get-FinOpsGraphCollector and surfaces worker summary' {
        InModuleScope FinOpsAssess {
            $auth = [pscustomobject]@{
                AccessToken = (New-TestSecureString -Value 'token')
                Source      = 'scope'
            }

            Mock Get-FinOpsAccessToken { $auth }
            Mock Assert-FinOpsReadOnlyScope {}
            Mock Get-FinOpsGraphCollector {
                [pscustomobject]@{
                    FilesWritten = @('users.csv', 'license_assignments.csv', 'usage.csv')
                    RowCounts    = [ordered]@{
                        users               = 1
                        license_assignments = 2
                        usage               = 3
                    }
                }
            }

            $result = Invoke-FinOpsLiveCollection -Surface Graph -OutputPath 'out'
            $result.FilesWritten | Should -Be @('users.csv', 'license_assignments.csv', 'usage.csv')
            $result.RowCounts.users | Should -Be 1
            Assert-MockCalled Get-FinOpsGraphCollector -Times 1 -Exactly
        }
    }
}
