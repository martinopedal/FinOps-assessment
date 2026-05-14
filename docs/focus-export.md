# FOCUS-aligned advisory CSV export

> ⚠️ **NOT a FOCUS 1.3 conformant Cost-and-Usage dataset.**
>
> This export is **advisory output**, not billed consumption.
> Every row describes a *corrective recommendation* derived from
> a `finops-assess` rule firing — not an invoice line, not a
> resource-usage record, not a cost forecast. The sidecar
> `manifest.json` declares `conformance_level: "non-conformant"`
> and lists every FOCUS column that is intentionally left empty
> or missing.
>
> **Cost columns are empty by design.** `BilledCost`,
> `ContractedCost`, `EffectiveCost`, and `ListCost` are emitted
> as empty strings on every row. Advisory savings are surfaced in
> the non-FOCUS `EstimatedMonthlySavingsUsd` column. **Do not**
> sum `EstimatedMonthlySavingsUsd` across rows expecting an
> invoice-equivalent total — the rule engine's conflict classes
> (e.g. competing right-sizing recommendations on the same
> resource) can double-count.

## What this export is for

The FOCUS-aligned advisory CSV is designed for **joining advisory
rows to your existing FOCUS Cost-and-Usage warehouse on `ResourceId`**.

Use it when you want to:

- Correlate `finops-assess` right-sizing findings with your actual
  billing data in FinOps Hubs, Cloudability, or a custom warehouse.
- Surface optimization recommendations in the same tooling that
  already consumes your cost data.
- Track which resources have outstanding advisory findings over time.

The join key is `ResourceId`. For Azure findings, this is the ARM resource
ID, which maps directly to the `ResourceId` column in FOCUS Cost-and-Usage
datasets. For M365, GitHub, and Azure DevOps findings, `ResourceId` is the
hashed principal (UPN/login), which is joinable to other `finops-assess`
runs on the same surface but not to Azure FOCUS billing data.

## What this export is NOT for

- **Billing reconciliation.** The cost columns (`BilledCost`,
  `ContractedCost`, `EffectiveCost`, `ListCost`) are empty. This is
  not your invoice.
- **Audit.** Advisory findings are estimates with confidence levels,
  not audit-grade billing records.
- **Replacing your CUR/MCA dataset.** Load this alongside your
  cost data, not instead of it.

## Column reference (all four surfaces)

Columns whose values differ per surface are marked with ✦.

| Column | Type | Source | FOCUS mandatory? |
|--------|------|--------|:---:|
| `ServiceProviderName` | string | constant `"Microsoft"` | ✅ |
| `HostProviderName` | string | constant `"Microsoft"` | ✅ |
| `ServiceName` ✦ | string | surface-dependent (see below) | ✅ |
| `ServiceCategory` ✦ | string | surface-dependent (see below) | ✅ |
| `ServiceSubcategory` | string | empty | no |
| `ChargeCategory` | string | constant `"Advisory"` | ✅ |
| `ChargeClass` | string | constant `"Optimization"` | ✅ |
| `ChargeFrequency` | string | constant `"Monthly"` | ✅ |
| `ChargeDescription` | string | `finding.recommendation` | ✅ |
| `SkuId` | string | `finding.current_sku` | no |
| `ResourceId` ✦ | string | `finding.principal` (see PII section) | ✅ |
| `ResourceType` ✦ | string | surface-dependent (see below) | no |
| `BillingPeriodStart` | datetime | first day of observation-window-end month | ✅ |
| `BillingPeriodEnd` | datetime | first day of next month | ✅ |
| `PricingCurrency` | string | constant `"USD"` | ✅ |
| `ListCost` | decimal | **empty by design** | ✅ (empty) |
| `ContractedCost` | decimal | **empty by design** | ✅ (empty) |
| `BilledCost` | decimal | **empty by design** | ✅ (empty) |
| `EffectiveCost` | decimal | **empty by design** | ✅ (empty) |
| `EstimatedMonthlySavingsUsd` | decimal | `finding.estimated_monthly_savings_usd` | non-FOCUS |
| `AdvisoryFindingKey` | string | SHA-256 hash of (rule_id, resource_id, evidence) | non-FOCUS |
| `RuleId` | string | `finding.rule_id` | non-FOCUS |
| `Severity` | string | `finding.severity` | non-FOCUS |

### Per-surface column values

| Surface | `ServiceName` | `ServiceCategory` | `ResourceType` |
|---------|---------------|-------------------|----------------|
| `azure` | `"Azure"` | `"Compute"` | `""` (empty) |
| `m365` | `"Microsoft 365"` | `"Collaboration"` | `"user_license"` |
| `github` | `"GitHub"` | `"Developer Tools"` | `"seat"` |
| `ado` | `"Azure DevOps"` | `"Developer Tools"` | `"seat"` |

### Intentionally unsupported FOCUS columns

The following FOCUS 1.3 columns are not emitted (see `unsupported_columns`
in the manifest):
`BilledCost`, `BillingAccountId`, `BillingAccountName`,
`CommitmentDiscountId`, `CommitmentDiscountName`, `CommitmentDiscountType`,
`ContractedCost`, `ContractedUnitPrice`, `EffectiveCost`, `ListCost`,
`ListUnitPrice`, `PricingQuantity`, `PricingUnit`, `Region`,
`SkuPriceId`, `UsageQuantity`, `UsageUnit`.

## Manifest sidecar

Every `export focus-aligned` invocation writes two files:

- `<output>.csv` — the advisory rows
- `<output>.csv.manifest.json` — the sidecar contract

The manifest documents: tool version, source report metadata, conformance
level, surfaces included, per-surface skip counts, row count, unsupported
columns, join-key stability contracts, PII handling mode, and the
AdvisoryFindingKey algorithm.

See `docs/schema.md` § "FOCUS-aligned advisory manifest" for the
field-by-field contract and JSON Schema reference.

## AdvisoryFindingKey: stability contract

`AdvisoryFindingKey` is a stable, reproducible identifier for the
combination of `(rule_id, resource_id, evidence)`:

```
sha256(rule_id \x00 resource_id \x00 normalized_evidence_json)
```

**Stability guarantee:** for the same `(rule_id, resource_id, evidence)`
tuple, the key is identical across runs, tools versions (within the same
`evidence_key_algorithm` version), and platforms.

**When to re-key:** if the evidence shape of a rule changes (e.g. a new
field is added or a field is renamed), the rule's `evidence_key_version`
is bumped. The manifest's `evidence_key_algorithm` string documents which
version is active. Under `v0.5.0` and `v0.6.0`:

```
evidence_key_fields: ["rule_id", "resource_id", "normalized_evidence"]
evidence_key_algorithm: "sha256(rule_id \x00 resource_id \x00 normalized_evidence_json)"
```

**Evidence canonicalisation:** the evidence dict is JSON-serialised with
sorted keys, compact separators, and `allow_nan=False`. `None` maps to
`""`. Floats use `repr()` for consistent precision. Dict keys are sorted
at every nesting level. List order is **preserved** — rule authors who
emit unordered lists (sets) must sort at evidence-construction time.

## Calendar-month bucketing — known limitation

`BillingPeriodStart` and `BillingPeriodEnd` are derived from the
`observation_window_end` field in the finding's evidence:

- `BillingPeriodStart` = first day of the month containing
  `observation_window_end` at `00:00:00 UTC`
- `BillingPeriodEnd` = first day of the *next* month at `00:00:00 UTC`

When a finding is relevant to multiple months (e.g. a VM that has been
idle for 60 days), it collapses to the observation-window-end month.
This is the correct FOCUS-warehouse-joinability trade-off: the alternative
(one row per month) would multiply row counts and confuse aggregations.
Do not expect the exported `BillingPeriod` to equal the calendar months
over which the waste occurred.

## ResourceId and PII: multi-surface considerations

### Azure

Azure ARM resource IDs are the FOCUS `ResourceId` join key. The manifest
records `pii_handling.mode: "azure_resource_id_cleartext"` (or the hashed
variant if `--pii-redaction` is active). Resource names embedded in ARM IDs
(e.g. `/.../virtualMachines/vm-john-test01`) may contain user-chosen strings
that reveal environment hints or user names.

### M365, GitHub, ADO

For SaaS surfaces, `ResourceId` is `finding.principal`, which is the user
identity (UPN for M365/ADO, login handle for GitHub). Under the default
`--pii-redaction` mode, this is the engine's salted hash.

- **With `--pii-redaction` (default):** `ResourceId` = salted hash. The
  manifest records mode `"principal_per_run_salted_hash"` (per-run salt,
  unstable across runs) or `"principal_tenant_stable_salted_hash"` (when
  the operator has configured a tenant-stable salt via `--pii-salt-file`
  or `FINOPS_PII_SALT`).
- **With `--no-pii-redaction`:** `ResourceId` = cleartext UPN/login. The
  manifest records mode `"principal_cleartext"`.

SaaS `ResourceId` values are **not joinable to Azure FOCUS billing data**.
They are joinable to other `finops-assess` runs on the same surface
(self-join for trend analysis).

### Currency limitation for M365

`PricingCurrency` is always `"USD"` because catalog prices are USD list
prices. M365 tenants billed in EUR, GBP, JPY, or other local currencies
will see USD estimates, not local-currency amounts. To convert to local
currency, apply your own exchange rate to `EstimatedMonthlySavingsUsd`.
