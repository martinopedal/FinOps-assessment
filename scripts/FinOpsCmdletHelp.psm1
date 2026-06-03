Set-StrictMode -Version Latest

function Get-HelpSectionBody {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$HelpText,

        [Parameter(Mandatory)]
        [string]$Section
    )

    $pattern = "(?ims)^\s*\.$([regex]::Escape($Section))\s*(?<body>.*?)(?=^\s*\.[A-Z][A-Z0-9_-]*\b|\z)"
    $match = [regex]::Match($HelpText, $pattern)
    if (-not $match.Success) {
        return ''
    }
    return [string]$match.Groups['body'].Value
}

function Test-FinOpsCmdletHelpCompleteness {
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param(
        [Parameter(Mandatory)]
        [string[]]$Name,

        [switch]$ThrowOnFailure
    )

    $offenders = [System.Collections.Generic.List[object]]::new()
    foreach ($cmdletName in $Name) {
        $command = Get-Command -Name $cmdletName -ErrorAction Stop
        $definition = [string]$command.Definition

        $synopsis = ''
        $descriptionText = ''
        $exampleCount = 0

        $helpBlockMatch = [regex]::Match($definition, '(?s)<#(?<help>.*?)#>')
        if ($helpBlockMatch.Success) {
            $helpText = [string]$helpBlockMatch.Groups['help'].Value
            $synopsis = Get-HelpSectionBody -HelpText $helpText -Section 'SYNOPSIS'
            $descriptionText = Get-HelpSectionBody -HelpText $helpText -Section 'DESCRIPTION'
            $exampleCount = [regex]::Matches($helpText, '(?im)^\s*\.EXAMPLE\b').Count
        } else {
            $help = Get-Help -Name $cmdletName -Full -ErrorAction Stop
            $synopsis = [string]$help.Synopsis
            $descriptionText = [string](
                @($help.Description | ForEach-Object { $_.Text }) -join [Environment]::NewLine
            )
            $exampleText = [string](Get-Help -Name $cmdletName -Examples | Out-String)
            if (-not [string]::IsNullOrWhiteSpace($exampleText) -and
                $exampleText -notmatch '(?im)no example') {
                $exampleCount = 1
            }
        }

        $missing = [System.Collections.Generic.List[string]]::new()
        if ([string]::IsNullOrWhiteSpace($synopsis) -or
            $synopsis.Trim() -ceq $cmdletName -or
            $synopsis.Trim() -match '^\{\{\s*Fill in the Synopsis\s*\}\}$') {
            $missing.Add('SYNOPSIS')
        }
        if ([string]::IsNullOrWhiteSpace($descriptionText)) {
            $missing.Add('DESCRIPTION')
        }
        if ($exampleCount -lt 1) {
            $missing.Add('EXAMPLE')
        }

        if ($missing.Count -gt 0) {
            $offenders.Add([pscustomobject]@{
                    Name    = $cmdletName
                    Missing = @($missing)
                })
        }
    }

    if ($ThrowOnFailure -and $offenders.Count -gt 0) {
        $details = @(
            $offenders | ForEach-Object { "$($_.Name) [$($_.Missing -join ',')]" }
        ) -join '; '
        throw "Help-completeness gate failed for: $details. Each public cmdlet needs non-empty .SYNOPSIS, .DESCRIPTION, and >=1 .EXAMPLE."
    }

    return @($offenders)
}

Export-ModuleMember -Function Test-FinOpsCmdletHelpCompleteness
