Set-StrictMode -Version Latest

$script:FinOpsTriageCsvColumns = @(
    'finding_ref',
    'source_finding_index',
    'rule_id',
    'surface',
    'severity',
    'confidence',
    'principal',
    'priority_bucket',
    'priority_rationale',
    'suggested_owner_role',
    'current_sku',
    'recommended_sku',
    'estimated_monthly_savings_usd',
    'evidence_ref',
    'verification_checklist',
    'followup_questions',
    'advisory'
)

function Get-FinOpsTriageCsvCell {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter()] [AllowNull()] [object] $Value)

    if ($null -eq $Value) { return '' }
    if ($Value -is [bool]) { return ([bool] $Value) ? 'True' : 'False' }
    if (
        $Value -is [int] -or $Value -is [long] -or $Value -is [short] -or
        $Value -is [byte] -or $Value -is [sbyte] -or $Value -is [uint16] -or
        $Value -is [uint32]
    ) {
        return ([string] $Value)
    }
    if ($Value -is [double] -or $Value -is [float] -or $Value -is [decimal]) {
        return Format-FinOpsPyFloat -Value ([double] $Value)
    }

    $text = [string] $Value
    if ($text.Length -gt 0 -and $script:FinOpsFormulaPrefixes -contains $text[0]) {
        return "'" + $text
    }
    return $text
}

function ConvertTo-FinOpsTriageCsv {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [object] $Triage)

    $lines = [System.Collections.Generic.List[string]]::new()
    $header = ($script:FinOpsTriageCsvColumns | ForEach-Object { ConvertTo-FinOpsCsvField -Value $_ }) -join ','
    [void] $lines.Add($header)

    foreach ($item in @($Triage.items)) {
        $row = [ordered]@{
            finding_ref                   = $item.finding_ref
            source_finding_index          = $item.source_finding_index
            rule_id                       = $item.rule_id
            surface                       = $item.surface
            severity                      = $item.severity
            confidence                    = $item.confidence
            principal                     = $item.principal
            priority_bucket               = $item.priority_bucket
            priority_rationale            = $item.priority_rationale
            suggested_owner_role          = $item.suggested_owner_role
            current_sku                   = $item.current_sku
            recommended_sku               = $item.recommended_sku
            estimated_monthly_savings_usd = $item.estimated_monthly_savings_usd
            evidence_ref                  = $item.evidence_ref
            verification_checklist        = (@($item.verification_checklist) -join ' | ')
            followup_questions            = (@($item.followup_questions) -join ' | ')
            advisory                      = $item.advisory
        }
        $cells = foreach ($column in $script:FinOpsTriageCsvColumns) {
            ConvertTo-FinOpsCsvField -Value (Get-FinOpsTriageCsvCell -Value $row[$column])
        }
        [void] $lines.Add(($cells -join ','))
    }

    return ($lines -join "`n") + "`n"
}

function Write-FinOpsTriageCsv {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $Triage,
        [Parameter(Mandatory)] [string] $OutputPath
    )

    $directory = Split-Path -Parent $OutputPath
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $csv = ConvertTo-FinOpsTriageCsv -Triage $Triage
    [System.IO.File]::WriteAllText($OutputPath, ($csv -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
    return $OutputPath
}

function Write-FinOpsTriageJson {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [object] $Triage,
        [Parameter(Mandatory)] [string] $OutputPath
    )

    $directory = Split-Path -Parent $OutputPath
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $json = $Triage | ConvertTo-Json -Depth 64
    [System.IO.File]::WriteAllText($OutputPath, ($json -replace "`r`n", "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    return $OutputPath
}
