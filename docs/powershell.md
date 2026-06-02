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

### Security cmdlets (no Python subcommand)

These have no `finops-assess` subcommand equivalent — they are the
runtime building blocks of the read-only security contract (plan.md
§4.1 / §1.7a criterion 9). They are exported and unit-tested today; the
Phase-6 live collectors will call them at the credential boundary.

| PowerShell cmdlet              | Purpose                                          |
|--------------------------------|--------------------------------------------------|
| `Test-FinOpsReadOnlyScope`     | Non-throwing classifier: read / write / unknown  |
| `Assert-FinOpsReadOnlyScope`   | Fail-closed guard: throws on a write or unknown scope |

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

### `Test-FinOpsReadOnlyScope`

Classifies a credential's authorisation **without throwing**. Accepts
either a decoded JWT access token (`-AccessToken`) or an explicit list
of scopes/app-roles (`-Scope`, with an optional `-Surface` hint).
Returns a structured result:

```powershell
Test-FinOpsReadOnlyScope -Scope 'User.Read.All','Directory.Read.All'
Test-FinOpsReadOnlyScope -AccessToken $token   # routes surface from the aud claim
```

| Field              | Meaning                                                     |
|--------------------|-------------------------------------------------------------|
| `IsReadOnly`       | `$true` only if no write scope, no unknown scope, and claims are sufficient |
| `Surface`          | `Graph` / `AzureResourceManager` / `AzureDevOps` / `GitHub` (or `Unknown`) |
| `ClaimSource`      | which claim was inspected (`scp`, `roles`, `X-OAuth-Scopes`, …) |
| `ClaimsSufficient` | `$false` when the surface's posture can't be proven from claims (see ARM below) |
| `WriteScopes` / `ReadScopes` / `UnknownScopes` | the classified breakdown |

The classifier is **pattern-based for the write decision**: a novel or
renamed write scope (`*.Write`, `*.ReadWrite.*`, `*.Manage`,
`*_write`, GitHub `repo`/`admin:*`/`workflow`, …) still matches a write
pattern and is reported as not read-only. Read patterns only ever
*allow*; they never override a write match.

### `Assert-FinOpsReadOnlyScope`

The **fail-closed guard**. Throws if the credential carries any write
scope (always) or any unknown / claim-insufficient scope (unless
`-AllowUnknownScopes` is supplied). `-AllowUnknownScopes` warns and
permits *unknown* scopes through, but **never** rescues a write scope.
This is the cmdlet the live collectors will call before any cloud read.

```powershell
Assert-FinOpsReadOnlyScope -AccessToken $token         # throws on any write/unknown
Assert-FinOpsReadOnlyScope -Scope 'vso.work' -Surface AzureDevOps
```

#### Azure Resource Manager limitation (honest carve-out)

ARM read-vs-write capability is governed by **Azure RBAC role
assignments, not by token scopes** — an ARM access token's claims do
*not* reveal whether the principal can write. The guard therefore
classifies ARM tokens as **claim-insufficient and refuses them
fail-closed** by default. Proving ARM read-only requires RBAC
introspection, which lands with the Phase-6 collectors. This is a
deliberate refusal, not a coverage gap: the module would rather refuse
an ARM credential it cannot vet than pass a write-capable one.

## Read-only guarantees (current state)

| Guarantee                              | Phase 0 state                                  |
|----------------------------------------|------------------------------------------------|
| No cloud calls / mutation paths in code | ✅ enforced (PSScriptAnalyzer + Pester tripwire) |
| Bans `Invoke-Expression`, `*.ReadWrite.*`, cloud mutation cmdlets | ✅ enforced in CI |
| Runtime credential **scope guard** (refuse write-scoped tokens) | ✅ **implemented & unit-tested** (`Assert-FinOpsReadOnlyScope`); not yet *wired* into a live collector (no credential path ships until Phase 6) |

`Get-FinOpsInfo` reports `RuntimeScopeGuardEnforced = $false` because no
credential-bearing code path exists yet for the guard to sit in front of
— the guard cmdlet is present and tested, but there is nothing to
enforce it *at* until the Phase-6 collectors land. The structured
`ScopeGuard` field reports per-surface coverage honestly (including the
ARM limitation above). Do not treat the Phase-0 module as
security-complete.

## Conformance & CI

CI runs PSScriptAnalyzer (settings in
`powershell/PSScriptAnalyzerSettings.psd1`) and Pester across
`{ubuntu-latest, windows-latest, macos-latest}` on pwsh 7, and folds the
result into the single `required-checks` summary that branch protection
requires. The cross-engine conformance harness (canonicalised artifact
equality, not raw byte-equality) is introduced in Phase 1.
