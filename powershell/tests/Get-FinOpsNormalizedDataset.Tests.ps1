#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
    $script:DemoDir = Join-Path $script:RepoRoot 'src' 'finops_assess' 'demo'
    $script:GoldenPath = Join-Path $script:RepoRoot 'tests' 'fixtures' 'ps_conformance' 'demo-normalised.json'
    Import-Module $script:ModuleManifest -Force

    # Run the private normaliser over a directory and hand the result back
    # across the module-scope boundary as a plain object tree.
    function script:Get-NormalizedDemo {
        param([string] $Dir = $script:DemoDir)
        InModuleScope FinOpsAssess -Parameters @{ d = $Dir } {
            param($d)
            Get-FinOpsNormalizedDataset -InputDirectory $d
        }
    }

    function script:New-CsvDir {
        param([hashtable] $Files)
        $dir = Join-Path $TestDrive ([System.Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        foreach ($name in $Files.Keys) {
            $p = Join-Path $dir $name
            [System.IO.File]::WriteAllText($p, $Files[$name])
        }
        $dir
    }

    function script:Invoke-Normalize {
        param([string] $Dir)
        InModuleScope FinOpsAssess -Parameters @{ d = $Dir } {
            param($d)
            Get-FinOpsNormalizedDataset -InputDirectory $d
        }
    }

    function script:Test-NumberLike {
        param($Value)
        return ($Value -is [int]) -or ($Value -is [long]) -or `
            ($Value -is [double]) -or ($Value -is [decimal]) -or ($Value -is [single])
    }

    function script:Get-NamedPair {
        param($Obj)
        $pairs = [ordered]@{}
        if ($Obj -is [System.Collections.IDictionary]) {
            foreach ($k in $Obj.Keys) { $pairs[[string]$k] = $Obj[$k] }
        } else {
            foreach ($prop in $Obj.PSObject.Properties) { $pairs[$prop.Name] = $prop.Value }
        }
        $pairs
    }

    # Type-aware deep compare. Returns $null on match, else a path string for
    # the first mismatch. Numbers compare by value (int vs double is fine);
    # objects compare by key set; arrays compare by length then element-wise.
    function script:Compare-FinOpsTree {
        param($Expected, $Actual, [string] $Path = '$')

        if ($null -eq $Expected) {
            if ($null -ne $Actual) { return "$Path : expected null, got '$Actual'" }
            return $null
        }
        if ($null -eq $Actual) { return "$Path : expected '$Expected', got null" }

        if (script:Test-NumberLike $Expected) {
            if (-not (script:Test-NumberLike $Actual)) {
                return "$Path : expected number $Expected, got non-number '$Actual'"
            }
            $e = [double] $Expected
            $a = [double] $Actual
            $tol = 1e-9 * [math]::Max(1.0, [math]::Abs($e))
            if ([math]::Abs($e - $a) -gt $tol) {
                return "$Path : expected number $Expected, got $Actual"
            }
            return $null
        }

        if ($Expected -is [bool]) {
            if ($Actual -isnot [bool]) { return "$Path : expected bool $Expected, got '$Actual'" }
            if ($Expected -ne $Actual) { return "$Path : expected $Expected, got $Actual" }
            return $null
        }

        if ($Expected -is [string]) {
            if ([string]$Expected -cne [string]$Actual) {
                return "$Path : expected '$Expected', got '$Actual'"
            }
            return $null
        }

        $expIsList = ($Expected -is [System.Array]) -or ($Expected -is [System.Collections.IList])
        if ($expIsList) {
            $actList = @($Actual)
            $expList = @($Expected)
            if ($expList.Count -ne $actList.Count) {
                return "$Path : expected $($expList.Count) item(s), got $($actList.Count)"
            }
            for ($i = 0; $i -lt $expList.Count; $i++) {
                $r = script:Compare-FinOpsTree $expList[$i] $actList[$i] "$Path[$i]"
                if ($r) { return $r }
            }
            return $null
        }

        # Object / mapping.
        $expPairs = script:Get-NamedPair $Expected
        $actPairs = script:Get-NamedPair $Actual
        $expKeys = @($expPairs.Keys | Sort-Object)
        $actKeys = @($actPairs.Keys | Sort-Object)
        $missing = $expKeys | Where-Object { $_ -notin $actKeys }
        $extra = $actKeys | Where-Object { $_ -notin $expKeys }
        if ($missing) { return "$Path : missing key(s): $($missing -join ', ')" }
        if ($extra) { return "$Path : unexpected key(s): $($extra -join ', ')" }
        foreach ($k in $expKeys) {
            $r = script:Compare-FinOpsTree $expPairs[$k] $actPairs[$k] "$Path.$k"
            if ($r) { return $r }
        }
        return $null
    }
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Get-FinOpsNormalizedDataset over the demo tenant' {
    BeforeAll {
        $script:Demo = script:Get-NormalizedDemo
    }

    It 'produces every NormalizedDataset field' {
        $names = $script:Demo.PSObject.Properties.Name
        foreach ($f in 'users', 'assignments', 'usage', 'm365_family_summaries',
            'azure_resources', 'azure_reservations', 'azure_log_workspaces',
            'azure_benefit_recommendations', 'github_seats', 'github_orgs',
            'ado_seats', 'ado_orgs', 'overrides') {
            $names | Should -Contain $f
        }
    }

    It 'reads the expected record counts' {
        @($script:Demo.users).Count | Should -Be 11
        @($script:Demo.assignments).Count | Should -Be 13
        @($script:Demo.usage).Count | Should -Be 34
        @($script:Demo.azure_resources).Count | Should -Be 10
        @($script:Demo.azure_reservations).Count | Should -Be 2
        @($script:Demo.azure_log_workspaces).Count | Should -Be 2
        @($script:Demo.github_seats).Count | Should -Be 4
        @($script:Demo.github_orgs).Count | Should -Be 1
        @($script:Demo.ado_seats).Count | Should -Be 5
        @($script:Demo.ado_orgs).Count | Should -Be 1
    }

    It 'emits non-CSV-backed fields as empty lists' {
        @($script:Demo.m365_family_summaries).Count | Should -Be 0
        @($script:Demo.azure_benefit_recommendations).Count | Should -Be 0
    }

    It 'coerces scalar types and nulls correctly' {
        $alice = $script:Demo.users | Where-Object { $_.principal -eq 'alice@contoso.example' }
        $alice.account_enabled | Should -BeOfType ([bool])
        $alice.account_enabled | Should -BeTrue
        $alice.mailbox_size_gb | Should -BeOfType ([double])
        $alice.last_sign_in_days | Should -Be 3
        , $alice.groups | Should -BeOfType ([System.Array])
        $alice.groups | Should -Contain 'frontline'

        $hugo = $script:Demo.users | Where-Object { $_.principal -eq 'hugo@external.example' }
        $hugo.job_title | Should -BeNullOrEmpty
        $hugo.mailbox_size_gb | Should -BeNullOrEmpty
    }

    It 'reads overrides.yaml as a flat key/value map' {
        $script:Demo.overrides | Should -BeOfType ([System.Collections.IDictionary])
        $script:Demo.overrides.Keys.Count | Should -BeGreaterThan 0
    }
}

Describe 'Layer-2 conformance: PowerShell normalised dataset matches the Python golden' {
    It 'ships the committed golden fixture' {
        Test-Path -LiteralPath $script:GoldenPath -PathType Leaf |
            Should -BeTrue -Because 'scripts/generate_ps_conformance_fixtures.py must have produced it'
    }

    It 'deep-equals the Python-generated normalised demo dataset' {
        $goldenJson = [System.IO.File]::ReadAllText($script:GoldenPath)
        $expected = $goldenJson | ConvertFrom-Json
        $actual = script:Get-NormalizedDemo
        $diff = script:Compare-FinOpsTree $expected $actual
        $diff | Should -BeNullOrEmpty -Because "PowerShell normaliser diverged from Python: $diff"
    }
}

Describe 'Get-FinOpsNormalizedDataset strict-column contract' {
    It 'rejects an unknown CSV column' {
        $dir = script:New-CsvDir @{ 'users.csv' = "principal,bogus`nalice@x,1`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage "*unknown CSV column 'bogus'*"
    }

    It 'rejects a row with a non-empty cell beyond the header' {
        $dir = script:New-CsvDir @{ 'github_orgs.csv' = "org`ncontoso,extra`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage '*beyond the declared header columns*'
    }

    It 'rejects an unparseable boolean' {
        $dir = script:New-CsvDir @{ 'users.csv' = "principal,account_enabled`nalice@x,maybe`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage "*cannot parse bool 'maybe'*"
    }

    It 'rejects a value outside the enum (literal)' {
        $dir = script:New-CsvDir @{ 'ado_seats.csv' = "org,principal,sku_id,seat_type`nc,p@x,ADO.BASIC,platinum`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage '*is not one of*'
    }

    It 'enforces numeric lower bounds (ge)' {
        $dir = script:New-CsvDir @{ 'users.csv' = "principal,mailbox_size_gb`nalice@x,-5`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage '*less than minimum*'
    }

    It 'rejects a missing required value' {
        $dir = script:New-CsvDir @{ 'ado_orgs.csv' = "org,purchased_parallel_jobs`n,10`n" }
        { script:Invoke-Normalize $dir } | Should -Throw -ExpectedMessage '*required value is missing*'
    }

    It 'allows fewer cells than the header (treated as empty)' {
        $dir = script:New-CsvDir @{ 'users.csv' = "principal,display_name,department`nalice@x`n" }
        $ds = script:Invoke-Normalize $dir
        $u = @($ds.users)
        $u.Count | Should -Be 1
        $u[0].principal | Should -Be 'alice@x'
        $u[0].department | Should -BeNullOrEmpty
    }
}

Describe 'Read-FinOpsOverrides mini-parser' {
    It 'rejects nested / non-flat YAML' {
        $dir = script:New-CsvDir @{ 'overrides.yaml' = "parent:`n  child: 1`n" }
        { script:Invoke-Normalize $dir } | Should -Throw
    }
}
