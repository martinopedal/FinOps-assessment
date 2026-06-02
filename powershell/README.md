# FinOpsAssess (PowerShell engine)

Native PowerShell module delivered **side by side** with the Python
`finops-assess` tool. Same read-only FinOps assessment surface
(Microsoft 365, Azure, GitHub, Azure DevOps); the engines are kept in
parity by a cross-engine conformance harness.

See [`../docs/powershell.md`](../docs/powershell.md) for the full cmdlet
reference, parity matrix, and conformance contract, and
[`../docs/decisions/0001-powershell-side-by-side.md`](../docs/decisions/0001-powershell-side-by-side.md)
for the architecture decision.

## Status: Phase 0 (scaffold)

This release proves the runtime and the CI gate only. It ships two
cmdlets and **no cloud collectors**:

| Cmdlet                     | Purpose                                              |
|----------------------------|------------------------------------------------------|
| `Get-FinOpsInfo`           | Module version, read-only posture, in-scope surfaces |
| `Test-FinOpsConfiguration` | Structural self-test + version lock to the Python pkg |

> **Read-only posture, not yet enforced at runtime.** The module makes
> no cloud calls and contains no mutation paths, but the credential
> scope guard (which refuses to run against a write-scoped token) lands
> in a later, separately reviewed release. `Get-FinOpsInfo` reports
> `RuntimeScopeGuardEnforced = $false` in Phase 0.

## Requirements

PowerShell **7.2+** on Linux, macOS, or Windows. Windows PowerShell 5.1
is unsupported.

## Quick start (from a clone)

```powershell
Import-Module ./powershell/FinOpsAssess/FinOpsAssess.psd1 -Force
Get-FinOpsInfo
Test-FinOpsConfiguration
```

## Develop & test

```powershell
Install-Module Pester -MinimumVersion 5.5.0 -Scope CurrentUser
Install-Module PSScriptAnalyzer -Scope CurrentUser

Invoke-ScriptAnalyzer -Path ./powershell -Recurse -Settings ./powershell/PSScriptAnalyzerSettings.psd1
Invoke-Pester -Path ./powershell/tests
```

CI runs the same two gates across `{ubuntu, windows, macos}` on pwsh 7
and folds them into the `required-checks` summary.
