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

Describe 'Invoke-FinOpsRestRequest' {
    It 'constructs bearer and basic authorization headers' {
        InModuleScope FinOpsAssess {
            $headersSeen = [System.Collections.Generic.List[hashtable]]::new()
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $ResponseHeadersVariable
                $headersSeen.Add($Headers)
                [pscustomobject]@{ ok = $true }
            }

            $bearer = [pscustomobject]@{
                AccessToken = (New-TestSecureString -Value 'bearer-token')
                Source      = 'caller-bearer'
            }
            $pat = [pscustomobject]@{
                AccessToken = (New-TestSecureString -Value 'pat-token')
                Source      = 'caller-pat'
            }

            Invoke-FinOpsRestRequest -Uri 'https://example.test/a' -Auth $bearer | Out-Null
            Invoke-FinOpsRestRequest -Uri 'https://example.test/b' -Auth $pat | Out-Null

            $headersSeen[0]['Authorization'] | Should -Be 'Bearer bearer-token'
            $headersSeen[1]['Authorization'] | Should -Be ('Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(':pat-token')))
        }
    }

    It 'paginates Graph @odata.nextLink across pages' {
        InModuleScope FinOpsAssess {
            $script:graphCalls = 0
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $script:graphCalls++
                if ($script:graphCalls -eq 1) {
                    return [pscustomobject]@{
                        value = @([pscustomobject]@{ id = 1 })
                        '@odata.nextLink' = 'https://graph.test/page2'
                    }
                }
                return [pscustomobject]@{ value = @([pscustomobject]@{ id = 2 }) }
            }

            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            $result = Invoke-FinOpsRestRequest -Uri 'https://graph.test/page1' -Auth $auth -Paging GraphODataNext -ValueProperty value
            @($result).Count | Should -Be 2
            $result[0].id | Should -Be 1
            $result[1].id | Should -Be 2
        }
    }

    It 'paginates ARM nextLink across pages' {
        InModuleScope FinOpsAssess {
            $script:armCalls = 0
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $script:armCalls++
                if ($script:armCalls -eq 1) {
                    return [pscustomobject]@{ value = @([pscustomobject]@{ name = 'vm1' }); nextLink = 'https://arm.test/page2' }
                }
                return [pscustomobject]@{ value = @([pscustomobject]@{ name = 'vm2' }) }
            }

            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            $result = Invoke-FinOpsRestRequest -Uri 'https://arm.test/page1' -Auth $auth -Paging ArmNextLink -ValueProperty value
            @($result).Count | Should -Be 2
        }
    }

    It 'paginates GitHub Link rel next across pages' {
        InModuleScope FinOpsAssess {
            $script:ghCalls = 0
            $shim = {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable, $ErrorAction)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable, $ErrorAction
                $script:ghCalls++
                if ($script:ghCalls -eq 1) {
                    return [pscustomobject]@{
                        Content = '[{"id":1}]'
                        Headers = @{ Link = '<https://api.github.com/page2>; rel="next"' }
                    }
                }
                return [pscustomobject]@{
                    Content = '[{"id":2}]'
                    Headers = @{}
                }
            }
            Set-Item -Path 'Function:Invoke-WebRequest' -Value $shim
            try {
                $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
                $result = Invoke-FinOpsRestRequest -Uri 'https://api.github.com/page1' -Auth $auth -Paging GitHubLink
                @($result).Count | Should -Be 2
            } finally {
                Remove-Item -Path 'Function:Invoke-WebRequest' -ErrorAction SilentlyContinue
            }
        }
    }

    It 'paginates ADO continuation token' {
        InModuleScope FinOpsAssess {
            $script:adoCalls = 0
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $script:adoCalls++
                if ($script:adoCalls -eq 1) {
                    return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u1' }); continuationToken = 'token-2' }
                }
                return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u2' }) }
            }

            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            $result = Invoke-FinOpsRestRequest -Uri 'https://dev.azure.com/org/_apis/userentitlements?api-version=7.1' -Auth $auth -Paging AdoContinuation -ValueProperty value
            @($result).Count | Should -Be 2
        }
    }

    It 'retries once on 429 with Retry-After and then succeeds' {
        InModuleScope FinOpsAssess {
            $script:attempts = 0
            Mock Start-Sleep {}
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $script:attempts++
                if ($script:attempts -eq 1) {
                    Set-Variable -Name 'responseHeaders' -Value @{ 'Retry-After' = '1' } -Scope 1
                    $response = [pscustomobject]@{ StatusCode = 429 }
                    $ex = [System.Exception]::new('too many requests')
                    $ex | Add-Member -MemberType NoteProperty -Name Response -Value $response
                    throw $ex
                }
                return [pscustomobject]@{ ok = $true }
            }

            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            $result = Invoke-FinOpsRestRequest -Uri 'https://graph.test/retry' -Auth $auth
            $result.ok | Should -BeTrue
            $script:attempts | Should -Be 2
            Assert-MockCalled Start-Sleep -Times 1 -Exactly
        }
    }

    It 'returns null on 404 when Accept404AsNull is supplied' {
        InModuleScope FinOpsAssess {
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $response = [pscustomobject]@{ StatusCode = 404 }
                $ex = [System.Exception]::new('not found')
                $ex | Add-Member -MemberType NoteProperty -Name Response -Value $response
                throw $ex
            }
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            $result = Invoke-FinOpsRestRequest -Uri 'https://graph.test/missing' -Auth $auth -Accept404AsNull
            $result | Should -Be $null
        }
    }

    It 'never writes request body or Authorization header to streams on failure' {
        InModuleScope FinOpsAssess {
            Mock Invoke-RestMethod {
                param($Method, $Uri, $Headers, $ResponseHeadersVariable)
                $null = $Method, $Uri, $Headers, $ResponseHeadersVariable
                $response = [pscustomobject]@{ StatusCode = 500 }
                $ex = [System.Exception]::new('server error')
                $ex | Add-Member -MemberType NoteProperty -Name Response -Value $response
                throw $ex
            }
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'secret-token'); Source = 'caller-bearer' }

            $all = @()
            try {
                $all = & { Invoke-FinOpsRestRequest -Uri 'https://graph.test/fail' -Auth $auth -Headers @{ probe = 'value' } -Verbose } *>&1
            } catch {
                $all += $_
            }
            $text = ($all | Out-String)
            $text | Should -Not -Match 'Authorization'
            $text | Should -Not -Match 'secret-token'
            $text | Should -Not -Match 'client_secret'
            $text | Should -Not -Match 'client_assertion'
        }
    }

    It 'rejects Method Post as a parameter-binding failure' {
        InModuleScope FinOpsAssess {
            $auth = [pscustomobject]@{ AccessToken = (New-TestSecureString -Value 'x'); Source = 'caller-bearer' }
            { Invoke-FinOpsRestRequest -Uri 'https://example.test' -Method Post -Auth $auth } |
                Should -Throw -ErrorId 'ParameterArgumentValidationError*'
        }
    }
}
