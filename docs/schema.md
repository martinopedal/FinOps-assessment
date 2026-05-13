# Data schema reference

> Reflects `src/finops_assess/models.py`, `src/finops_assess/engine.py`,
> and the reporter implementations under `src/finops_assess/reporters/`.
> Keep this document in sync when those runtime contracts change.

This document describes every pydantic model in the `finops_assess`
package, the CSV columns the collector expects for each model, and the
JSON shape emitted in a findings report.

---

## Primitive types

| Alias | Type |
|-------|------|
| `Cloud` | `"m365" \| "azure" \| "github" \| "ado"` |
| `Severity` | `"info" \| "low" \| "medium" \| "high"` |
| `Confidence` | `"high" \| "medium" \| "low"` |

---

## Catalogue model: `CatalogEntry`

Stored in `data/catalog/{surface}/*.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Microsoft service-plan / SKU ID (e.g. `SPE_E3`) |
| `display_name` | `str` | ✅ | Human-readable name |
| `family` | `str` | ✅ | SKU family group (e.g. `m365_enterprise`) |
| `cloud` | `Cloud` | ✅ | Surface: `m365`, `azure`, `github`, or `ado` |
| `list_price_usd_month` | `float \| null` | n/a | Monthly list price in USD; omit or `null` if unknown |
| `source_url` | `str \| null` | n/a | Public citation URL (never the raw diagram) |
| `includes` | `list[str]` | n/a | Child SKU IDs (bundle composition) |
| `features` | `list[str]` | n/a | Capability tags from the controlled vocabulary |
| `successor_of` | `list[str]` | n/a | Predecessor SKU IDs (upgrade path hints) |
| `notes` | `str \| null` | n/a | Free-text annotation |

---

## Persona model: `Persona`

Stored in `data/personas.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Unique persona slug (e.g. `information_worker`) |
| `display_name` | `str` | ✅ | Human-readable label |
| `description` | `str \| null` | n/a | Brief explanation |
| `required_features` | `list[str]` | n/a | Minimum feature tags this persona must have covered |
| `title_patterns` | `list[str]` | n/a | Job-title regex patterns that map to this persona |
| `group_patterns` | `list[str]` | n/a | Group-name regex patterns that map to this persona |

---

## Rule model: `Rule`

Stored in `data/rules/{surface}.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Rule ID, `SURFACE.SHORT_NAME` screaming-snake-case |
| `surface` | `Cloud` | ✅ | Which surface this rule targets |
| `severity` | `Severity` | n/a | Default `"medium"` |
| `summary` | `str` | ✅ | One-line rule description |
| `recommendation_template` | `str` | ✅ | Jinja-style template with `{principal}` etc. |
| `inactivity_days` | `int \| null` | n/a | Inactivity window the rule uses |
| `enabled` | `bool` | n/a | Default `true`; set `false` to disable without deleting |
| `evidence_key_version` | `int` | n/a | Default `1`. Version of the AdvisoryFindingKey hash algorithm for this rule. Bump to `2+` when the rule's evidence shape changes (forces re-keying in downstream warehouses). See `docs/focus-export.md` §"AdvisoryFindingKey: stability contract". |

---

## Finding model: `Finding`

Emitted by the rule engine into the JSON report and all derived
formats (HTML, CSV, PDF).

| Field | Type | Notes |
|-------|------|-------|
| `rule_id` | `str` | Rule that fired (e.g. `M365.UNUSED_LICENSE_30D`) |
| `surface` | `Cloud` | Surface the finding belongs to |
| `severity` | `Severity` | Severity of the finding |
| `principal` | `str` | Affected principal (salted-hash when `--pii-redaction` is on) |
| `current_sku` | `str \| null` | The SKU / seat the principal currently holds |
| `recommended_sku` | `str \| null` | Suggested cheaper or more appropriate SKU |
| `estimated_monthly_savings_usd` | `float \| null` | Estimated monthly saving if actioned |
| `recommendation` | `str` | Human-readable recommendation text |
| `evidence_ref` | `str \| null` | Reserved for a future evidence-bundle reference |
| `confidence` | `Confidence` | Confidence of the finding (`"high"`, `"medium"`, or `"low"`) |
| `evidence` | `dict` | Rule-specific diagnostic detail (raw signals) |

---

## Persona resolution model: `PersonaAssignment`

Computed at runtime by `src/finops_assess/persona.py`; not loaded from a
CSV file.

| Field | Type | Notes |
|-------|------|-------|
| `principal` | `str` | Principal identifier that was assigned a persona |
| `persona_id` | `str` | Chosen `Persona.id` |
| `matched_by` | `"override" \| "title" \| "group" \| "fallback"` | Which signal won during persona assignment |
| `confidence` | `Confidence` | Confidence in the assignment |

The assignment map itself is internal, but its aggregated counts are
emitted in the JSON report as `summary.persona_distribution`.

---

## Normalised input models

These models describe the CSV files the collector layer writes (and the
rule engine reads). Every live collector (`graph`, `arm`, `github`,
`ado`) produces the same shapes; the rule engine is source-agnostic.

### `UserRecord`: `samples/users.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | UPN or unique identifier |
| `display_name` | `str \| null` | Display name |
| `user_type` | `"member" \| "guest" \| "shared_mailbox" \| "service"` | Default `"member"` |
| `account_enabled` | `bool` | Default `true` |
| `job_title` | `str \| null` | Used for persona title-pattern matching |
| `department` | `str \| null` | Informational |
| `groups` | `list[str]` | Pipe-delimited in CSV (e.g. `GroupA\|GroupB`) |
| `mailbox_size_gb` | `float \| null` | Current mailbox quota consumed |
| `last_sign_in_days` | `int \| null` | Days since last interactive sign-in |

### `LicenseAssignment`: `samples/license_assignments.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | Must match a `UserRecord.principal` |
| `sku_id` | `str` | Must be a known `CatalogEntry.id` |
| `assigned_date` | `str \| null` | ISO-8601 date string |

### `UsageSignal`: `samples/usage.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | Target principal |
| `signal` | `str` | Capability key (e.g. `copilot`, `teams`, `exchange`) |
| `last_activity_days` | `int \| null` | Days since last observed activity; `null` = never |

### `AzureResource`: `samples/azure_resources.csv`

| Column | Type | Notes |
|--------|------|-------|
| `resource_id` | `str` | ARM resource ID or unique key |
| `resource_type` | `"virtualMachine" \| "managedDisk" \| "publicIp"` | |
| `sku` | `str \| null` | VM size, disk SKU, etc. |
| `location` | `str \| null` | Azure region |
| `avg_cpu_pct` | `float \| null` | Average CPU utilisation (0 to 100) |
| `p95_cpu_pct` | `float \| null` | P95 CPU utilisation (0 to 100) |
| `p95_mem_pct` | `float \| null` | P95 memory utilisation (0 to 100) |
| `avg_net_kbps` | `float \| null` | Average network throughput |
| `days_inactive` | `int \| null` | Days without meaningful activity |
| `attached` | `bool \| null` | `false` = unattached disk |
| `associated` | `bool \| null` | `false` = unassociated public IP |
| `monthly_cost_usd` | `float \| null` | Estimated monthly cost |
| `recommended_sku` | `str \| null` | Suggested right-size target |
| `subscription_id` | `str \| null` | Azure subscription ID |
| `subscription_offer` | `str \| null` | `"DevTest"` etc. |
| `env_tag` | `str \| null` | Value of the `env` resource tag |

### `AzureReservation`: `samples/azure_reservations.csv`

| Column | Type | Notes |
|--------|------|-------|
| `reservation_id` | `str` | RI or Savings Plan ID |
| `reservation_name` | `str \| null` | Friendly name |
| `sku` | `str \| null` | Reserved SKU |
| `scope` | `str \| null` | Scope (shared, single subscription, etc.) |
| `utilization_pct` | `float \| null` | 30-day average utilisation (0 to 100) |
| `monthly_cost_usd` | `float \| null` | Monthly commitment cost |

### `AzureLogWorkspace`: `samples/azure_log_workspaces.csv`

| Column | Type | Notes |
|--------|------|-------|
| `workspace_id` | `str` | Log Analytics workspace ID |
| `workspace_name` | `str \| null` | Friendly name |
| `daily_gb` | `float \| null` | Average daily ingest volume (GB) |
| `commitment_tier_gb` | `float \| null` | Current commitment tier threshold |
| `recommended_tier` | `str \| null` | Optimal commitment tier; `null` if already optimal |
| `est_savings_pct` | `float \| null` | Estimated savings if moved to the recommended tier |
| `monthly_cost_usd` | `float \| null` | Current monthly workspace cost |

### `GitHubSeat`: `samples/github_seats.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | GitHub handle or unique identifier |
| `org` | `str \| null` | GitHub organisation slug |
| `seat_type` | `"enterprise" \| "team" \| "copilot_business" \| "copilot_enterprise" \| "ghas_committer"` | |
| `sku_id` | `str \| null` | Catalogue SKU reference |
| `last_activity_days` | `int \| null` | Days since last contribution / sign-in |
| `copilot_acceptances_30d` | `int \| null` | Accepted suggestions in last 30 days (Copilot seats only) |

### `GitHubOrg`: `samples/github_orgs.csv`

| Column | Type | Notes |
|--------|------|-------|
| `org` | `str` | GitHub organisation slug |
| `ghas_repo_count` | `int \| null` | Repos with GHAS enabled |
| `actively_scanned_repos` | `int \| null` | Repos that produced a scan alert |
| `active_committers` | `int \| null` | Unique committers in trailing 90 days |
| `runner_tier` | `str \| null` | Current runner plan / tier |
| `runner_minutes_used` | `int \| null` | Runner minutes consumed in the billing period |
| `runner_minutes_included` | `int \| null` | Runner minutes included in the current plan |

### `AdoSeat`: `samples/ado_seats.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | ADO user principal |
| `org` | `str \| null` | ADO organisation URL or slug |
| `seat_type` | `"stakeholder" \| "basic" \| "basic_plus_test"` | |
| `sku_id` | `str \| null` | Catalogue SKU reference |
| `last_activity_days` | `int \| null` | Days since last work-item, code, or pipeline activity |
| `only_stakeholder_activity` | `bool \| null` | `true` = only board reads / comments observed |
| `last_test_plan_days` | `int \| null` | Days since last Test Plans activity (`basic_plus_test` only) |

### `AdoOrgUsage`: `samples/ado_orgs.csv`

| Column | Type | Notes |
|--------|------|-------|
| `org` | `str` | ADO organisation URL or slug |
| `purchased_parallel_jobs` | `int \| null` | Number of purchased Microsoft-hosted parallel jobs |
| `p95_concurrent_jobs` | `int \| null` | P95 concurrent job count in the billing period |

---

## `NormalizedDataset`: rule-engine input

Aggregates all of the above records into a single object passed to the
rule engine.

| Field | Type | Source CSV |
|-------|------|------------|
| `users` | `list[UserRecord]` | `users.csv` |
| `assignments` | `list[LicenseAssignment]` | `license_assignments.csv` |
| `usage` | `list[UsageSignal]` | `usage.csv` |
| `azure_resources` | `list[AzureResource]` | `azure_resources.csv` |
| `azure_reservations` | `list[AzureReservation]` | `azure_reservations.csv` |
| `azure_log_workspaces` | `list[AzureLogWorkspace]` | `azure_log_workspaces.csv` |
| `github_seats` | `list[GitHubSeat]` | `github_seats.csv` |
| `github_orgs` | `list[GitHubOrg]` | `github_orgs.csv` |
| `ado_seats` | `list[AdoSeat]` | `ado_seats.csv` |
| `ado_orgs` | `list[AdoOrgUsage]` | `ado_orgs.csv` |
| `overrides` | `dict[str, str]` | `overrides.yaml` |

---

## JSON report output

The `finops-assess run` and `finops-assess demo` commands write a
JSON file with this top-level structure:

```json
{
  "run": {
    "tool": "finops-assess",
    "version": "0.1.0",
    "schema_version": "1.0",
    "generated_at": "2026-05-05T10:00:00+00:00",
    "input": "<redacted>/samples",
    "pii_redaction": true,
    "mode": "read-only"
  },
  "summary": {
    "rule_counts": {
      "M365.UNUSED_LICENSE_30D": 3,
      "AZ.UNATTACHED_DISK": 1
    },
    "rules_skipped_no_impl": [],
    "total_findings": 34,
    "principals_evaluated": 8,
    "assignments_evaluated": 10,
    "azure_resources_evaluated": 4,
    "persona_distribution": {
      "information_worker": 5,
      "service_account": 1
    }
  },
  "findings": [ /* list of Finding objects */ ]
}
```

### `run`

| Field | Type | Notes |
|-------|------|-------|
| `tool` | `str` | Always `finops-assess` |
| `version` | `str` | Package version |
| `schema_version` | `str` | Report envelope schema version; currently `1.0` |
| `generated_at` | `str` | ISO-8601 timestamp |
| `input` | `str` | Input path; when PII redaction is enabled, only the leaf directory name is preserved |
| `pii_redaction` | `bool` | Whether finding principals were redacted |
| `mode` | `str` | Always `read-only` |

### `summary`

| Field | Type | Notes |
|-------|------|-------|
| `rule_counts` | `dict[str, int]` | Per-rule finding counts |
| `rules_skipped_no_impl` | `list[str]` | Rule IDs present in YAML but missing an implementation |
| `total_findings` | `int` | Total findings emitted |
| `principals_evaluated` | `int` | Number of principals in `users.csv` |
| `assignments_evaluated` | `int` | Number of license assignments evaluated |
| `azure_resources_evaluated` | `int` | Number of Azure resources evaluated |
| `persona_distribution` | `dict[str, int]` | Count of principals per resolved persona |
| `pii_redaction` | `"disabled"` | Present only when `--no-pii-redaction` is used |

Each element of `findings` matches the `Finding` schema above.

---

## CSV report output

`--format csv` (or `--format all`) writes a flat CSV where every
`Finding` field is a column. Multi-value fields (like `evidence`) are
JSON-serialised. Formula-injection characters (`=`, `+`, `-`, `@`) are
prefix-sanitised automatically.

Column order: `rule_id`, `surface`, `severity`, `confidence`,
`principal`, `current_sku`, `recommended_sku`,
`estimated_monthly_savings_usd`, `recommendation`, `evidence_ref`,
`evidence_json`.

`evidence_json` contains the `Finding.evidence` payload serialised as a
JSON string so the structured detail survives the flattening round-trip.

---

## Advisory triage artefact

`finops-assess triage --input report.json --output-dir triage/` reads an
existing read-only JSON report and emits `triage.json` and/or `triage.csv`.
The artefact is deterministic, schema-versioned, and advisory: it helps an
analyst prioritise verification work but never remediates or mutates systems.

The command preserves the source report's `run.pii_redaction` posture. If the
source report contains salted-hash principals, triage carries those hashes
verbatim; if an operator intentionally generated an unredacted report, triage
passes those principals through and clearly records `pii_redaction: false`.

### `TriageReport.run`

| Field | Type | Notes |
|-------|------|-------|
| `tool` | `str` | Always `finops-assess-triage` |
| `version` | `str \| null` | Source package version |
| `schema_version` | `str` | Triage schema version; currently `1.0` |
| `generated_at` | `str` | Copied from the source report for byte-stable output |
| `mode` | `"advisory"` | Triage mode; not a remediation mode |
| `pii_redaction` | `bool` | Copied from the source report |
| `advisory` | `true` | Machine-checkable advisory marker |
| `advisory_banner` | `str` | Human-readable warning to verify before action |
| `copilot_helper` | `"disabled" \| "sdk" \| "cli" \| "unavailable"` | Optional GitHub Copilot helper discovery status |

### `TriageItem`

| Field | Type | Notes |
|-------|------|-------|
| `finding_ref` | `str` | Stable derived hash pointer back to the source finding |
| `source_finding_index` | `int` | Zero-based index into the source report's `findings` array |
| `rule_id` | `str` | Source finding rule ID |
| `surface` | `Cloud` | Source finding surface |
| `severity` | `Severity` | Intrinsic rule severity |
| `confidence` | `Confidence` | Source finding confidence |
| `principal` | `str` | Source finding principal, unchanged |
| `current_sku` / `recommended_sku` | `str \| null` | Source SKU fields |
| `estimated_monthly_savings_usd` | `float \| null` | Source savings estimate |
| `evidence_ref` | `str \| null` | Source evidence reference, when present |
| `priority_bucket` | `"p1" \| "p2" \| "p3" \| "p4"` | Advisory analyst queue priority |
| `priority_rationale` | `str` | Deterministic rationale using severity, confidence, and savings |
| `suggested_owner_role` | `identity-admin \| license-admin \| azure-owner \| github-org-admin \| ado-org-admin \| finops-analyst` | Closed-vocabulary role, never a person or directory lookup |
| `verification_checklist` | `list[str]` | Conservative checks before any human action |
| `followup_questions` | `list[str]` | Questions for the owning admin/team |
| `advisory` | `true` | Per-item invariant |

Severity and triage priority are intentionally separate: `severity` is the
rule's intrinsic risk/cost classification, while `priority_bucket` is an
advisory queue order for analyst workload. The current mapping is:

| Inputs | Bucket |
|--------|--------|
| `severity=high` and `confidence=high` | `p1` |
| `severity=high`, or `severity=medium` with savings ≥ `$100/mo` | `p2` |
| `severity=medium`, or `confidence=medium` | `p3` |
| Everything else | `p4` |

The triage CSV column order is stable: `finding_ref`,
`source_finding_index`, `rule_id`, `surface`, `severity`, `confidence`,
`principal`, `priority_bucket`, `priority_rationale`, `suggested_owner_role`,
`current_sku`, `recommended_sku`, `estimated_monthly_savings_usd`,
`evidence_ref`, `verification_checklist`, `followup_questions`, `advisory`.

---

## FOCUS-aligned advisory manifest (v0.5.0)

`finops-assess export focus-aligned --input report.json --output out.csv`
emits `out.csv` (the advisory rows) and a sidecar `out.csv.manifest.json`
describing the export contract. See [`docs/focus-export.md`](focus-export.md)
for usage, column semantics, and the AdvisoryFindingKey stability contract.

The manifest is validated against
`src/finops_assess/schemas/focus_aligned_manifest.schema.json` (Draft 2020-12).
The schema is **additive-only**: readers must tolerate unknown top-level fields.

### Manifest top-level fields

| Field | Type | Notes |
|-------|------|-------|
| `manifest_schema_version` | `"0.1"` | Incremented when a breaking change is introduced |
| `generated_at` | ISO-8601 UTC | Honours `SOURCE_DATE_EPOCH` |
| `tool.name` | `"finops-assess"` | Always |
| `tool.version` | `str` | Package version at generation time |
| `focus_version` | `"1.3"` | FOCUS spec this export aligns to |
| `conformance_level` | `"non-conformant"` | Always; this is advisory, not billed cost |
| `advisory` | `true` | Machine-checkable advisory flag |
| `advisory_banner` | `str` | Human-readable warning — display before loading |
| `row_count` | `int` | Number of data rows in the CSV |
| `surfaces_included` | `list[str]` | Surfaces with ≥1 finding in the CSV |
| `surfaces_skipped` | `{surface: int}` | Skipped surfaces and their finding counts (always present, may be all-zero) |
| `pii_redaction` | `bool` | Copied from the source report |
| `evidence_key_version` | `int` | Algorithm version for AdvisoryFindingKey hashes in this file |
| `column_order` | `list[str]` | Ordered column names for the CSV |
