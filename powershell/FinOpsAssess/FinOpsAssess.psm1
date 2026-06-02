Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Module-root anchored paths so dot-sourced Private/Public files resolve
# the same way regardless of the caller's location (cross-platform).
$script:ModuleRoot = $PSScriptRoot

# Repo root is two levels up from powershell/FinOpsAssess/. Computed
# without requiring the path to exist so the module still imports when
# installed standalone (where the Python source tree is absent).
$script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))

# Dot-source Private helpers first, then Public cmdlets.
$privateFiles = @(Get-ChildItem -Path (Join-Path $PSScriptRoot 'Private') -Filter '*.ps1' -ErrorAction SilentlyContinue)
$publicFiles  = @(Get-ChildItem -Path (Join-Path $PSScriptRoot 'Public') -Filter '*.ps1' -ErrorAction SilentlyContinue)

foreach ($file in $privateFiles + $publicFiles) {
    . $file.FullName
}

Export-ModuleMember -Function $publicFiles.BaseName
