<#
.SYNOPSIS
    PowerShell wrapper around `finops-assess` for PowerShell-native operators.

.DESCRIPTION
    Invokes the `finops-assess` Python CLI without requiring the operator to
    interact with Python directly, and hands back the JSON report as a native
    PowerShell object so it can flow through the rest of a PowerShell
    pipeline (Group-Object, Where-Object, Export-Csv, …).

    This script is read-only by construction:
      * It only ever calls `finops-assess` subcommands that read data.
      * No `Invoke-Expression` — `finops-assess` is invoked with a
        validated argument array.
      * It never writes to or mutates any cloud system.

    Compatible with Windows PowerShell 5.1+ and PowerShell 7+ on
    Linux / macOS / Windows.

.PARAMETER InputDir
    Directory containing normalised CSV files (users.csv,
    license_assignments.csv, usage.csv, azure_resources.csv) and an
    optional overrides.yaml. Mutually exclusive with -Demo.

.PARAMETER OutputDir
    Directory to write reports into. Created if it does not exist.
    Defaults to the current directory.

.PARAMETER Format
    One of `json`, `html`, or `both`. Defaults to `both`.

.PARAMETER NoPiiRedaction
    Disable salted hashing of principals in the report (opt-in;
    redaction is on by default).

.PARAMETER Demo
    Run against the bundled synthetic tenant via `finops-assess demo`
    instead of an operator-supplied -InputDir.

.EXAMPLE
    PS> ./Invoke-FinOpsAssess.ps1 -Demo -OutputDir ./out
    Runs the bundled demo and writes demo-report.{json,html} to ./out.

.EXAMPLE
    PS> $report = ./Invoke-FinOpsAssess.ps1 -InputDir ./samples
    PS> $report.findings | Where-Object severity -eq 'high' | Format-Table

.NOTES
    Requires the `finops-assess` Python package to be installed and on
    the PATH. Install with `pip install finops-assess` or
    `pip install -e .` from a checkout.
#>
[CmdletBinding(DefaultParameterSetName = 'FromInputDir')]
param(
    [Parameter(ParameterSetName = 'FromInputDir', Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })]
    [string]$InputDir,

    [Parameter()]
    [string]$OutputDir = (Get-Location).Path,

    [Parameter()]
    [ValidateSet('json', 'html', 'both')]
    [string]$Format = 'both',

    [Parameter()]
    [switch]$NoPiiRedaction,

    [Parameter(ParameterSetName = 'Demo', Mandatory = $true)]
    [switch]$Demo
)

$ErrorActionPreference = 'Stop'

# Resolve the finops-assess executable cross-platform without invoking a shell.
$finopsCommand = Get-Command -Name 'finops-assess' -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $finopsCommand) {
    throw "finops-assess CLI not found on PATH. Install with 'pip install finops-assess'."
}
$finopsExe = $finopsCommand.Source

# Ensure the output directory exists.
$null = New-Item -ItemType Directory -Path $OutputDir -Force

if ($Demo.IsPresent) {
    $argList = @('demo', '--output-dir', $OutputDir)
    if ($NoPiiRedaction.IsPresent) { $argList += '--no-pii-redaction' }

    & $finopsExe @argList
    if ($LASTEXITCODE -ne 0) {
        throw "finops-assess demo failed with exit code $LASTEXITCODE."
    }
    $jsonPath = Join-Path -Path $OutputDir -ChildPath 'demo-report.json'
}
else {
    $jsonPath = Join-Path -Path $OutputDir -ChildPath 'report.json'
    $argList = @(
        'run',
        '--input', $InputDir,
        '--output', $jsonPath,
        '--format', $Format
    )
    if ($NoPiiRedaction.IsPresent) { $argList += '--no-pii-redaction' }
    if ($Format -in @('html', 'both')) {
        $htmlPath = Join-Path -Path $OutputDir -ChildPath 'report.html'
        $argList += @('--html-output', $htmlPath)
    }

    & $finopsExe @argList
    if ($LASTEXITCODE -ne 0) {
        throw "finops-assess run failed with exit code $LASTEXITCODE."
    }
}

# Emit the JSON report as a PowerShell object so callers can pipe it.
if (Test-Path -LiteralPath $jsonPath) {
    Get-Content -LiteralPath $jsonPath -Raw -Encoding utf8 | ConvertFrom-Json
}
