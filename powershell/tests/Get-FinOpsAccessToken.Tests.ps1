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

Describe 'Get-FinOpsAccessToken' {
    BeforeEach {
        $script:OriginalEnv = @{
            AZURE_TENANT_ID            = $env:AZURE_TENANT_ID
            AZURE_CLIENT_ID            = $env:AZURE_CLIENT_ID
            AZURE_CLIENT_SECRET        = $env:AZURE_CLIENT_SECRET
            AZURE_FEDERATED_TOKEN_FILE = $env:AZURE_FEDERATED_TOKEN_FILE
        }
        Remove-Item Env:AZURE_TENANT_ID, Env:AZURE_CLIENT_ID, Env:AZURE_CLIENT_SECRET, Env:AZURE_FEDERATED_TOKEN_FILE -ErrorAction SilentlyContinue
    }

    AfterEach {
        foreach ($entry in $script:OriginalEnv.GetEnumerator()) {
            if ($null -eq $entry.Value) { Remove-Item "Env:$($entry.Key)" -ErrorAction SilentlyContinue }
            else { Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value }
        }
        Remove-Item (Join-Path $PSScriptRoot 'federated-token.txt') -ErrorAction SilentlyContinue
    }

    It 'uses Az.Accounts when available' {
        InModuleScope FinOpsAssess {
            Mock Get-Module { [pscustomobject]@{ Name = 'Az.Accounts' } } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            Mock Get-AzAccessToken { [pscustomobject]@{ Token = 'az-token-value'; ExpiresOn = [DateTimeOffset]'2026-01-01T00:00:00+00:00' } }

            $result = Get-FinOpsAccessToken -Scope graph
            $result.Source | Should -Be 'az.accounts'
            $result.Surface | Should -Be 'Graph'
            $result.AccessToken | Should -BeOfType ([System.Security.SecureString])
            $result.ExpiresOn | Should -Be ([DateTimeOffset]'2026-01-01T00:00:00+00:00')
            Assert-MockCalled Get-AzAccessToken -Times 1 -Exactly -ParameterFilter { $ResourceUrl -eq 'https://graph.microsoft.com' }
        }
    }

    It 'uses workload identity when Az.Accounts is unavailable' {
        $tokenPath = Join-Path $PSScriptRoot 'federated-token.txt'
        [System.IO.File]::WriteAllText($tokenPath, 'federated-assertion', (New-Object System.Text.UTF8Encoding($false)))
        $env:AZURE_FEDERATED_TOKEN_FILE = $tokenPath
        $env:AZURE_CLIENT_ID = 'client-id'
        $env:AZURE_TENANT_ID = 'tenant-id'

        InModuleScope FinOpsAssess {
            Mock Get-Module { $null } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            Mock Invoke-RestMethod { [pscustomobject]@{ access_token = 'wi-token-value'; expires_in = 3600 } } -ParameterFilter { $Uri -like '*oauth2/v2.0/token' -and $Method -eq 'Post' }

            $result = Get-FinOpsAccessToken -Scope arm
            $result.Source | Should -Be 'workload-identity'
            $result.Surface | Should -Be 'AzureResourceManager'
            $result.AccessToken | Should -BeOfType ([System.Security.SecureString])
            Assert-MockCalled Invoke-RestMethod -Times 1 -Exactly
        }
    }

    It 'uses client secret when federated identity is unavailable' {
        $env:AZURE_CLIENT_ID = 'client-id'
        $env:AZURE_TENANT_ID = 'tenant-id'
        $env:AZURE_CLIENT_SECRET = 'secret-value'

        InModuleScope FinOpsAssess {
            Mock Get-Module { $null } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            Mock Invoke-RestMethod { [pscustomobject]@{ access_token = 'secret-token-value'; expires_in = 3600 } } -ParameterFilter { $Uri -like '*oauth2/v2.0/token' -and $Method -eq 'Post' }

            $result = Get-FinOpsAccessToken -Scope graph
            $result.Source | Should -Be 'client-secret'
            $result.AccessToken | Should -BeOfType ([System.Security.SecureString])
        }
    }

    It 'passes through caller bearer and caller PAT as SecureString' {
        InModuleScope FinOpsAssess {
            $bearer = New-TestSecureString -Value 'bearer-value'
            $pat = New-TestSecureString -Value 'pat-value'

            $bearerResult = Get-FinOpsAccessToken -Token $bearer
            $patResult = Get-FinOpsAccessToken -Pat $pat

            $bearerResult.Source | Should -Be 'caller-bearer'
            $patResult.Source | Should -Be 'caller-pat'
            $bearerResult.AccessToken | Should -BeOfType ([System.Security.SecureString])
            $patResult.AccessToken | Should -BeOfType ([System.Security.SecureString])
        }
    }

    It 'does not write token values to verbose, host, or output streams' {
        $env:AZURE_CLIENT_ID = 'client-id'
        $env:AZURE_TENANT_ID = 'tenant-id'
        $env:AZURE_CLIENT_SECRET = 'super-secret-value'

        InModuleScope FinOpsAssess {
            Mock Get-Module { $null } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            Mock Invoke-RestMethod { [pscustomobject]@{ access_token = 'token-never-log-me'; expires_in = 3600 } }
            Mock Write-Host {}

            $allStreams = & { Get-FinOpsAccessToken -Scope graph -Verbose } *>&1
            $streamText = ($allStreams | Out-String)

            $streamText | Should -Not -Match 'token-never-log-me'
            $streamText | Should -Not -Match 'super-secret-value'
            Assert-MockCalled Write-Host -Times 0 -Exactly
        }
    }

    It 'fails closed when no supported credential source exists' {
        InModuleScope FinOpsAssess {
            Mock Get-Module { $null } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            { Get-FinOpsAccessToken -Scope graph } | Should -Throw -ExpectedMessage '*no supported credential source resolved*'
        }
    }

    It 'does not leak client_secret or client_assertion on token endpoint failure' {
        $tokenPath = Join-Path $PSScriptRoot 'federated-token.txt'
        [System.IO.File]::WriteAllText($tokenPath, 'assertion-should-not-leak', (New-Object System.Text.UTF8Encoding($false)))
        $env:AZURE_FEDERATED_TOKEN_FILE = $tokenPath
        $env:AZURE_CLIENT_ID = 'client-id'
        $env:AZURE_TENANT_ID = 'tenant-id'

        InModuleScope FinOpsAssess {
            Mock Get-Module { $null } -ParameterFilter { $ListAvailable -and $Name -eq 'Az.Accounts' }
            Mock Invoke-RestMethod { throw 'simulated-token-endpoint-failure' }

            $allStreams = @()
            try {
                $allStreams = & { Get-FinOpsAccessToken -Scope graph -Verbose } *>&1
            } catch {
                $allStreams += $_
            }
            $text = ($allStreams | Out-String)
            $text | Should -Match 'Token acquisition failed'
            $text | Should -Not -Match 'client_secret'
            $text | Should -Not -Match 'client_assertion'
            $text | Should -Not -Match 'assertion-should-not-leak'
        }
    }
}
