# Changelog

All notable changes to `finops-assess` are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project follows semantic versioning once it reaches a tagged
release.

## Unreleased

### Added

- **PowerShell engine — normalise core (offline CSV → normalised
  dataset).** Second slice of Phase 1. The native engine reimplements the
  offline collector (`collect_from_directory`): a self-contained RFC-4180
  CSV reader (`ConvertFrom-FinOpsCsvText`) plus a schema-driven
  coercer/validator (`Get-FinOpsNormalizedDataset`) turn a directory of
  per-surface CSVs into the same `NormalizedDataset` shape the Python
  engine produces. It honours the identical strict-column contract
  (unknown column / extra non-empty cell = error; empty cell → schema
  default; fixed bool token set; `|`-split lists; enum, `ge`/`le`, and
  length bounds; required fields) and reads `overrides.yaml` as a
  documented flat `key: value` YAML subset. A fourth projection file,
  `powershell/FinOpsAssess/data/schema.json` (derived from the pydantic
  v2 models by `scripts/generate_ps_data_projection.py`), makes the
  normaliser data-driven so the schema is never re-encoded in code.
  **Layer-2 conformance** (docs/plan.md §5a — "same normalised dataset")
  is now proven: the committed golden
  `tests/fixtures/ps_conformance/demo-normalised.json` is generated from
  the Python engine by `scripts/generate_ps_conformance_fixtures.py`
  (drift-gated by `tests/test_ps_conformance_fixtures.py`), and a Pester
  test runs the PowerShell normaliser over the same demo tenant and
  type-aware deep-compares against it. 15 new Pester tests
  (counts/coercion/nulls, strict-contract failures, overrides parser,
  conformance). Docs: `docs/powershell.md` gains a "Normalise core"
  section. Layer-5 byte-canonical artifact equality is deferred to the
  JSON-reporter slice.
- **PowerShell engine — shared data projection
  (`powershell/FinOpsAssess/data`).** First slice of Phase 1. The shared
  catalogue/persona/rule YAML under `data/` is projected to canonical
  JSON at build time by `scripts/generate_ps_data_projection.py` (run via
  the already-validated Python loaders, so the JSON carries fully
  resolved pydantic shapes and defaults). The module reads it at runtime
  with the built-in `ConvertFrom-Json` — no PowerShell YAML dependency.
  New private loader `Get-FinOpsDataProjection` returns
  `Catalog`/`Personas`/`Rules` as arrays (single-element-safe) and throws
  clearly on a missing/unparseable file; `Test-FinOpsConfiguration` now
  asserts the projection loads and is non-empty. List order preserves the
  Python loader iteration order (not a re-sort by `id`) so both engines
  iterate identically. Drift is gated two ways: a new pytest
  (`tests/test_ps_data_projection.py`, byte-compares a fresh regeneration
  across the required Python matrix) and a `--check` step added to the
  `catalog-validation` CI job. 8 new Pester tests (load path, array
  shape, counts, UTF-8 round-trip, missing-file error). Docs:
  `docs/powershell.md` gains a "Shared data projection" section.
- **PowerShell engine — read-only credential scope guard
  (`powershell/FinOpsAssess`).** Implements the Phase-0 security contract
  (plan.md §4.1 / §1.7a criterion 9). New exported cmdlets
  `Test-FinOpsReadOnlyScope` (non-throwing classifier) and
  `Assert-FinOpsReadOnlyScope` (fail-closed guard that throws on any
  write scope always, and on unknown/claim-insufficient scopes unless
  `-AllowUnknownScopes`). Classification is pattern-based for the write
  decision (Graph/Entra, GitHub classic, Azure DevOps, ARM), so novel or
  renamed write scopes are still refused; read patterns only ever allow.
  Surface routing is by JWT `aud` claim (no signature verification by
  design — see threat-model notes). **Azure Resource Manager** tokens are
  refused fail-closed because read-only is RBAC-side and not provable
  from claims (RBAC introspection lands in Phase 6). `Get-FinOpsInfo`
  gains a structured `ScopeGuard` coverage field;
  `RuntimeScopeGuardEnforced` stays `$false` until the guard is wired
  into a live credential path. ~22 new Pester tests (adversarial scope
  corpus + round-trip JWT). Docs updated: `docs/powershell.md`,
  `powershell/README.md`.
- **PowerShell engine — Phase 0 scaffold (`powershell/FinOpsAssess`).**
  First native PowerShell module delivered side-by-side with the Python
  tool. Ships `Get-FinOpsInfo` (version, read-only posture, in-scope
  surfaces) and `Test-FinOpsConfiguration` (structural self-test +
  version-lock to the Python package). Module targets `pwsh` ≥ 7.2 only.
  Read-only by design (no cloud calls / mutation paths, enforced by a
  PSScriptAnalyzer + Pester tripwire) — but `Get-FinOpsInfo` reports
  `RuntimeScopeGuardEnforced = $false`: runtime credential-scope
  enforcement is deferred to a later, separately reviewed PR. New CI job
  `lint-and-test-powershell` (PSScriptAnalyzer + Pester across
  ubuntu/windows/macos on pwsh 7), folded into the `required-checks`
  summary. New docs: `docs/powershell.md`, `powershell/README.md`.

### Changed

- **PowerShell side-by-side engine — approved-to-plan (docs / governance
  only).** `docs/plan.md` §1.7 rewritten additively: Python remains the
  reference / conformance-oracle engine, and a native PowerShell engine
  (`pwsh` ≥ 7.2 only; Windows PowerShell 5.1 is out of scope) is
  admitted as a deliberately-justified, governed second runtime that
  ships *alongside* Python. PDF reporting is delegated to Python,
  possibly permanently. New `docs/plan.md` §1.7a records the
  falsifiable phase gate (8 capability-parity criteria + 8 security
  falsification gates from Noor) that would have to be cleared *before*
  retiring Python could even be proposed at a fresh §11 stage-4. New
  ADR `docs/decisions/0001-powershell-side-by-side.md` records the
  decision, Noor's dissent on full transition, and the binding gating
  PR sequence (PR #1 read-only scope-guard parity → PR #2 PII salt
  byte-parity → conformance harness → first PS rules). New §7a
  governance in `.github/copilot-instructions.md` makes
  dual-maintenance binding from this commit forward. **No engine
  code, schemas, rules, or workflows change in this release entry —
  this is docs / governance only.**

## v0.6.0

### Added

- **FOCUS exporter: multi-surface support (#71)**: `finops-assess export focus-aligned`
  now exports Azure, Microsoft 365, GitHub, and Azure DevOps findings in a single
  advisory CSV by default. New `--surface` CLI flag (choices: `azure`, `m365`,
  `github`, `ado`, `all`; default: `all`) lets operators restrict output to a
  single surface. Use `--surface azure` to reproduce the v0.5.0 Azure-only behavior
  exactly. Per-surface FOCUS column mapping: `ServiceName`, `ServiceCategory`, and
  `ResourceType` are set per-surface (e.g. `ServiceName: "Microsoft 365"`,
  `ResourceType: "user_license"` for M365 rows). Rows are sorted by
  `(surface, RuleId, ResourceId)` for byte-deterministic output. The manifest
  `pii_handling.mode` now distinguishes Azure-only exports (`azure_resource_id_*`)
  from multi-surface exports (`principal_*`). The JSON Schema enum for
  `pii_handling.mode` widens from 3 to 6 values (additive, no version bump).

- **Reporter template overlay (#74)**: New `--allow-template-overlay <dir>` CLI
  flag lets operators supply custom Jinja2 templates that override the bundled
  per-rule `.j2` files for the `--format playbook` export. Overlay templates run
  in a `jinja2.sandbox.SandboxedEnvironment`; `{% include %}` and `{% import %}`
  are rejected at AST parse time (C1), all content is loaded via `FileSystemLoader`
  — never `from_string()` (C2), and three security tests cover path-traversal
  blocking, extra-file isolation, and callable blocking (C3). A pre-flight render
  checks every overlay template against a fixture finding before writing any
  output. Manifest `template_sources` array records `source: "wheel"|"overlay"` and
  SHA-256 provenance for each template used in the run.

## v0.5.0

### Added

- **Tenant-stable PII salt mode (#73)**: New `--pii-salt-file` CLI option and
  `FINOPS_PII_SALT` environment variable enable operators to use a consistent salt
  across assessment runs, making principal hashes stable for cross-run ticket
  deduplication and trend analysis. The default behavior (per-run random salt) is
  unchanged — tenant-stable mode is opt-in only. When enabled, the report's `run.salt_mode`
  field reflects `"tenant_stable"` and reporter manifests mark ticket_key stability as
  `"stable"` for all surfaces. **Security note**: tenant-stable salt enables cross-run
  principal correlation; if your salt leaks, principals can be re-identified across all
  runs that used it. Operators must protect the salt file or environment variable as they
  would a database encryption key.
- `finops-assess run --format playbook` — emits a JSONL playbook export (one ticket
  per finding) rendered from per-rule Jinja2 templates, suitable for loading into
  ServiceNow, Jira, or GitHub Issues. Includes atomic-write (Option C), manifest
  sidecar (`<output>.jsonl.manifest.json` with SHA-256 integrity check), orphan
  detection, and `--cleanup-orphans` / `--skip-warnings` CLI flags. Each row
  contains `ticket_key`, `title`, `description`, `remediation_steps`,
  `verification_checklist`, `references`, `adapter_hints`, `template_render_inputs`,
  and `pii_warning`. 23 per-rule `.j2` templates ship under
  `src/finops_assess/data/playbooks/`. (#61)
- **AZ.AHB_ELIGIBLE** rule — flags Windows VMs running pay-as-you-go without Azure
  Hybrid Benefit applied (severity: info). New `os_type` and `license_type` fields on
  `AzureResource`; ARM collector reads `storageProfile.osDisk.osType` and
  `properties.licenseType`. (#59)
- `Rule.adapter_class: str = Field(default="generic")` field on the Rule model —
  enables per-rule ticket adapter customisation without YAML changes.
- New JSON Schemas `src/finops_assess/schemas/playbook_row.schema.json` and
  `src/finops_assess/schemas/playbook_manifest.schema.json` (`schema_version "0.1"`).
- Committed examples `examples/playbook.jsonl` and
  `examples/playbook.jsonl.manifest.json`, regenerated by `scripts/generate_docs.py`.
- `finops-assess export focus-aligned` subcommand — emits a FOCUS 1.3-shaped
  advisory CSV with sidecar `manifest.json` for joining advisory findings to
  FinOps Hubs / Cloudability / FOCUS-aligned cost datasets. Azure-only in this
  release; M365 / GitHub / ADO ship in v0.6.0 once the stable-principal-salt
  feature lands. See `docs/focus-export.md`. (#58, epic #57)
- `Rule.evidence_key_version: int = 1` field on the Rule model — enables versioned
  evolution of the AdvisoryFindingKey when a rule's evidence shape changes in v0.6.0+.
- New JSON Schema `src/finops_assess/schemas/focus_aligned_manifest.schema.json`
  (`manifest_schema_version "0.1"`) — additive-only contract for the sidecar manifest.
- Shared determinism module `src/finops_assess/reporters/_determinism.py` — centralises
  `SOURCE_DATE_EPOCH` timestamp logic for all reporters.
- Committed examples `examples/focus-aligned.csv` and
  `examples/focus-aligned.csv.manifest.json`, regenerated by `scripts/generate_docs.py`.

### Changed

- `docs/roadmap/focus-mapping.md` refreshed: status changed from
  `exploratory — documentation only` to `partially shipped (Azure-only, v0.5.0)`;
  mapping table retained for the M365/GitHub/ADO surfaces still in flight.

### Notes

- The exporter emits `BilledCost` / `ContractedCost` / `EffectiveCost` / `ListCost`
  as empty strings on every row by design — advisory savings are in the non-FOCUS
  `EstimatedMonthlySavingsUsd` column. The manifest declares
  `conformance_level: "non-conformant"`.

## Unreleased

### Added

- `AZ.RESERVATION_SCOPE_MISMATCH` rule: flags single-scope Azure reservations
  whose discount applies to one subscription while sibling subscriptions carry
  significant on-demand spend (≥ $50/mo by default) on likely-compatible
  workloads. The rule pre-aggregates spend per subscription from
  `azure_resources` and compares with the reservation's
  `applied_scope_subscription_ids` to identify scope-widening opportunities.
  Adds `applied_scope_subscription_ids: list[str] | None` to the
  `AzureReservation` model (pipe-separated in CSV mode). ARM collector now
  populates the field from `properties.appliedScopes`. Legacy CSVs without
  the new column load unchanged; the rule abstains on those rows. Ships with
  a per-rule playbook template and 14 unit tests. (#59)
- `AZ.COMMITMENT_RENEWAL_REVIEW` rule: surfaces Azure reservations expiring
  within 60 days whose operator has NOT configured auto-renew on the
  Microsoft.Capacity reservations API. The rule reads the API's
  `properties.expiryDate` and `properties.renew` fields directly (no
  heuristic) and abstains on missing signals, malformed dates, already-expired
  reservations, and reservations with auto-renew already on. Recommendation
  wording asks the operator to verify whether the workload still needs reserved
  capacity before renewing, exchanging, or planning the on-demand fallback.
  Adds two optional fields to the `AzureReservation` model: `expiry_date`
  (ISO 8601 `YYYY-MM-DD` string) and `auto_renew` (tri-state boolean).
  Legacy `azure_reservations.csv` files without the new columns load
  unchanged and the rule abstains on those rows. ARM collector now also
  filters out reservations whose `displayProvisioningState` is not
  `Succeeded`. New `FINOPS_NOW_OVERRIDE` env var anchors the rule's "today"
  for deterministic demo-report regeneration and the engine smoke test;
  production runs leave it unset and use the wall clock. (#59)
- Operator-facing agentic-FinOps architecture guide (`docs/agentic-finops.md`)
  explaining how the tool's read-only audit half plus an operator-controlled
  remediation-PR-against-IaC-repo add-on form a clean base for an agentic
  FinOps program. Answers the recurring "is this a good base for opening
  PRs on findings?" question without changing posture.
- Binding agent contract for any future feature that takes action OUTSIDE
  the tool's process boundary based on a finding. Codifies the nine hard rules
  the remediation-PR drafter (issue #63) and other agentic features must
  satisfy: never write to the audited tenant; PR drafts to operator's own
  IaC repo only; drafts only, never auto-merge; mandatory PR-body schema;
  PII redaction at PR-render time; per-rule `allow_pr: false` opt-in;
  idempotency, rate limit, kill switch; drift handling.
- Strategic backlog epic (issue #57) capturing 16 prioritised items from
  the FinOps Foundation Framework + FOCUS spec + agentic + MCP research
  pass, with 6 child issues filed (#58 FOCUS export, #59 commitment-discount
  rule suite, #60 MCP server, #61 playbook reporter, #62 unit-economics
  card, #63 remediation-PR drafter).

- User-facing guide (`docs/user-guide.md`) showing what the tool delivers,
  with report previews, CLI visuals, worked over-licensed examples drawn from
  the deterministic demo report, and an explicit note on current under-licensed
  scope.
- `finops-assess triage`, an advisory subcommand that reads an existing
  read-only JSON report and emits stable triage JSON/CSV artefacts while
  preserving source PII redaction. GitHub Copilot SDK/CLI helper discovery is
  explicit opt-in and gracefully skips when unavailable.
- Future-plan docs for GitHub Copilot-assisted triage and optional FinOps Hubs
  linkage, plus contributor guidance requiring docs updates with every PR.
- A read-only FinOps Hubs export/import design boundary that keeps Hubs
  optional, file-based, and operator controlled until a separate connector is
  reviewed.
- Exploratory frontier roadmap docs for FinOps Toolkit / FOCUS / Hubs alignment,
  Azure pricing intelligence, agreement discounts, commitments, SKU-mix reviews,
  data-collection frontiers, practice-review outputs, optional Copilot / Azure
  MCP assistance, and draft local operator skills.
- Exploratory FOCUS 1.2 correlation mapping (`docs/roadmap/focus-mapping.md`)
  documenting how today's `Finding` and `run` fields line up with FOCUS columns
  for operator-side correlation against an existing FinOps Toolkit / Hubs
  dataset. Docs-only; no exporter, schema, or collector changes.

## Shipped milestones

These items track the original delivery roadmap. Each is shipped on
`main` and is the cumulative state of the tool before the first
tagged release.

| ID | Deliverable | PR |
|----|-------------|----|
| M0 | Repo scaffold and the original plan | #1 |
| M1 | License catalogue YAML (87 SKUs) | #2 |
| M2 | CSV collector, persona engine, and the first 23 savings rules | #3 |
| M3 | HTML and JSON report, demo workflow, PowerShell wrapper | #4 |
| M4 | Microsoft Graph live collector with OIDC federated auth | #9 |
| M5 | Azure Cost Management collector | #9 |
| M6 | GitHub and Azure DevOps collectors | #9 |
| M7 | PDF executive report (WeasyPrint, deterministic build) | #7 |
| Bonus | Flat-CSV findings reporter for Excel pivots | #10 |

All milestones are `✅` shipped.
