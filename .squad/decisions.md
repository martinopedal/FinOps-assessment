# Squad Decisions

## Active Decisions


### 2026-05-13 — Stage-3 plan for #58 FOCUS-aligned advisory exporter (Maya, Opus 4.7)

## §11 Stage-3 Plan — FOCUS-aligned advisory exporter (#58)

> **Author:** Maya (Lead / FinOps PM) — model: Opus 4.7
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #58 (epic #57 child) — release `release:v0.5.0`
> **Branch (planned):** `squad/58-focus-aligned-export`
> **Implementer:** Diego (collector / module owner) + Yuki (tests + docs sweep)

This plan turns the locked stage-2 consensus into a file-level
checklist precise enough that the implementer makes zero
architectural decisions. D1–D7 and the six confirmed blockers are
**immutable** — if anything below contradicts them, treat the
consensus as the source of truth and flag the contradiction back to
me before merging.

---

### Inputs (locked)

- `C:\Users\martinopedal\.copilot\session-state\00cb0f92-01d8-49ec-b313-1616120d0178\files\focus-1-3-consensus.md` — **the locked stage-2 consensus.** Verbatim source for D1–D7, the six confirmed blockers, scope boundaries, and the help-text block. Do not revisit.
- `C:\Users\martinopedal\.copilot\session-state\00cb0f92-01d8-49ec-b313-1616120d0178\files\focus-1-3-research-brief.md` — stage-1 research brief (FOCUS 1.3 spec walkthrough + finding→column mapping table). Reference only; sections 7–9 truncated in the working copy.
- `C:\Users\martinopedal\.copilot\session-state\00cb0f92-01d8-49ec-b313-1616120d0178\files\focus-1-3-rubberduck-gpt.md` — GPT-5.4 critique (verdict REVISE-AND-RE-RUBBERDUCK; coined the `export` verb and `focus-aligned` noun adopted in D6).
- `C:\Users\martinopedal\.copilot\session-state\00cb0f92-01d8-49ec-b313-1616120d0178\files\focus-1-3-rubberduck-sonnet.md` — Sonnet 4.5 critique (pushed the Azure-only scope adopted in D1 and the savings-as-non-FOCUS-column posture adopted in blocker 1).
- `C:\git\FinOps-assessment\.squad\decisions.md` — 2026-05-12 entries on local-spawn preference and rubric posture. Apply as-is.
- `C:\git\FinOps-assessment\docs\plan.md` §6 (rules table) and §11 (delivery loop). The new export module gets a §6 cross-reference; the §11 stages 1–4 artefacts above land verbatim in the PR body.

### Stage-3 corrections to the consensus

The consensus brief (section "blockers", item 3) cites the per-run
salt as living in `src/finops_assess/json_reporter.py`. **Verified
against the repo:** the salt actually lives in
`C:\git\FinOps-assessment\src\finops_assess\engine.py` — generated at
`engine.py:151` (`salt_value = salt if salt is not None else
secrets.token_hex(16)`) and consumed at `engine.py:70-75` inside
`RuleContext.redact()`. The semantic claim (per-run salt makes
M365 PrincipalHash non-joinable across runs) is unchanged; only
the file pointer was wrong. The consensus stays locked; this
correction is bookkeeping for the implementer so they read the
right source while modelling the manifest's `pii_handling` field.

No other contradictions found. D1–D7, blockers 1–6, residual risks
1–4, and the help-text block are accepted verbatim.

### File-level changes

All paths are absolute Windows-style. LoC estimates include
docstrings + blank lines, exclude tests.

| # | Path | Verb | Purpose | LoC |
|---|------|------|---------|----:|
| 1 | `C:\git\FinOps-assessment\src\finops_assess\reporters\focus_aligned.py` | NEW | The exporter module: column projection, manifest assembly, deterministic write. | ~280 |
| 2 | `C:\git\FinOps-assessment\src\finops_assess\reporters\__init__.py` | MODIFIED | Re-export `write_focus_aligned_export` and `build_focus_aligned_manifest` for symmetry with the existing reporter exports. | +4 |
| 3 | `C:\git\FinOps-assessment\src\finops_assess\schemas\__init__.py` | NEW | Empty package marker so `importlib.resources.files("finops_assess.schemas")` works at runtime. | 1 |
| 4 | `C:\git\FinOps-assessment\src\finops_assess\schemas\focus_aligned_manifest.schema.json` | NEW | JSON Schema (draft 2020-12) for the manifest contract. Bundled as package-data; consumed by the validator test. | ~140 (JSON) |
| 5 | `C:\git\FinOps-assessment\src\finops_assess\cli.py` | MODIFIED | Add `@main.group() export` and `@export.command("focus-aligned")` subcommand wiring. | +60 |
| 6 | `C:\git\FinOps-assessment\pyproject.toml` | MODIFIED | (a) add `"schemas/*.json"` to `[tool.setuptools.package-data].finops_assess`; (b) add `"jsonschema>=4.21"` to the `[project.optional-dependencies].dev` list (validator test only — runtime stays dependency-free). | +2 |
| 7 | `C:\git\FinOps-assessment\tests\test_focus_aligned_reporter.py` | NEW | Sixteen enumerated tests — see §"Test enumeration". | ~480 |
| 8 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\input-azure-two-findings.json` | NEW | Hand-authored canonical findings JSON (2 Azure findings, both with stable resource IDs, distinct rule IDs, distinct evidence shapes). The single source of input for golden + determinism + key-stability tests. | ~80 (JSON) |
| 9 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\input-mixed-surfaces.json` | NEW | Findings JSON with 2 Azure + 1 M365 + 1 GitHub + 1 ADO finding. Drives the skipped-surface test. | ~120 (JSON) |
| 10 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\input-empty.json` | NEW | Findings JSON with `"findings": []`. Drives the zero-findings empty-CSV test. | ~30 (JSON) |
| 11 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\golden-azure.csv` | NEW | Byte-identical expected CSV for `input-azure-two-findings.json` rendered with `SOURCE_DATE_EPOCH=0`. LF line endings, pinned via `.gitattributes`. | 3 lines |
| 12 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\golden-azure.manifest.json` | NEW | Byte-identical expected manifest for the same input. | ~40 (JSON) |
| 13 | `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\golden-cli-help.txt` | NEW | Snapshot of `finops-assess export focus-aligned --help` output. | ~14 |
| 14 | `C:\git\FinOps-assessment\scripts\generate_docs.py` | MODIFIED | (a) extend `regenerate_examples` to render `examples\focus-aligned.csv` + `examples\focus-aligned.manifest.json` from the bundled demo report (filter Azure-only sub-slice); (b) extend the `--check` diff loop already in place to cover the two new artefacts; (c) export new module-level constant `FOCUS_BASENAME = "focus-aligned"`. | +35 |
| 15 | `C:\git\FinOps-assessment\examples\focus-aligned.csv` | NEW (generated, committed) | Generated artefact, byte-pinned LF via `.gitattributes`. | n/a |
| 16 | `C:\git\FinOps-assessment\examples\focus-aligned.manifest.json` | NEW (generated, committed) | Generated artefact, byte-pinned LF via `.gitattributes`. | n/a |
| 17 | `C:\git\FinOps-assessment\.gitattributes` | MODIFIED | Append two `text eol=lf` lines for the two new examples. | +2 |
| 18 | `C:\git\FinOps-assessment\docs\focus-export.md` | NEW | Operator-facing user doc. Warning-banner heavy: non-conformance, advisory-not-billing, calendar-month bucketing limitation, AdvisoryFindingKey stability contract, Azure-only scope + v0.6.0 D7 deferral pointer. | ~180 |
| 19 | `C:\git\FinOps-assessment\README.md` | MODIFIED | Add a one-line entry to the reports section linking to `docs/focus-export.md`; reference the new CLI subcommand. | +6 |
| 20 | `C:\git\FinOps-assessment\docs\user-guide.md` | MODIFIED | New `## Exporting findings to a FOCUS-aligned advisory CSV` section after the existing report section; embed the consensus help-text block; link to `docs/focus-export.md` for the full warning-banner content. | +35 |
| 21 | `C:\git\FinOps-assessment\CHANGELOG.md` | MODIFIED | New `## v0.5.0` entry — see §"Docs & generated-artefact updates" for skeleton. | +18 |
| 22 | `C:\git\FinOps-assessment\docs\plan.md` §6 | MODIFIED | Add a single line under §6 cross-referencing the export module (NOT a new rule — exporter is a derived view, not a rule). Wording: "Findings can additionally be projected onto a FOCUS-aligned advisory CSV via `finops-assess export focus-aligned`; see `docs/focus-export.md`." | +2 |
| 23 | `C:\git\FinOps-assessment\docs\roadmap\focus-mapping.md` | MODIFIED | Refresh: (a) status banner changes from `exploratory — documentation only` to `partially shipped (Azure-only, v0.5.0)`; (b) add a "Shipped surface" section that points at `docs/focus-export.md` and the CLI subcommand; (c) keep the rest of the exploratory mapping table intact (it still describes the M365/GitHub/ADO surfaces NOT shipped in v0.5.0); (d) downgrade the "no code, rule, collector, model, CSV column, or workflow changes" sentence to "no rule, collector, or model changes; the export reporter is a derived view that projects existing `Finding` fields". | +25, −5 |
| 24 | `C:\git\FinOps-assessment\docs\schema.md` | MODIFIED (CHECK) | Add a short subsection after the existing report-envelope description: `## FOCUS-aligned advisory manifest (v0.5.0)` describing `manifest_schema_version`, the field list, and pointing at the JSON Schema in `src/finops_assess/schemas/`. The manifest is **not** part of the canonical report envelope; it is a sidecar contract. Make that explicit. | +30 |
| 25 | `C:\git\FinOps-assessment\data\` | NO CHANGE | No catalogue, persona, or rule edits. Confirmed. |
| 26 | `C:\git\FinOps-assessment\src\finops_assess\data\` | NO CHANGE | No mirror updates needed (no rule/catalogue YAML touched). The new `src/finops_assess/schemas/` tree is a sibling, not a mirror — `tests/test_packaged_data.py` covers `data/` only and does not regress. |

**On combining the manifest into one module (§3 question):** I went
back and forth and came down on **single module**
(`focus_aligned.py`) rather than splitting
`focus_aligned_manifest.py`. Two reasons: (1) the manifest assembly
is ~70 LoC of dict construction with zero business logic — splitting
it forces a circular import for the `AdvisoryFindingKey` helper that
both the row writer and the manifest writer need to call; (2) the
existing reporter pattern is one module per output format
(`json_reporter.py`, `csv_reporter.py`, `html_reporter.py`,
`pdf_reporter.py`) and we keep the convention. The exported public
surface from `focus_aligned.py` is exactly two functions:
`write_focus_aligned_export(report, output_csv)` and
`build_focus_aligned_manifest(report)` — the second is exposed so a
future consumer (or a deeper test) can build the manifest dict
without round-tripping through the filesystem. The CSV writer always
calls the manifest writer internally so the two artefacts never
disagree.

### Manifest JSON shape (exact contract)

`manifest_schema_version` is the only field whose value is **frozen
forever** at the v0.5.0 value `"0.1"`. Any field rename, removal,
or type change requires a major bump and a deprecation cycle. New
fields are additive — consumers MUST ignore unknown fields. (See
§"v0.6.0 D7 tracking issue" for the planned additive shape.)

Field-by-field contract:

| Field | Type | Required | Enum / pattern | Example value | Notes |
|-------|------|:--------:|----------------|---------------|-------|
| `manifest_schema_version` | string | ✅ | exact `"0.1"` for v0.5.0 | `"0.1"` | Bump to `"0.2"` only on a breaking change. v0.6.0 may stay at `"0.1"` if all changes are additive (D7 fields qualify). |
| `tool` | object | ✅ | — | `{"name": "finops-assess", "version": "0.5.0"}` | Mirrors `report.run.tool` and `report.run.version` from the source JSON. |
| `tool.name` | string | ✅ | exact `"finops-assess"` | `"finops-assess"` | Constant. |
| `tool.version` | string | ✅ | semver string | `"0.5.0"` | Read from `finops_assess.__version__`. |
| `generated_at` | string | ✅ | RFC 3339 UTC ISO-8601, second precision | `"1970-01-01T00:00:00+00:00"` | Honours `SOURCE_DATE_EPOCH`. Algorithm identical to `json_reporter._generated_at()` — re-use that helper, do not re-invent. |
| `source_report` | object | ✅ | — | `{"path": "<redacted>/run.json", "schema_version": "1.0", "pii_redaction": true}` | Echoes `report.run.input`, `report.run.schema_version`, `report.run.pii_redaction`. Path is whatever the source report carries — we do NOT re-redact (the source is already redacted or not, by operator choice on the upstream `run`). |
| `source_report.path` | string | ✅ | — | as above | |
| `source_report.schema_version` | string | ✅ | — | `"1.0"` | |
| `source_report.pii_redaction` | bool | ✅ | — | `true` | |
| `dataset_type` | string | ✅ | exact `"advisory"` | `"advisory"` | Constant in v0.5.0. Distinguishes from FOCUS `"billing"` Cost-and-Usage datasets. Reserved future values: `"billing"`, `"forecast"`, `"hybrid"` — none populated today. |
| `focus_version` | string | ✅ | exact `"1.3"` | `"1.3"` | Spec version we shape against. |
| `conformance_level` | string | ✅ | exact `"non-conformant"` | `"non-conformant"` | Reserved future values: `"partial"`, `"conformant"` — only `"non-conformant"` legal in v0.5.0. The exporter MUST refuse to emit anything else; encode the constant in code. |
| `conformance_rationale` | string | ✅ | — | `"Rows describe corrective recommendations, not billed consumption. Cost columns (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. See docs/focus-export.md."` | Constant string in code, line-wrapped at 100 chars in source. |
| `surfaces_included` | array<string> | ✅ | each in `{"azure"}` (v0.5.0) | `["azure"]` | **Alphabetical sort** required (encoded as a `sorted()` call before serialisation). v0.6.0 will broaden the enum; the alphabetical rule means v0.5.0 output will be `["azure"]`, v0.6.0 output may be `["ado","azure","github","m365"]`. |
| `surfaces_skipped` | object | ✅ | keys in `{"m365","github","ado"}`, values are non-negative integers | `{"ado": 0, "github": 0, "m365": 0}` | Per-surface count of findings filtered out. Always present, even when all zero, so consumers can rely on the keys. Same alphabetical-key-order rule as `surfaces_included`. |
| `row_count` | integer | ✅ | ≥ 0 | `2` | Number of rows in the sibling CSV (excluding header). |
| `unsupported_columns` | array<string> | ✅ | FOCUS column names | `["BilledCost","BillingAccountId","BillingAccountName","CommitmentDiscountId","CommitmentDiscountName","CommitmentDiscountType","ContractedCost","ContractedUnitPrice","EffectiveCost","ListCost","ListUnitPrice","PricingQuantity","PricingUnit","Region","SkuPriceId","UsageQuantity","UsageUnit"]` | Static list in code — the FOCUS 1.3 mandatory columns we emit empty (cost columns) plus the FOCUS columns we don't emit at all (commitment, billing-account, region, pricing-quantity). Kept as a Python tuple constant; serialised in declaration order. |
| `join_keys` | array<object> | ✅ | — | `[{"column": "ResourceId", "joins_to": "FOCUS.ResourceId", "stability": "stable"}, {"column": "AdvisoryFindingKey", "joins_to": null, "stability": "stable", "notes": "Stable across runs for the same (rule_id, resource_id, evidence). Not a FOCUS column."}]` | Documents which output columns are intended for joining downstream and how stable they are across runs. Each entry has `column`, `joins_to` (FOCUS column name or `null`), `stability` (enum: `"stable" \| "per_run" \| "best_effort"`), and an optional `notes` string. Order is fixed in code. |
| `pii_handling` | object | ✅ | see below | `{"mode": "azure_resource_id_cleartext"}` | **v0.5.0 single-key shape: `{"mode": <enum>}`.** Designed so v0.6.0 can ADD `salt_source`, `principal_hash_algorithm`, etc. without breaking v0.5.0 consumers (they'll see the new keys and ignore them). Enum for `mode` in v0.5.0 is exactly `"azure_resource_id_cleartext"` (the Azure-only scope means principals are ARM resource IDs, no PII). v0.6.0 will broaden to `{"stable_salt","ephemeral_salt","cleartext","azure_resource_id_cleartext"}`. |
| `non_additive_warning` | bool | ✅ | exact `true` for v0.5.0 | `true` | Hard-coded `true`. Documents that summing `EstimatedMonthlySavingsUsd` across rows can double-count when conflict classes fire (the v0.5.0 Azure scope has no known conflict classes today, but the warning stays on so consumers don't rely on the "no conflicts today" property — D3 deferred conflict-class metadata to follow-up). |
| `column_order` | array<string> | ✅ | — | `["ServiceProviderName","HostProviderName","ServiceName","ServiceCategory","ServiceSubcategory","ChargeCategory","ChargeClass","ChargeFrequency","ChargeDescription","SkuId","ResourceId","ResourceType","BillingPeriodStart","BillingPeriodEnd","PricingCurrency","ListCost","ContractedCost","BilledCost","EffectiveCost","EstimatedMonthlySavingsUsd","AdvisoryFindingKey","RuleId","Severity"]` | Authoritative declaration of CSV column order. Single source of truth for both the writer and the golden test. |
| `evidence_key_fields` | array<string> | ✅ | — | `["rule_id","resource_id","normalized_evidence"]` | Documents the inputs to the AdvisoryFindingKey hash so downstream consumers know what stability the key promises. |
| `evidence_key_algorithm` | string | ✅ | — | `"sha256(rule_id \\x00 resource_id \\x00 normalized_evidence_json)"` | Free-form string but value is fixed. v0.6.0 may extend if `evidence_key_version` per-rule lands as a hash input (see §"AdvisoryFindingKey derivation algorithm"). |

**Non-deterministic field handling.** `generated_at` is the only
field that varies across runs. It MUST honour `SOURCE_DATE_EPOCH`
exactly the way `src\finops_assess\reporters\json_reporter.py:15-38`
already does — re-use `_generated_at()` (lift it to a shared helper
in a new `src\finops_assess\reporters\_determinism.py` module if
mypy --strict objects to a cross-module private import; otherwise
the implementer may import it through a deliberate public alias).
Every other field is content-derived and therefore byte-stable for a
given input.

**Complete example — Azure-only, 2 findings:**

```json
{
  "manifest_schema_version": "0.1",
  "tool": { "name": "finops-assess", "version": "0.5.0" },
  "generated_at": "1970-01-01T00:00:00+00:00",
  "source_report": {
    "path": "<redacted>/run.json",
    "schema_version": "1.0",
    "pii_redaction": true
  },
  "dataset_type": "advisory",
  "focus_version": "1.3",
  "conformance_level": "non-conformant",
  "conformance_rationale": "Rows describe corrective recommendations, not billed consumption. Cost columns (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. See docs/focus-export.md.",
  "surfaces_included": ["azure"],
  "surfaces_skipped": { "ado": 0, "github": 0, "m365": 0 },
  "row_count": 2,
  "unsupported_columns": [
    "BilledCost", "BillingAccountId", "BillingAccountName",
    "CommitmentDiscountId", "CommitmentDiscountName", "CommitmentDiscountType",
    "ContractedCost", "ContractedUnitPrice", "EffectiveCost", "ListCost",
    "ListUnitPrice", "PricingQuantity", "PricingUnit", "Region",
    "SkuPriceId", "UsageQuantity", "UsageUnit"
  ],
  "join_keys": [
    { "column": "ResourceId", "joins_to": "FOCUS.ResourceId", "stability": "stable" },
    { "column": "AdvisoryFindingKey", "joins_to": null, "stability": "stable",
      "notes": "Stable across runs for the same (rule_id, resource_id, evidence). Not a FOCUS column." }
  ],
  "pii_handling": { "mode": "azure_resource_id_cleartext" },
  "non_additive_warning": true,
  "column_order": [
    "ServiceProviderName", "HostProviderName", "ServiceName", "ServiceCategory",
    "ServiceSubcategory", "ChargeCategory", "ChargeClass", "ChargeFrequency",
    "ChargeDescription", "SkuId", "ResourceId", "ResourceType",
    "BillingPeriodStart", "BillingPeriodEnd", "PricingCurrency",
    "ListCost", "ContractedCost", "BilledCost", "EffectiveCost",
    "EstimatedMonthlySavingsUsd", "AdvisoryFindingKey", "RuleId", "Severity"
  ],
  "evidence_key_fields": ["rule_id", "resource_id", "normalized_evidence"],
  "evidence_key_algorithm": "sha256(rule_id \\x00 resource_id \\x00 normalized_evidence_json)"
}
```

**JSON serialisation rules for the manifest writer:**

- `json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)`. **Not** `sort_keys=True` — the field order in the example above is the *contract*, and sort_keys would clobber it.
- Trailing `"\n"` appended.
- Write via `output.write_text(payload, encoding="utf-8", newline="")` — same cross-platform pattern as `json_reporter.py:97`.

### AdvisoryFindingKey derivation algorithm

**Pseudocode:**

```python
SEP = b"\x00"  # ASCII NUL — never appears in rule_id, resource_id, or JSON output.

def advisory_finding_key(finding: dict) -> str:
    rule_id = finding["rule_id"]
    resource_id = finding["principal"]  # Azure-only scope: principal IS resource ID
    normalized = _normalize_evidence(finding.get("evidence") or {})
    payload = (
        rule_id.encode("utf-8")
        + SEP
        + resource_id.encode("utf-8")
        + SEP
        + normalized.encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()


def _normalize_evidence(evidence: dict) -> str:
    """Canonicalise the evidence dict to a single deterministic JSON string."""
    return json.dumps(
        _canonicalise(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonicalise(value):
    if value is None:
        return ""                        # null collapses to empty string
    if isinstance(value, bool):
        return value                     # JSON-serialised as true/false
    if isinstance(value, int):
        return value                     # JSON-serialised as exact integer
    if isinstance(value, float):
        # repr() preserves enough precision to round-trip; format consistently.
        return repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # Lists where order is not semantic should be sorted by the rule
        # author at evidence-construction time. We do NOT sort here, because
        # we cannot tell from the dict shape whether a list is a set or a
        # sequence. Sorting silently would silently corrupt rules whose
        # evidence list IS ordered (e.g. "top 3 nodes by waste"). See risk
        # register entry R7.
        return [_canonicalise(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalise(v) for key, v in sorted(value.items())}
    raise TypeError(f"unhashable evidence value type: {type(value).__name__}")
```

**Algorithm spec (binding):**

1. **Separator:** ASCII NUL byte (`b"\x00"`). Chosen over `||` because
   `||` could collide with operator-supplied resource IDs that contain
   the literal characters; NUL never appears in valid UTF-8 rule IDs,
   resource IDs, or `json.dumps` output (RFC 8259 §7 escapes control
   characters). This closes the cross-boundary injection vector
   flagged in residual risk #2.
2. **Inputs in order:** `rule_id`, then `resource_id`
   (= `finding["principal"]` under D1 Azure-only), then the
   canonicalised JSON of the evidence dict.
3. **Canonicalisation rules** (above): `None` → `""`; `bool` →
   `true`/`false`; `int` → exact int; `float` → `repr()` (so `1.0`
   and `1.00` produce the same key); `str` → verbatim; `list` →
   element-wise canonicalised, **order preserved** (see point 5);
   `dict` → key-sorted, value-canonicalised, recursive. Any other
   type raises `TypeError` at write time — the test suite must cover
   every type a rule actually emits (today: `str`, `int`, `float`,
   `bool`, `None`, `list[str]`, `dict[str, ...]`).
4. **JSON parameters:** `sort_keys=True, separators=(",", ":"),
   ensure_ascii=False, allow_nan=False`. The `allow_nan=False` flag
   is critical — `NaN` and `±Infinity` are not valid JSON and would
   produce non-deterministic keys across Python versions.
5. **List ordering:** **NOT** sorted by the canonicaliser. This is a
   deliberate trade-off documented in the risk register: rule
   authors who emit a list whose order is not semantic (e.g. a set
   of tags) MUST sort it at evidence-construction time. The
   alternative — silently sorting — would silently corrupt rules
   whose list IS ordered. The `evidence_key_version` mechanism
   (next paragraph) gives us an escape valve if we ever need to
   change this.

**Evidence-shape-change mitigation — DECISION: ship `evidence_key_version` per-rule.**

The consensus residual risk #2 ("evidence-shape change silently
breaks joins") forced a binary pick: (a) add an
`evidence_key_version: int` field on every Rule that participates
in the export, or (b) accept the risk and pin every Azure rule's
current key shape with a regression test.

I choose **(a) — `evidence_key_version` field on `Rule`** with the
following spec:

- **Schema change:** `src\finops_assess\models.py` `Rule` class gets
  `evidence_key_version: int = 1` (default 1 if absent in YAML).
  This is a **non-breaking schema addition** — `extra="forbid"` is
  satisfied by the explicit field, and existing YAML files with no
  `evidence_key_version:` key inherit the default.
- **YAML change:** `data/rules/azure.yaml` is **NOT touched in this
  PR** — every Azure rule defaults to `evidence_key_version: 1`.
  The field exists in the model so a future PR can bump it on a
  rule-by-rule basis when that rule's evidence shape changes.
- **Hash input:** the version is **NOT mixed into the hash** in
  v0.5.0. It is exposed in the manifest's `evidence_key_algorithm`
  field as future tooling: a rule-author who changes evidence shape
  in v0.6.0+ bumps the rule's `evidence_key_version` to 2, and the
  v0.6.0 exporter starts mixing it into the hash payload (becoming
  `sha256(rule_id || resource_id || version || normalized_evidence)`)
  — that change ships under `manifest_schema_version: "0.2"` so
  v0.5.0 consumers know to re-key.
- **Why ship the field but not yet use it:** declaring the migration
  contract NOW (with a one-line model field and a docs entry)
  prevents the painful schema bump six months from now when we
  actually need it. Risk surface is one optional pydantic field
  with a default value — `mypy --strict` and existing tests pass
  unchanged.
- **Why not option (b):** pinning every current key in a regression
  test creates a maintenance liability (every legitimate rule
  evidence improvement breaks a test) without giving consumers any
  signal that the key changed. (a) gives consumers a versioned
  contract; (b) gives consumers a silent break. The consensus
  residual risk explicitly called silent breakage the failure mode
  to mitigate.

**Justification for stage-3 (this is the most consequential design
choice in the PR):** the `Rule` model already has surface, severity,
inactivity_days as optional configuration knobs. Adding
`evidence_key_version: int = 1` with a default is a **non-breaking
addition** that costs ~3 lines and gives every future consumer a
versioned join-key contract. The consensus locked the residual risk
as "stage-3 must specify evidence-normalization rules + regression
test"; this discharges that obligation more durably than a static
pin.

### Test enumeration (no TBDs)

All tests live in `C:\git\FinOps-assessment\tests\test_focus_aligned_reporter.py`.
All fixtures live under `C:\git\FinOps-assessment\tests\fixtures\focus_aligned\`.

| # | Test function | Fixture(s) | Assertion (one line) | Expected fixture path |
|---|---------------|------------|----------------------|-----------------------|
| 1 | `test_golden_csv_byte_identical` | `input-azure-two-findings.json` | `write_focus_aligned_export(...)` produces exactly the bytes of `golden-azure.csv` (read with `Path.read_bytes()`). | `tests\fixtures\focus_aligned\golden-azure.csv` |
| 2 | `test_golden_manifest_byte_identical` | `input-azure-two-findings.json` | The sibling manifest produced alongside the CSV equals `golden-azure.manifest.json` byte-for-byte. | `tests\fixtures\focus_aligned\golden-azure.manifest.json` |
| 3 | `test_source_date_epoch_determinism_csv` | `input-azure-two-findings.json` | Two consecutive calls to `write_focus_aligned_export(...)` with `SOURCE_DATE_EPOCH=0` (set via `monkeypatch.setenv`) produce byte-identical CSV files. | n/a (in-memory compare) |
| 4 | `test_source_date_epoch_determinism_manifest` | `input-azure-two-findings.json` | Same as #3 for the manifest. Specifically asserts the `generated_at` field equals `"1970-01-01T00:00:00+00:00"`. | n/a |
| 5 | `test_manifest_validates_against_json_schema` | `input-azure-two-findings.json` | Use `jsonschema.Draft202012Validator(schema).validate(manifest_dict)`; schema loaded via `importlib.resources.files("finops_assess.schemas") / "focus_aligned_manifest.schema.json"`. Test uses `pytest.importorskip("jsonschema", reason="install with `pip install -e '.[dev]'`")` so the skip is loud and visible (CI installs `[dev]` so the test always runs in the gate). | `src\finops_assess\schemas\focus_aligned_manifest.schema.json` |
| 6 | `test_focus_cost_columns_are_empty` | `input-azure-two-findings.json` | Parse the rendered CSV with `csv.DictReader`; for every row, assert `row["ListCost"] == row["ContractedCost"] == row["BilledCost"] == row["EffectiveCost"] == ""`. Fails loud the day a future change tries to populate a FOCUS cost column from `estimated_monthly_savings_usd`. (Discharges blocker 6.) | n/a |
| 7 | `test_cli_help_snapshot` | n/a | `CliRunner().invoke(main, ["export", "focus-aligned", "--help"])` exit code 0; stdout equals `golden-cli-help.txt` byte-for-byte. (Pinning the help text catches accidental option renames.) | `tests\fixtures\focus_aligned\golden-cli-help.txt` |
| 8 | `test_skipped_surface_count_logged` | `input-mixed-surfaces.json` | `CliRunner().invoke(main, ["export", "focus-aligned", "--input", ..., "--output", ...])` exit code 0; stdout contains `"Skipped 3 non-Azure findings (m365=1, github=1, ado=1)"` exactly. CSV row count is 2. Manifest `surfaces_skipped` equals `{"ado": 1, "github": 1, "m365": 1}`. | n/a |
| 9 | `test_advisory_finding_key_stable_across_runs` | `input-azure-two-findings.json` | Two consecutive calls to `_advisory_finding_key(finding)` against the same finding dict produce the same hash. Also: load the CSV and assert the `AdvisoryFindingKey` column matches the value computed by the helper directly (round-trip). | n/a |
| 10 | `test_advisory_finding_key_changes_on_evidence_change` | `input-azure-two-findings.json` | Take finding[0]; mutate one evidence value; recompute key; assert it differs from the original. Repeat for: changed scalar, added key, removed key, list element re-ordered. (The list-reorder case asserts that reordering a list IS treated as semantic — see normalisation rule #5.) | n/a |
| 11 | `test_advisory_finding_key_separator_collision_resistance` | n/a | Construct two finding dicts where naive concatenation would collide (e.g. `rule_id="A", resource_id="B|C"` vs `rule_id="A|B", resource_id="C"`). Assert the keys differ — proves the NUL-byte separator works. | n/a |
| 12 | `test_cross_platform_line_endings` | `input-azure-two-findings.json` | After writing the CSV via `write_focus_aligned_export(...)`, read the bytes back and assert no `\r` byte is present (LF-only). Same for the manifest. Mirrors the cross-platform pattern at `html_reporter.py:89` and `json_reporter.py:97`. | n/a |
| 13 | `test_empty_findings_produces_header_only_csv_and_zero_row_manifest` | `input-empty.json` | CSV contains exactly one line (the header) ending in `\n`. Manifest `row_count == 0`, `surfaces_included == ["azure"]` (still — the manifest declares the *intended* surface scope, not the populated one), `surfaces_skipped` keys all map to 0. CLI exits 0. | n/a |
| 14 | `test_evidence_key_version_field_present_with_default_one` | n/a | Load `data/rules/azure.yaml` via `load_rules()`; assert every loaded `Rule` has `evidence_key_version == 1`. Documents that the field exists on the model and defaults correctly without forcing a YAML edit. | n/a |
| 15 | `test_packaged_schema_drift` | n/a | Hash the contents of `src/finops_assess/schemas/focus_aligned_manifest.schema.json` from both the resource path (importlib.resources) and the source tree path; assert equal. Mirrors the gate in `tests/test_packaged_data.py` for the schemas tree. | n/a |
| 16 | `test_generate_docs_check_includes_focus_artefacts` | n/a | Subprocess `python scripts/generate_docs.py --check` after touching `examples/focus-aligned.csv`; assert exit code 1 and stderr contains `"drifted: examples/focus-aligned.csv"`. (Confirms the docs-freshness gate covers the new artefacts.) | n/a |

The "consensus mandatory list" (golden CSV, golden manifest,
SOURCE_DATE_EPOCH determinism, schema validator, negative
cost-field, CLI help, skipped-surface count, AdvisoryFindingKey
stability + sensitivity, cross-platform line endings, packaged-data
drift, generate_docs --check freshness) is fully covered by tests
1–13 + 15–16. Test 14 is the stage-3-added regression for the
`evidence_key_version` model addition.

### CLI wiring

The `export` group is added under `main` symmetrically with the
existing `catalog` group (`cli.py` line ~421). The `focus-aligned`
subcommand carries the help text from D6 verbatim:

```python
@main.group()
def export() -> None:
    """Export findings to interoperability formats (advisory, not billing)."""


@export.command("focus-aligned")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Canonical findings JSON from `finops-assess run`.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Destination CSV path; manifest written alongside.",
)
def export_focus_aligned(input_path: Path, output_path: Path) -> None:
    """Emit a FOCUS-aligned advisory CSV from a finops-assess findings report.

    This export is NOT a FOCUS 1.3 conformant Cost-and-Usage dataset. Rows
    describe corrective recommendations, not billed consumption. Cost columns
    (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally
    empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. See
    the sidecar manifest.json and docs/focus-export.md before loading.
    """
```

**Error-handling contract** (every branch is a test):

- `--input` does not exist → click raises `UsageError` automatically (`click.Path(exists=True)`); CLI exits 2. No custom handling needed.
- `--input` exists but is not valid JSON → catch `json.JSONDecodeError`, `click.echo("ERROR: ...", err=True)`, `raise click.exceptions.Exit(1)`.
- `--input` is JSON but missing the canonical `findings` key → same as above with message `"input does not look like a finops-assess report (no 'findings' key)"`.
- Output dir does not exist → `output_path.parent.mkdir(parents=True, exist_ok=True)` (matches the pattern in `csv_reporter.py:99` and `json_reporter.py:92`). No error.
- Output dir is unwritable → let the `OSError` propagate; click renders it. Don't swallow.
- Input contains zero Azure findings AND zero non-Azure findings (truly empty) → emit header-only CSV + manifest with `row_count: 0`, `surfaces_included: ["azure"]`, `surfaces_skipped: {"ado": 0, "github": 0, "m365": 0}`. Exit 0. CLI prints `"Wrote 0 advisory rows to <path> (manifest: <path>)"`. **Rationale: empty is a legitimate state — the operator may have filtered findings or run against a clean tenant. Failing loud here would force CI scripts to special-case zero, which is exactly the kind of operator-hostile behaviour the consensus warns against.**
- Input contains non-Azure findings → filter them, count by surface, emit `click.echo(f"Skipped {n} non-Azure findings (m365={a}, github={b}, ado={c})")`. Exit 0.
- `SOURCE_DATE_EPOCH` set → `generated_at` derived from epoch (per `_generated_at()`); CSV otherwise byte-identical.
- `SOURCE_DATE_EPOCH` unset → `generated_at` is wall-clock UTC; everything else still byte-identical.

### Cross-platform & determinism

- Every `write_text(...)` call uses `encoding="utf-8", newline=""`.
  Reference: `html_reporter.py:89` and `json_reporter.py:97`. The CSV
  writer uses `output.open("w", encoding="utf-8", newline="")` with a
  `csv.DictWriter(lineterminator="\n", quoting=csv.QUOTE_MINIMAL)` —
  exact pattern at `csv_reporter.py:101-110`.
- `generated_at` honours `SOURCE_DATE_EPOCH` via the existing
  `_generated_at()` helper at `json_reporter.py:15-38`. **Action for
  the implementer:** lift `_generated_at` from a private into a
  module-public `generated_at_iso()` (or add a deliberate
  `_determinism.py` shared module under
  `src/finops_assess/reporters/`) so the FOCUS exporter calls the
  same code path. Do NOT reimplement the epoch parsing — bug parity
  matters more than DRY here.
- `scripts\generate_docs.py` invokes the new export inside
  `regenerate_examples` (line ~200): after the existing
  `write_csv_report` call, add
  ```python
  from finops_assess.reporters.focus_aligned import write_focus_aligned_export
  write_focus_aligned_export(report, target_dir / f"{FOCUS_BASENAME}.csv")
  ```
  The exporter writes both the CSV and the sibling
  `<basename>.manifest.json`, so a single call produces both
  artefacts.
- `.github\workflows\docs.yml` runs `python scripts/generate_docs.py
  --check` on every push (already gated). The `--check` path's
  existing `_diff_examples` loop (lines 266–278) already iterates
  every file in `EXAMPLES_DIR` so the new artefacts get diffed for
  free — no workflow change needed.
- **`.gitattributes` update is mandatory**: the byte-equal compare
  in `_diff_examples` is performed on the working tree, and on
  Windows checkouts with `core.autocrlf=true` (the GitHub-hosted
  runner default) committed files get rewritten with CRLF unless
  pinned. Append:
  ```
  examples/focus-aligned.csv text eol=lf
  examples/focus-aligned.manifest.json text eol=lf
  ```

### Docs & generated-artefact updates

**`docs\focus-export.md` — required structure (operator-facing):**

1. **Banner block (warning-banner-heavy, near-verbatim):**

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
   > stable-principal-salt feature lands — see the v0.6.0
   > tracking issue.

2. **Sections:**
   - `## What this export is for` — joining advisory rows to your existing FOCUS Cost-and-Usage warehouse on `ResourceId`.
   - `## What this export is NOT for` — billing reconciliation, audit, replacing your CUR/MCA dataset.
   - `## Column reference` — table of every emitted column, type, source, FOCUS-mandatory yes/no.
   - `## Manifest sidecar` — pointer to `docs/schema.md` for the field-by-field manifest contract.
   - `## AdvisoryFindingKey: stability contract` — explains how to use the column for cross-run join, and explicitly calls out the `evidence_key_version` migration mechanism for v0.6.0+.
   - `## Calendar-month bucketing — known limitation` — discharge of residual risk #4: explain that mid-month-relevant findings collapse to observation month.
   - `## Why ResourceId is cleartext (not hashed)` — explanation that Azure ARM resource IDs are not PII; v0.6.0 M365 path will hash via stable salt.
   - `## v0.6.0 roadmap` — Azure-DevOps / GitHub / M365 deferred; pointer to the D7 tracking issue.

**`README.md` — addition (under existing reports section):**

A single bullet: `Export findings to a FOCUS-aligned advisory CSV
for joining to FinOps Hubs / Cloudability / your warehouse:
\`finops-assess export focus-aligned --input run.json --output
focus-aligned.csv\` ([details](docs/focus-export.md)).`

**`docs\user-guide.md` — new section after the existing report
section:**

```
## Exporting findings to a FOCUS-aligned advisory CSV

`finops-assess` can project findings onto a CSV shaped like the
FinOps Foundation FOCUS 1.3 Cost-and-Usage spec, suitable for joining
to your existing FOCUS-aligned cost dataset. The output is **advisory**,
not billed consumption — see [`docs/focus-export.md`](focus-export.md)
for the full warning banner before loading.

[help-text block from D6, verbatim]

The output is two files: `<output>.csv` (the rows) and
`<output>.manifest.json` (the sidecar contract). Both honour
`SOURCE_DATE_EPOCH` for byte-deterministic builds.
```

**`CHANGELOG.md` — `## v0.5.0` skeleton:**

```
## v0.5.0

### Added
- `finops-assess export focus-aligned` subcommand — emits a FOCUS 1.3-shaped advisory CSV with sidecar `manifest.json` for joining advisory findings to FinOps Hubs / Cloudability / FOCUS-aligned cost datasets. Azure-only in this release; M365 / GitHub / ADO ship in v0.6.0 once the stable-principal-salt feature lands. See `docs/focus-export.md`. (#58, epic #57)
- `Rule.evidence_key_version: int = 1` field — enables versioned evolution of the AdvisoryFindingKey when a rule's evidence shape changes in v0.6.0+.
- New JSON Schema `src/finops_assess/schemas/focus_aligned_manifest.schema.json` (manifest_schema_version `"0.1"`) — additive-only contract.
- New committed examples `examples/focus-aligned.csv` and `examples/focus-aligned.manifest.json`, regenerated by `scripts/generate_docs.py`.

### Changed
- `docs/roadmap/focus-mapping.md` refreshed: status downgraded from `exploratory — documentation only` to `partially shipped (Azure-only, v0.5.0)`; mapping table retained for the M365/GitHub/ADO surfaces still in flight.

### Notes
- The exporter emits `BilledCost` / `ContractedCost` / `EffectiveCost` / `ListCost` as empty strings on every row by design — advisory savings are in the non-FOCUS `EstimatedMonthlySavingsUsd` column. The manifest declares `conformance_level: "non-conformant"`.
```

### v0.6.0 D7 tracking issue (to file alongside the v0.5.0 PR)

Open this **after** the v0.5.0 PR opens so the issue body can
cross-link the v0.5.0 PR number.

- **Title:** `feat: M365 surface in FOCUS-aligned advisory exporter (v0.6.0 — D7 unblock)`
- **Labels:** `release:v0.6.0`, `type:feature`, `squad`, `priority:p2`, `go:needs-research`
- **Milestone:** none (release-label-driven)
- **Body:**

  ```
  **Parent epic:** #57
  **Predecessor:** #58 (v0.5.0 Azure-only export)

  ## Why
  v0.5.0 shipped FOCUS-aligned advisory export for Azure findings
  only. The locked stage-2 consensus (D7) defined five gates that
  must ALL pass before M365 findings can ship in the export without
  silently breaking cross-run joins.

  ## D7 unblock criteria (all five required)

  1. **Persisted operator-managed salt:** `--principal-salt-file <path>`
     CLI option or `FINOPS_PRINCIPAL_SALT` env var implemented in
     `src/finops_assess/engine.py`, replacing the per-run
     `secrets.token_hex(16)` at `engine.py:151` when supplied. Default
     behaviour (per-run salt) unchanged.
  2. **Cross-run stability test:** golden test that runs the same input
     twice with the same salt file and asserts identical
     `PrincipalHash` values; same input with no salt file asserts
     different values.
  3. **Manifest field:** `pii_handling` extends from
     `{"mode": "azure_resource_id_cleartext"}` (v0.5.0) to
     `{"mode": <enum>, "salt_source": "<file|env|generated>"}`. Enum
     extends to include `"stable_salt"`, `"ephemeral_salt"`,
     `"cleartext"`. Manifest-schema-version stays at `"0.1"` (additive
     change).
  4. **Conflict-class documentation:** `docs/focus-export.md`
     enumerates every M365 rule pair that can fire on the same
     principal (e.g. `M365.DUPLICATE_BUNDLE` × `M365.OVER_LICENSED_VS_PERSONA`),
     and the manifest's `non_additive_warning: true` is upgraded to a
     structured `known_conflict_classes: [{"rules": [...], "principal_field": "..."}]`
     list.
  5. **Schema test:** any shipped M365 row whose `PrincipalHash` is
     empty when redaction is on fails the test suite.

  Without ALL FIVE, M365 stays out — there is no partial path.

  ## Out of scope (defer further)
  - Parquet output format
  - GitHub / Azure DevOps surface inclusion (separate D7-style gates apply)
  - `conflicts_with_finding_ids` column on the CSV (deferred to follow-up rule-engine epic, see consensus D3)
  - FinOps Hubs upload connector
  ```

### Validation gates the implementer must pass before merge

Run locally before pushing **and** in this order:

```bash
# Schema gates (fast)
finops-assess validate                   # catalog + personas + rules schema
ruff check . && ruff format --check .
mypy src

# Test gates (slower)
pytest                                   # full suite, including the 16 new tests
python scripts/generate_docs.py --check  # docs freshness gate (covers the two new artefacts)

# Smoke test of the new subcommand
finops-assess demo --output-dir ./.tmp-demo
finops-assess export focus-aligned \
  --input ./.tmp-demo/demo-report.json \
  --output ./.tmp-export/focus-aligned.csv
# Confirm: ./.tmp-export/focus-aligned.csv exists, ./.tmp-export/focus-aligned.manifest.json exists,
# manifest_schema_version is "0.1", surfaces_included is ["azure"].
```

CI (`.github/workflows/ci.yml`) runs `ruff`, `mypy`, `pytest` on
the `{ubuntu-latest, windows-latest, macos-latest} × {3.11, 3.12}`
matrix and `.github/workflows/docs.yml` runs the freshness gate.
**Both must be green** before stage-4 sign-off; the `required-checks`
summary job is the single context branch protection enforces.

### Branch + PR conventions

- **Branch:** `squad/58-focus-aligned-export`
- **Commit message convention:** Conventional Commits, e.g.
  `feat(reporters): FOCUS-aligned advisory exporter (#58)`,
  `test(reporters): golden + determinism for focus_aligned`,
  `docs(focus-export): operator-facing user doc + warning banner`,
  `chore(deps): add jsonschema to dev extras for manifest validator`.
  **Every commit must include the `Co-authored-by: Copilot <...>`
  trailer per the repo policy.**
- **PR body — required sections, in order:**
  1. **Stage-1 research summary** — link to `focus-1-3-research-brief.md` plus a 3-line summary in-PR.
  2. **Stage-2 consensus** — paste the entire locked consensus block verbatim (it is short — ~80 lines — and the PR is the durable record).
  3. **Stage-3 plan** — paste THIS document verbatim.
  4. `Closes #58`.
  5. `**Stage-4 Adversarial Review — Noor**` placeholder marker (Coordinator fills the verdict comment after review).
  6. PR is opened as **draft** per the session-end policy; flipped to ready-for-review only after CI is green.

### Risk register (4 inherited + stage-3 specific)

| # | Severity | Risk | Mitigation | Owner |
|---|:--------:|------|------------|-------|
| R1 | P1 | **Azure-only under-delivers vs Cloudability/Vantage** (consensus residual #1). | Documented in `docs/focus-export.md` and the manifest's `surfaces_included`/`surfaces_skipped`. v0.6.0 D7 tracking issue gives a public unblock contract. Accept the gap. | Maya |
| R2 | P0 | **Evidence-shape change silently breaks cross-run joins** (consensus residual #2). | Ship `Rule.evidence_key_version: int = 1` field NOW; documented in manifest's `evidence_key_algorithm`; tests #9–#11 pin current behaviour. Future shape change bumps `evidence_key_version` per-rule and `manifest_schema_version` to `"0.2"`. | Diego |
| R3 | P2 | **Manifest field gaps surface on first integration** (consensus residual #3). | `manifest_schema_version: "0.1"` declared; consumers MUST ignore unknown fields (documented in `docs/focus-export.md`); v0.6.0 additive changes stay at `"0.1"`. JSON Schema (test #5) gives a machine-readable contract. | Yuki |
| R4 | P2 | **Calendar-month bucketing collapses multi-month-relevant findings** (consensus residual #4). | Documented limitation in `docs/focus-export.md` § "Calendar-month bucketing — known limitation". Acceptable trade-off for FOCUS-warehouse joinability (D4). | Maya |
| R5 | P1 | **`evidence_key_version` schema-addition causes existing rule YAML to fail validation.** | Default value `= 1` makes it a non-breaking addition under `extra="forbid"`; test #14 asserts every existing Azure rule loads with the default. | Diego |
| R6 | P2 | **JSON Schema vendoring drift — schema in `src/finops_assess/schemas/` could diverge from the docs description in `docs/schema.md`.** | Test #15 (packaged-data drift) hashes the schema file from both paths. `docs/schema.md` references the schema by path, not by reproduction; if a future PR updates the schema, the docs-update obligation in `.github/copilot-instructions.md` catches the drift. | Yuki |
| R7 | P2 | **List-evidence ordering trap: a rule author who emits an unordered list (set) creates non-deterministic keys across runs because Python `set` → `list` is implementation-defined.** | Documented in algorithm spec rule #5 and in the rule-author docs (add a one-paragraph callout to `docs/rules.md` template the next time it regenerates — not in scope for this PR but flag for follow-up). For v0.5.0 every Azure rule's evidence is dicts and ordered lists; verified by inspection in stage-1 research. | Diego |
| R8 | P2 | **Empty input edge case (zero findings) might surprise CI scripts that grep stdout for finding counts.** | CLI prints a clear `"Wrote 0 advisory rows..."` line on the empty path; documented in the `--help` and in the user guide. Test #13 pins the behaviour. | Yuki |
| R9 | P1 | **`jsonschema` dev-extra is not installed in every contributor environment** — the validator test could be silently skipped, hiding manifest-schema bugs. | Test #5 uses `pytest.importorskip("jsonschema", reason="install with `pip install -e '.[dev]'`")` rather than a try/except, so the skip is loud and visible in pytest output. CI installs `[dev]` so the test always runs in the gate. | Yuki |

### Ready-to-implement checklist

Copy-paste into a working branch checklist:

- [ ] Create branch `squad/58-focus-aligned-export` off `main`.
- [ ] Add `evidence_key_version: int = 1` to `Rule` in `src\finops_assess\models.py`. Run `pytest tests/test_loaders.py` — must stay green.
- [ ] Lift `_generated_at()` from `src\finops_assess\reporters\json_reporter.py` to a shared helper (either public alias or `src\finops_assess\reporters\_determinism.py`).
- [ ] Implement `src\finops_assess\reporters\focus_aligned.py` (column projection + manifest assembly + writer + `_advisory_finding_key` helper). Re-export from `src\finops_assess\reporters\__init__.py`.
- [ ] Create `src\finops_assess\schemas\__init__.py` (empty) and `src\finops_assess\schemas\focus_aligned_manifest.schema.json` (Draft 2020-12).
- [ ] Add `"schemas/*.json"` to `[tool.setuptools.package-data].finops_assess` in `pyproject.toml`. Add `"jsonschema>=4.21"` to `[project.optional-dependencies].dev`.
- [ ] Wire CLI: `@main.group() export` and `@export.command("focus-aligned")` in `src\finops_assess\cli.py`. Help text matches D6 verbatim.
- [ ] Hand-author `tests\fixtures\focus_aligned\input-azure-two-findings.json` (2 Azure findings, distinct rule IDs, distinct evidence shapes — at minimum one with a list value, one with a nested dict).
- [ ] Hand-author `tests\fixtures\focus_aligned\input-mixed-surfaces.json` and `input-empty.json`.
- [ ] Generate the goldens: run the exporter with `SOURCE_DATE_EPOCH=0` against `input-azure-two-findings.json`, copy the outputs to `golden-azure.csv` and `golden-azure.manifest.json`. **Do not hand-edit afterwards.**
- [ ] Generate `golden-cli-help.txt` from `finops-assess export focus-aligned --help`.
- [ ] Implement all 16 tests in `tests\test_focus_aligned_reporter.py`.
- [ ] Extend `scripts\generate_docs.py` `regenerate_examples` to render `examples\focus-aligned.csv` + `.manifest.json`.
- [ ] Run `python scripts/generate_docs.py` — commit `examples\focus-aligned.csv` + `examples\focus-aligned.manifest.json`.
- [ ] Append two `text eol=lf` lines for the new examples to `.gitattributes`.
- [ ] Write `docs\focus-export.md` (warning-banner heavy).
- [ ] Update `README.md` (one bullet), `docs\user-guide.md` (new section), `CHANGELOG.md` (v0.5.0 entry), `docs\plan.md` §6 (one-line cross-reference), `docs\schema.md` (manifest subsection), `docs\roadmap\focus-mapping.md` (status refresh).
- [ ] Run all validation gates locally (see §"Validation gates").
- [ ] Push the branch; open the PR as draft with the §"Branch + PR conventions" body structure.
- [ ] Once CI is green, flip the PR to ready-for-review and tag the Coordinator for stage-4 routing to Noor.
- [ ] After the v0.5.0 PR is open, file the v0.6.0 D7 tracking issue with the body from §"v0.6.0 D7 tracking issue".

— Maya

### 2026-05-12T10:51Z  ,  User directive  ,  local-spawn preference when repo is open (Coordinator)

**By:** martinopedal (via Squad Coordinator)

**Decision:** When the local checkout is active and the user is at the keyboard, default to **local squad-member spawns** for follow-up work, not `@copilot`-direct bot routing. The `@copilot`-direct posture applies to **async/cloud/away-from-keyboard** work. Multi-agent fan-out stays on-request.

**Why:** Martin observed that routing #44 to @copilot when the local checkout was already open added GitHub round-trip latency and bot-cooking time without saving cost  ,  we'd rubric-review the bot's PR anyway, so we may as well spawn the right squad member locally and ship faster.

**Routing matrix update:**

| Context | Default routing |
|---------|----------------|
| User at local keyboard, repo open | Local squad spawn (Lightweight/Standard mode) |
| Async / cloud / away-from-keyboard | `@copilot`-direct (rubric review on PR) |
| Frontier-epic kickoff (architecture, security audit) | Multi-agent fan-out (on-request exception) |
| Routine work, no local session | `@copilot`-direct (rubric review on PR) |

**Supersedes/refines:** The 2026-05-12 rubric reframe entry (issue #25). The reframe still stands; this clarifies the trigger for local vs bot routing within the rubric posture.

### 2026-05-12  ,  Squad-PR auto-approve workflow for Noor-verdict comments (issue #47, PR #48)

**By:** Maya & Coordinator (design + implementation)

**Decision:** Squad PRs on `main` no longer require the `enforce_admins` toggle dance to bypass branch protection. Implement `.github/workflows/squad-approve.yml` that listens for the Stage-4 verdict comment (Noor's **`VERDICT: APPROVE`** line with the **`Stage-4 Marker`** tag). When both are present, the workflow submits a `github-actions[bot]` approval, satisfying branch protection's review-count rule.

**Design choice:** **Option A  ,  Workflow approval via `github-actions[bot]`** (implemented in #48).
- Trigger: PR comment by repo owner matching the verdict pattern.
- Action: Workflow runs, parses the comment, posts `github-actions` as a 2nd approver.
- Pros: Lightweight, no additional secrets, uses GitHub Actions permissions already granted, decouples verdict logic from GitHub API calls.
- Cons: Adds one more workflow file to the CI/CD surface; requires comment text discipline.

**Rejected alternatives (with one-line reasons):**
- **Option B  ,  Separate `noor-bot` GitHub App/PAT identity.** Highest-fidelity presentation (review genuinely shows under "Noor"), but requires creating + rotating a second identity. Deferred; A is async-friendly today with zero new credentials.
- **Option C  ,  Carve `squad/*` branches out of protection.** Rejected  ,  squad PRs are *more* sensitive, not less. Large security hole.
- **Option D  ,  Rulesets with owner-bypass.** Still requires manual owner action per merge; only marginally less janky than the toggle dance.
- **Option E  ,  Document the toggle dance as the official protocol.** Legitimises the workaround instead of fixing it; not async-friendly.

**Trust model gates:**
- Workflow triggers only on **exact match** of Noor's verdict marker (case-sensitive, full string).
- Approval is **only** submitted by `github-actions[bot]` (no human bot account).
- Comment author **must** be the repo owner (Martin) or admin.
- Workflow is **read-only** on the GitHub API  ,  only creates an approval, never closes/cancels PRs or modifies other resources.

**Rollback path:** If `github-actions[bot]` approval doesn't satisfy `required_approving_review_count` in practice (e.g. counted as same identity as Coordinator, or disallowed by org policy), pivot to **Option B (separate `noor-bot` identity)** and file a follow-up issue. Workflow is idempotent; no data loss.

**Status:** Merged in PR #48. Coordinator followed up with `fix(squad): restore main's line endings` to correct Maya's editor (LF → CRLF) so the diff is clean.

### 2026-05-12  ,  Squad-memory bootstrap & label-drift cleanup (issue #23)

**Decision:** Land the 🟢-trivial squad-state cleanup from Maya's gap analysis (`.squad/decisions/inbox/maya-gap-analysis-2026-05-12.md`, §C) in a single PR closing #23, after Noor's stage-4 sign-off (`.squad/decisions/inbox/noor-stage4-2026-05-12.md`).

**Scope (in this decision, no others):**
1. Refresh `.squad/identity/now.md` (was pinned to "Initial setup" since 2026-05-04).
2. Seed `.squad/identity/wisdom.md` with the five Noor-approved patterns (PR archeology). Pattern (f) was rejected as a duplicate of (c) and pattern (d) was reworded per Noor's E.2.
3. Replace the `milestone:M1`–`milestone:M7` row in `.squad/routing.md` with the actual `release:v0.4.0`–`release:v1.0.0` and `release:backlog` rows. Hard replace, no redirect (Noor's E.3 audit confirmed no historical link expects the `milestone:Mx` shape).
4. Fix `Issue label` column drift in `.squad/team.md` and the `Route To` column in `.squad/routing.md`: actual labels are `squad:maya`/`squad:priya`/`squad:diego`/`squad:sam`/`squad:noor`/`squad:yuki`  ,  not the role-based names the docs assumed.
5. Update `.squad/team.md` Project Context: add `Last activity: 2026-05-12`; replace `Roadmap: docs/plan.md §2 (M0–M7)` with `Roadmap: CHANGELOG.md (shipped) + docs/roadmap/README.md (frontier)`.
6. Append Learnings to `.squad/agents/lead/history.md` and `.squad/agents/security-reviewer/history.md`.

**Out of scope (deferred to backlog issues filed separately):**
- Rewriting `.squad/skills/project-conventions/SKILL.md` from `copilot-instructions.md` (🟡, Yuki).
- Pilot vs deprecate decision for Squad orchestration (🟡, spike).
- Auditing `.github/agents/squad.agent.md` against upstream `@bradygaster/squad-cli` (🟡, Sam).
- Frontier epic spikes (D.4–D.9 in Maya's plan)  ,  each gets its own §11 PR.

**Why:** 8 days post-bootstrap, Squad memory was empty (no `decisions.md` entries, no `inbox/`, every agent history seed boilerplate, `now.md` stale, `wisdom.md` empty, `project-conventions` skill was the placeholder). Routing references labels that do not exist. Land the trivial cleanup as one PR; punt anything 🟡/🔴 to its own issue + §11 loop.

### 2026-05-12  ,  PR #22 (FOCUS 1.2 mapping) merge clearance

**Decision:** PR #22 (`docs(roadmap): add exploratory FOCUS 1.2 correlation mapping`) cleared for squash-merge with a non-contract banner ([commit `e453265`](https://github.com/martinopedal/FinOps-assessment/commit/e453265)) inserted at the top of `docs/roadmap/focus-mapping.md`.

**Why:** Noor's stage-4 review (E.1) confirmed all five hard rules in `.github/copilot-instructions.md` are preserved. Residual risk was *expectation drift* from the doc's "Source field" column reading like a soft schema-stability contract. The banner collapses that risk to zero.

**Implication:** The doc explicitly does **not** commit the project to ship a FOCUS exporter, a Hubs connector, or any specific CLI surface, and does **not** freeze the current `Finding`/`run` field set. Any future field rename moves the doc in the same PR.

### 2026-05-12  ,  Pilot frontier epic D.4 if/when Squad orchestration is activated

**Decision:** If Martin elects to pilot the Squad-orchestrated §11 loop on a frontier epic (Maya's D.2 spike outcome), the pilot is **D.4  ,  Azure pricing intelligence (region/SKU/meter variance)**, not D.5/D.6/D.7.

**Why (Noor's E.4):** D.4 is spike + data-contract only (no rule YAML, no collector  ,  read-only posture cannot be at risk); it exercises the full §11 loop because it has multiple natural reviewers baked in (Diego for surface, Yuki for tests, Noor for copyright + schema); it avoids the PII / sovereign-cloud complications of D.6 and the commercial-terms complications of D.5/D.7.

**Falsification criteria  ,  Squad is parked if any two fire at pilot merge:**
1. **Cycle time regression.** Pilot PR takes ≥ 2× the median wall-clock time of the last five `@copilot`-direct docs PRs (#18–#22).
2. **No multi-author signal.** Fewer than three distinct squad members contribute substantive content (a routing acknowledgement comment does not count).
3. **No catch the direct path would have missed.** Stage-4 produces zero amendments to the stage-3 plan **and** code review surfaces zero issues a single-author `@copilot` review would not have caught.
4. **Squad memory does not accumulate.** Post-pilot, `.squad/decisions.md` still has fewer than two merged entries from `inbox/`, or `wisdom.md` gains no pattern.

**Rollback condition:** If two or more fire, the next decision is "Squad is parked": future frontier epics route through `@copilot`-direct with §11 in the PR body; `.squad/team.md` is reframed as a *review rubric* (whose voice to channel when adversarial-reading a PR), not an *orchestration scaffold*; squad workflows stay in place because they are cheap, but no new epic is required to traverse them. Revisit after two more shipped epics.

**Status:** Pending Martin's input on D.2 (the meta-spike). Until then, the `@copilot`-direct path remains the workflow that's actually shipping.

### 2026-05-12  ,  squad-cli upstream audit (issue #26)

**Verdict:** Local `.github/agents/squad.agent.md` stamps v0.8.25; upstream npm latest is v0.9.4 (2 minor versions ahead). **Do NOT wholesale re-align.** The ~7.4 KB of local divergence is intentional and justified:
- Inlined skill content (vs upstream's delegated pattern)  ,  keeps coordinator self-contained
- Removed TypeScript SDK Mode  ,  project doesn't use the SDK
- Removed Azure DevOps support  ,  project is GitHub-only  
- Added local `squad-pr-route.yml`  ,  fills a gap upstream didn't have at v0.8.25

Workflow drift (4 of 5 core workflows modified) is intentional, not re-aligned. **Instead:** File separate issues to evaluate upstream improvements *worth* adopting  ,  e.g., routing enforcement refusal rule from upstream PR #890 (v0.9.4).

**Meta-finding:** Coordinator session-start governance stamps v0.9.1, but on-disk `.github/agents/squad.agent.md` stamps v0.8.25. Third installation channel (likely user-level `~/.copilot/` or CLI-bundled copy) exists beyond what local repo pins. This is not a contradiction  ,  the on-disk repo file is project governance; the session-start governance is the active runtime. They drift independently. Future agents should know the difference.

### 2026-05-12  ,  Squad reframed as review rubric (issue #25)

**Decision:** The squad-orchestrated §11 pilot on a frontier epic (proposed in the *Pilot frontier epic D.4* decision above) is **not** being run. Instead, the squad scaffold is reframed as a **review rubric**: the workflow that ships work remains `@copilot`-direct with §11 stages documented in the PR body  ,  the same workflow that shipped M0–M7 across PRs #4–#22. The roster in `.squad/team.md` documents whose voice a reviewer should channel adversarially when reading any PR.

**Why:** 22 of 22 shipped PRs since project bootstrap have used the `@copilot`-direct path. Two squad-orchestrated batches this session  ,  the bootstrap PR #33 (Maya stage-3 + Noor stage-4) and the followup batch (Yuki on #24, Sam on #26 in parallel)  ,  produced quality results. But every productive moment was either a single-agent task with full ceremony or Coordinator-as-router; the promised value of multi-agent fan-out on a real epic was never tested. Falsification criterion (2) from the D.4 pilot decision  ,  *no multi-author signal in shipped work*  ,  was already true before the pilot started. The squad scaffold's value lives in the *rubric* (Maya's gap analyses and Noor's adversarial passes  ,  both real wins) and in the per-agent voices, not in formal orchestration.

**Implications:**
- Frontier epics #27–#30 (D.4–D.7) ship via `@copilot`-direct with §11 in the PR body. No formal squad-orchestrated stage-3/stage-4 spawns.
- Multi-agent stage-3/stage-4 spawns remain available on request for genuinely non-trivial PRs (architecture proposals, security audits, frontier-epic kickoffs) but are not the default.
- `.squad/team.md` gains a Posture section (this PR) making the rubric framing explicit.
- The squad workflows (`squad-triage`, `squad-pr-route`, `squad-issue-assign`) stay in place because they are cheap, useful for label routing, and channel the rubric automatically.
- `.squad/decisions.md`, `wisdom.md`, and agent histories continue to accumulate  ,  the rubric still produces and consumes squad memory.

**Falsification  ,  re-open issue #25 if any of these fire:**
1. Two consecutive frontier-epic PRs (D.4–D.7) ship with substantive defects that a stage-4 adversarial spawn would have caught.
2. Reviewer fatigue: a single `@copilot`-direct PR accumulates more than five review cycles before merge.
3. A squad member's domain expertise is consistently absent from PRs in their surface  ,  the rubric voices are not actually being channeled.

If any fire, re-run issue #25 with fresh evidence and re-evaluate the pilot.

**Status:** Closes #25.

### 2026-05-12  ,  Azure pricing module  ,  observation/profile family contract (issues #27, #28, #30)

**Decision:** `pricing.py` module (introduced in #27, extended in #28 and #30) is the canonical owner of the observation/profile family for Azure pricing data. Observations are **runtime data** supplied by collectors or customers (customer-specific EA/MCA/CSP rates), not catalog constants. The **hard boundary** is: `data/catalog/` holds vendor list prices (published, versioned); `src/finops_assess/pricing.py` defines the data contract and collectors populate it with customer-observed rates and agreements.

**Scope (all in this decision, no others):**
- #27 introduces `PricingObservation` model for region-specific pricing observations (base rates by region and meter ID)
- #28 extends with `CommitmentDiscount` and commitment-agreement subtypes (RI/Savings Plans, one-year/three-year term contracts)
- #30 adds `AgreementMultiplier` for agreement-type cost modifiers (Enterprise, MCA, CSP tier-specific rates)

**Why:** Separating observations from catalog prevents hard-coding of tenant-specific agreements into source control (security + compliance boundary). Allows the tool to operate with list prices (default) or customer-specific effective rates without repository mutation. Future pricing extensions (e.g., spot-instance discounts, reservation exchanges, hybrid-benefit pricing) belong in this module unless justified otherwise.

**Source/Linked PRs:** #39 (D.4 pricing intelligence  ,  stage 1 research + data contract), #42 (D.5 commitments  ,  stage 1 research + contract addenda), #43 (D.7 agreement types  ,  stage 1 research + contract addenda).

**Inbox file:** `.squad/decisions/inbox/diego-pricing-observation-contract.md` (proposed in #27, addended in #28 and #30).

### 2026-05-12  ,  M365 SKU-mix aggregate-summary contract (issue #29)

**Decision:** `M365FamilySummary` model (introduced in #29) is aggregate-only; tenant-id and per-principal fields are explicitly rejected by `extra='forbid'`. The 15-family `Literal` enum (`m365_e1_tier`, `m365_e3_tier`, `m365_e5_tier`, `office365`, `entra_p1`, `entra_p2`, `ems_e3`, `ems_e5`, `defender_o365_p1`, `defender_o365_p2`, `defender_cloud_apps`, `copilot_m365`, `copilot_pro`, `copilot_studio`, `gsa`) is the schema contract. Fields are aggregate counts and optional feature-usage signal counts; no user IDs, tenant IDs, or per-principal identifiers are permitted (preserves hard rule 4: PII redaction by construction).

**Why:** M365 pricing and licensing rules naturally operate on family-level aggregates (E1/E3/E5 tier fragmentation, Entra P2 feature usage vs assignment, security-addon overlap). The model enforces this at validation time: any attempt to leak per-principal data (a common data-governance drift vector in compliance audits) fails fast with a clear error. `extra="forbid"` makes future field additions explicit decisions.

**Source/Linked PR:** #40 (D.6 SKU-mix intelligence  ,  stage 1 research + data contract).

**Inbox file:** `.squad/decisions/inbox/priya-m365-family-summary.md` (proposed in #29).

### 2026-05-12  ,  Derived report views  ,  architectural principle (issue #31)

**Decision:** Report sections that surface **posture** rather than **data** are **derived views**  ,  they read the canonical JSON report and do NOT extend it. Advisory disclaimers are mandatory. Certification, scoring, level, rating language is forbidden in body content. Six binding rules (read-only over canonical, no schema additions, graceful degradation, mandatory advisory disclaimer, forbidden-word guard, vendor-neutral phrasing) enforce this contract in future reporter sections.

**Why:** The practice-review section in #31 added four posture cues (pricing assumptions, data-quality warnings, commitment posture, SKU-mix posture) without mutating the canonical report schema. Deriving them from existing fields avoids schema version bumps for non-data changes and prevents competing summary surfaces. The discipline generalizes to future confidence/completeness sections.

**Source/Linked PR:** #41 (D.8 reporter multi-cloud section  ,  includes FinOps practice-review posture layer).

**Inbox file:** `.squad/decisions/inbox/maya-derived-report-views-2026-05-12.md`.

### 2026-05-12  ,  Local-clear batch outcome  ,  falsification-test data on multi-agent fan-out

**Context:** On 2026-05-12 morning, the rubric reframe (issue #25) concluded that squad-orchestrated §11 was parked  ,  the shipping workflow remained `@copilot`-direct with §11 stages in PR bodies, same as M0–M7. By afternoon, Martin invoked the on-request exception for a **full local clear** of all 7 open backlog issues (#27–#32, #35) as a falsification test: does multi-agent fan-out beat the `@copilot`-direct baseline the rubric deprecated?

**Empirical outcome:**

- **7/7 issues closed via local squad**  ,  All issues routed to squad members; all merged within the batch window.
- **Head-to-head data point (#27 Diego vs #36 bot collision):** Diego's pricing contract (PR #39) won on §11-stage discipline (all 5 stages explicitly articulated), dedicated module placement (`pricing.py` as canonical owner), and pattern-setting for #28/#30 extensibility. Bot's #36 PR had no equivalent stage-3 plan or stage-4 adversarial pass before opening.
- **Lockout-revision chain (#28 commitments):** Diego round-1 rejected (scope gap + test coverage gap) → Yuki revised & resubmitted (round 2) → Yuki rejected (regex `\b` snake_case bug in language guardrail test) → Diego revised (round 3 with explicit lookahead) → Approved. Three-round review added orchestration cost a pure-autonomous bot might not trigger; concretely justified by catching a regex security boundary bug that round-1 and round-2 missed.
- **Five single-round approvals** (#29, #30, #31, #32, #35)  ,  Priya's M365 contract, Diego's agreement-types extension, Maya's derived-views principle, Sam's runbook, Yuki's routing-enforcement rule all approved on first submission.
- **Net cycle time: all 7 issues closed from initial spawn to final merge.** Coordinator ran the §11 loop hands-off after Martin's option-E choice.

**Falsification verdict  ,  Does multi-agent beat `@copilot`-direct baseline?**

*Signals where multi-agent won:*
- **§11-stage discipline:** No agent skipped a stage or hand-waved a plan. All PRs opened with stage-3 checklist in body; stage-4 adversarial reviews were live (not performative). Bot's #36 had no equivalent gate.
- **Pattern-setting consistency:** Diego's pricing decision was weaponized across #28 and #30 via the single `diego-pricing-observation-contract.md` decision document  ,  §11 stage-3 output was reused, not re-negotiated. Bot baseline has no equivalent multi-PR decision inheritance.
- **Noor's security catch (round 2 of #28):** The regex `\b` snake_case bug in the language guardrail test  ,  a boundary case that historically required manual audit. Noor's stage-4 adversarial pass caught it; bot's autonomous review on #36 did not surface an equivalent self-check.
- **Parallel throughput:** Four Wave-A agents in parallel (Priya, Diego, Maya, Sam) finished faster than four sequential single-agent passes would have. Yuki's round-2 revision on #28 was asynchronous, not a blocker on the other 6.

*Signals where multi-agent was costly:*
- **Three-round review on #28:** Lockout-revision cycle added overhead an autonomous bot wouldn't trigger, because the bot wouldn't have written the language-guardrail regex test in the first place  ,  that's a quality concession the baseline trades to avoid review latency.
- **Opus 4.7 tier costs:** Noor's stage-4 reviews consumed premium reasoning capacity; `@copilot`-direct on M0–M7 baseline ran at free tier. This batch spent more compute on adversarial review than a fast-path baseline.

*Net verdict:*
- **This batch produced higher-quality contracts with traceable design rationale** (3 promoted decisions from stage-3 plans). The rubric reframe is **VINDICATED**.
- **The per-call review costs justify themselves on frontier-epic kickoffs** (#27 pricing, #29 M365) where pattern-setting rationale matters for downstream extensions. They're overkill for routine work (#32 runbook, #35 routing rule) where the baseline suffices.
- **Noor's security catch on #28 (regex bug) is a concrete example** of multi-agent thoroughness the baseline historically missed  ,  but it was a function of the *specific test design*, not the orchestration model. The bot could have caught it if its test author had written the guardrail; the squad model surfaced it because Noor was asked to read adversarially.

**Action  ,  Keep rubric reframe as default; allow on-request exceptions (today's batch was a clean example); don't re-open #25.**

---

## 2026-05-12  ,  Wave: Protection-fix shipped + standing directive

### 2026-05-12  ,  Required-checks summary job replaces "CI" context (issue #51)

**By:** Maya (Lead / FinOps PM)

**Decision:** Replace the brittle branch-protection contract `contexts: ["CI"]` with a single summary job that publishes the literal context `required-checks`. The job lives at the end of `.github/workflows/ci.yml`, `needs: [lint-and-test, catalog-validation]`, runs `if: always()`, and asserts every upstream `needs.*.result == 'success'` via `actions/github-script@v9`  ,  failing the summary (and therefore the protection check) if any matrix shard or sibling job failed or was skipped.

**Why this matters:** Branch protection required the context name `CI`, but `name: CI` at the workflow level is *not* a published check context  ,  only job names (and matrix expansions) are. So `gh api PUT .../merge` returned `HTTP 405 Required status check 'CI' is expected` on every squad PR (#46, #48, #50) even with all checks green. This was the last remaining trigger for the `enforce_admins` toggle-dance after #47/#48 made review-count async-friendly.

**Trade-offs considered:**
- **Option A  ,  list every matrix context in protection** (`Lint, type-check, test (ubuntu-latest / py3.11)` × 6, plus `Validate YAML catalog & rules`): strongest correctness, but every matrix dimension change (add Python 3.13, drop macOS, etc.) silently breaks merge until protection is re-edited. Rejected on brittleness.
- **Option B  ,  summary `required-checks` job** (chosen): one stable contract; matrix changes invisible to protection; cost is one extra runner-minute per PR. The `if: always()` + explicit `needs.*.result` check is the canonical GitHub Actions summary-job idiom and handles `failure`, `cancelled`, and `skipped` correctly (only `'success'` passes).
- **Option C  ,  rename a job to `CI`**: cheapest but couples the protection contract to a generic, easy-to-rename job name and gives no aggregation guarantee. Rejected.
- **Option D  ,  drop `required_status_checks` entirely**: lets red CI merge. Rejected outright.

**Operator handoff (Coordinator, post-merge):** After this PR merges to `main`, swap the protection contract:

```
gh api --method PATCH \
  repos/martinopedal/FinOps-assessment/branches/main/protection/required_status_checks \
  --raw-field 'contexts[]=required-checks' \
  --field 'strict=true'
```

Until that PATCH lands, this PR itself still requires one final `enforce_admins` toggle-dance to merge  ,  it is the bootstrap cost, identical in shape to the #47/#48 cutover. All subsequent squad PRs become fully async-mergeable: open → squad label → Stage-4 Noor verdict comment → bot approval → all-green CI → `gh pr merge --squash` (no `--admin`, no toggle).

**Forward gotcha (binding on every future contributor):** Every new top-level job added to `.github/workflows/ci.yml` MUST be appended to the `required-checks` job's `needs:` list. Otherwise the summary will report success while the new job runs ungated by branch protection. The §11 Stage-4 reviewer is responsible for catching this on any PR that touches `ci.yml`.

**Related:** issue #47, #51; PRs #48 (auto-approve workflow), #50 (auto-approve inaugural test).

### 2026-05-12  ,  Standing directive: write everything to squad so sessions can break off cleanly

**By:** Martin Opedal (via Coordinator)

**What:** Every coordinator turn that produces durable state (decisions, scope, audit findings, in-flight PR ceremony, open follow-ups) MUST write that state into the squad system (`.squad/` files committed via PR, or GitHub issues) BEFORE the session ends. Local-only scratch (session-state plan.md, SQL todos, chat memory) is insufficient for handoff because it lives only on the active machine and disappears with the session.

**Why this matters:** Sessions end without warning (rate limits, token expiry, network drop, machine sleep, user pivots). The next session  ,  possibly a different agent on a different machine  ,  has no access to local scratch. The squad system (`.squad/decisions.md`, `.squad/identity/now.md`, `.squad/agents/{name}/history.md`, GitHub issues) IS the durable cross-session memory. Anything not written there is lost.

**Operational rules:**
1. **In-flight PR ceremony state** must be captured in either: (a) the PR body checklist, (b) a GitHub issue body if multi-PR, or (c) `.squad/identity/now.md` if single-session.
2. **Open scope decisions** awaiting user input must be filed as a GitHub issue with full context, audit findings, and a numbered list of decisions needed. Bare chat questions are not durable.
3. **Standing directives** (rules of the form "always X" / "never Y" / "from now on Z") must be promoted to `.squad/decisions.md` via the inbox. Capture in chat is not enough.
4. **Audit findings** that block work must be captured in the issue or PR that owns the work, not in chat.
5. **At session end**, Coordinator's final user-visible message must include the GitHub URL(s) (PR or issue) where the durable state lives.

**Trade-offs considered:**
- **Lighter alternative  ,  only write to squad when "important":** rejected. The threshold for "important" drifts; in practice things get lost.
- **Heavier alternative  ,  write every turn to squad:** rejected. Generates noise; not every chat turn produces durable state. The rule is: durable STATE writes to squad, not durable chat.
- **Status quo (this directive's predecessor):** plan.md in session-state + SQL todos + chat memory. Worked when sessions ran end-to-end on one machine, but fails on session breaks.

**Related:** PR #52 (the work that prompted this directive  ,  Coordinator was wrapping #52 ceremony when user reminded), Issue #53 (the pending docs-voice work that triggered the "log everything" reminder), `.github/copilot-instructions.md` Session Protocol Start & End (existing session-bookend rules).

**Scope:** Binding on Squad (Coordinator) on every session start AND every session end. Reviewers must check that any user directive in chat was captured to inbox before approving the wrap PR.

---

## 2026-05-13  ,  Wave: Docs-voice SKILL adopted

### 2026-05-13  ,  Docs-voice scope: emoji + em-dash + AI-language + skill location (issue #53, PR #55)

**By:** Maya (Lead), encoding the four scope decisions Martin set on issue #53 before PR #55 opened.

**Decisions:**

1. **Emoji policy: pragmatic, keep role badges.** Permitted across docs of record: ✅ and ❌ for binary status; squad role badges (🏗️ ⚛️ 🔧 🧪 📋 🔄) because they are functional UI in routing tables and rosters; capability traffic-lights (🟢 🟡 🔴) only inside `.squad/team.md`, `.squad/routing.md`, and the capability columns they feed. Strip every other emoji.

2. **Em-dash policy: full sweep, except historical logs.** Remove every em-dash and en-dash from docs of record. Replace with a comma, a period, or "and" per the news-fetcher rule. Skip `.squad/orchestration-log/` and `.squad/log/` because rewriting historical artifacts rewrites history.

3. **AI-language scope: full news-fetcher blacklist.** Apply the full blacklist (leverage, unlock, comprehensive, robust, seamless, holistic, cutting-edge, journey, delve, empower, streamline, furthermore, moreover, additionally, on the other hand, in conclusion, in today's world, it is worth noting, and the rest of the list inside the SKILL). The four hits found during audit were a starting point, not the whole scope. Replace abstract verbs and vague qualifiers with concrete nouns and specific verbs.

4. **Voice profile location: skill only.** The anonymized voice profile lives only at `.squad/skills/docs-voice/SKILL.md`. No duplicate at `docs/voice/`, no copy in `docs/style.md`. The SKILL is the canonical source; agents auto-read it through the normal skill-loading path.

**Scope of "docs of record":** all `.md` files under `.github/`, `docs/`, `.squad/` (except `orchestration-log/` and `log/` subfolders), the project README and CHANGELOG, AND the catalogue YAML `summary` and `recommendation_template` fields under `data/catalog/` and `data/rules/`. Those YAML prose fields render verbatim into `docs/rules.md` (via `scripts/generate_docs.py`) and into every JSON / HTML / CSV / PDF report, so they ARE docs of record.

**Operational consequence (from PR #55 follow-up fix):** When a `summary` or `recommendation_template` in `data/rules/{surface}.yaml` changes, the docs-voice SKILL applies. Re-run `python scripts/generate_docs.py` to regenerate `docs/rules.md` and `examples/demo-report.{json,html,csv}`, and commit those alongside the YAML in the same PR. Forgetting this trips both the docs-freshness gate (`tests/test_generate_docs.py::test_check_mode_passes_for_committed_artifacts`) and the SKILL contract. PR #55 caught one such miss (`additionally-assigned` in `M365.DUPLICATE_BUNDLE`) on the post-merge sweep at commit `f54177a`; the fix was to edit the YAML, regenerate, and re-push.

**Trade-offs considered:**

- **Voice page in `docs/`** vs skill: rejected. Docs of record describe the product. The voice rule belongs to the agent system that produces the docs, not the docs themselves.
- **Soft em-dash policy** (allow in long-form prose): rejected. Operators of an enterprise FinOps tool read in scan-mode; a comma reads cleanly there and an em-dash is the strongest single-character "this was generated" signal in our corpus.
- **Emoji-zero policy:** rejected because role badges and ✅/❌ are functional UI in routing tables and status surfaces, not decoration.
- **Strip catalogue YAML prose from scope:** rejected. The fields render unchanged into reports; exempting them would mean the docs-voice contract dies at the first regenerate.

**Related:** issue #53, PR #55, `.squad/skills/docs-voice/SKILL.md`, the `M365.DUPLICATE_BUNDLE` follow-up fix in commit `f54177a`.

**Scope:** Binding on every PR that touches docs of record OR catalogue YAML prose fields. Stage-4 reviewer (Noor) checks both.

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- The drop-box pattern: agents write to `.squad/decisions/inbox/{name}-{slug}.md`; Scribe merges into this file at session end and clears the inbox (which is gitignored)
