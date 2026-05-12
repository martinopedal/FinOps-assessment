# FOCUS correlation mapping (exploratory)

> **Status:** `exploratory` , documentation only. This file is the first
> implementation slice of the *FinOps Toolkit / FOCUS / Hubs alignment* epic
> from [`docs/roadmap/README.md`](README.md). It does **not** ship a new
> schema, a new reporter, a FOCUS-formatted output, or a Hubs connector. No
> code, rule, collector, model, CSV column, or workflow changes are made by
> introducing this document.
>
> **FOCUS target version:** 1.2. If later research updates the target, this
> document and the roadmap index move together in the same PR.

>  **Non-contract notice.** This document is exploratory and advisory.
> Nothing here commits the project to ship a FOCUS exporter, a Hubs
> connector, or any specific CLI surface, and nothing here freezes the
> current `Finding` or `run` field set. If a future PR renames or removes
> a field cited below, this document moves with it in the same PR. The
> FOCUS specification and FinOps Toolkit / Hubs documentation remain with
> their owners , see *Sources* below for the authoritative references.

## Why this exists

`finops-assess` emits **advisory savings findings**, not billing rows. A
practitioner who already runs FinOps Foundation **FOCUS**-aligned tooling
(for example via the Microsoft **FinOps Toolkit** or **FinOps Hubs**) needs
to correlate a finding back to the cost data that motivated it without us
duplicating, replacing, or reshaping their cost dataset.

This mapping is the **operator-side correlation guide**. It says:

- which FOCUS 1.2 columns a reader can use to filter their own cost dataset
  for the principal, SKU, surface, or charge a finding refers to;
- which FOCUS columns we **cannot** populate today, and why;
- which guardrails apply if and when a future PR adds an actual export.

The mapping is **best-effort and approximate**. Findings are recommendations,
not invoice lines, so several FOCUS columns simply do not have a
corresponding field in `Finding` or `run` today.

## Scope and read-only guardrails

- The CLI does not produce FOCUS-formatted CSV or Parquet today, and this
  document does not change that. Any future FOCUS export must land in its own
  reviewed PR with schema, tests, and docs.
- The CLI does not upload to FinOps Hubs. Hubs interoperability remains the
  file-based, operator-controlled boundary documented in the roadmap.
- The mapping references only public spec column **names**. The full FOCUS
  column tables, their definitions, and any vendor pricing tables remain
  with their owners; readers should consult the linked sources for the
  authoritative definitions.
- PII redaction continues to apply to the source `Finding`. Any future export
  must inherit, not relax, that redaction posture.

## Source field reference (current runtime contracts)

These are the fields that exist **today** in the canonical JSON report and
that this mapping draws from. They are the source of truth , if they drift,
this document drifts with them in the same PR.

`run` envelope (see [`docs/schema.md`](../schema.md) §Report envelope):

| Field | Type | Notes |
|---|---|---|
| `run.tool` | string | Always `"finops-assess"`. |
| `run.version` | string | Tool semver. |
| `run.schema_version` | string | Report schema version (currently `"1.0"`). |
| `run.generated_at` | ISO-8601 timestamp | Honours `SOURCE_DATE_EPOCH`. |
| `run.input` | string | Input path (redacted to leaf when PII redaction is on). |
| `run.pii_redaction` | bool | Whether principal hashing is active. |
| `run.mode` | string | Always `"read-only"`. |

`Finding` row (see [`docs/schema.md`](../schema.md) §`Finding`):

| Field | Type | Notes |
|---|---|---|
| `rule_id` | string | e.g. `M365.UNUSED_LICENSE_30D`. |
| `surface` | enum | `m365` \| `azure` \| `github` \| `ado`. |
| `severity` | enum | `info` \| `low` \| `medium` \| `high`. |
| `principal` | string | UPN / object id / seat id / repo path; salted-hash when redaction is on. |
| `current_sku` | string \| null | Catalogue SKU id (e.g. `SPE_E3`). |
| `recommended_sku` | string \| null | Catalogue SKU id, when the rule recommends a step-down. |
| `estimated_monthly_savings_usd` | float \| null | Conservative estimate; null when list price is unknown. |
| `recommendation` | string | Human-readable advice (always phrased as *consider* / *verify and then*). |
| `evidence_ref` | string \| null | Pointer into the evidence bundle. |
| `confidence` | enum | `high` \| `medium` \| `low`. |
| `evidence` | object | Rule-specific signals (activity counters, persona, etc.). |

## FOCUS 1.2 correlation table

For each FOCUS column the *Source field* column shows the closest field that
exists in a finding **today**. *Mapping* describes how a reader would join
the two datasets in a downstream tool. Columns marked `not-populated` have no
direct counterpart in `Finding` and would need a future schema slice before
an export could fill them.

### Identifiers and time

| FOCUS column | Source field | Mapping |
|---|---|---|
| `BillingAccountId` | not-populated | Findings are tenant-/enterprise-scoped, not billing-account-scoped. A future Azure/M365 collector slice could carry it through `evidence`. |
| `BillingAccountName` | not-populated | As above. |
| `SubAccountId` | not-populated | Azure subscription / GitHub enterprise / ADO organisation id is sometimes embedded in `principal` for non-user surfaces but is not a typed field. |
| `SubAccountName` | not-populated | As above. |
| `BillingPeriodStart` / `BillingPeriodEnd` | not-populated | Findings are point-in-time observations, not invoiced period totals. |
| `ChargePeriodStart` / `ChargePeriodEnd` | `run.generated_at` (approximate) | Use the run timestamp as the *as-of* moment when correlating to a billing month; do not treat it as a charge period boundary. |

### Service taxonomy

| FOCUS column | Source field | Mapping |
|---|---|---|
| `ProviderName` | derived from `surface` | Map `m365`/`azure` → *Microsoft*, `github` → *GitHub*, `ado` → *Microsoft* (Azure DevOps). |
| `PublisherName` | derived from `surface` | Same as `ProviderName` for first-party SKUs covered by the catalogue today. |
| `InvoiceIssuerName` | not-populated | Depends on the customer agreement (EA, MCA, CSP, MOSP); not modelled. |
| `ServiceCategory` | derived from `surface` | Coarse mapping: `m365` → *Productivity & Collaboration*; `azure` → *Compute / Storage / Networking / etc.* (depends on the rule); `github`/`ado` → *Developer Tools*. The exact FOCUS taxonomy value is the reader's responsibility. |
| `ServiceSubcategory` | derived from `rule_id` surface prefix | Approximate , for example `AZ.IDLE_VM_14D` correlates to *Compute*, `AZ.UNATTACHED_DISK` to *Storage*, `M365.COPILOT_INACTIVE_60D` to *Productivity / AI assistance*. |
| `ServiceName` | derived from `current_sku` (via catalogue) | Look up `current_sku` in `data/catalog/<surface>/*.yaml` to recover the human-readable service name. |

### Charge identity

| FOCUS column | Source field | Mapping |
|---|---|---|
| `ChargeCategory` | constant | Always *Usage* in spirit , findings describe ongoing per-period charges, not one-off purchases or adjustments. |
| `ChargeClass` | constant | Findings are **not** corrections; treat as a regular charge for filtering purposes. |
| `ChargeFrequency` | constant | The rules engine assumes monthly billing for `estimated_monthly_savings_usd`. Reservation/Savings Plan-related findings may bridge multiple frequencies in a future slice. |
| `ChargeDescription` | `recommendation` (advisory) | The recommendation text is operator-readable, not invoice-readable; use it as commentary, not as a join key. |
| `SkuId` | `current_sku`, `recommended_sku` | Both fields hold catalogue SKU ids. For Microsoft surfaces the catalogue id matches the public service-plan / SKU id (e.g. `SPE_E3`); for GitHub/ADO it matches the seat-tier id used by the relevant API. |
| `SkuPriceId` | not-populated | Pricing-profile granularity (region/term/agreement) is not modelled today; see *Agreement types and discounts* in the roadmap. |

### Resource and location

| FOCUS column | Source field | Mapping |
|---|---|---|
| `ResourceId` | `principal` (Azure surface only) | Azure rules embed the ARM resource id in `principal`. For M365/GitHub/ADO `principal` is a user / seat / repo id, not a resource id. |
| `ResourceName` | `evidence` (rule-specific) | When present it is a per-rule key inside `evidence`; not a stable typed field. |
| `ResourceType` | derived from `rule_id` | E.g. `AZ.IDLE_VM_14D` → *VM*, `AZ.UNATTACHED_DISK` → *Disk*, `AZ.PUBLIC_IP_UNATTACHED` → *PublicIp*. |
| `RegionId` / `RegionName` | not-populated | Region-aware findings are tracked under *Azure region price comparisons* in the roadmap and will arrive with their own observation contract. |
| `AvailabilityZone` | not-populated | Out of scope for the current rule set. |

### Cost amounts and currency

| FOCUS column | Source field | Mapping |
|---|---|---|
| `ListCost` | `estimated_monthly_savings_usd` (advisory) | Findings expose the **avoidable** monthly amount, not the gross or list charge for the period. Do not treat the savings figure as a FOCUS cost amount; use it to prioritise findings and to look up the matching charge in the reader's own dataset. |
| `ContractedCost` | not-populated | Tenant-specific agreement pricing is not modelled. |
| `BilledCost` | not-populated | The tool does not consume invoiced cost lines today. |
| `EffectiveCost` | not-populated | As above; FinOps Hubs / FOCUS exports remain the source of truth. |
| `PricingCurrency` | constant `USD` | All catalogue list prices are USD. Findings inherit USD via `estimated_monthly_savings_usd`. |
| `BillingCurrency` | not-populated | Driven by the reader's billing account, not the tool. |

### Commitment discounts

| FOCUS column | Source field | Mapping |
|---|---|---|
| `CommitmentDiscountId` | not-populated | The current `AZ.RESERVATION_UNDERUTILIZED` rule reads coverage signals from the normalised dataset but does not yet emit the reservation id as a typed field; tracked under *RI and Savings Plans* in the roadmap. |
| `CommitmentDiscountType` | not-populated | As above. |
| `CommitmentDiscountStatus` | not-populated | As above. |
| `CommitmentDiscountCategory` | not-populated | As above. |

### Tags

| FOCUS column | Source field | Mapping |
|---|---|---|
| `Tags` | `evidence` (rule-specific) | Some Azure rules carry through tags they used in their reasoning (for example the `env=` tag for `AZ.DEV_TEST_SUB_PRODUCTION_PRICING`). They are not a stable typed field across rules. |

## Operator workflow (today, without an exporter)

1. Run `finops-assess run` to produce the canonical JSON report.
2. For each finding the operator wants to correlate, build a filter against
   their existing FOCUS-aligned dataset using the columns above:
   - join key for Microsoft SKU work: `ServiceName` ← catalogue lookup of
     `current_sku`;
   - join key for an Azure resource finding: `ResourceId` ← `principal`;
   - join key for a per-tenant view: `BillingAccountId` /
     `SubAccountId` come from the operator's dataset, not the tool.
3. Use `estimated_monthly_savings_usd` only as a *priority* signal. The
   authoritative cost figure for a recommendation is the matching charge in
   the operator's FOCUS dataset, not the tool's estimate.

## What this document does NOT change

- No new pydantic model, CSV column, rule, collector, reporter, catalogue
  entry, persona, example artefact, or CI workflow.
- No FOCUS-formatted export is produced or claimed.
- No FinOps Hubs upload, deployment, or write path is introduced.
- No third-party diagram or pricing table is copied. The FOCUS specification,
  Microsoft service taxonomy, and FinOps Toolkit / Hubs documentation remain
  with their owners.

## Sources (authoritative, public)

- FinOps Foundation , FOCUS specification index:
  <https://focus.finops.org/>
- FinOps Foundation , FOCUS GitHub organisation (spec source):
  <https://github.com/FinOps-Open-Cost-and-Usage-Spec>
- Microsoft FinOps Toolkit (overview):
  <https://learn.microsoft.com/cloud-computing/finops/toolkit/finops-toolkit-overview>
- Microsoft FinOps Hubs (overview):
  <https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/finops-hubs-overview>
- Microsoft Azure Retail Prices REST API:
  <https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices>

## Reserved follow-ups

A future, separately-reviewed PR may add any of the following. None of them
are introduced here; each requires its own §11 delivery loop:

- A `finops-assess export --format focus` subcommand that materialises the
  fields above as a FOCUS-shaped CSV / Parquet file, with explicit
  `not-populated` columns for the gaps documented in this table.
- A reservation-aware `evidence` shape that carries `CommitmentDiscountId`
  and friends through to consumers.
- A region-aware observation contract feeding `RegionId` / `RegionName`.
- A pricing profile input feeding `SkuPriceId`, `ContractedCost`, and
  `BillingCurrency`.
