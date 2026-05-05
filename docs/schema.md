# Data schema reference

> Auto-generated from `src/finops_assess/models.py` (pydantic v2).
> Do not edit by hand — update the source models and regenerate.

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

## Catalogue model — `CatalogEntry`

Stored in `data/catalog/{surface}/*.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Microsoft service-plan / SKU ID (e.g. `SPE_E3`) |
| `display_name` | `str` | ✅ | Human-readable name |
| `family` | `str` | ✅ | SKU family group (e.g. `m365_enterprise`) |
| `cloud` | `Cloud` | ✅ | Surface: `m365`, `azure`, `github`, or `ado` |
| `list_price_usd_month` | `float \| null` | — | Monthly list price in USD; omit or `null` if unknown |
| `source_url` | `str \| null` | — | Public citation URL (never the raw diagram) |
| `includes` | `list[str]` | — | Child SKU IDs (bundle composition) |
| `features` | `list[str]` | — | Capability tags from the controlled vocabulary |
| `successor_of` | `list[str]` | — | Predecessor SKU IDs (upgrade path hints) |
| `notes` | `str \| null` | — | Free-text annotation |

---

## Persona model — `Persona`

Stored in `data/personas.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Unique persona slug (e.g. `information_worker`) |
| `display_name` | `str` | ✅ | Human-readable label |
| `description` | `str \| null` | — | Brief explanation |
| `required_features` | `list[str]` | — | Minimum feature tags this persona must have covered |
| `title_patterns` | `list[str]` | — | Job-title regex patterns that map to this persona |
| `group_patterns` | `list[str]` | — | Group-name regex patterns that map to this persona |

---

## Rule model — `Rule`

Stored in `data/rules/{surface}.yaml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | Rule ID — `SURFACE.SHORT_NAME` screaming-snake-case |
| `surface` | `Cloud` | ✅ | Which surface this rule targets |
| `severity` | `Severity` | — | Default `"medium"` |
| `summary` | `str` | ✅ | One-line rule description |
| `recommendation_template` | `str` | ✅ | Jinja-style template with `{principal}` etc. |
| `inactivity_days` | `int \| null` | — | Inactivity window the rule uses |
| `enabled` | `bool` | — | Default `true`; set `false` to disable without deleting |

---

## Finding model — `Finding`

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

## Normalised input models

These models describe the CSV files the collector layer writes (and the
rule engine reads). Every live collector (`graph`, `arm`, `github`,
`ado`) produces the same shapes; the rule engine is source-agnostic.

### `UserRecord` — `samples/users.csv`

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

### `LicenseAssignment` — `samples/license_assignments.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | Must match a `UserRecord.principal` |
| `sku_id` | `str` | Must be a known `CatalogEntry.id` |
| `assigned_date` | `str \| null` | ISO-8601 date string |

### `UsageSignal` — `samples/usage.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | Target principal |
| `signal` | `str` | Capability key (e.g. `copilot`, `teams`, `exchange`) |
| `last_activity_days` | `int \| null` | Days since last observed activity; `null` = never |

### `AzureResource` — `samples/azure_resources.csv`

| Column | Type | Notes |
|--------|------|-------|
| `resource_id` | `str` | ARM resource ID or unique key |
| `resource_type` | `"virtualMachine" \| "managedDisk" \| "publicIp"` | |
| `sku` | `str \| null` | VM size, disk SKU, etc. |
| `location` | `str \| null` | Azure region |
| `avg_cpu_pct` | `float \| null` | Average CPU utilisation (0–100) |
| `p95_cpu_pct` | `float \| null` | P95 CPU utilisation (0–100) |
| `p95_mem_pct` | `float \| null` | P95 memory utilisation (0–100) |
| `avg_net_kbps` | `float \| null` | Average network throughput |
| `days_inactive` | `int \| null` | Days without meaningful activity |
| `attached` | `bool \| null` | `false` = unattached disk |
| `associated` | `bool \| null` | `false` = unassociated public IP |
| `monthly_cost_usd` | `float \| null` | Estimated monthly cost |
| `recommended_sku` | `str \| null` | Suggested right-size target |
| `subscription_id` | `str \| null` | Azure subscription ID |
| `subscription_offer` | `str \| null` | `"DevTest"` etc. |
| `env_tag` | `str \| null` | Value of the `env` resource tag |

### `AzureReservation` — `samples/azure_reservations.csv`

| Column | Type | Notes |
|--------|------|-------|
| `reservation_id` | `str` | RI or Savings Plan ID |
| `reservation_name` | `str \| null` | Friendly name |
| `sku` | `str \| null` | Reserved SKU |
| `scope` | `str \| null` | Scope (shared, single subscription, etc.) |
| `utilization_pct` | `float \| null` | 30-day average utilisation (0–100) |
| `monthly_cost_usd` | `float \| null` | Monthly commitment cost |

### `AzureLogWorkspace` — `samples/azure_log_workspaces.csv`

| Column | Type | Notes |
|--------|------|-------|
| `workspace_id` | `str` | Log Analytics workspace ID |
| `workspace_name` | `str \| null` | Friendly name |
| `daily_gb` | `float \| null` | Average daily ingest volume (GB) |
| `commitment_tier_gb` | `float \| null` | Current commitment tier threshold |
| `recommended_tier` | `str \| null` | Optimal commitment tier; `null` if already optimal |
| `est_savings_pct` | `float \| null` | Estimated savings if moved to the recommended tier |
| `monthly_cost_usd` | `float \| null` | Current monthly workspace cost |

### `GitHubSeat` — `samples/github_seats.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | GitHub handle or unique identifier |
| `org` | `str \| null` | GitHub organisation slug |
| `seat_type` | `"enterprise" \| "team" \| "copilot_business" \| "copilot_enterprise" \| "ghas_committer"` | |
| `sku_id` | `str \| null` | Catalogue SKU reference |
| `last_activity_days` | `int \| null` | Days since last contribution / sign-in |
| `copilot_acceptances_30d` | `int \| null` | Accepted suggestions in last 30 days (Copilot seats only) |

### `GitHubOrg` — `samples/github_orgs.csv`

| Column | Type | Notes |
|--------|------|-------|
| `org` | `str` | GitHub organisation slug |
| `ghas_repo_count` | `int \| null` | Repos with GHAS enabled |
| `actively_scanned_repos` | `int \| null` | Repos that produced a scan alert |
| `active_committers` | `int \| null` | Unique committers in trailing 90 days |
| `runner_tier` | `str \| null` | Current runner plan / tier |
| `runner_minutes_used` | `int \| null` | Runner minutes consumed in the billing period |
| `runner_minutes_included` | `int \| null` | Runner minutes included in the current plan |

### `AdoSeat` — `samples/ado_seats.csv`

| Column | Type | Notes |
|--------|------|-------|
| `principal` | `str` | ADO user principal |
| `org` | `str \| null` | ADO organisation URL or slug |
| `seat_type` | `"stakeholder" \| "basic" \| "basic_plus_test"` | |
| `sku_id` | `str \| null` | Catalogue SKU reference |
| `last_activity_days` | `int \| null` | Days since last work-item, code, or pipeline activity |
| `only_stakeholder_activity` | `bool \| null` | `true` = only board reads / comments observed |
| `last_test_plan_days` | `int \| null` | Days since last Test Plans activity (`basic_plus_test` only) |

### `AdoOrgUsage` — `samples/ado_orgs.csv`

| Column | Type | Notes |
|--------|------|-------|
| `org` | `str` | ADO organisation URL or slug |
| `purchased_parallel_jobs` | `int \| null` | Number of purchased Microsoft-hosted parallel jobs |
| `p95_concurrent_jobs` | `int \| null` | P95 concurrent job count in the billing period |

---

## `NormalizedDataset` — rule-engine input

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
    "version": "0.1.0",
    "generated_at": "2026-05-05T10:00:00Z",
    "input_dir": "./samples",
    "pii_redaction": true
  },
  "summary": {
    "total_findings": 34,
    "rules_run": 23,
    "rules_skipped_no_impl": [],
    "estimated_monthly_savings_usd": 1234.56
  },
  "findings": [ /* list of Finding objects */ ]
}
```

Each element of `findings` matches the `Finding` schema above.

---

## CSV report output

`--format csv` (or `--format all`) writes a flat CSV where every
`Finding` field is a column. Multi-value fields (like `evidence`) are
JSON-serialised. Formula-injection characters (`=`, `+`, `-`, `@`) are
prefix-sanitised automatically.

Column order: `rule_id`, `surface`, `severity`, `principal`,
`current_sku`, `recommended_sku`, `estimated_monthly_savings_usd`,
`recommendation`, `confidence`, `evidence_ref`, `evidence`.
