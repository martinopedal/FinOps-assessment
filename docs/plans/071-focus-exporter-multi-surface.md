# §11 Stage-3 Plan — FOCUS exporter: M365 / GitHub / ADO surface support (#71)

**Author:** Maya (Lead / FinOps PM) — model: **Opus 4.6**
**Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
**Issue:** #71 — `release:v0.6.0`, `priority:p1`
**Predecessor:** PR #70 (FOCUS-aligned advisory CSV, Azure-only, D1–D6)
**Dependency:** #73 (tenant-stable PII salt) — merged as PR #95
**Implementer (planned):** Diego (reporter module) + Yuki (tests + docs + golden-fixture pinning)

> This document is the stage-3 plan only. No product code is changed in
> this PR. The implementation PR is a sibling on
> `squad/71-impl-focus-exporter-multi-surface` (Diego, after Noor's
> stage-4 verdict).

---

## §1 Research brief

### 1.1 FOCUS spec reference

The FinOps Open Cost and Usage Specification (FOCUS) is published at
<https://focus.finops.org/>. The current version is **FOCUS 1.3**. The
spec defines a normalised billing schema for cloud cost data with
mandatory columns including:

| FOCUS column | Relevance to advisory export | Mapping notes for SaaS surfaces |
|---|---|---|
| `BillingPeriodStart` / `BillingPeriodEnd` | ✅ Mandatory | Calendar-month bucketing via `observation_window_end` — same algorithm as Azure (D4). All surfaces share the `_billing_period()` function. |
| `ServiceProviderName` | ✅ Mandatory | `"Microsoft"` for all four surfaces. |
| `HostProviderName` | ✅ Mandatory | `"Microsoft"` for all four surfaces (even GitHub — Microsoft subsidiary). |
| `ServiceName` | ✅ Mandatory | **Surface-dependent:** `"Azure"` → Azure, `"Microsoft 365"` → M365, `"GitHub"` → GitHub, `"Azure DevOps"` → ADO. This is the key surface discriminator column. |
| `ServiceCategory` | ✅ Mandatory | **Surface-dependent:** `"Compute"` (Azure default), `"Collaboration"` (M365), `"Developer Tools"` (GitHub, ADO). These categories follow FOCUS § ServiceCategory guidance for SaaS. |
| `ServiceSubcategory` | Optional | Empty for all surfaces in v0.6.0 (not enough signal to sub-categorise). |
| `ChargeCategory` | ✅ Mandatory | Constant `"Advisory"` — this export is not billing data. FOCUS defines `Purchase` / `Usage` / `Tax` / `Credit` / `Adjustment`; none fit advisory output. `"Advisory"` is a non-FOCUS extension documented in `conformance_rationale`. |
| `ChargeClass` | ✅ Mandatory | Constant `"Optimization"` for all surfaces. |
| `ChargeFrequency` | ✅ Mandatory | `"Monthly"` for M365/GitHub/ADO (per-seat licensing is monthly); `"Monthly"` for Azure (carried over from D1–D6). |
| `ChargeDescription` | ✅ Mandatory | `finding.recommendation` verbatim. |
| `SkuId` | Optional | `finding.current_sku` — present for all surfaces (M365 SKU ID, GitHub seat type, ADO access level). |
| `ResourceId` | ✅ Mandatory | **Critical surface difference.** Azure: ARM resource ID. M365/GitHub/ADO: `finding.principal` (salted hash under PII redaction, UPN/login cleartext under `--no-pii-redaction`). See §1.2. |
| `ResourceType` | Optional | Empty in v0.5.0 (Azure). v0.6.0: surface-specific type hints — `"user_license"` (M365), `"seat"` (GitHub/ADO). Informational only. |
| `BillingAccountId` | ❌ Not emitted | No clean mapping for M365 (tenant ID is PII-adjacent), GitHub (enterprise slug is semi-public but not a billing account), or ADO (org name). Remains in `unsupported_columns`. |
| `BillingAccountName` | ❌ Not emitted | Same rationale as `BillingAccountId`. |
| `Region` | ❌ Not emitted | Not applicable to per-seat SaaS licensing. |
| `PricingCurrency` | ✅ Mandatory | `"USD"` — advisory export uses catalog `list_price_usd_month` which is always USD. M365 tenants may bill in local currency; this export does NOT reflect that. Documented as a known limitation. |
| Cost columns (`ListCost`, `ContractedCost`, `BilledCost`, `EffectiveCost`) | ❌ Empty by design | Same as Azure-only D1–D6. Advisory export does not contain billing amounts. |

**Columns with no clean SaaS mapping** — `BillingAccountId`,
`BillingAccountName`, `Region`, `AvailabilityZone`, `SkuPriceId`,
`CommitmentDiscount*`, `PricingQuantity`, `PricingUnit`,
`UsageQuantity`, `UsageUnit`, `ListUnitPrice`, `ContractedUnitPrice`.
All remain in `_UNSUPPORTED_COLUMNS` and are omitted from CSV rows.
No sentinel values are used — empty/absent is the FOCUS-recommended
handling for inapplicable columns.

### 1.2 ResourceId and PII: the multi-surface principal problem

Azure findings use ARM resource IDs as `ResourceId` — these are not
user-PII (they identify infrastructure, not people). The FOCUS join
story is clean: `ResourceId` in advisory rows joins to
`ResourceId` in FOCUS Cost-and-Usage data.

M365, GitHub, and ADO findings use `principal` as `ResourceId`:

| Surface | `finding.principal` content | PII? | Under redaction |
|---|---|---|---|
| M365 | UPN (e.g. `user@contoso.com`) | ✅ Yes | Salted hash (`sha256:…`) |
| GitHub | Login handle (e.g. `octocat`) | ⚠️ Semi-public | Salted hash |
| ADO | UPN or display name | ✅ Yes | Salted hash |

**With PII redaction ON (default):** `ResourceId` = the engine's salted
hash. Cross-run joins require tenant-stable salt (#73, now shipped).
Without a stable salt, `ResourceId` rotates per run and cannot be
joined. The manifest `pii_handling` block documents this.

**With PII redaction OFF:** `ResourceId` = cleartext UPN/login. Joinable
to HR/IAM systems but carries PII risk.

**FOCUS join story for SaaS surfaces:** There is no standard FOCUS
Cost-and-Usage dataset for M365/GitHub/ADO licensing. The `ResourceId`
column in SaaS advisory rows is **not joinable to Azure FOCUS data**.
It is joinable to other runs of `finops-assess` on the same surface
(self-join for trend analysis). The manifest documents this limitation.

### 1.3 Existing codebase: what ships in v0.5.0 (Azure-only)

| Component | File:line | Relevance |
|---|---|---|
| Column contract | `focus_aligned.py:36-62` | `COLUMN_ORDER` tuple — shared across all surfaces. No column changes needed. |
| AdvisoryFindingKey | `focus_aligned.py:97-158` | `advisory_finding_key()` — surface-agnostic. Works on any `(rule_id, principal, evidence)` triple. No changes needed. |
| BillingPeriod | `focus_aligned.py:166-204` | `_billing_period()` — reads `evidence.observation_window_end`. Surface-agnostic. No changes needed. |
| Row projection | `focus_aligned.py:212-244` | `_row_for()` — **Azure-specific** (hardcoded `ServiceName: "Azure"`, `ServiceCategory: "Compute"`). Must be generalised. |
| Surface filter | `focus_aligned.py:252-267` | `_partition_findings()` — explicitly skips M365/GitHub/ADO. Must be replaced with multi-surface routing. |
| Manifest builder | `focus_aligned.py:275-385` | `build_focus_aligned_manifest()` — references "azure" only in `surfaces_included`. Must accept multi-surface context. |
| Writer | `focus_aligned.py:393-434` | `write_focus_aligned_export()` — calls `_partition_findings()`. Must call the new multi-surface router instead. |
| Determinism | `_determinism.py:1-44` | `generated_at_iso()` — shared, no changes. |
| CLI entry point | `cli.py:857-919` | `export focus-aligned` command — currently logs skipped non-Azure counts. Must gain `--surface` flag. |
| JSON Schema | `schemas/focus_aligned_manifest.schema.json` | `surfaces_included` enum must widen; `pii_handling.mode` enum must widen to include non-Azure modes. |

### 1.4 Pricing strategy: where BilledCost / EstimatedMonthlySavingsUsd come from

**Cost columns remain empty** — same as Azure-only. This is not changing.

**`EstimatedMonthlySavingsUsd`** is populated by the rule engine, not
the FOCUS exporter. The engine's savings calculation is:
`catalog.list_price_usd_month × seat_count` for per-seat rules,
or rule-specific formulas for usage rules. When
`list_price_usd_month` is `null` in the catalog entry,
`estimated_monthly_savings_usd` on the finding is `null`, and the
CSV emits an empty string. The FOCUS exporter never performs pricing
lookups — it passes through whatever the engine computed.

**Currency limitation:** `PricingCurrency` is always `"USD"` because
catalog prices are USD. M365 tenants billed in EUR/GBP/JPY etc. will
see USD estimates, not local-currency amounts. FOCUS handles non-USD
via the `BillingCurrency` column (not emitted) and `ExchangeRate`
columns. We do not emit these; the manifest documents this gap. This
is acceptable for an advisory (non-conformant) export.

---

## §2 Rubberduck walkthrough

### 2.1 Approach summary

**Extend `focus_aligned.py` with a single multi-surface entry point**
rather than creating three new per-surface modules. Rationale:

1. The FOCUS column set is identical across all four surfaces — only
   `ServiceName`, `ServiceCategory`, `ServiceSubcategory`, and
   `ResourceType` vary. A dispatch dict handles this cleanly.
2. The `AdvisoryFindingKey`, `_billing_period()`, and `_normalize_evidence()`
   functions are already surface-agnostic.
3. A single module keeps the manifest builder, column contract, and
   writer in one place — no import graph changes, no new `__init__.py`
   exports.
4. Per-surface modules would duplicate 90% of the code for a 4-line
   dispatch difference.

**Alternative rejected:** Three new files (`focus_m365.py`,
`focus_github.py`, `focus_ado.py`) with shared base class. This was
considered and rejected: the variant behaviour is a 4-key dict lookup,
not a class hierarchy. YAGNI — if future surfaces need genuinely
different column logic (e.g. AWS), we can refactor to a strategy
pattern then.

### 2.2 Edge cases

**E1 — Prorated licenses (M365 mid-month assignment/removal).**
The engine's `M365.UNUSED_LICENSE_30D` rule fires based on sign-in
inactivity, not billing proration. `EstimatedMonthlySavingsUsd` is
the full monthly list price — there is no proration logic. FOCUS
`ChargeFrequency: "Monthly"` is correct. The export does not claim
to represent partial-month charges. No action needed.

**E2 — Mid-period seat changes (GitHub org member added/removed).**
Same as E1. The engine fires on activity signals, not billing events.
`EstimatedMonthlySavingsUsd` reflects the full seat price. FOCUS
`BillingPeriod` reflects the observation-window-end month, which is
correct for the advisory context.

**E3 — Suspended/disabled accounts.**
M365: `account_enabled: false` in `UserRecord`. The engine may fire
`M365.DISABLED_WITH_LICENSE` — the FOCUS exporter treats this like any
other finding. `ResourceId` is the (hashed) UPN. No special handling.
GitHub: suspended members don't appear in the REST API's seat list.
The exporter only sees findings the engine emits — no special handling.
ADO: disabled users may retain access-level assignments. Same approach.

**E4 — Free tiers (Visual Studio Dev Essentials, GitHub Free).**
GitHub Free orgs have no billable seats. The engine will not fire
`GH.INACTIVE_SEAT_90D` if `sku_id` maps to a free-tier catalog entry
with `list_price_usd_month: 0` (the rule checks `> 0`). If a finding
somehow fires, `EstimatedMonthlySavingsUsd` = 0, which is valid
advisory output. Dev Essentials users in ADO are `stakeholder` seats —
free, so `estimated_monthly_savings_usd` = 0 or null. No issue.

**E5 — Bundled SKUs already broken out by `data/catalog/` includes.**
When the engine fires on a parent bundle (e.g. `SPE_E5` which
`includes: [ENTERPRISEPACK, ...]`), the finding's `current_sku` is the
parent bundle ID. The FOCUS exporter passes `current_sku` through to
`SkuId`. It does NOT break out child SKUs — that is the engine's
responsibility, not the reporter's. No action needed.

**E6 — ADO basic vs basic+test plans.**
`ADO.TEST_PLANS_UNUSED` fires on `basic_plus_test` seats with no Test
Plans activity. The finding carries `current_sku: "basic_plus_test"` and
`recommended_sku: "basic"`. The exporter maps `SkuId` = `current_sku`.
The `ServiceCategory` is `"Developer Tools"` for all ADO findings. No
special handling.

**E7 — Power Platform per-app vs per-user licensing.**
Power Platform SKUs in `data/catalog/m365/` have distinct catalog IDs.
The engine fires surface=`m365` rules for these. The exporter treats them
identically to any other M365 finding — `ServiceName: "Microsoft 365"`.
This is slightly imprecise (Power Platform could arguably be a separate
service), but it is consistent with how the engine classifies them
(`surface: "m365"`). A future `ServiceSubcategory: "Power Platform"`
could be added in v0.7 if needed.

**E8 — M365 trial SKUs.**
Trial SKUs have `list_price_usd_month: 0` or `null` in the catalog.
The engine may fire usage rules; `EstimatedMonthlySavingsUsd` will be
0 or null. The FOCUS exporter passes this through. Advisory value:
"you have trial SKUs being consumed; consider whether to convert or
remove." Valid output.

**E9 — FOCUS ChargeCategory for license fees vs usage fees.**
FOCUS defines `Purchase` for one-time/recurring license fees and
`Usage` for consumption-based charges. Neither applies to advisory
output. Our `ChargeCategory: "Advisory"` is a non-FOCUS extension.
This is already documented in `conformance_rationale` and does not
change for SaaS surfaces.

**E10 — Non-USD currencies.**
M365 tenants are typically billed in local currency (EUR, GBP, JPY,
etc.). The advisory export uses `PricingCurrency: "USD"` because
catalog prices are USD list prices. The export does NOT attempt
currency conversion. FOCUS provides `BillingCurrency` and
`ExchangeRate*` columns for this purpose, but we do not emit them
(they are in `_UNSUPPORTED_COLUMNS`). This is a known limitation
documented in the manifest and in `docs/focus-export.md`. Operators
who need local-currency estimates must apply their own rate.

**E11 — PII leakage through BillingAccountName or ResourceName.**
`BillingAccountId` and `BillingAccountName` are not emitted (in
`_UNSUPPORTED_COLUMNS`). `ResourceId` for SaaS surfaces is
`finding.principal`, which is salted-hashed under default PII
redaction. No new PII exposure path. `ResourceType` is a constant
string (`"user_license"`, `"seat"`) — no PII content.

### 2.3 ChargeCategory and ChargeClass semantics

FOCUS 1.3 defines `ChargeCategory` values: `Purchase`, `Usage`, `Tax`,
`Credit`, `Adjustment`. None of these fit advisory output. Our existing
`"Advisory"` extension is correct for all surfaces. `ChargeClass:
"Optimization"` is similarly a non-standard extension that applies to
all surfaces (all findings are optimization recommendations).

### 2.4 Manifest changes

The manifest `pii_handling.mode` field currently uses Azure-specific
mode names (`azure_resource_id_cleartext`,
`azure_resource_id_per_run_salted_hash`,
`azure_resource_id_tenant_stable_salted_hash`). For a multi-surface
export, these names are misleading when the export includes
M365/GitHub/ADO findings where the principal is a UPN/login, not an
ARM resource ID.

**Decision:** Add new mode enum values for multi-surface exports:
- `"principal_cleartext"` — when `--no-pii-redaction` and non-Azure
  surfaces are present
- `"principal_per_run_salted_hash"` — default redaction with non-Azure
  surfaces
- `"principal_tenant_stable_salted_hash"` — tenant-stable salt with
  non-Azure surfaces

The existing Azure-only mode values remain valid when the export
contains only Azure findings. The mode is selected based on which
surfaces are actually present in the exported rows. The JSON schema
enum in `focus_aligned_manifest.schema.json` widens to include the
new values (additive, no version bump per the schema description).

### 2.5 What could go wrong

1. **Golden fixture drift.** Adding M365/GitHub/ADO rows to the
   existing `input-mixed-surfaces.json` fixture changes the CSV output
   and manifest (those surfaces are no longer skipped). All golden
   comparisons must be regenerated. **Mitigation:** the test plan
   (§4) specifies exact fixture updates.

2. **Backward-incompatible manifest change.** The `pii_handling.mode`
   enum widens; consumers that strict-match on the old enum may break.
   **Mitigation:** the schema description already mandates
   forward-compatible reads (`Consumers MUST accept unknown values`).
   The `manifest_schema_version` stays `"0.1"`.

3. **`surfaces_skipped` semantics change.** In v0.5.0,
   `surfaces_skipped` always has M365/GitHub/ADO counts. In v0.6.0
   with `--surface all`, it will be empty (or contain only surfaces
   with 0 findings). **Mitigation:** the JSON schema already defines
   `surfaces_skipped` as `additionalProperties: integer`. Empty dict
   is valid.

---

## §3 Implementation plan

### 3.1 Architecture decision: single-module extension

Extend `src/finops_assess/reporters/focus_aligned.py` with a
surface-dispatch dict and replace `_partition_findings()` with a
surface-filter function that accepts a set of requested surfaces.
No new per-surface modules.

### 3.2 File-level changes

| # | File | Change | Notes |
|---|------|--------|-------|
| F1 | `src/finops_assess/reporters/focus_aligned.py` | Add `_SURFACE_META` dispatch dict mapping `surface → (ServiceName, ServiceCategory, ResourceType)`. Values: `azure → ("Azure", "Compute", "")`, `m365 → ("Microsoft 365", "Collaboration", "user_license")`, `github → ("GitHub", "Developer Tools", "seat")`, `ado → ("Azure DevOps", "Developer Tools", "seat")`. | New constant dict. |
| F2 | `src/finops_assess/reporters/focus_aligned.py` | Refactor `_row_for(finding)` to read surface from `finding["surface"]` and look up `ServiceName`, `ServiceCategory`, `ResourceType` from `_SURFACE_META`. Fall back to current Azure values for unknown surfaces. | Minimal change to existing function. |
| F3 | `src/finops_assess/reporters/focus_aligned.py` | Replace `_partition_findings()` with `_filter_findings(findings, surfaces: set[str])` that returns `(included_rows, skipped_counts)` based on the requested surface set. When `surfaces={"azure","m365","github","ado"}`, all findings are included. When `surfaces={"azure"}`, behavior is identical to v0.5.0. | Backward-compatible replacement. |
| F4 | `src/finops_assess/reporters/focus_aligned.py` | Update `build_focus_aligned_manifest()` to accept `surfaces_included: set[str]` instead of hardcoding `{"azure"}`. Update `pii_handling.mode` selection: if surfaces_included contains any non-Azure surface, use the new `principal_*` mode names; if Azure-only, use the existing `azure_resource_id_*` names. | Backward-compatible when called with `{"azure"}`. |
| F5 | `src/finops_assess/reporters/focus_aligned.py` | Update `write_focus_aligned_export()` signature: add `surfaces: set[str] | None = None` parameter (default `None` = `{"azure"}` for backward compat). Call `_filter_findings(findings, surfaces)`. Pass `surfaces_included` to manifest builder. | Backward-compatible default. |
| F6 | `src/finops_assess/cli.py` | Add `--surface` option to `export focus-aligned` command. Type: `click.Choice(["azure", "m365", "github", "ado", "all"])`, default `"all"`. When `"all"`, pass `{"azure", "m365", "github", "ado"}`. Thread to `write_focus_aligned_export()`. | New CLI option; default changes from implicit Azure-only to explicit all-surfaces. |
| F7 | `src/finops_assess/cli.py` | Update the post-export log message: instead of logging "Skipped N non-Azure findings", log the actual `surfaces_skipped` dict from the manifest. | Minor log message fix. |
| F8 | `src/finops_assess/schemas/focus_aligned_manifest.schema.json` | Widen `pii_handling.mode` enum to include `"principal_cleartext"`, `"principal_per_run_salted_hash"`, `"principal_tenant_stable_salted_hash"`. Widen `surfaces_included` description. No version bump (additive under `"additionalProperties": true`). | Schema update. |
| F9 | `tests/test_focus_aligned_reporter.py` | Update test 8 (`test_skipped_surface_count_logged`) to test the new `--surface` flag behavior. When `--surface all`, all surfaces are included and `surfaces_skipped` is empty. When `--surface azure`, behavior matches v0.5.0. | Existing test update. |
| F10 | `tests/test_focus_aligned_reporter.py` | Add new tests (see §4 test plan). | New tests. |
| F11 | `tests/fixtures/focus_aligned/golden-multi-surface.csv` | New golden fixture: export of `input-mixed-surfaces.json` with `--surface all`. Contains Azure + M365 + GitHub + ADO rows sorted by `(surface, rule_id, principal)`. | New fixture. |
| F12 | `tests/fixtures/focus_aligned/golden-multi-surface.manifest.json` | New golden manifest for the multi-surface export. | New fixture. |
| F13 | `tests/fixtures/focus_aligned/input-multi-surface-full.json` | New input fixture with 2+ findings per surface (8+ findings total) to exercise per-surface column mapping thoroughly. Includes findings with `estimated_monthly_savings_usd: null` and `evidence: {}`. | New fixture. |
| F14 | `docs/focus-export.md` | Update "Azure-only in v0.5.0" callout to reflect multi-surface support. Add SaaS-specific column mapping table. Update ResourceId section for SaaS surfaces. Add currency limitation note. Update `v0.6.0 roadmap` section to reflect shipped status. | Doc update. |
| F15 | `docs/schema.md` | Update FOCUS-aligned manifest section with new `pii_handling.mode` enum values. | Doc update. |
| F16 | `docs/user-guide.md` | Add `--surface` flag documentation to the `export focus-aligned` usage section. | Doc update. |
| F17 | `docs/plan.md` §6 | Update "FOCUS-aligned advisory export" subsection to state multi-surface support shipped in v0.6.0. | Doc update. |
| F18 | `CHANGELOG.md` | v0.6.0 entry: "FOCUS exporter: M365, GitHub, and Azure DevOps surfaces now included in advisory CSV export (`--surface all`, default)." | Doc update. |

### 3.3 Surface-meta dispatch dict (F1)

```python
_SURFACE_META: dict[str, tuple[str, str, str]] = {
    # surface → (ServiceName, ServiceCategory, ResourceType)
    "azure": ("Azure", "Compute", ""),
    "m365": ("Microsoft 365", "Collaboration", "user_license"),
    "github": ("GitHub", "Developer Tools", "seat"),
    "ado": ("Azure DevOps", "Developer Tools", "seat"),
}
```

This is the single source of truth for per-surface column values.
Unknown surfaces fall through to `("Unknown", "Unknown", "")` with
a `_log.warning()`.

### 3.4 Refactored `_row_for()` (F2)

```python
def _row_for(finding: dict[str, Any]) -> dict[str, str]:
    surface = finding.get("surface", "azure")
    svc_name, svc_cat, res_type = _SURFACE_META.get(
        surface, ("Unknown", "Unknown", "")
    )
    bp_start, bp_end = _billing_period(finding)
    savings = finding.get("estimated_monthly_savings_usd")
    savings_str = "" if savings is None else str(savings)

    return {
        "ServiceProviderName": "Microsoft",
        "HostProviderName": "Microsoft",
        "ServiceName": svc_name,
        "ServiceCategory": svc_cat,
        "ServiceSubcategory": "",
        "ChargeCategory": "Advisory",
        "ChargeClass": "Optimization",
        "ChargeFrequency": "Monthly",
        "ChargeDescription": finding.get("recommendation", ""),
        "SkuId": finding.get("current_sku") or "",
        "ResourceId": finding.get("principal", ""),
        "ResourceType": res_type,
        "BillingPeriodStart": bp_start,
        "BillingPeriodEnd": bp_end,
        "PricingCurrency": "USD",
        "ListCost": "",
        "ContractedCost": "",
        "BilledCost": "",
        "EffectiveCost": "",
        "EstimatedMonthlySavingsUsd": savings_str,
        "AdvisoryFindingKey": advisory_finding_key(finding),
        "RuleId": finding.get("rule_id", ""),
        "Severity": finding.get("severity", ""),
    }
```

### 3.5 Surface filter replacement (F3)

```python
_ALL_SURFACES: frozenset[str] = frozenset({"azure", "m365", "github", "ado"})

def _filter_findings(
    findings: list[dict[str, Any]],
    surfaces: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    included: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for f in findings:
        surface = f.get("surface", "")
        if surface in surfaces:
            included.append(f)
        else:
            skipped[surface] = skipped.get(surface, 0) + 1
    return included, dict(sorted(skipped.items()))
```

### 3.6 PII handling mode selection (F4)

```python
def _pii_mode_name(
    pii_redaction: bool,
    salt_mode: str,
    surfaces_included: set[str],
) -> str:
    has_non_azure = bool(surfaces_included - {"azure"})
    if not pii_redaction:
        return "principal_cleartext" if has_non_azure else "azure_resource_id_cleartext"
    if salt_mode == "tenant_stable":
        return (
            "principal_tenant_stable_salted_hash"
            if has_non_azure
            else "azure_resource_id_tenant_stable_salted_hash"
        )
    return (
        "principal_per_run_salted_hash"
        if has_non_azure
        else "azure_resource_id_per_run_salted_hash"
    )
```

### 3.7 CSV sort key for determinism

Rows are sorted by `(surface, RuleId, ResourceId)` before writing.
This ensures byte-deterministic output regardless of finding order in
the input report. The sort key is the same triple that makes
`AdvisoryFindingKey` unique per row (minus evidence, which does not
affect sort order for non-duplicate findings).

### 3.8 CLI `--surface` flag (F6)

```python
@export.command("focus-aligned")
@click.option(
    "--surface",
    "surface",
    type=click.Choice(["azure", "m365", "github", "ado", "all"], case_sensitive=False),
    default="all",
    help="Surface(s) to include. Default: all.",
)
# ... existing --input and --output options ...
def export_focus_aligned(
    input_path: Path,
    output_path: Path,
    surface: str,
) -> None:
    surfaces = _ALL_SURFACES if surface == "all" else {surface}
    # ... existing JSON load ...
    csv_path, manifest_path = write_focus_aligned_export(
        report, output_path, surfaces=surfaces,
    )
```

### 3.9 Backward compatibility contract

| Scenario | v0.5.0 behavior | v0.6.0 behavior | Byte-identical? |
|---|---|---|---|
| `export focus-aligned` with Azure-only report, no `--surface` flag | Azure rows exported, M365/GH/ADO skipped | Azure rows exported (no M365/GH/ADO findings to include) | ❌ No — manifest `surfaces_included` changes from `["azure"]` to `["ado","azure","github","m365"]` because the _requested_ set is all. |
| `export focus-aligned --surface azure` with Azure-only report | N/A (flag doesn't exist) | Azure rows exported, identical to v0.5.0 | ✅ Yes — manifest matches v0.5.0 exactly. |
| `export focus-aligned` with mixed-surface report, no `--surface` flag | Azure rows only, M365/GH/ADO skipped and counted | All surfaces included | ❌ No — this is the feature. |

**Implication:** The default behavior changes from "Azure-only" to
"all surfaces". This is intentional — the D7 unblock is the whole
point of this issue. Operators who want Azure-only behavior can pass
`--surface azure`. The golden fixture for `test_golden_csv_byte_identical`
must continue to work: since the input has only Azure findings, the
CSV output is unchanged; only the manifest changes. We add
`--surface azure` to golden tests to preserve byte-identity.

### 3.10 No new dependencies

This feature uses only stdlib (`csv`, `json`, `hashlib`, `pathlib`)
and pydantic (already a dependency). No new PyPI packages.

### 3.11 No `models.py` changes

The FOCUS exporter reads from the `Finding` model and the engine's
JSON report dict. No new pydantic models are needed. The per-surface
observation types (`M365LicenseObservation`, `GitHubSeatObservation`,
etc.) are consumed by collectors/engine, not by reporters.

---

## §4 Test plan

### 4.1 Existing tests (update, don't break)

| Test | File | Action |
|---|---|---|
| `test_golden_csv_byte_identical` | `test_focus_aligned_reporter.py` | Add `--surface azure` to the render call to preserve byte-identity with the existing golden fixture. |
| `test_golden_manifest_byte_identical` | `test_focus_aligned_reporter.py` | Same — pass `surfaces={"azure"}` to `write_focus_aligned_export()`. |
| `test_skipped_surface_count_logged` | `test_focus_aligned_reporter.py` | Update: with `--surface all`, the mixed-surface input produces 5 rows (not 2) and `surfaces_skipped` is `{}`. Add a second variant that passes `--surface azure` and asserts v0.5.0 behavior. |

### 4.2 New tests

| # | Test | Description | Fixture |
|---|---|---|---|
| T1 | `test_multi_surface_golden_csv` | Golden-compare: render `input-multi-surface-full.json` with `--surface all` + `SOURCE_DATE_EPOCH=0`. Byte-compare against `golden-multi-surface.csv`. | `input-multi-surface-full.json`, `golden-multi-surface.csv` |
| T2 | `test_multi_surface_golden_manifest` | Golden-compare: manifest from T1 byte-compared against `golden-multi-surface.manifest.json`. | `golden-multi-surface.manifest.json` |
| T3 | `test_multi_surface_service_name_mapping` | Parse T1's CSV; assert `ServiceName` column values: `"Azure"` for azure findings, `"Microsoft 365"` for m365, `"GitHub"` for github, `"Azure DevOps"` for ado. | Same input as T1. |
| T4 | `test_multi_surface_service_category_mapping` | Assert `ServiceCategory`: `"Compute"` for azure, `"Collaboration"` for m365, `"Developer Tools"` for github/ado. | Same input as T1. |
| T5 | `test_multi_surface_resource_type_mapping` | Assert `ResourceType`: `""` for azure, `"user_license"` for m365, `"seat"` for github/ado. | Same input as T1. |
| T6 | `test_surface_flag_azure_only` | Pass `--surface azure` with mixed-surface input. Assert only Azure rows in CSV, `surfaces_skipped` has non-zero M365/GH/ADO counts. | `input-mixed-surfaces.json` |
| T7 | `test_surface_flag_single_non_azure` | Pass `--surface m365` with mixed-surface input. Assert only M365 rows in CSV. | `input-mixed-surfaces.json` |
| T8 | `test_pii_handling_mode_multi_surface` | Render with `pii_redaction=true`, `salt_mode="per_run"`, `surfaces={"azure","m365"}`. Assert manifest `pii_handling.mode` = `"principal_per_run_salted_hash"`. | Synthetic report dict. |
| T9 | `test_pii_handling_mode_azure_only` | Render with `pii_redaction=true`, `salt_mode="per_run"`, `surfaces={"azure"}`. Assert manifest `pii_handling.mode` = `"azure_resource_id_per_run_salted_hash"` (v0.5.0 behavior). | Synthetic report dict. |
| T10 | `test_determinism_multi_surface` | Two runs with `SOURCE_DATE_EPOCH=0` and `--surface all` on multi-surface input. Assert byte-identical CSV and manifest. | `input-multi-surface-full.json` |
| T11 | `test_sort_order_deterministic` | Render multi-surface input where findings are in reverse order. Assert CSV row order is `(surface, RuleId, ResourceId)` sorted. | Synthetic report dict with shuffled findings. |
| T12 | `test_manifest_surfaces_included_all` | With `--surface all`, assert `surfaces_included` = `["ado", "azure", "github", "m365"]` (alphabetically sorted). | Any multi-surface input. |
| T13 | `test_manifest_schema_validates_multi_surface` | Load `golden-multi-surface.manifest.json`, validate against `focus_aligned_manifest.schema.json`. | Golden fixture. |
| T14 | `test_cli_surface_flag_help` | `--help` output includes `--surface` and lists the valid choices. | CLI runner. |
| T15 | `test_empty_savings_null_handling` | Finding with `estimated_monthly_savings_usd: null` emits empty string in `EstimatedMonthlySavingsUsd` column. Finding with `0` emits `"0"`. | Synthetic report dict with both cases. |

### 4.3 Golden fixture generation

All golden fixtures are generated with `SOURCE_DATE_EPOCH=0` and
committed with `text eol=lf` in `.gitattributes` (already configured).
The implementer must run `scripts/generate_docs.py --check` after
generating to confirm no example-report drift.

### 4.4 Cross-platform CI

Tests use `pathlib.Path` for all fixture paths. Golden CSV files use
LF line endings enforced by the csv writer's `lineterminator="\n"`.
No platform-specific code paths.

---

## §5 Documentation updates

| Doc | Update |
|---|---|
| `docs/focus-export.md` | Remove "Azure-only in v0.5.0" callout. Add SaaS surface column mapping table. Update ResourceId section for SaaS principals. Add currency limitation note for M365 local-currency billing. Update v0.6.0 roadmap to reflect shipped. |
| `docs/schema.md` | Add new `pii_handling.mode` enum values to FOCUS-aligned manifest section. Update `surfaces_included` description. |
| `docs/user-guide.md` | Add `--surface` flag to `export focus-aligned` usage. Document default=all behavior. |
| `docs/plan.md` §6 | Change "Azure-only in v0.5.0" to "Multi-surface (Azure, M365, GitHub, ADO) from v0.6.0." |
| `CHANGELOG.md` | v0.6.0: "FOCUS exporter: M365, GitHub, and Azure DevOps surfaces now included in advisory CSV export (`--surface all`, default)." |
| `README.md` | Update features list if it mentions Azure-only FOCUS export. |
| `docs/focus-export.md` focus-mapping status | Update to `fully shipped` per issue #71 AC. |

**`scripts/generate_docs.py --check`** must pass after all doc + golden
fixture updates.

---

## §6 Plan invariants (stage-4 verification table for Noor)

| # | Invariant | Evidence | Verification |
|---|---|---|---|
| I1 | **Determinism** | `SOURCE_DATE_EPOCH` honoured via `_determinism.py`. Sort key `(surface, RuleId, ResourceId)` ensures row ordering is input-order-independent. | T10 (byte-identical across runs), T11 (sort order). |
| I2 | **PII redaction** | `ResourceId` for SaaS surfaces is `finding.principal`, which is already salted-hashed by the engine when `pii_redaction=True`. The exporter does not add or remove any PII fields. `BillingAccountId`/`BillingAccountName` are not emitted. `ResourceType` is a constant string (no PII). | T8/T9 (pii_handling mode), E11 (§2.2). |
| I3 | **Manifest provenance** | Manifest `surfaces_included` reflects the actual surfaces in the export. `pii_handling.mode` adapts to multi-surface context. `manifest_schema_version` stays `"0.1"` (additive change). | T2 (golden manifest), T12 (surfaces_included), T13 (schema validation). |
| I4 | **No copyrighted FOCUS spec text** | This plan links to <https://focus.finops.org/> and paraphrases column semantics. No spec text is copied into the repo. | Manual review of plan + implementation PR. |
| I5 | **Schema-first** | No `models.py` changes needed (F11 in §3.2). The JSON schema (`focus_aligned_manifest.schema.json`) is updated before implementation code is committed. | F8 in §3.2. |
| I6 | **No new dependencies** | Only stdlib + pydantic (existing). No `pip install` changes. | F10 in §3.10. |
| I7 | **Backward compatibility** | `write_focus_aligned_export(report, path)` with no `surfaces` arg defaults to `{"azure"}` behavior. `--surface azure` CLI flag restores v0.5.0 behavior exactly. | §3.9 compat table, T6 (azure-only flag). |
| I8 | **Read-only posture** | No new API calls, no write scopes, no mutation paths. The exporter reads a JSON report and writes a CSV + manifest. | Architecture is pass-through (§1.3). |

---

## §7 Delivery strategy: one PR vs staggered

### Decision: single PR, all four surfaces

**All four surfaces ship in one PR.** Rationale:

1. **The code change is small.** The core diff is a 4-entry dispatch dict,
   a refactored filter function, a manifest mode selector, and a CLI flag.
   The per-surface logic is < 10 lines per surface. There is no per-surface
   module, no per-surface class, no per-surface test file. Staggering this
   across 3 PRs would create more merge overhead than it saves.

2. **The test infrastructure is shared.** Golden fixtures, determinism
   tests, and schema validation all operate on the same multi-surface input.
   Splitting surfaces would require partial golden fixtures that get
   invalidated by the next surface PR.

3. **The issue AC is atomic.** Issue #71 requires `surfaces_skipped` for
   M365/GitHub/ADO to drop to 0. Shipping one surface at a time leaves the
   issue open with partial AC satisfaction.

4. **The prerequisite (#73, tenant-stable salt) is already merged.** There
   is no dependency ordering that would benefit from staggering.

### Minimum-viable scope for v0.6.0

**Everything in this plan ships in v0.6.0.** The cut-line is this plan.
Nothing is deferred to v0.7.

### What defers to v0.7 (explicitly out of scope)

| Item | Rationale |
|---|---|
| `ServiceSubcategory` population (e.g. `"Power Platform"` for M365 Power SKUs) | Requires additional catalog metadata not yet available. Low value for advisory output. |
| `BillingAccountId` / `BillingAccountName` emission | Would require M365 tenant ID (PII), GitHub enterprise slug, ADO org name. PII and join-key design work needed. |
| Non-USD `BillingCurrency` / `ExchangeRate` columns | Requires currency conversion infrastructure not in scope. |
| Per-surface `ChargeFrequency` variants (annual commitments) | All current rules are monthly; annual pricing is not in the catalog. |
| FOCUS conformance level upgrade from `"non-conformant"` | Requires cost columns to be populated — blocked on billing data integration. |
| `--surface` accepting comma-separated list (e.g. `--surface azure,m365`) | `click.Choice` does not support multi-value out of the box. Single-value or `all` is sufficient for v0.6.0. |
