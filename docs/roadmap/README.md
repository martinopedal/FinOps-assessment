# Frontier roadmap

This roadmap is an exploratory index for the next FinOps-assessment frontiers. It
implements the first, documentation-only step of the broader plan: name the work,
record guardrails, and split future implementation into small reviewed PRs. It does
not ship new schemas, rules, collectors, pricing data, or integrations.

## Read-only posture

All future work remains read-only by construction. `finops-assess` must not upload
to FinOps Hubs, deploy Azure resources, call remediation APIs, request write
scopes, embed long-lived secrets, or expose unredacted PII by default. Live
collectors continue to be thin adapters that produce local normalized data for the
existing rule engine.

## Status legend

| Status | Meaning |
|---|---|
| `exploratory` | Documented candidate; not committed as shipped scope. |
| `planned-pr` | Thin vertical slice needs its own issue/PR and §11 loop. |
| `blocked` | Requires human/security consensus before implementation. |

## Frontier epics

| Epic | Status | First implementation slice | Guardrails |
|---|---|---|---|
| FinOps Toolkit / FOCUS / Hubs alignment | exploratory | Document a file-based mapping from current findings to FOCUS-style correlation fields ([`focus-mapping.md`](focus-mapping.md)). | Target FOCUS 1.2 unless later research updates it; Hubs is consume/export-file only, never deploy/upload. |
| Azure region price comparisons | exploratory | Add a future normalized region-price observation contract before rules. | Use Azure Retail Prices API or customer-supplied exports; do not copy pricing tables. |
| Agreement types and discounts | exploratory | Add a future pricing profile input that can express list, EA, MCA, CSP, MOSP, and negotiated multipliers. | Default to public list price; tenant-specific discounts must be customer-supplied and never hard-coded. |
| RI and Savings Plans | exploratory | Expand commitment data around coverage, utilization, scope, renewal, and eligible on-demand spend. | Findings must say “consider” or “verify and then”; no commitment purchase/exchange automation. |
| SKU-mix reviews: M365, Entra, Copilot, security, GSA | exploratory | Add SKU-family summaries before adding rules. | Link and credit public sources only; sovereign/GSA coverage needs security/compliance review before collectors. |
| Data collection frontier | exploratory | Add CSV contracts before any live collector extensions. | Read-only scopes only; OIDC/federated auth preferred; no tenant IDs or secrets in repo. |
| FinOps practice-review outputs | exploratory | Add a future report section for pricing assumptions, data-quality warnings, commitment posture, and SKU-mix posture. | Canonical JSON remains source of truth; practice review is advisory, not a maturity certification. |
| GitHub Copilot and Azure MCP assistance | exploratory | Keep assist as optional operator-side helper discovery, never a required runtime dependency. | Default off; redacted payloads only unless operator explicitly opts in; no write-capable tool paths. |
| Local assessment skills/runbooks | exploratory | Maintain a skills index with draft prompt/runbook inventory. | Runbooks are documentation, not executable automation; unshipped commands are labelled `(planned)`. |

## Reserved rule IDs, not yet implemented

These names are intentionally reserved only in this roadmap. Do not add them to
`data/rules/` until their schema, inputs, implementation, tests, and docs land in a
separate PR.

- `AZ.REGION_PRICE_VARIANCE`
- `AZ.SKU_REGION_RIGHTSIZE`
- `AZ.METER_PRICE_ANOMALY`
- `AZ.COMMITMENT_UNDER_COVERED`
- `AZ.COMMITMENT_OVER_COMMITTED`
- `AZ.RESERVATION_SCOPE_MISMATCH`
- `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`
- `AZ.COMMITMENT_RENEWAL_REVIEW`
- `M365.SKU_MIX_FRAGMENTED`
- `M365.ENTRA_P2_UNUSED`
- `M365.SECURITY_ADDON_OVERLAP`
- `M365.COPILOT_SKU_MIX_REVIEW`
- `M365.GSA_UNUSED_OR_OVERLAP`

## Sourcing and copyright guardrails

- Cite Microsoft Learn, Azure Retail Prices API, FinOps Foundation / FOCUS docs,
  FinOps Toolkit docs, and M365 Maps where relevant.
- Do not copy third-party diagrams, proprietary pricing tables, or customer rate
  cards into the repo.
- Treat regional prices and agreement discounts as volatile observations, not
  catalogue constants, unless a future reviewed data contract says otherwise.

## What this PR does NOT change

- No pydantic models, CSV schemas, rules, collectors, reporters, catalog entries,
  personas, examples, or CI workflows are changed.
- No FinOps Toolkit, FinOps Hubs, FOCUS, Copilot, or MCP compatibility claim is
  shipped.
- No local skill file is executable or allowed to mutate a tenant.
