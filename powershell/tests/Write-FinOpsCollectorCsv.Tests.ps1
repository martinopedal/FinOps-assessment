#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:ModuleManifest = Join-Path $PSScriptRoot '..' 'FinOpsAssess' 'FinOpsAssess.psd1'
    Import-Module $script:ModuleManifest -Force
}

AfterAll {
    Remove-Module FinOpsAssess -Force -ErrorAction SilentlyContinue
}

Describe 'Write-FinOpsCollectorCsv' {
    BeforeEach {
        $script:OutDir = Join-Path $PSScriptRoot 'tmp-csv'
        $script:OutPath = Join-Path $script:OutDir 'collector.csv'
        Remove-Item -LiteralPath $script:OutDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    AfterEach {
        Remove-Item -LiteralPath $script:OutDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    It 'preserves header order and writes empty cells for null values' {
        InModuleScope FinOpsAssess -Parameters @{ OutPath = $script:OutPath } {
            param($OutPath)
            $header = @('b', 'a', 'c')
            $rows = @(
                [pscustomobject]@{ b = '1'; a = $null; c = '3' }
            )
            Write-FinOpsCollectorCsv -Path $OutPath -Header $header -Row $rows | Out-Null
            $text = [System.IO.File]::ReadAllText($OutPath, [System.Text.Encoding]::UTF8)
            $text.Split("`n")[0] | Should -Be 'b,a,c'
            $text.Split("`n")[1] | Should -Be '1,,3'
        }
    }

    It 'writes LF line endings and UTF-8 without BOM' {
        InModuleScope FinOpsAssess -Parameters @{ OutPath = $script:OutPath } {
            param($OutPath)
            $header = @('a')
            $rows = @([pscustomobject]@{ a = 'x' })
            Write-FinOpsCollectorCsv -Path $OutPath -Header $header -Row $rows | Out-Null
            $bytes = [System.IO.File]::ReadAllBytes($OutPath)
            $bytes | Should -Not -Contain 0x0D
            @($bytes[0], $bytes[1], $bytes[2]) | Should -Not -Be @(0xEF, 0xBB, 0xBF)
        }
    }

    It 'quotes comma quote and newline values per RFC 4180' {
        InModuleScope FinOpsAssess -Parameters @{ OutPath = $script:OutPath } {
            param($OutPath)
            $header = @('a', 'b', 'c')
            $rows = @(
                [pscustomobject]@{
                    a = 'one,two'
                    b = 'say "hi"'
                    c = "multi`nline"
                }
            )
            Write-FinOpsCollectorCsv -Path $OutPath -Header $header -Row $rows | Out-Null
            $text = [System.IO.File]::ReadAllText($OutPath, [System.Text.Encoding]::UTF8)
            $text | Should -Match '"one,two","say ""hi""","multi'
        }
    }

    It 'cleans up temporary file after atomic move' {
        InModuleScope FinOpsAssess -Parameters @{ OutPath = $script:OutPath } {
            param($OutPath)
            Write-FinOpsCollectorCsv -Path $OutPath -Header @('a') -Row @([pscustomobject]@{ a = 'x' }) | Out-Null
            Test-Path -LiteralPath ($OutPath + '.tmp') | Should -BeFalse
        }
    }

    It 'round-trips via ConvertFrom-FinOpsCsvText to the same cells' {
        InModuleScope FinOpsAssess -Parameters @{ OutPath = $script:OutPath } {
            param($OutPath)
            $header = @('x', 'y')
            $rows = @(
                [pscustomobject]@{ x = '1'; y = '2' },
                [pscustomobject]@{ x = ''; y = "a`nb" }
            )
            Write-FinOpsCollectorCsv -Path $OutPath -Header $header -Row $rows | Out-Null
            $raw = [System.IO.File]::ReadAllText($OutPath, [System.Text.Encoding]::UTF8)
            $parsed = ConvertFrom-FinOpsCsvText -Text $raw
            $parsed[0] | Should -Be @('x', 'y')
            $parsed[1] | Should -Be @('1', '2')
            $parsed[2] | Should -Be @('', "a`nb")
        }
    }
}
