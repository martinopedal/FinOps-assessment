#requires -Module @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
    $script:HelpModulePath = Join-Path $script:RepoRoot 'scripts' 'FinOpsCmdletHelp.psm1'
    $script:ManifestPath = Join-Path $script:RepoRoot 'powershell' 'FinOpsAssess' 'FinOpsAssess.psd1'
    Import-Module $script:HelpModulePath -Force
}

Describe 'Test-FinOpsCmdletHelpCompleteness' {
    AfterEach {
        foreach ($name in @('Test-DocHelpComplete', 'Test-DocHelpMissingDescription', 'Test-DocHelpMissingExample', 'Test-DocHelpPlaceholderSynopsis')) {
            Remove-Item -LiteralPath "Function:\global:$name" -ErrorAction SilentlyContinue
        }
    }

    It 'passes for a cmdlet with synopsis, description, and example' {
        function global:Test-DocHelpComplete {
            <#
            .SYNOPSIS
                Complete help block.

            .DESCRIPTION
                This function has complete comment-based help.

            .EXAMPLE
                Test-DocHelpComplete
            #>
            [CmdletBinding()]
            param()
        }

        $offenders = @(Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpComplete')
        $offenders.Count | Should -Be 0
    }

    It 'flags a cmdlet that is missing .DESCRIPTION' {
        function global:Test-DocHelpMissingDescription {
            <#
            .SYNOPSIS
                Missing description block.

            .EXAMPLE
                Test-DocHelpMissingDescription
            #>
            [CmdletBinding()]
            param()
        }

        $offenders = Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpMissingDescription'
        $offenders.Count | Should -Be 1
        @($offenders[0].Missing) | Should -Contain 'DESCRIPTION'
        {
            Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpMissingDescription' -ThrowOnFailure
        } | Should -Throw -ExpectedMessage '*Test-DocHelpMissingDescription [[]DESCRIPTION[]]*'
    }

    It 'flags a cmdlet that is missing .EXAMPLE' {
        function global:Test-DocHelpMissingExample {
            <#
            .SYNOPSIS
                Missing example block.

            .DESCRIPTION
                This function intentionally has no example.
            #>
            [CmdletBinding()]
            param()
        }

        $offenders = Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpMissingExample'
        $offenders.Count | Should -Be 1
        @($offenders[0].Missing) | Should -Contain 'EXAMPLE'
        {
            Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpMissingExample' -ThrowOnFailure
        } | Should -Throw -ExpectedMessage '*Test-DocHelpMissingExample [[]EXAMPLE[]]*'
    }

    It 'flags a cmdlet that uses the placeholder synopsis text' {
        function global:Test-DocHelpPlaceholderSynopsis {
            <#
            .SYNOPSIS
                {{ Fill in the Synopsis }}

            .DESCRIPTION
                Description exists.

            .EXAMPLE
                Test-DocHelpPlaceholderSynopsis
            #>
            [CmdletBinding()]
            param()
        }

        $offenders = Test-FinOpsCmdletHelpCompleteness -Name 'Test-DocHelpPlaceholderSynopsis'
        $offenders.Count | Should -Be 1
        @($offenders[0].Missing) | Should -Contain 'SYNOPSIS'
    }

    It 'passes all exported FinOpsAssess cmdlets' {
        Import-Module $script:ManifestPath -Force
        $manifest = Import-PowerShellDataFile -LiteralPath $script:ManifestPath
        $offenders = Test-FinOpsCmdletHelpCompleteness -Name @($manifest.FunctionsToExport)
        $offenders | Should -BeNullOrEmpty
    }
}
