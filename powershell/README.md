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

This release proves the runtime and the CI gate, and adds the read-only
credential scope guard. It ships four cmdlets and **no cloud
collectors**:

| Cmdlet                       | Purpose                                              |
|------------------------------|------------------------------------------------------|
| `Get-FinOpsInfo`             | Module version, read-only posture, in-scope surfaces |
| `Test-FinOpsConfiguration`   | Structural self-test + version lock to the Python pkg |
| `Test-FinOpsReadOnlyScope`   | Non-throwing classifier: read / write / unknown scope |
| `Assert-FinOpsReadOnlyScope` | Fail-closed guard: throws on a write or unknown scope |

> **Read-only scope guard: implemented, not yet wired.** The guard
> cmdlets (`Assert-FinOpsReadOnlyScope` / `Test-FinOpsReadOnlyScope`)
> are implemented and unit-tested today, but no credential-bearing code
> path ships yet for them to sit in front of (live collectors land in
> Phase 6). `Get-FinOpsInfo` therefore reports
> `RuntimeScopeGuardEnforced = $false`. ARM tokens are refused
> fail-closed because read-only cannot be proven from token claims
> (it is RBAC-side). Do not treat this module as security-complete.

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

CI runs the same gates across `{ubuntu, windows, macos}` on pwsh 7
and folds them into the `required-checks` summary.
