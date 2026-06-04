#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:DataRoot = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'data'
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsDataProjection' {
    It 'ships the projection files alongside the module' {
        foreach ($name in 'catalog.json', 'personas.json', 'rules.json', 'schema.json', 'playbooks.json') {
            Test-Path -LiteralPath (Join-Path $script:DataRoot $name) -PathType Leaf |
                Should -BeTrue -Because "$name must be packaged with the module"
        }
    }

    It 'loads via the real module path and returns projection collections' {
        InModuleScope FinOpsAssess {
            $data = Get-FinOpsDataProjection
            $data.PSObject.Properties.Name | Should -Contain 'Catalog'
            $data.PSObject.Properties.Name | Should -Contain 'Personas'
            $data.PSObject.Properties.Name | Should -Contain 'Rules'
            $data.PSObject.Properties.Name | Should -Contain 'Playbooks'
        }
    }

    It 'returns each collection as an array even via single-item assignment' {
        InModuleScope FinOpsAssess {
            $data = Get-FinOpsDataProjection
            # @() forces an array type; the loader guarantees this so callers
            # never have to guard against ConvertFrom-Json scalar-unwrapping.
            , $data.Catalog | Should -BeOfType ([System.Array])
            , $data.Personas | Should -BeOfType ([System.Array])
            , $data.Rules | Should -BeOfType ([System.Array])
        }
    }

    It 'loads the expected number of catalogue, persona, and rule entries' {
        InModuleScope FinOpsAssess {
            $data = Get-FinOpsDataProjection
            $data.Catalog.Count | Should -BeGreaterThan 0
            $data.Personas.Count | Should -BeGreaterThan 0
            $data.Rules.Count | Should -Be 28
        }
    }

    It 'preserves entry shape including resolved defaults' {
        InModuleScope FinOpsAssess {
            $data = Get-FinOpsDataProjection
            $rule = $data.Rules | Select-Object -First 1
            $rule.id | Should -Not -BeNullOrEmpty
            $rule.surface | Should -Not -BeNullOrEmpty
            $rule.PSObject.Properties.Name | Should -Contain 'enabled'
            $rule.PSObject.Properties.Name | Should -Contain 'evidence_key_version'
            $rule.PSObject.Properties.Name | Should -Contain 'adapter_class'
        }
    }

    It 'round-trips non-ASCII (UTF-8) text without corruption' {
        InModuleScope FinOpsAssess {
            $data = Get-FinOpsDataProjection
            $emDash = [char]0x2014
            $withEmDash = @($data.Catalog | Where-Object { $_.display_name -like "*$emDash*" })
            $withEmDash.Count | Should -BeGreaterThan 0 -Because 'the catalogue contains em-dash display names that must survive UTF-8 decode'
        }
    }

    It 'throws a clear error when a projection file is missing' {
        InModuleScope FinOpsAssess {
            $missing = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
            { Get-FinOpsDataProjection -DataRoot $missing } |
                Should -Throw -ExpectedMessage '*projection file is missing*'
        }
    }
}

Describe 'Test-FinOpsConfiguration includes the data projection check' {
    It 'reports a passing data-projection check' {
        $result = Test-FinOpsConfiguration -PassThru
        $result.Success | Should -BeTrue
        $projChecks = @($result.Checks | Where-Object { $_.Check -like 'data-projection-*' })
        $projChecks.Count | Should -Be 3
        @($projChecks | Where-Object { $_.Status -ne 'pass' }).Count | Should -Be 0
    }
}
