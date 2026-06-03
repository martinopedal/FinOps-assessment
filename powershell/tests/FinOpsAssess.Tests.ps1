#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'FinOpsAssess module surface' {
    It 'exports exactly the expected public functions' {
        $exported = (Get-Command -Module FinOpsAssess -CommandType Function).Name | Sort-Object
        $exported | Should -Be @('Assert-FinOpsReadOnlyScope', 'Export-FinOpsFocusAligned', 'Export-FinOpsPlaybook', 'Get-FinOpsInfo', 'Invoke-FinOpsAssessment', 'Invoke-FinOpsLiveCollection', 'Invoke-FinOpsTriage', 'Test-FinOpsConfiguration', 'Test-FinOpsReadOnlyScope')
    }

    It 'declares PowerShell 7.2+ as the minimum supported version' {
        $manifest = Import-PowerShellDataFile -Path $script:ModuleManifest
        $manifest.PowerShellVersion | Should -Be '7.2'
        $manifest.CompatiblePSEditions | Should -Be @('Core')
    }
}

Describe 'Get-FinOpsInfo' {
    BeforeAll { $script:info = Get-FinOpsInfo }

    It 'reports a module version that matches the manifest' {
        $manifest = Import-PowerShellDataFile -Path $script:ModuleManifest
        $script:info.ModuleVersion | Should -Be $manifest.ModuleVersion
    }

    It 'advertises a read-only posture with Graph enforcement and partial rollout' {
        $script:info.ReadOnly | Should -BeTrue
        $script:info.RuntimeScopeGuardEnforced | Should -BeTrue
        $script:info.PostureStatement | Should -Match 'Live collectors enforce'
        $script:info.PostureStatement | Should -Match 'Graph'
        $script:info.PostureStatement | Should -Match 'AzureResourceManager'
        $script:info.PostureStatement | Should -Not -Match 'no cloud calls, collectors, or mutation paths ship in this phase'
    }

    It 'reports structured scope-guard coverage and per-surface enforcement' {
        $script:info.ScopeGuard.Available | Should -BeTrue
        $script:info.ScopeGuard.Enforced | Should -Be 'partial'
        $script:info.ScopeGuard.DefaultPolicy | Should -Be 'fail-closed-on-write-or-unknown'
        $script:info.ScopeGuard.EnforcedBySurface.Graph | Should -BeTrue
        $script:info.ScopeGuard.EnforcedBySurface.AzureResourceManager | Should -BeTrue
        $script:info.ScopeGuard.EnforcedBySurface.GitHub | Should -BeFalse
        $script:info.ScopeGuard.EnforcedBySurface.AzureDevOps | Should -BeFalse
        $script:info.ScopeGuard.Coverage.AzureResourceManager | Should -Match 'operator-attested via two-key consent'
    }

    It 'lists the four in-scope surfaces' {
        foreach ($surface in @('Microsoft 365', 'Azure', 'GitHub', 'Azure DevOps')) {
            $script:info.Surfaces | Should -Contain $surface
        }
    }
}

Describe 'Version lock between the PowerShell module and the Python package' {
    It 'manifest ModuleVersion equals the Python __version__' {
        $manifest = Import-PowerShellDataFile -Path $script:ModuleManifest
        $initPath = Join-Path $script:RepoRoot 'src' 'finops_assess' '__init__.py'
        Test-Path -LiteralPath $initPath | Should -BeTrue
        $content = Get-Content -LiteralPath $initPath -Raw
        $match = [regex]::Match($content, '__version__\s*=\s*"([^"]+)"')
        $match.Success | Should -BeTrue
        $manifest.ModuleVersion | Should -Be $match.Groups[1].Value
    }
}

Describe 'Test-FinOpsConfiguration' {
    It 'returns a successful structured result inside the repo tree' {
        $result = Test-FinOpsConfiguration -PassThru
        $result.Success | Should -BeTrue
        ($result.Checks | Where-Object { $_.Check -eq 'version-lock' }).Status | Should -Be 'pass'
    }
}

Describe 'Read-only tripwire: no mutation-shaped code in the module' {
    BeforeAll {
        # The scope-guard policy file is the ONE legitimate home for the
        # forbidden literal patterns (it enumerates them to detect them).
        # Every other module file must stay clean.
        $script:PolicyFileName = 'Get-FinOpsReadOnlyScopePolicy.ps1'
    }

    It 'contains no forbidden patterns in module source' {
        $scanRoot = Join-Path $PSScriptRoot '..' 'FinOpsAssess'
        $files = Get-ChildItem -Path $scanRoot -Recurse -Include '*.ps1', '*.psm1', '*.psd1' -File |
            Where-Object { $_.Name -ne $script:PolicyFileName }

        $patterns = @(
            'Invoke-Expression',
            '\biex\b',
            '\.ReadWrite\.',
            '(Set|Remove|New|Update|Add|Disable|Enable)-Mg',
            '(Set|Remove|New|Update)-Az[A-Z]',
            'Invoke-(RestMethod|WebRequest)[^\r\n]*-Method\s*[''"]?(POST|PUT|PATCH|DELETE)'
        )

        $hits = foreach ($file in $files) {
            $text = Get-Content -LiteralPath $file.FullName -Raw
            foreach ($pattern in $patterns) {
                if ($text -match $pattern) { "$($file.Name) matched /$pattern/" }
            }
        }

        $hits | Should -BeNullOrEmpty
    }

    It 'counter-tripwire: the ONLY file carrying the .ReadWrite. literal is the policy file' {
        $scanRoot = Join-Path $PSScriptRoot '..' 'FinOpsAssess'
        $files = Get-ChildItem -Path $scanRoot -Recurse -Include '*.ps1', '*.psm1', '*.psd1' -File

        $carriers = foreach ($file in $files) {
            $text = Get-Content -LiteralPath $file.FullName -Raw
            if ($text -match '\.ReadWrite\.') { $file.Name }
        }

        @($carriers) | Should -Be @($script:PolicyFileName)
    }
}

Describe 'Read-only scope guard: write/admin scopes are refused' {
    BeforeAll {
        # Build a minimal JWT (header.payload.signature) from a claims
        # hashtable so the corpus round-trips through real base64url decoding.
        function script:New-TestJwt {
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

    It 'refuses a Graph delegated write scope (scp)' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'User.ReadWrite.All' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw -ExpectedMessage '*write/admin scope*'
    }

    It 'refuses a Graph application write role (roles)' {
        $jwt = New-TestJwt -Claims @{ aud = '00000003-0000-0000-c000-000000000000'; roles = @('Directory.ReadWrite.All') }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw -ExpectedMessage '*write/admin scope*'
    }

    It 'refuses a mixed read+write token (write wins)' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'User.Read.All Group.ReadWrite.All' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw -ExpectedMessage '*Group.ReadWrite.All*'
    }

    It 'refuses .AccessAsUser.All (write capability without the word Write)' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'Directory.AccessAsUser.All' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw
    }

    It 'refuses Mail.Send (mutation that does not say Write)' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'Mail.Send' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw
    }

    It 'refuses full_access_as_app (Exchange full mailbox)' {
        $jwt = New-TestJwt -Claims @{ aud = '00000003-0000-0000-c000-000000000000'; roles = @('full_access_as_app') }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw
    }

    It 'refuses an Azure DevOps write scope' {
        $jwt = New-TestJwt -Claims @{ aud = '499b84ac-1321-427f-aa17-267ca6975798'; scp = 'vso.work_write' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw -ExpectedMessage '*write/admin scope*'
    }

    It 'refuses GitHub classic write/admin scopes' {
        { Assert-FinOpsReadOnlyScope -Scope 'repo', 'read:org' -Surface GitHub } | Should -Throw
        { Assert-FinOpsReadOnlyScope -Scope 'admin:org' -Surface GitHub } | Should -Throw
        { Assert-FinOpsReadOnlyScope -Scope 'workflow' -Surface GitHub } | Should -Throw
    }

    It 'refuses GitHub public_repo (read/write on public repos)' {
        # public_repo grants read/WRITE to code, statuses, and deployments on
        # public repos -- a write-capable "read-shaped" scope.
        { Assert-FinOpsReadOnlyScope -Scope 'public_repo' -Surface GitHub } | Should -Throw
        (Test-FinOpsReadOnlyScope -Scope 'public_repo' -Surface GitHub).IsReadOnly | Should -BeFalse
    }

    It 'refuses GitHub repo:status (read/write on commit statuses)' {
        { Assert-FinOpsReadOnlyScope -Scope 'repo:status' -Surface GitHub } | Should -Throw
        (Test-FinOpsReadOnlyScope -Scope 'repo:status' -Surface GitHub).IsReadOnly | Should -BeFalse
    }
}

Describe 'Read-only scope guard: read-only credentials pass' {
    BeforeAll {
        function script:New-TestJwt {
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

    It 'passes a Graph read-only delegated token' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'User.Read.All Directory.Read.All' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Not -Throw
        (Test-FinOpsReadOnlyScope -AccessToken $jwt).IsReadOnly | Should -BeTrue
    }

    It 'passes a Graph read-only application token' {
        $jwt = New-TestJwt -Claims @{ aud = '00000003-0000-0000-c000-000000000000'; roles = @('User.Read.All', 'Organization.Read.All') }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Not -Throw
    }

    It 'passes GitHub read-only scopes' {
        { Assert-FinOpsReadOnlyScope -Scope 'read:org', 'read:packages' -Surface GitHub } | Should -Not -Throw
    }

    It 'passes an Azure DevOps read scope' {
        $jwt = New-TestJwt -Claims @{ aud = '499b84ac-1321-427f-aa17-267ca6975798'; scp = 'vso.work' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Not -Throw
    }

    It 'classifies the surface from the audience claim' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://graph.microsoft.com'; scp = 'User.Read.All' }
        (Test-FinOpsReadOnlyScope -AccessToken $jwt).Surface | Should -Be 'Graph'
    }
}

Describe 'Read-only scope guard: fail-closed on unknown / insufficient claims' {
    BeforeAll {
        function script:New-TestJwt {
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

    It 'refuses an ARM token (read-only not provable from claims)' {
        $jwt = New-TestJwt -Claims @{ aud = 'https://management.azure.com'; scp = 'user_impersonation' }
        { Assert-FinOpsReadOnlyScope -AccessToken $jwt } | Should -Throw
        $r = Test-FinOpsReadOnlyScope -AccessToken $jwt
        $r.Surface | Should -Be 'AzureResourceManager'
        $r.ClaimsSufficient | Should -BeFalse
        $r.IsReadOnly | Should -BeFalse
    }

    It 'refuses an unrecognised scope by default (fail-closed)' {
        { Assert-FinOpsReadOnlyScope -Scope 'Something.Mysterious.All' } | Should -Throw -ExpectedMessage '*fail-closed*'
    }

    It 'refuses an empty granted-scope list (e.g. fine-grained PAT)' {
        { Assert-FinOpsReadOnlyScope -Scope @() } | Should -Throw
    }

    It 'refuses a token-shaped string passed as a scope' {
        { Assert-FinOpsReadOnlyScope -Scope 'github_pat_11ABCDEF0example' } | Should -Throw
    }

    It '-AllowUnknownScopes downgrades unknown to a warning but still passes' {
        { Assert-FinOpsReadOnlyScope -Scope 'Something.Mysterious.All' -AllowUnknownScopes -WarningAction SilentlyContinue } | Should -Not -Throw
    }

    It '-AllowUnknownScopes does NOT rescue a write scope' {
        { Assert-FinOpsReadOnlyScope -Scope 'repo' -Surface GitHub -AllowUnknownScopes -WarningAction SilentlyContinue } | Should -Throw -ExpectedMessage '*write/admin scope*'
    }

    It 'rejects a malformed (non-JWT) token' {
        { Test-FinOpsReadOnlyScope -AccessToken 'not-a-jwt' } | Should -Throw
    }
}
