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
>
> **Azure-only in v0.5.0.** Microsoft 365, GitHub, and Azure
> DevOps findings are filtered out and counted in
> `surfaces_skipped`. M365 ships in v0.6.0 once the
> stable-principal-salt feature lands — see the
> [v0.6.0 tracking issue](#v060-roadmap).

## What this export is for

The FOCUS-aligned advisory CSV is designed for **joining advisory
rows to your existing FOCUS Cost-and-Usage warehouse on `ResourceId`**.

Use it when you want to:

- Correlate `finops-assess` right-sizing findings with your actual
  billing data in FinOps Hubs, Cloudability, or a custom warehouse.
- Surface optimization recommendations in the same tooling that
  already consumes your cost data.
- Track which resources have outstanding advisory findings over time.

The join key is `ResourceId` (an ARM resource ID in the Azure scope),
which maps directly to the `ResourceId` column in FOCUS Cost-and-Usage
datasets.

## What this export is NOT for

- **Billing reconciliation.** The cost columns (`BilledCost`,
  `ContractedCost`, `EffectiveCost`, `ListCost`) are empty. This is
  not your invoice.
- **Audit.** Advisory findings are estimates with confidence levels,
  not audit-grade billing records.
- **Replacing your CUR/MCA dataset.** Load this alongside your
  cost data, not instead of it.

## Column reference

| Column | Type | Source | FOCUS mandatory? |
|--------|------|--------|:---:|
| `ServiceProviderName` | string | constant `"Microsoft"` | ✅ |
| `HostProviderName` | string | constant `"Microsoft"` | ✅ |
| `ServiceName` | string | constant `"Azure"` | ✅ |
| `ServiceCategory` | string | constant `"Compute"` | ✅ |
| `ServiceSubcategory` | string | empty | no |
| `ChargeCategory` | string | constant `"Advisory"` | ✅ |
| `ChargeClass` | string | constant `"Optimization"` | ✅ |
| `ChargeFrequency` | string | constant `"Monthly"` | ✅ |
| `ChargeDescription` | string | `finding.recommendation` | ✅ |
| `SkuId` | string | `finding.current_sku` | no |
| `ResourceId` | string | `finding.principal` (ARM resource ID) | ✅ |
| `ResourceType` | string | empty | no |
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
version is active. Under `v0.5.0`:

```
evidence_key_fields: ["rule_id", "resource_id", "normalized_evidence"]
evidence_key_algorithm: "sha256(rule_id \x00 resource_id \x00 normalized_evidence_json)"
```

When `evidence_key_version` is mixed in (v0.6.0+), the algorithm string
will change to:
```
sha256(rule_id \x00 resource_id \x00 version \x00 normalized_evidence_json)
```

and `manifest_schema_version` will bump to `"0.2"`. Consumers that join
on `AdvisoryFindingKey` should re-key their warehouse rows when they see
a new `manifest_schema_version`.

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

## Why ResourceId is cleartext (not hashed)

Azure ARM resource IDs are the FOCUS `ResourceId` join key. Hashing them
would defeat the primary purpose of the export — joining advisory findings
to cost-warehouse rows by resource ID. The manifest records
`pii_handling: {"mode": "azure_resource_id_cleartext"}` to signal this
posture explicitly.

Resource names embedded in ARM IDs (e.g.
`/.../virtualMachines/vm-john-test01`) may contain user-chosen strings that
reveal environment hints or user names. Operators with strong PII
requirements should apply their own redaction to the CSV before loading
into a shared warehouse.

M365 findings (not shipped in v0.5.0) will use a stable-salt
principal hash — see the v0.6.0 D7 tracking issue below.

## v0.6.0 roadmap

M365, GitHub, and Azure DevOps surfaces are deferred pending the D7
unblock criteria:

1. Persisted operator-managed salt (`--principal-salt-file` or
   `FINOPS_PRINCIPAL_SALT` env var) to make `PrincipalHash` stable
   across runs.
2. Cross-run stability test.
3. Extended `pii_handling` manifest field (`salt_source`,
   `principal_hash_algorithm`).
4. Conflict-class documentation per M365 rule pair.
5. Schema test that rejects empty `PrincipalHash` when redaction is on.

All five must pass before M365 ships in the export. See the v0.6.0
tracking issue for the full contract.
