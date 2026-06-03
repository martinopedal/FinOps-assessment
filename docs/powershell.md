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
| `collect`                | `Invoke-FinOpsLiveCollection`| 🟡 Phase 6a scaffold (auth/guard/dispatcher); surface workers land in 6b–6e |
| `run`                    | `Invoke-FinOpsAssessment`    | 🟡 report envelope + JSON reporter + **8 M365 rules** + CSV reporter (Phase 2); **12 Azure rules** (Phase 3); **4 GitHub rules + 4 ADO rules** (Phase 4); ✅ full-document HTML reporter byte-parity over `samples/` (Phase 5c) |
| `demo`                   | `Invoke-FinOpsDemo`          | ⛔ not started (Phase 1)           |
| `triage`                 | `Invoke-FinOpsTriage`        | ✅ advisory triage JSON+CSV parity (Phase 5a) + ✅ practice-review HTML fragment parity via private helpers (Phase 5b), both over `samples/` |
| `catalog refresh`        | `Update-FinOpsCatalog`       | ⛔ not started (Phase 6)           |
| `catalog coverage`       | `Test-FinOpsCatalogCoverage` | ⛔ not started (Phase 6)           |
| `export focus-aligned`   | `Export-FinOpsFocusAligned`  | ✅ advisory CSV + manifest byte parity over `samples/` (Phase 5e) |
| `run --format playbook`  | `Export-FinOpsPlaybook`      | ✅ playbook/ticket JSONL + manifest parity over `samples/` (Phase 5d, standalone exporter) |

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
> mirrors Python's rule- and input-iteration order exactly.

## GitHub + ADO rules (Phase 4)

Phase 4 ports the four `GH.*` and four `ADO.*` savings rules to the
native engine via `Get-FinOpsGitHubRuleRegistry` and
`Get-FinOpsAdoRuleRegistry`, extending parity to **GitHub and Azure
DevOps findings**. Both registries are auto-discovered by the existing
`Get-FinOpsRuleRegistry` aggregator — no edits to
`Invoke-FinOpsRuleEngine.ps1` were required.

### GitHub rules (4)

| Rule ID | Severity | Signal | Savings |
|---|---|---|---|
| `GH.INACTIVE_SEAT_90D` | high | Enterprise/Team seat inactive ≥ 90 days | catalog seat price |
| `GH.COPILOT_INACTIVE_30D` | high | Copilot seat with 0 acceptances in 30 days | catalog seat price |
| `GH.GHAS_OVER_PROVISIONED` | medium | GHAS-enabled repos > actively-scanned repos | null (committer mapping not in snapshot) |
| `GH.RUNNER_TIER_MISMATCH` | low | Runner minutes ≥ 25% above/below included quota | null (per-arch pricing not in catalog) |

### ADO rules (4)

| Rule ID | Severity | Signal | Savings |
|---|---|---|---|
| `ADO.INACTIVE_BASIC_90D` | high | Basic/Basic+Test seat inactive ≥ 90 days | catalog seat price |
| `ADO.STAKEHOLDER_ELIGIBLE` | medium | Basic seat with only board-read activity, < 90 days inactive | full Basic seat price |
| `ADO.PARALLEL_JOBS_OVER_PROVISIONED` | medium | Purchased hosted parallel jobs exceed P95 by ≥ 2 | surplus × hosted job price |
| `ADO.TEST_PLANS_UNUSED` | medium | Basic+Test seat with no Test Plan activity in 60 days | Basic+Test price − Basic price; recommends ADO.BASIC |

### Parity traps addressed

- **No `sorted()` in either rule file** — emission order is pure dataset
  iteration order (`github_seats` / `github_orgs` / `ado_seats` /
  `ado_orgs`), simpler than M365.
- **PS collection unrolling**: helpers that return collections use
  `return ,$collection` to prevent PowerShell scalar unrolling.
- **`[object]`-typed params**: null-capable fields (`savings`,
  `recommended_sku`, `evidence_ref`, `current_sku` on org-level rules)
  use `[object]` so the JSON serialiser emits `null` rather than omitting
  the key.
- **Ordinal case-sensitivity**: `seat_type` matches use
  `[System.StringComparer]::Ordinal` / `-ceq` throughout.
- **Money float typing**: catalog prices are `.00` floats; savings via
  `[math]::Round(…, 2)` stays `[double]`; `Format-FinOpsPyFloat` appends
  `.0` on whole numbers so `6.0` serialises correctly.

> **Honest parity claim — read this.** Phase 4 proves **GitHub and ADO
> rule-slice parity**: over the bundled demo tenant, the native engine
> produces the same GH/ADO findings (same rule IDs firing, same fields,
> same salted principals, same savings) and the same surface `rule_counts`
> as Python. Four committed goldens enforce this in CI:
> `demo-report-github.canonical.json` / `demo-report-github.csv` and
> `demo-report-ado.canonical.json` / `demo-report-ado.csv` under
> `tests/fixtures/ps_conformance/`. The CSV compare uses the combined
> report output filtered to the surface prefix, preserving natural
> emission order as a drift check. The 12 `AZ.*` rules are now
> implemented natively (Phase 3) and enforced by
> `demo-report-azure.canonical.json` / `demo-report-azure.csv`; no rule
> ids remain in `summary.rules_skipped_no_impl`.

## Advisory triage (`Invoke-FinOpsTriage`) — Phase 5a

Phase 5a ports Python `triage.py` + `triage_reporter.py` to native
PowerShell:

- `Build-FinOpsTriage` (`Private/Get-FinOpsTriage.ps1`) mirrors Python
  triage item derivation and envelope shape (`run`/`source`/`summary`/`items`)
  with insertion-order-preserving ordered dictionaries.
- `ConvertTo-FinOpsCanonicalJson` + `Get-FinOpsTriageFindingRef` implement
  Python-compatible canonical payload hashing for deterministic
  `finding_ref` values (sorted keys, compact separators, ensure_ascii escapes).
- `Write-FinOpsTriageJson` writes UTF-8 no BOM, LF-only, trailing newline JSON.
- `Write-FinOpsTriageCsv` writes the 17-column triage CSV in Python order with
  `QUOTE_MINIMAL`, formula-prefix sanitisation, and `" | "` list joins.
- Public cmdlet: `Invoke-FinOpsTriage -InputReport <json> -OutputDirectory <dir> -Format json|csv|both`.

Conformance artefacts:

- `tests/fixtures/ps_conformance/demo-triage.json`
- `tests/fixtures/ps_conformance/demo-triage.csv`

Generated by `scripts/generate_ps_triage_fixtures.py` (with `--check` drift
mode), drift-gated by `tests/test_ps_triage_fixtures.py`, and byte-compared in
Pester via `[System.IO.File]::ReadAllBytes`.

> **Honest parity claim — read this.** Phase 5a proves advisory triage
> JSON+CSV byte parity over the committed `samples/` corpus. Scope is
> deterministic, read-only triage artefact generation from an existing report;
> no remediation or network actions are introduced.

## Practice-review fragment parity (Phase 5b)

Phase 5b ports Python `reporters/practice_review.py` to native PowerShell as
private helpers (`Private/Get-FinOpsPracticeReview.ps1`):

- `Get-FinOpsPracticeReview` builds the same structured context shape
  (`header`, `heading`, `disclaimer`, pricing/data-quality/commitment/SKU-mix
  posture sections).
- `Get-FinOpsPracticeReviewHtml` renders the same standalone HTML fragment as
  Python `render_practice_review_section(report)`.
- `ConvertTo-FinOpsHtmlEscaped` reproduces Python `html.escape(..., quote=True)`
  entity forms and replacement ordering exactly.

Conformance artefact:

- `tests/fixtures/ps_conformance/demo-practice-review.html`

Generated by `scripts/generate_ps_practice_review_fixtures.py` (with `--check`
drift mode), drift-gated by `tests/test_ps_practice_review_fixtures.py`, and
byte-compared in Pester via `[System.IO.File]::ReadAllBytes`.

> **Honest parity claim — read this.** Phase 5b proves practice-review
> structured-context + HTML-fragment parity over the committed `samples/`
> corpus. In that corpus, commitment-coverage and M365 family-summary upstream
> fields are absent, so those sub-sections intentionally render the
> "not yet surfaced" degraded path.

## Full-document HTML parity (Phase 5c)

Phase 5c ports Python `reporters/html_reporter.py` +
`templates/report.html.j2` to native PowerShell with a hand-emitted renderer
(`Private/ConvertTo-FinOpsHtmlReport.ps1`) and wires
`Invoke-FinOpsAssessment -Format html`.

Conformance artefact:

- `tests/fixtures/ps_conformance/demo-report.html`

Generated by `scripts/generate_ps_html_fixtures.py` (with `--check` drift mode),
drift-gated by `tests/test_ps_html_fixtures.py`, and byte-compared in Pester
against `ConvertTo-FinOpsHtmlReport`.

## FOCUS-aligned advisory export (`Export-FinOpsFocusAligned`) — Phase 5e

Phase 5e ports Python `reporters/focus_aligned.py` to native PowerShell:

- `Write-FinOpsFocusAlignedExport` (`Private/Get-FinOpsFocusAligned.ps1`) writes
  the 23-column FOCUS-aligned advisory CSV plus `<csv>.manifest.json` with
  deterministic ordering and LF UTF-8 (no BOM) output.
- `Get-FinOpsFocusAdvisoryFindingKey` mirrors Python `advisory_finding_key`
  semantics, including evidence canonicalisation (`None -> ""`, float
  `repr`-as-string, dict key sort, list order preserve) and
  `ensure_ascii=False` JSON envelopes.
- Billing periods mirror Python fallback semantics: parse
  `observation_window_end` when possible; otherwise fall back to
  `SOURCE_DATE_EPOCH`-aware UTC month.
- Public cmdlet: `Export-FinOpsFocusAligned -InputReport <json> -OutputPath <csv> [-Surface ...]`.

Conformance artefacts:

- `tests/fixtures/ps_conformance/demo-focus.csv`
- `tests/fixtures/ps_conformance/demo-focus.csv.manifest.json`

Generated by `scripts/generate_ps_focus_fixtures.py` (with `--check` drift
mode), drift-gated by `tests/test_ps_focus_fixtures.py`, and byte-compared in
Pester via `[System.IO.File]::ReadAllBytes`.

> **Honest parity claim — read this.** Phase 5e proves FOCUS-aligned advisory
> CSV + manifest byte parity over the committed `samples/` corpus (all four
> surfaces, redaction default on). The corpus is ASCII, so the
> `ensure_ascii=False` path and tenant-stable/cleartext manifest branches are
> implemented but not exercised by the committed fixtures.

## Playbook / ticket export parity (`Export-FinOpsPlaybook`) — Phase 5d

Phase 5d ports Python `reporters/playbook.py` to native PowerShell as:

- `Public/Export-FinOpsPlaybook.ps1`
- `Private/Get-FinOpsPlaybook.ps1`

The cmdlet reads an existing report JSON (`ConvertFrom-FinOpsReportJson`) and
emits:

- `playbook.jsonl` (one JSON object per row, UTF-8 no-BOM, LF)
- `playbook.jsonl.manifest.json` (indent=2, trailing newline)

Conformance artefacts:

- `tests/fixtures/ps_conformance/demo-playbook.jsonl`
- `tests/fixtures/ps_conformance/demo-playbook.jsonl.manifest.json`

Generated by `scripts/generate_ps_playbook_fixtures.py` (`--check` drift mode),
drift-gated by `tests/test_ps_playbook_fixtures.py`, and byte-compared in
Pester via `[System.IO.File]::ReadAllBytes`.

> **Honest parity claim — read this.** Phase 5d proves byte parity over the
> committed `samples/` corpus (40 findings) with fixed conformance salt and
> deterministic timestamps. Unexercised/deferred branches are explicitly out of
> scope for this slice: non-ASCII `ensure_ascii=False` paths, per-run/cleartext
> manifest branches, overlay/template provenance, orphan scan, and PII-warning
> CLI stderr behaviour.

## Live mode (Phase 6)

Phase 6a shipped the shared live-collector base and the public dispatcher
`Invoke-FinOpsLiveCollection`. Phase 6b now ships the Graph collector and
Phase 6c adds the ARM collector; GitHub/Azure DevOps remain staged in 6d–6e.

```powershell
Invoke-FinOpsLiveCollection -Surface Graph -OutputPath ./live
```

### Environment variables by surface

| Surface | Required env (default path) | Notes |
|---|---|---|
| Graph | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and one of `AZURE_FEDERATED_TOKEN_FILE` or `AZURE_CLIENT_SECRET` | Uses `Get-FinOpsAccessToken -Scope graph` |
| ARM | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, one of `AZURE_FEDERATED_TOKEN_FILE` or `AZURE_CLIENT_SECRET`, and `FINOPS_ACCEPT_ARM_RBAC_RISK=1` | Requires `-AcceptArmRbacRisk` + env two-key consent |
| GitHub | `GITHUB_TOKEN` (or pass `-Token`/`-Pat`) | Classic scopes are validated by the read-only guard |
| Azure DevOps | `AZURE_DEVOPS_TOKEN` or `AZURE_DEVOPS_PAT` (or pass `-Token`/`-Pat`) | Bearer or PAT paths both flow through the guard |

### Graph (Microsoft 365)

`Invoke-FinOpsLiveCollection -Surface Graph` writes:
`users.csv`, `license_assignments.csv`, and `usage.csv`.

- **Required environment/auth inputs:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
  plus one of `AZURE_FEDERATED_TOKEN_FILE` (OIDC/workload identity) or
  `AZURE_CLIENT_SECRET` (service principal secret).
- **Endpoints called:**
  - `GET https://graph.microsoft.com/v1.0/users?...&$top=999&$count=true`
    with `ConsistencyLevel: eventual`
  - `GET .../reports/getMailboxUsageDetail(period='D30')`
  - `GET .../reports/getOffice365ActiveUserDetail(period='D30')`
  - `GET .../reports/getMicrosoft365CopilotUsageSummary(period='D30')`
- **Required read-only Graph permissions:**
  `User.Read.All`, `Reports.Read.All`, `Organization.Read.All`, and
  `AuditLog.Read.All` (required for `signInActivity`).

`Get-FinOpsInfo` now reports per-surface posture truthfully:
Graph + ARM enforcement are live (`ScopeGuard.Enforced = 'partial'`,
`RuntimeScopeGuardEnforced = $true`) while GitHub/ADO stay unshipped.

### Azure Resource Manager (ARM)

`Invoke-FinOpsLiveCollection -Surface Arm` writes:
`azure_resources.csv`, `azure_reservations.csv`, `azure_log_workspaces.csv`,
and `azure_benefit_recommendations.csv`.

- **Required environment/auth inputs:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
  and one of `AZURE_FEDERATED_TOKEN_FILE` (OIDC/workload identity) or
  `AZURE_CLIENT_SECRET` (service principal secret).
- **Required read-only role:** Azure built-in **Reader** role is sufficient.
- **Two-key consent model (operator attestation):**
  - switch: `-AcceptArmRbacRisk`
  - env: `FINOPS_ACCEPT_ARM_RBAC_RISK=1`
  - both are required; otherwise the dispatcher refuses to run.
- **Why attested:** ARM read/write capability is RBAC-side and cannot be
  proven from token claims alone; RBAC introspection is deferred.
- **Endpoints called:**
  - `GET https://management.azure.com/subscriptions?...`
  - `GET .../virtualMachines?...`
  - `GET .../disks?...`
  - `GET .../publicIPAddresses?...`
  - `GET .../providers/Microsoft.Capacity/reservations?...`
  - `GET .../providers/Microsoft.CostManagement/benefitRecommendations?...`
  - `GET .../providers/Microsoft.OperationalInsights/workspaces?...`
  - `GET .../usages?...`
  - `GET .../providers/microsoft.insights/metrics?...` (unless `-SkipMetrics`)
  - `GET https://prices.azure.com/api/retail/prices?...` (**anonymous**, no
    `Authorization` header; public read-only pricing metadata).

### SecureString posture (honest note)

Tokens and PATs stay as `SecureString` through module plumbing and are only
unwrapped in short-lived locals when a header must be built or token claims must
be inspected. On Linux/macOS, `SecureString` is operational hardening (avoids
echo/history/accidental logging), **not** cryptographic memory protection.

### Deterministic clock + CSV notes

- `Get-FinOpsNow` honors `FINOPS_NOW_OVERRIDE=yyyy-MM-dd` for deterministic
  day-math in tests and fixture generation.
- `Write-FinOpsCollectorCsv` writes UTF-8 (no BOM) with **LF** line endings and
  RFC-4180 quoting.
- Live-collector parity assertions are structural at normalized-dataset level
  (plus targeted literal checks), not full-file byte equality.

### Phase sequencing

- **6a (this slice):** auth + GET-only REST wrapper + atomic CSV writer + dispatcher.
- **6b–6e:** Graph, ARM, GitHub, and Azure DevOps collectors.

## Conformance & CI

CI runs PSScriptAnalyzer (settings in
`powershell/PSScriptAnalyzerSettings.psd1`) and Pester across
`{ubuntu-latest, windows-latest, macos-latest}` on pwsh 7, and folds the
result into the single `required-checks` summary that branch protection
requires. The cross-engine conformance harness (canonicalised artifact
equality, not raw byte-equality) is introduced in Phase 1.
