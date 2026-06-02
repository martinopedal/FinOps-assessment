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
        $exported | Should -Be @('Get-FinOpsInfo', 'Test-FinOpsConfiguration')
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

    It 'advertises a read-only posture with the scope guard NOT yet enforced' {
        $script:info.ReadOnly | Should -BeTrue
        $script:info.RuntimeScopeGuardEnforced | Should -BeFalse
        $script:info.PostureStatement | Should -Match 'not yet implemented'
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
    It 'contains no forbidden patterns in module source' {
        $scanRoot = Join-Path $PSScriptRoot '..' 'FinOpsAssess'
        $files = Get-ChildItem -Path $scanRoot -Recurse -Include '*.ps1', '*.psm1', '*.psd1' -File

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
}
