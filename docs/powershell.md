# Run it from PowerShell (native module)

`FinOpsAssess` is a native PowerShell engine delivered **side by side**
with the Python `finops-assess` CLI. The intent is full subcommand
parity over the same read-only assessment surface (Microsoft 365, Azure,
GitHub, Azure DevOps), with the two engines kept honest by a
cross-engine conformance harness.

This page tracks what the module does **today**. It is being delivered
in phases (see [`plan.md`](plan.md) §1.7a and the ADR
[`decisions/0001-powershell-side-by-side.md`](decisions/0001-powershell-side-by-side.md)).

## Why a second engine?

The decision, its honest cost (double maintenance of ~1.6k LOC of rule
semantics), and the governance that prevents drift (§7a dual-maintenance
rule + conformance gate) are recorded in the ADR. The short version: the
project is trialling a native PowerShell engine; if it proves out, more
of the workload moves to PowerShell over time. Until then, **both
engines must stay in parity or the feature is explicitly marked
unsupported in PowerShell.**

## Requirements

- **PowerShell 7.2+** on Linux, macOS, or Windows.
- Windows PowerShell **5.1 is unsupported** and carries no parity
  guarantee (materially different JSON, encoding, TLS, and class
  behaviour).

## Install / import

Phase 0 is not yet published to the PowerShell Gallery. Import from a
clone:

```powershell
Import-Module ./powershell/FinOpsAssess/FinOpsAssess.psd1 -Force
```

## Cmdlet parity matrix

| Python subcommand        | PowerShell cmdlet            | Phase 0 status                    |
|--------------------------|------------------------------|-----------------------------------|
| `info`                   | `Get-FinOpsInfo`             | ✅ implemented                     |
| `validate`               | `Test-FinOpsConfiguration`   | 🟡 structural + version-lock only; schema validation in Phase 1 |
| `collect`                | `Invoke-FinOpsCollection`    | ⛔ not started (Phase 6)           |
| `run`                    | `Invoke-FinOpsAssessment`    | ⛔ not started (Phase 1+)          |
| `demo`                   | `Invoke-FinOpsDemo`          | ⛔ not started (Phase 1)           |
| `triage`                 | `Export-FinOpsTriage`        | ⛔ not started (Phase 5)           |
| `catalog refresh`        | `Update-FinOpsCatalog`       | ⛔ not started (Phase 6)           |
| `catalog coverage`       | `Test-FinOpsCatalogCoverage` | ⛔ not started (Phase 6)           |
| `export focus-aligned`   | `Export-FinOpsFocusReport`   | ⛔ not started (Phase 5)           |

`pdf` output is explicitly **not** native: `Invoke-FinOpsAssessment
-Format pdf` will delegate to the Python engine (WeasyPrint), documented
as a deliberate non-native dependency rather than a parity gap.

## Cmdlet reference (Phase 0)

### `Get-FinOpsInfo`

Returns module version, the pinned Python package version, the four
in-scope surfaces, and the read-only posture. No cloud calls.

```powershell
Get-FinOpsInfo
```

### `Test-FinOpsConfiguration`

Structural self-test. In Phase 0 it checks: the manifest imports, the
`Public/`+`Private/` layout is intact, and the module version is locked
to the Python package version (`src/finops_assess/__init__.py`). Throws
on failure (CI-safe); use `-PassThru` for the structured result object.

```powershell
Test-FinOpsConfiguration
(Test-FinOpsConfiguration -PassThru).Checks
```

Full catalogue + personas + rules schema validation is **deferred to
Phase 1**, when the shared data projection lands.

## Read-only guarantees (current state)

| Guarantee                              | Phase 0 state                                  |
|----------------------------------------|------------------------------------------------|
| No cloud calls / mutation paths in code | ✅ enforced (PSScriptAnalyzer + Pester tripwire) |
| Bans `Invoke-Expression`, `*.ReadWrite.*`, cloud mutation cmdlets | ✅ enforced in CI |
| Runtime credential **scope guard** (refuse write-scoped tokens) | ⛔ **not yet implemented** — dedicated, separately reviewed PR |

`Get-FinOpsInfo` reports `RuntimeScopeGuardEnforced = $false` until the
scope-guard release lands. Do not treat the Phase-0 module as
security-complete.

## Conformance & CI

CI runs PSScriptAnalyzer (settings in
`powershell/PSScriptAnalyzerSettings.psd1`) and Pester across
`{ubuntu-latest, windows-latest, macos-latest}` on pwsh 7, and folds the
result into the single `required-checks` summary that branch protection
requires. The cross-engine conformance harness (canonicalised artifact
equality, not raw byte-equality) is introduced in Phase 1.
