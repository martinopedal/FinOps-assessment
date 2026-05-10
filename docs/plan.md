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
7. **Python is the engine language.** Cross-platform, first-class SDKs
   for Graph / ARM / GitHub / ADO, strong schema/typing tools
   (pydantic v2, mypy strict). PowerShell is a great *admin shell* but
   not a great normalisation/reporting engine, and we need one engine
   that runs identically on Linux runners, in containers, and on a
   Windows admin's laptop. A thin PowerShell wrapper script
   (`scripts/Invoke-FinOpsAssess.ps1`) ships alongside the Python CLI so
   PowerShell-native operators can pipeline our JSON output without
   touching Python directly; collectors may shell out to `pwsh` only
   when a PowerShell-only module returns materially richer data than
   the raw API (documented exception, not the default).

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

---

## 7. Data sources & APIs (live collectors)

| Source | API | Auth |
|---|---|---|
| Entra ID / M365 | Microsoft Graph v1.0 (`users`, `subscribedSkus`, `reports/*`, `auditLogs/signIns`) | Workload-identity OIDC; app registration with `*.Read.All` |
| Azure resources | ARM (`Microsoft.Compute`, `Microsoft.Network`, `Microsoft.Storage`, etc.) | Same federated credential, `Reader` role |
| Azure cost | Cost Management `query` API + Retail Prices API (anon) | Same |
| GitHub | REST `/enterprises/{ent}/consumed-licenses`, `/enterprises/{ent}/copilot/billing/seats`, `/orgs/{org}/audit-log` | GitHub App with read-only Enterprise + Org perms |
| Azure DevOps | `vsaex` user-entitlements, `_apis/userentitlements`, `pipelines` usage | PAT (read) or Entra-backed service principal |

All collectors emit the same normalized record shape so the rule engine
is source-agnostic.

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

- All Graph / ARM / GitHub / ADO scopes are **read-only**. The CLI
  refuses to start if a credential with write scope is detected.
- Live-mode runs default to **OIDC federated credentials** in GitHub
  Actions; no long-lived secrets in the repo.
- All emitted reports redact UPN local-parts behind a salted hash by
  default; `--no-pii-redaction` is opt-in.
- Repo hardening (applied immediately after first PR lands):
  branch protection on `main`, required CI, required review,
  Dependabot for `pip` + `github-actions`, secret scanning + push
  protection, CodeQL on the Python package, signed commits encouraged.

---

## 10. Open questions

1. Should the catalogue carry **EA / CSP discount tiers** as multipliers,
   or assume list price and document the gap? *Proposed: list price in
   v1, multiplier file once Cost Management ingest is in place.*
2. Persona inference confidence, surface as a column? *Yes; rules with
   confidence < 0.7 are downgraded to "advisory".*
3. How to handle **per-user Copilot for M365** vs **GitHub Copilot** vs
   **Copilot Studio** in the same report without confusing the reader?
   *Group under a single "Copilot" report section with sub-tables.*

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
