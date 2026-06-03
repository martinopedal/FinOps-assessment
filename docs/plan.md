# FinOps Assessment: Plan

> **Contributor documentation.** If you only want to run the tool,
> start from the project [README](../README.md). Release history is
> in [`CHANGELOG.md`](../CHANGELOG.md).

> **Scope**: A read-only auditing tool that ingests licensing, identity,
> usage, and cost data across the **Microsoft ecosystem** and emits
> right-sizing and savings recommendations.
>
> **Surfaces covered**: Microsoft 365 (incl. Entra ID / EMS, Defender,
> Purview, Power Platform), Azure, GitHub, Azure DevOps.
>
> **Non-goals (v1)**: making changes (no writes, no remediation),
> third-party SaaS outside Microsoft, on-prem CALs, perpetual licensing
> reconciliation.

---

## 1. Guiding principles

1. **Read-only by construction.** Collectors only ever request read /
   `*.Read.All` scopes. The schema for emitted recommendations is
   advisory: every rule output must include the *exact* admin action a
   human would take, never an automated mutation.
2. **Evidence-first.** Every recommendation links back to the raw rows /
   API responses that produced it (stored as a hash + path inside the
   evidence bundle), so an admin can defend the call.
3. **Offline-first.** The default entry point is a CSV / JSON ingest
   path. Live collectors (Graph, ARM, Cost Management, GitHub, ADO) are
   thin adapters that produce the same normalized schema.
4. **Persona-driven sizing.** The right-size question is never "is this
   user over-licensed?" in the abstract; it's "given this user's
   *persona*, are they on the cheapest SKU that still covers the
   features they actually use?"
5. **Catalogue is data, not code.** SKUs, features, list prices, and
   bundle relationships live in versioned YAML, seeded from public
   sources (Aaron Dinnage's M365 Maps, Microsoft Learn SKU IDs,
   Azure retail prices API). Rules reference catalogue entries by ID.
6. **No redistribution of third-party copyrighted material.** We link
   to and credit source diagrams; we do not copy them.
7. **Python is the reference / conformance-oracle engine; a native
   PowerShell engine is admitted as a deliberately-justified, governed
   second runtime that ships *alongside* Python.** Python remains the
   normative implementation: the schemas in `src/finops_assess/models.py`
   (pydantic v2, `extra="forbid"`), the rule semantics in
   `data/rules/**`, and the byte-deterministic reporter outputs are the
   conformance oracle that any second runtime must reproduce. A native
   PowerShell engine (PowerShell 7.2+ only; Windows PowerShell 5.1 is
   out of scope) is admitted because a non-trivial fraction of the
   target operator population (M365 / Entra / Defender / Purview / Intune
   admins) lives in `pwsh` natively, and a PS-native CLI removes the
   "install Python first" friction barrier for those operators. The PS
   engine is a peer engine, not a wrapper: it runs its own collectors,
   rules, and JSON/CSV/manifest reporters, and is held to the same
   read-only / PII-redaction / no-secrets / no-third-party-copyright
   hard rules as Python. **PDF reporting is explicitly delegated to
   Python** (the PS engine renders to JSON/CSV/Markdown and shells out
   to the Python CLI for PDF, or simply does not offer PDF) — possibly
   permanently. The PS engine is governed by the same five-stage
   delivery loop (§11), the same docs-voice rules, and the same
   no-mutation posture as Python. **Dual-maintenance is the default
   end-state, not a transition phase**: every new Python rule,
   collector, or reporter must either land PS parity in the same PR /
   release, or declare the feature explicitly unsupported in PS with a
   dated compatibility note (see §7a, and the §7a governance rule
   mirrored into `.github/copilot-instructions.md`). Retiring Python in
   favour of PS-only is **deferred** to a separate decision gate (§1.7a)
   and explicitly does **not** happen in this initiative; even reaching
   §1.7a's bar requires a fresh stage-4 adversarial review and is not
   pre-approved here. Until the PS engine ships its first parity
   release, the legacy thin wrapper (`scripts/Invoke-FinOpsAssess.ps1`)
   stays in place; collectors may continue to shell out to `pwsh` for a
   Python rule only when a PowerShell-only module returns materially
   richer data than the raw API (documented exception, not the
   default).

---

### 1.7a Go-full-PowerShell phase gate

This sub-section is **only** the falsification gate that would have to
be cleared *before* the project could even propose retiring Python in
favour of a PS-only engine. Reaching this bar does **not** automatically
trigger retirement; it merely unlocks a fresh stage-3 plan and a fresh
stage-4 adversarial review on a future "go-PS-only" proposal. Until
every criterion below is satisfied with public, reproducible evidence,
the answer to "can we drop Python yet?" is **no**, and dual-maintenance
(§1.7 and §7a) remains in force.

**Capability-parity criteria.** The PS engine must demonstrate, with
public evidence linked from the gate-evaluation issue:

1. **Sustained conformance parity for ≥ 3 consecutive releases.** A
   conformance harness produces byte-identical (or formally
   equivalence-classed) JSON / CSV / manifest outputs for a shared
   fixture corpus across both engines, green for three consecutive
   tagged releases with no engine-specific xfails accumulating.
2. **3-OS CI parity on `pwsh` 7.2+.** The PS engine's full test +
   conformance + lint matrix passes on `{ubuntu-latest,
   windows-latest, macos-latest} × pwsh ≥ 7.2`, included in the
   single `required-checks` summary context (see §11) — not as an
   ungated parallel job.
3. **PDF resolved or formally accepted as Python-only.** Either the PS
   engine renders PDF natively at parity, **or** the project records a
   binding ADR that PDF remains a Python-delegated capability
   permanently (in which case "go PS-only" implies dropping native
   PDF — that trade-off must be re-ratified at the future stage-4).
4. **Live-collector read-only parity.** Every live collector (Graph,
   ARM, Cost Management, GitHub, Azure DevOps) is implemented natively
   in PS using read-only scopes only, with the §9 scope-guard refusing
   to run on a write-capable token — and has been exercised against a
   real tenant under OIDC federated credentials (no PATs / secrets) for
   ≥ 6 months without a read-only escape.
5. **Measured maintenance-cost data.** ≥ 2 consecutive quarters of
   tracked engineering-time data on dual-maintenance (PR-level labels
   `engine:python` / `engine:powershell` / `engine:both`, time-to-merge,
   defect rates). Retirement requires *measured* evidence that PS-only
   would lower total cost without lowering quality — not assertion.
6. **Operator adoption ≥ 50 % across ≥ 3 distinct organisations.**
   Voluntary, opt-in telemetry or attestations from real operators
   showing the PS engine is materially used in production (not just
   dogfooded by maintainers), across at least three independent
   organisations.
7. **PII algorithm formally pinned.** The salted-hash redaction
   algorithm (HMAC variant, salt derivation, normalisation rules) is
   pinned in a versioned spec document, with shared test vectors that
   both engines reproduce byte-for-byte and that any future change goes
   through a `pii_algorithm_version` bump in the manifest.
8. **Zero open 🔴 conformance defects.** No open `conformance:🔴`
   issues at the gate-evaluation moment; any closed ones are closed
   with linked regression fixtures.

**Security-falsification gates (Noor, binding).** In addition to the
capability criteria above, retirement requires:

9. **Token-claim catch-rate ≥ Python for ≥ 2 releases.** The §9
   read-only scope-guard in PS, exercising actual-token claim
   introspection (not static config), catches every write/admin scope
   the Python guard catches across a shared adversarial corpus, for
   two consecutive tagged releases.
10. **Shared PII test vectors green for ≥ 6 months.** The shared
    PII-redaction test-vector suite (HR-4 byte-parity) is green on
    both engines continuously for ≥ 6 months with no
    PS-engine-specific deviations or `xfail`-on-PS exemptions.
11. **No growing `xfail`-on-PS list.** The conformance harness reports
    a non-increasing count of PS-engine `xfail`s release-over-release;
    a sustained upward trend disqualifies the gate.
12. **Schema rigor equivalence.** The PS engine enforces schema rigor
    operationally equivalent to pydantic v2 `extra="forbid"` —
    unknown fields rejected at ingest, type coercion explicit, optional
    vs required parity — verified by a shared fuzz / property-based
    schema-conformance test corpus.
13. **`pwsh`-only-on-Linux including live OIDC for ≥ 6 months.** The PS
    engine runs end-to-end on `pwsh` on Linux runners, including live
    OIDC-federated collector runs against a real tenant, for ≥ 6
    months continuously — closing the "PS = Windows-only" historical
    risk Noor flagged.
14. **Independent security review.** A non-Noor, non-maintainer
    reviewer (external pen-test or an explicitly different security
    reviewer of equivalent rigor) signs off on the PS engine's
    read-only posture, secret-handling, and PII implementation.
15. **HR-3 copyright audit.** A repo-wide audit confirms the PS engine
    introduced no third-party copyrighted material (vendored modules,
    bundled diagrams, copied pricing tables) — same bar as Python.
16. **Sunset ADR preserves CodeQL / Dependabot equivalents.** Before
    Python is retired, an ADR records equivalent supply-chain controls
    for the PS engine (static analysis comparable to CodeQL, dependency
    update / advisory tracking comparable to Dependabot) — Python's
    existing controls are not silently dropped.

**Decisions recorded as binding inputs to this gate** (Martin, owner,
2026-06-02):

- **D1 — Dual-maintenance funding:** PERMANENT; the §7a governance
  rule (no new Python rule / collector / reporter reaches stable
  without same-PR PS parity, or an explicit dated unsupported-note) is
  ACCEPTED and binding.
- **D2 — Transition intent:** REAL COMMITMENT — the project will
  invest in §1.7a so Python *can* eventually be retired once the gate
  is met; this is not a paper exercise.
- **D3 — PDF:** Python-only (delegated) is ACCEPTED, possibly
  permanent (criterion 3 codifies the re-ratification requirement).
- **D4 — PS version:** PowerShell 7.2+ only; Windows PowerShell 5.1 is
  out of scope.

**Process to retire Python.** Even if every criterion 1–16 is
demonstrably met, retiring Python requires a fresh §11 cycle —
research → rubberduck → stage-3 plan → **fresh stage-4 adversarial
review (Noor or successor)** → consensus → implementation. Noor's
stage-4 verdict on the *current* initiative explicitly REJECTS
pre-approving full transition; that rejection stands until the fresh
stage-4 reverses it.

---

## 2. Milestones

The shipped milestone history has moved to [`CHANGELOG.md`](../CHANGELOG.md).
Future delivery tracking lives in GitHub issues with a `squad:*` label.

---

## 3. Architecture

```
                ┌─────────────────────────────────────────────┐
                │                Collectors                   │
                │  CSV  Graph  ARM  GitHub  ADO  CostMgmt     │
                └───────────────────┬─────────────────────────┘
                                    │  normalized records
                                    ▼
                ┌─────────────────────────────────────────────┐
                │   Normalizer  (catalog-aware enrichment)    │
                │   • resolves SKU IDs; catalog entries      │
                │   • joins users ↔ assignments ↔ usage       │
                └───────────────────┬─────────────────────────┘
                                    ▼
                ┌─────────────────────────────────────────────┐
                │  Persona engine  (assigns each principal a  │
                │  persona based on signals + overrides)      │
                └───────────────────┬─────────────────────────┘
                                    ▼
                ┌─────────────────────────────────────────────┐
                │   Rule engine  (deterministic, declarative) │
                │   inputs: catalog, personas, signals        │
                │   outputs: findings + evidence refs         │
                └───────────────────┬─────────────────────────┘
                                    ▼
                ┌─────────────────────────────────────────────┐
                │   Reporters   JSON · HTML · PDF · CSV       │
                └─────────────────────────────────────────────┘
```

### Package layout

```
src/finops_assess/
  __init__.py
  cli.py                # `finops-assess` entry point (Click)
  models.py             # pydantic models for Catalog, Persona, Rule, Finding
  catalog/
    __init__.py         # loader + validator (`python -m finops_assess.catalog`)
  rules/
    __init__.py         # loader + validator + engine
  collectors/
    base.py
    csv_collector.py
    graph_collector.py
    arm_collector.py
    github_collector.py
    ado_collector.py
  reporters/
    json_reporter.py
    html_reporter.py
    pdf_reporter.py
  data/                 # packaged mirror of repo-root data/ for wheel installs
data/
  catalog/
    m365/   azure/   github/   ado/
  personas.yaml
  rules/
    m365.yaml   azure.yaml   github.yaml   ado.yaml
samples/                # synthetic tenants for tests + `demo`
tests/
docs/
  plan.md       # this file
  schema.md     # data and report contract reference
```

The repo-root `data/` tree is the authoring location for catalogue, persona,
and rule YAML. `src/finops_assess/data/` is a byte-identical packaged mirror so
`finops-assess validate`, `run`, and `demo` work after a non-editable wheel
install; CI guards the mirror against drift.

---

## 4. Catalogue model

A SKU entry:

```yaml
- id: SPE_E3                            # Microsoft service-plan / SKU ID
  display_name: Microsoft 365 E3
  family: m365_enterprise
  cloud: m365
  list_price_usd_month: 36.00           # nullable; rules degrade gracefully
  source_url: https://m365maps.com/...  # citation, never the diagram itself
  includes:                              # bundle composition
    - EXCHANGE_S_ENTERPRISE
    - SHAREPOINTENTERPRISE
    - TEAMS1
    - INTUNE_A
    - AAD_PREMIUM
  features:                              # canonical capability tags
    - mailbox.100gb
    - office.desktop
    - intune.mdm
    - entra.p1
    - defender.o365.p1
  successor_of: [SPE_E1]                 # upgrade path hints
```

Canonical **feature tags** form a small controlled vocabulary
(`mailbox.*`, `office.*`, `teams.*`, `intune.*`, `entra.*`,
`defender.*`, `purview.*`, `power.*`, `copilot.*`). Personas are
expressed in terms of these tags so that rules are catalogue-agnostic.

---

## 5. Persona model

Each principal is mapped to exactly one persona; a persona declares
the **minimum required feature tags**. Sample personas:

| Persona | Minimum features | Typical SKU |
|---|---|---|
| `frontline_kiosk` | `mailbox.2gb`, `teams.basic` | F1 |
| `frontline_worker` | `mailbox.2gb`, `office.web`, `teams.basic`, `intune.mam` | F3 |
| `information_worker` | `mailbox.50gb`, `office.desktop`, `teams.full` | E3 |
| `power_user_secure` | E3 features + `entra.p2`, `defender.o365.p2`, `purview.dlp` | E5 |
| `developer` | `office.web`, `teams.full`, `github.enterprise`, `vs.subscription` | E3 + GH EE + VS |
| `service_account` | none (excluded from licensing) | n/a |

Persona assignment signals (in priority order):

1. Explicit override in `samples/overrides.yaml`.
2. Job-title regex map (configurable per tenant).
3. Group-membership map.
4. Usage-fingerprint fallback (which service plans actually saw activity in
   the last N days).

---

## 6. Savings rules: initial set

Each rule has: `id`, `surface`, `severity`, `recommendation_template`,
`evidence_query`, `estimated_monthly_savings()`.

### M365 rules
- `M365.UNUSED_LICENSE_30D`: assigned SKU with no service-plan activity in 30 d.
- `M365.OVER_LICENSED_VS_PERSONA`: assigned SKU strictly dominates persona's required features; recommend cheapest covering SKU.
- `M365.DUPLICATE_BUNDLE`: user has both a bundle and a child SKU it already includes (e.g., E3 + standalone Exchange Online P1).
- `M365.DISABLED_USER_LICENSED`: `accountEnabled == false` but licenses still assigned.
- `M365.SHARED_MAILBOX_LICENSED`: shared mailbox <50 GB with an assigned user license.
- `M365.GUEST_PREMIUM_LICENSED`: Entra B2B guest carrying an interactive license.
- `M365.COPILOT_INACTIVE_60D`: Copilot add-on with zero Copilot activity in 60 d.
- `M365.E5_FEATURES_UNUSED`: E5 user with no Defender/Purview/Entra-P2 signal in 90 d; step down to E3 + targeted add-ons.

### Azure rules
- `AZ.IDLE_VM_14D`: VM with <5 % CPU and <100 KB/s net for 14 d.
- `AZ.UNATTACHED_DISK`: managed disk not attached for 7 d.
- `AZ.PUBLIC_IP_UNATTACHED`: standard public IP not associated.
- `AZ.OVERSIZED_VM`: P95 CPU & memory < 40 % for 14 d; recommend smaller SKU in same family.
- `AZ.RESERVATION_UNDERUTILIZED`: RI/Savings Plan utilization < 80 % for 30 d.
- `AZ.LOG_ANALYTICS_OVERINGEST`: workspace ingesting > commitment-tier sweet spot.
- `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`: scope with uncovered on-demand spend a Savings Plan would cover (Benefit Recommendations API).
- `AZ.COMMITMENT_UNDER_COVERED`: under-utilised reservation while a sibling subscription pays on-demand for a likely-compatible workload (scope-widening signal).
- `AZ.COMMITMENT_RENEWAL_REVIEW`: reservation expiring within 60 days with auto-renew not configured.
- `AZ.RESERVATION_SCOPE_MISMATCH`: single-scope reservation while sibling subscriptions carry significant on-demand spend for likely-compatible workloads.
- `AZ.AHB_ELIGIBLE`: Windows VM running without Azure Hybrid Benefit applied.
- `AZ.DEV_TEST_SUB_PRODUCTION_PRICING`: workload tagged `env=prod` running in a Dev/Test subscription (or vice-versa).

### GitHub rules
- `GH.INACTIVE_SEAT_90D`: Enterprise / Business seat with no contributions, reviews, or sign-in in 90 d.
- `GH.COPILOT_INACTIVE_30D`: Copilot Business/Enterprise seat with zero suggestions accepted in 30 d.
- `GH.GHAS_UNUSED`: Advanced Security committer count > active code-scanning repos.
- `GH.UNUSED_RUNNER_MINUTES`: paid runner minutes consumed << included quota; or vice-versa, persistently overspending an SKU tier with a cheaper bundle available.

### Azure DevOps rules
- `ADO.INACTIVE_BASIC_90D`: Basic seat with no work-item or repo activity in 90 d.
- `ADO.STAKEHOLDER_ELIGIBLE`: Basic seat whose only activity is reading boards / commenting; step down to free Stakeholder.
- `ADO.PARALLEL_JOBS_OVER_PROVISIONED`: purchased Microsoft-hosted parallel jobs > P95 concurrent usage.
- `ADO.TEST_PLANS_UNUSED`: Basic+Test seat with no Test Plans activity.

### FOCUS-aligned advisory export

Findings can additionally be projected onto a FOCUS-aligned advisory CSV via
`finops-assess export focus-aligned`; see [`docs/focus-export.md`](focus-export.md).
This export is NOT a FOCUS 1.3 conformant Cost-and-Usage dataset — it is an advisory
view that joins to your cost warehouse on `ResourceId`. Multi-surface (Azure, M365,
GitHub, ADO) from v0.6.0 (#71). Use `--surface azure` for v0.5.0 Azure-only behavior.

---

## 7. Data sources & APIs (live collectors)

| Source | API | Auth |
|---|---|---|
| Entra ID / M365 | Microsoft Graph v1.0 (`users`, `subscribedSkus`, `reports/*`, `auditLogs/signIns`) | Workload-identity OIDC; app registration with `*.Read.All` |
| Azure resources | ARM (`Microsoft.Compute`, `Microsoft.Network`, `Microsoft.Storage`, etc.) | Same federated credential, `Reader` role |
| Azure cost | Cost Management `query` API + Retail Prices API (anon) | Same |
| GitHub | REST `/enterprises/{ent}/consumed-licenses`, `/enterprises/{ent}/copilot/billing/seats`, `/orgs/{org}/settings/billing/advanced-security`, `/orgs/{org}/settings/billing/actions` | GitHub App / token with read-only Enterprise + Org billing perms |
| Azure DevOps | `vsaex` user-entitlements, `_apis/userentitlements`, `pipelines` usage | PAT (read) or Entra-backed service principal |

All collectors emit the same normalized record shape so the rule engine
is source-agnostic.

**Phase-6 status:** PowerShell live-collector base scaffolding shipped in
Phase 6a (`Get-FinOpsAccessToken`, `Invoke-FinOpsRestRequest` GET-only,
`Write-FinOpsCollectorCsv`, `Get-FinOpsNow`, `Invoke-FinOpsLiveCollection`
dispatcher + scope-guard call-site). Phase 6b shipped the Graph collector
(`Get-FinOpsGraphCollector` + dispatcher Graph arm), Phase 6c shipped the
ARM collector (`Get-FinOpsArmCollector` + dispatcher Arm arm with two-key
operator-attested consent), and Phase 6d now ships the GitHub collector
(`Get-FinOpsGitHubCollector` + dispatcher GitHub arm using `X-OAuth-Scopes`
probe classification for classic PATs and fail-closed fine-grained PAT
handling unless `-AllowUnknownScopes` is operator-attested). Phase 6e ships
the Azure DevOps collector (`Get-FinOpsAdoCollector` + dispatcher Ado arm with
PAT/Bearer auth paths and guard enforcement), completing Phase 6 parity across
all four live-collector surfaces.

---

## 7a. Dual-maintenance governance (PowerShell side-by-side)

This section is the canonical home of the §7a governance rule
referenced by §1.7 / §1.7a and mirrored into
`.github/copilot-instructions.md`. It is binding from the moment the
docs-only "approve PowerShell side-by-side engine" PR merges and stays
in force until and unless retirement of either engine is approved
through a fresh §11 stage-4 review (see §1.7a).

**Rule.** No new Python rule, collector, or reporter reaches stable
unless either:

- **(a)** PowerShell parity (same rule / collector / reporter,
  reproducing byte-deterministic outputs against the shared
  conformance fixture corpus) lands in the *same* PR or release; or
- **(b)** the PowerShell module explicitly declares the feature
  unsupported with a dated compatibility note (`unsupported_since:
  YYYY-MM-DD`, with a one-line rationale and a link to a tracking
  issue), and the conformance harness is updated to skip it
  intentionally (an explicit `xfail` / skip with the same dated
  rationale, *not* an implicit silent miss).

The conformance CI job mechanically enforces this: a Python rule /
collector / reporter that has neither a PS implementation nor a
matching dated unsupported-note + harness skip causes the conformance
job to fail, which fails the single `required-checks` summary
context. Reviewers do not chase compliance manually.

**Symmetry.** The same rule applies in reverse once the PS engine
ships its first parity release: a PS rule / collector / reporter
without same-PR Python parity (or a dated Python unsupported-note +
harness skip) also fails conformance. Neither engine is permitted to
quietly diverge.

**Out of scope of §7a.** PDF reporting is delegated to Python by
explicit decision (§1.7 / §1.7a criterion 3); the PS engine is *not*
required to ship PDF parity, and the lack of PS-native PDF does not
trigger a §7a violation. Any future change to that delegation
requires re-ratification at a fresh stage-4.

---

## 8. Reporting

- **JSON**: canonical machine-readable output; one file per run, plus a
  per-finding evidence bundle (gzip'd JSONL).
- **HTML**: single self-contained file; tables grouped by surface and
  severity; each finding shows persona, current SKU, recommended SKU,
  estimated monthly savings, and an "Evidence" disclosure with the raw
  rows. Built with Jinja2 + a vendored print-friendly CSS.
- **PDF**: WeasyPrint render of the HTML with an executive
  summary page.
- **CSV**: flattened findings for pivoting in Excel.

---

## 9. Security & operations

> **Operator reference:** the consolidated security posture lives in
> [`docs/security.md`](security.md) — read-only contract, OIDC auth,
> PII redaction, overlay-template sandbox, and the change-management
> anchor for future security additions. The bullets below remain the
> plan-level summary; deep-dives belong in `docs/security.md`.

- All Graph / ARM / GitHub / ADO scopes are **read-only**. The CLI
  refuses to start if a credential with write scope is detected.
- Live-mode runs default to **OIDC federated credentials** in GitHub
  Actions; no long-lived secrets in the repo.
- All emitted reports redact UPN local-parts behind a salted hash by
  default; `--no-pii-redaction` is opt-in.
- **Tenant-stable PII salt** (#73, v0.6.0): operators may supply a
  persistent salt via `--pii-salt-file` or `FINOPS_PII_SALT` for
  cross-run principal stability; default remains per-run rotation.
  Plan: `docs/plans/073-engine-tenant-stable-pii-salt.md`.
- **Reporter template overlay** (#74, v0.6.0): operator-supplied Jinja2
  templates via `--allow-template-overlay <dir>` with
  `SandboxedEnvironment`, pre-flight validation, and per-template
  SHA-256 provenance in `manifest.template_sources[]`.
  Plan: `docs/plans/074-reporter-template-overlay.md`.
- **FOCUS exporter multi-surface** (#71, v0.6.0): extends advisory CSV
  export to M365, GitHub, and Azure DevOps surfaces with per-surface
  `ServiceName`/`ServiceCategory` mapping, `--surface` CLI flag, and
  widened `pii_handling.mode` manifest enum.
  Plan: `docs/plans/071-focus-exporter-multi-surface.md`.
- Repo hardening (applied immediately after first PR lands):
  branch protection on `main`, required CI, required review,
  Dependabot for `pip` + `github-actions`, secret scanning + push
  protection, CodeQL on the Python package, signed commits encouraged.

---

## 10. Open questions and future plan

### Future plan: Copilot-assisted triage and FinOps Hubs

This section records the next-PR plan for two related but unshipped
capabilities: using GitHub Copilot to help triage findings, and linking
`finops-assess` outputs with FinOps Hubs when a customer has both GitHub
Copilot and FinOps Hubs.

### Current boundary

- GitHub Copilot is currently assessed as a **licensed GitHub seat** via
  `GH.COPILOT_INACTIVE_30D`.
- Microsoft 365 Copilot is currently assessed via
  `M365.COPILOT_INACTIVE_60D`.
- The product now provides a deterministic `finops-assess triage` advisory
  JSON/CSV artefact derived from existing findings. GitHub Copilot SDK/CLI
  helper discovery is explicit opt-in and disabled by default; no finding data
  is sent to Copilot by the default command path.
- The product does **not** yet provide live Copilot natural-language
  enrichment or FinOps Hubs integration.

### Next-PR checklist

1. ✅ Define a read-only triage contract that takes existing `Finding`
   records plus redacted evidence and emits analyst-facing triage
   metadata: priority rationale, suggested owner, verification checklist,
   and recommended follow-up questions.
2. ✅ Add a UX contract first: GitHub Copilot may assist
   analysts in understanding and grouping findings, but it must not take
   remediation actions, request write scopes, or expose unredacted PII by
   default. The first shipped step mirrors the azure-analyzer pattern:
   optional helper discovery is behind an explicit opt-in flag and gracefully
   skips when the SDK/CLI is unavailable.
3. ✅ Add a FinOps Hubs export/import design that treats FinOps Hubs as an
   optional integration surface: customers with both tools can correlate
   Azure cost context, commitment data, and `finops-assess` findings,
   while customers without FinOps Hubs keep the existing offline workflow.
4. ✅ Keep the first implementation small: emit a stable JSON/CSV artefact
   that FinOps Hubs workflows or GitHub Copilot prompts can consume before
   adding any live connector.
5. ✅ Add tests around redaction, schema stability, and the guarantee that
   triage/export paths remain read-only and advisory.
6. ✅ Update user docs, schema docs, generated examples, and changelog in
   the same PR that ships the implementation.

FinOps Hubs compatibility is **not claimed** by the first triage artefact.
The shipped contract is a stable JSON/CSV shape, versioned by
`TRIAGE_SCHEMA_VERSION`, that downstream Hubs workflows may consume before a
dedicated connector is designed.

### FinOps Hubs export/import design

FinOps Hubs remains an optional downstream surface, not a required runtime
dependency. The current integration boundary is:

1. `finops-assess` continues to emit local JSON, CSV, and advisory triage
   artefacts only. It does not call FinOps Hubs APIs, provision storage,
   deploy Data Factory pipelines, or write to a customer's FinOps Hubs
   environment.
2. Handoff is file-based and operator controlled. A customer may place
   `demo-report.json`, `demo-report.csv`, `triage.json`, or `triage.csv` in
   their own FinOps Hubs landing zone after local review. The tool should
   document the file contract but must not automate upload or mutation in v1.
3. Correlation keys are intentionally conservative: `run.generated_at`,
   `run.schema_version`, `finding_ref`, `rule_id`, `surface`, redacted
   `principal`, `current_sku`, `recommended_sku`, and
   `estimated_monthly_savings_usd`. These let FinOps Hubs users join
   findings to Azure cost and commitment exports without requiring raw PII.
4. Any future connector must be a new, reviewed capability with an issue,
   explicit read-only or customer-local storage semantics, tests proving PII
   redaction remains on by default, and docs that state how data leaves the
   local machine.

This means customers with FinOps Hubs can build their own ingestion around the
stable report and triage files today, while customers without Hubs keep the same
offline workflow and outputs.

### Acceptance criteria

- No new write scopes, long-lived secrets, tenant IDs, PATs, or mutation
  paths are introduced.
- Copilot-assisted triage output is clearly labelled advisory and includes
  evidence references back to the original finding.
- FinOps Hubs linkage is optional, documented, and degrades gracefully when
  FinOps Hubs data is absent.
- PII redaction remains on by default for any prompt, export, or triage
  payload.

### Open questions

1. **RESOLVED (PR #30):** Pricing profiles are customer-supplied inputs, NOT catalogue constants. Default posture is list price (multiplier=1.0, source=default_list). Agreement discounts (EA/MCA/CSP/MOSP/negotiated) are modeled as optional `PricingProfile` inputs with explicit currency, scope, and temporal bounds. Rules join observations with profiles; the model enforces no tenant-specific rate cards in the repo.
4. **IN PROGRESS (#75):** Scribe-after-Stage-4 serialization — housekeeping
   commits must not race with bot approval. Stage-3 plan at
   `docs/plans/075-serialize-scribe-behind-stage4.md`.
2. Persona inference confidence, surface as a column? *Yes; rules with
   confidence < 0.7 are downgraded to "advisory".*
3. How to handle **per-user Copilot for M365** vs **GitHub Copilot** vs
   **Copilot Studio** in the same report without confusing the reader?
   *Group under a single "Copilot" report section with sub-tables.*

### Frontier roadmap index

The next frontier is documented as **exploratory**, not shipped scope, in
[`docs/roadmap/README.md`](roadmap/README.md). It records guardrails and future
thin-slice PRs for FinOps Toolkit / FOCUS / Hubs alignment, Azure region price
comparisons, agreement discount profiles, RI and Savings Plan reviews, M365 /
Entra / Copilot / security / GSA SKU-mix reviews, data-collection frontiers,
practice-review outputs, and optional GitHub Copilot / Azure MCP assistance.

Local operator skill and runbook ideas are indexed in
[`docs/skills/README.md`](skills/README.md). They are draft documentation only:
no command, rule, collector, schema, pricing profile, Hubs connector, or MCP
integration is shipped until a later PR completes the §11 loop for that slice.

---

## 11. Per-step delivery process (multi-agent)

Every change of any size is delivered through a fixed five-stage
loop. Each stage is owned by a dedicated sub-agent, invoked via the
Copilot CLI's `task` tool with the `agent_type` shown, so the work
is parallelisable, reviewable, and auditable. **No code change skips
stages 1 to 4.**

| # | Stage | Agent | Model | Output |
|---|-------|-------|-------|--------|
| 1 | **Research** | `explore` (parallel-safe) | Haiku (cost-first; reads docs + repo) | A short brief: relevant API surfaces, SKU IDs, prior-art links, public docs, identified unknowns. Read-only, no code edits. |
| 2 | **Rubberduck** | `general-purpose` | Sonnet | Plain-English walkthrough of the proposed approach against the brief: what could go wrong, edge cases, false-positive risks, security implications, alternative designs considered. |
| 3 | **Plan** | `general-purpose` | **Opus 4.7 (always)** | Concrete checklist of file-level changes (paths, schemas, rule IDs), tests to add, and acceptance criteria, small enough to fit in one PR. Posted into the issue/PR before any edits. Plan owns the most consequential reasoning of the loop and is the one stage where we never trade capability for cost. |
| 4 | **Consensus** | Human reviewer + `general-purpose` adversarial pass | **Opus 4.7** for the adversarial pass | Reviewer signs off on the plan; an adversarial agent run challenges the plan ("steelman the case against shipping this"). Disagreements are resolved by amending the plan, not by overriding it silently. |
| 5 | **Implement** | `general-purpose` (or `task` for narrow mechanical edits) | Sonnet by default; Opus 4.7 if the plan calls for it; Haiku for purely mechanical edits | The actual code/data/doc changes, plus tests, plus a `parallel_validation` (code review + CodeQL) gate before opening the PR. |

Stages 1 to 3 produce **artefacts that live in the PR description or in
`docs/decisions/`** so future contributors can reconstruct *why* a
choice was made, not just *what* changed. Stage 4 must reach explicit
agreement; "no objections raised within X" does not count as consensus
for security-relevant or schema-changing work.

When an agent fails or hits a dead-end, the next agent must restate
the brief from stage 1 in its own words before proceeding, this
catches misunderstandings early and prevents single-agent tunnel
vision. Agents are stateless across invocations; the PR is the shared
memory.

This process is mirrored in `.github/copilot-instructions.md` so that
Copilot-assisted work picks it up automatically.

### Squad team that executes the loop

The five stages map onto a [Squad](https://github.com/bradygaster/squad)
team initialised under `.squad/`:

| Stage | Owner(s) | Squad label | Model |
|-------|----------|-------------|-------|
| 1. Research | surface specialist (Priya / Diego / Sam) | `squad:m365-specialist` · `squad:azure-specialist` · `squad:devsurfaces-specialist` | Haiku |
| 2. Rubberduck | same surface specialist + Lead | as above + `squad:lead` | Sonnet |
| 3. Plan | Lead (Maya) | `squad:lead` | **Opus 4.7 (always)** |
| 4. Consensus | Lead + Security reviewer (Noor, adversarial pass) | `squad:lead` + `squad:security-reviewer` | **Opus 4.7** for the adversarial pass |
| 5. Implement | surface specialist + Tester (Yuki) + optionally `@copilot` for green-rated work | `squad:{specialist}` + `squad:tester` (+ `squad:copilot`) | Sonnet (default) |

Charters live under `.squad/agents/{member}/charter.md`. Routing rules
live in `.squad/routing.md`. Issue templates under
`.github/ISSUE_TEMPLATE/` open tasks straight onto the squad inbox
(`squad` label). The Lead triages within one working day.

The squad runs **on cloud agents** via GitHub Actions, `squad-triage`,
`squad-issue-assign`, and `squad-pr-route` react to label events on
**both issues and pull requests**, so labelling a PR with
`squad:{member}` posts the same routing acknowledgment that labelling
an issue does. `sync-squad-labels` keeps the `squad:{member}` label set
in sync with `.squad/team.md` on every push to that file.
