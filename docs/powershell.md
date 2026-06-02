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
| `run`                    | `Invoke-FinOpsAssessment`    | 🟡 report envelope + JSON reporter + **8 M365 rules** + CSV reporter (Phase 2); Azure/GitHub/ADO findings deferred to Phases 3–4 |
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

## Shared data projection

The PowerShell engine must read the **same** catalogue, persona, and
rule data as the Python tool, but adding a PowerShell YAML parser would
introduce a third-party dependency and risk a second, subtly different
parser. Instead the shared YAML under `data/` is projected to canonical
JSON at build time and packaged with the module under
`powershell/FinOpsAssess/data/{catalog,personas,rules}.json`. At runtime
the engine only needs the built-in `ConvertFrom-Json`.

- **Generator:** `scripts/generate_ps_data_projection.py` runs the
  already-validated Python loaders (`load_catalog`, `load_personas`,
  `load_rules`), so the JSON carries fully resolved shapes — including
  pydantic defaults such as `rule.enabled`, `evidence_key_version`, and
  `adapter_class`. The PowerShell side never re-implements validation or
  defaulting.
- **Ordering:** each list preserves the **Python loader iteration order**
  (sorted file paths, then document order), *not* a re-sort by `id`, so
  both engines iterate the data identically and order-sensitive
  behaviour stays in parity. Object keys are sorted for byte-stable
  output (irrelevant to PowerShell, which reads by property name).
- **Drift gate:** the projection is a generated artifact, never
  hand-edited. `tests/test_ps_data_projection.py` regenerates in memory
  and byte-compares against the committed files, and the
  `catalog-validation` CI job runs
  `python scripts/generate_ps_data_projection.py --check`. A PR that
  edits the shared YAML must regenerate and commit the projection or CI
  fails.
- **Runtime loader:** the private `Get-FinOpsDataProjection` cmdlet reads
  the three files via `ConvertFrom-Json`, returns a `[pscustomobject]`
  with `Catalog`/`Personas`/`Rules`, always materialises each as an
  array (so single-element projections never unwrap to a scalar), and
  throws a clear error on a missing or unparseable file.
  `Test-FinOpsConfiguration` now asserts the projection loads and is
  non-empty.

> **Money values stay floats for now.** The projection serialises prices
> as JSON numbers (`model_dump` → `ConvertFrom-Json` `[double]`), which
> is fine for *loading* static data. Before the JSON reporter and
> conformance harness perform savings arithmetic, a money formatting/
> rounding rule will be pinned (Phase 1) so cross-engine byte parity does
> not rely on raw binary-float formatting.

## Normalise core (offline CSV → normalised dataset)

The PowerShell engine reimplements the offline collector
(`finops_assess.collectors.csv_collector.collect_from_directory`): it
reads a directory of per-surface CSV files and coerces + validates every
cell into the same `NormalizedDataset` shape the Python engine produces.
This is the **second** conformance layer (docs/plan.md §5a) — proving the
two engines agree on the *normalised dataset* before any rule fires, so a
divergence is caught at the source rather than in findings.

- **Schema projection:** the same generator emits a fourth file,
  `powershell/FinOpsAssess/data/schema.json`, derived from the pydantic
  v2 record models. It lists, per model, each field's `kind`
  (`string`/`int`/`float`/`bool`/`list`/`literal`), nullability,
  required-ness, enum members, and numeric/length bounds, plus the
  `dataset field → CSV file → model` mapping and the bool/list token
  rules. The PowerShell normaliser is **data-driven** from this file, so
  it never re-encodes the schema in code. Same drift gate as the data
  projection (`tests/test_ps_data_projection.py` + `--check`).
- **Strict-column contract (mirrors Python exactly):** the CSV header is
  authoritative. An unknown column is an error; a row with a non-empty
  cell beyond the header is an error; a row with fewer cells than the
  header treats the missing cells as empty; an empty cell is omitted so
  the schema default applies. Booleans parse from a fixed true/false
  token set, lists split on `|` (trimmed, empties dropped), and
  `int`/`float` parse with the invariant culture. Enum, `ge`/`le`, and
  `min_length`/`max_length` bounds and required fields are enforced.
- **CSV parser:** a self-contained RFC-4180 reader
  (`ConvertFrom-FinOpsCsvText`) is used instead of `Import-Csv` so the
  strict-column behaviour matches Python's `csv.DictReader` semantics
  (rather than `Import-Csv`'s silent column coalescing), with no
  dependency on `Microsoft.VisualBasic` `TextFieldParser`.
- **`m365_family_summaries`** has no CSV source (it is derived later in
  the Python pipeline); the normaliser emits it as an empty list for
  dataset-shape parity, exactly as the Python collector does.

> **`overrides.yaml` is a documented YAML *subset*, not full PyYAML.**
> The normaliser reads `overrides.yaml` as a strict flat `key: value`
> mapping (blank lines, `#` comments, and optionally quoted scalar
> values). Nested structures, anchors, tags, and flow collections are
> rejected with a clear error. This matches how the demo overrides file
> is used; if a future override needs richer YAML, the limitation (and
> the reason) must be revisited here and in the conformance harness.

**Conformance status:** layer 2 (same normalised dataset) is proven
**now** — the committed golden fixture
`tests/fixtures/ps_conformance/demo-normalised.json` is generated from
the Python engine
(`scripts/generate_ps_conformance_fixtures.py`, drift-gated by
`tests/test_ps_conformance_fixtures.py`), and a Pester test runs the
PowerShell normaliser over the same demo tenant and deep-compares
(type-aware: numbers as numbers) against it. Layer-5 byte-canonical
artifact equality is **deferred** to the report/JSON-reporter slice,
where the cross-engine money formatting/rounding rule is pinned.

## Report model + JSON reporter (`Invoke-FinOpsAssessment`)

The third slice of Phase 1 ports the shared report envelope and the JSON
reporter. `Invoke-FinOpsAssessment` runs the native pipeline end to end
on offline CSVs — normalise → persona assignment → build report → write
JSON — and is a faithful port of Python's `build_report` /
`write_json_report`:

- **Run metadata** (`run.tool`, `run.version`, `run.generated_at`,
  `run.input`, `run.salt_mode`, `run.pii_redaction`, …) matches Python
  field-for-field. `run.version` is sourced from the module manifest
  `ModuleVersion`, so the conformance compare mechanically fails if the
  PowerShell module version ever drifts from the Python package version.
- **Determinism** honours `SOURCE_DATE_EPOCH` exactly as Python does
  (`Get-FinOpsGeneratedAt`): a valid epoch renders a UTC, colon-bearing
  ISO-8601 timestamp (`1970-01-01T00:00:00+00:00`); an unset or
  out-of-range value silently falls back to wall-clock UTC.
- **Persona assignment** is ported in `Get-FinOpsPersonaAssignment`
  using `[regex]::IsMatch` (case-sensitive, honouring inline `(?i)`) so
  the title/group matching is byte-for-byte equivalent to Python's
  `re.search`, producing an identical `summary.persona_distribution`.
- **PII redaction** defaults on; `-NoPiiRedaction` opts out, and
  `-PiiSalt` selects the tenant-stable salt mode (otherwise `per_run`).

> **Honest parity claim — read this.** This slice proves **report-
> envelope parity**, not findings parity. There are no rule
> implementations yet, so the native engine emits an empty `findings`
> array and self-documents that fact (`summary.rule_counts = {}`,
> `summary.total_findings = 0`, `summary.rules_skipped_no_impl` lists all
> 28 rule IDs). To compare honestly, both engines' reports are projected
> through a **declared canonicaliser profile**, `report-structural-v1`
> (`scripts/canonicalize_report.py`), which masks the rule-dependent
> fields and collapses `findings` to a fixed sentinel. The committed
> golden `tests/fixtures/ps_conformance/demo-report-structural.canonical.json`
> is generated from a **real** Python report (with real findings); the
> native report projects to the **same bytes** because the masked fields
> are exactly the ones that differ. What is proven: run-metadata +
> dataset-derived counts + persona-distribution + a schema-valid envelope
> (`src/finops_assess/schemas/report.schema.json`) + `findings` is an
> array. What is **explicitly not** claimed: finding contents, savings
> numbers, or which rules fire — all deferred to the rule phases (2–5),
> where the money formatting/rounding rule is pinned and the canonical
> compare is extended to include findings.

## M365 rules + CSV reporter (Phase 2)

Phase 2 ports the eight `M365.*` savings rules and the flat-CSV reporter
to the native engine, lifting `Invoke-FinOpsAssessment` from
report-envelope parity to **M365 rule-slice parity**. The ported rules
are `M365.UNUSED_LICENSE_30D`, `M365.OVER_LICENSED_VS_PERSONA`,
`M365.DUPLICATE_BUNDLE`, `M365.DISABLED_USER_LICENSED`,
`M365.SHARED_MAILBOX_LICENSED`, `M365.GUEST_PREMIUM_LICENSED`,
`M365.COPILOT_INACTIVE_60D`, and `M365.E5_FEATURES_UNUSED`
(`Invoke-FinOpsRuleEngine` + `Get-FinOpsM365RuleRegistry`, faithful ports
of `engine.run_rules` and `rules_impl/m365_rules.py`).

- **CSV output**: `Invoke-FinOpsAssessment -Format csv` emits the flat
  findings table (`ConvertTo-FinOpsCsvReport` / `Write-FinOpsCsvReport`),
  a hand-rolled port of `reporters/csv_reporter.py` — fixed column order,
  `evidence_json` serialised by a Python-`json.dumps`-compatible compact
  serialiser (`ConvertTo-FinOpsCompactJson`), `csv.QUOTE_MINIMAL`
  quoting, the same formula-injection cell sanitiser, and LF line
  endings. `Export-Csv` is **not** used (it quotes differently and adds a
  `#TYPE` header).
- **Determinism for findings**: pass `-PiiSalt <salt>` to pin the
  tenant-stable salt so the salted-hash of each principal is reproducible
  across runs and engines; combined with `SOURCE_DATE_EPOCH` this makes
  the whole findings set byte-reproducible.

> **Honest parity claim — read this.** Phase 2 proves **M365 rule-slice
> parity**: over the bundled demo tenant, the native engine produces the
> same M365 findings (same rule IDs firing, same finding fields, same
> evidence, same salted principals, same savings numbers) and the same
> M365 `rule_counts` as Python, and the CSV reporter matches Python
> byte-for-byte. Two committed goldens enforce this in CI:
> `tests/fixtures/ps_conformance/demo-report-m365.canonical.json` (the
> `report-m365-v1` canonical projection — full M365 finding contents,
> sorted, with the money field coerced to float so int/float JSON
> formatting cannot diverge) and `…/demo-report-m365.csv` (the
> `csv_reporter` output in **natural report order**). The JSON compare
> sorts findings, so the CSV compare deliberately does **not** — it
> doubles as an emission-order drift check, since the PowerShell engine
> mirrors Python's rule- and input-iteration order exactly. What is
> **explicitly not** claimed: Azure/GitHub/ADO findings (their rule IDs
> remain in `summary.rules_skipped_no_impl`, 20 of them), whole-report
> parity, or any non-CSV reporter. `summary.total_findings` and the full
> `rules_skipped_no_impl` list legitimately differ between engines (the
> native engine skips 20 rules, Python skips none), so the `report-m365-v1`
> profile masks them and filters `rule_counts` to the `M365.*` keys.

## Conformance & CI

CI runs PSScriptAnalyzer (settings in
`powershell/PSScriptAnalyzerSettings.psd1`) and Pester across
`{ubuntu-latest, windows-latest, macos-latest}` on pwsh 7, and folds the
result into the single `required-checks` summary that branch protection
requires. The cross-engine conformance harness (canonicalised artifact
equality, not raw byte-equality) is introduced in Phase 1.
