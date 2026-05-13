# Squad Decisions

## Active Decisions


### 2026-05-13 — Stage-3 plan for #61 playbook / ticket reporter (Maya, Opus 4.7)

## §11 Stage-3 Plan — Playbook / ticket reporter (#61)

> **Author:** Maya (Lead / FinOps PM) — model: Opus 4.7
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #61 (epic #57 child) — release `release:v0.5.0`, priority `priority:p1`
> **Branch (planned):** `squad/61-playbook-reporter`
> **Implementer:** Diego (reporter module owner — same hands as #58) + Yuki (tests, docs, golden-fixture pinning)
> **Foundation block under:** #16 (FinOps roadmap) — prerequisite for #63 (remediation-PR drafter)

This plan turns the locked stage-2 consensus
(`61-consensus.md`) into a file-level checklist precise enough that
the implementer makes zero architectural decisions. The four
divergences (D1–D4), six convergent amendments, five Noor
predictions, and five research OQs are **closed below** — if anything
in the implementation diverges from the lockings in §1, treat the
locking as the source of truth and flag the contradiction back to me
before merging.

The exporter pattern, byte-contract discipline, manifest-sidecar
shape, and golden-fixture pinning are inherited verbatim from #58.
This is a deliberate copy of the architectural posture that worked;
no new patterns are coined here.

---

### Inputs (locked)

- `C:\Users\martinopedal\.copilot\session-state\00cb0f92-01d8-49ec-b313-1616120d0178\files\61-consensus.md` — **the locked stage-2 consensus.** Verbatim source for the six convergent amendments, the four divergence points, and the eight-item stage-3 prep checklist. Do not revisit.
- Stage-1 research brief (`research-61-playbook` Haiku explore agent history) — sections A (schema patterns), B (existing reporter precedent), C (Jinja2 availability), D (10 risks / 5 OQs), E (test patterns), F (file-level skeleton), G (cross-platform / CI). Confidence A/B/C/D/E/G HIGH, F MEDIUM.
- Stage-2 rubberduck Sonnet 4.5 (`rubberduck-61-sonnet`) — APPROVE WITH AMENDMENTS, 8-item checklist, 5 Noor predictions.
- Stage-2 rubberduck GPT-5.4 (`rubberduck-61-gpt`) — APPROVE WITH AMENDMENTS, 5 blockers, "neutral row + adapter hints" model, BLOCKING PII finding (D2).
- `C:\git\FinOps-assessment\.squad\decisions.md` — Diego's #58 entry (FOCUS-aligned exporter): the format mirror, golden-fixture pinning skill, generative test pattern, and "single module per output format" convention all carry over.
- `C:\git\FinOps-assessment\src\finops_assess\reporters\focus_aligned.py` — structural template for `playbook_reporter.py`.
- `C:\git\FinOps-assessment\src\finops_assess\reporters\_determinism.py` — reused for `generated_at_iso()` and `SOURCE_DATE_EPOCH` honouring.
- `C:\git\FinOps-assessment\src\finops_assess\schemas\focus_aligned_manifest.schema.json` — structural template for `playbook_manifest.schema.json`.

### Stage-3 corrections to the consensus

The consensus (D2, GPT's BLOCKING finding) flagged the per-run salt
behavior in `engine.py:70-75,151`. **Verified against the repo at
commit `39b3230`:**

- `RuleContext.redact()` (`engine.py:70-75`) hashes the principal as `sha256(f"{salt}:{principal}")` and returns the first 16 hex chars prefixed `sha256:`.
- `run_rules()` (`engine.py:137,151`) accepts an optional `salt: str | None` parameter; when `None` (the CLI default), the salt is generated per invocation via `secrets.token_hex(16)`.
- `cli.py` does **not** currently flow a stable salt; every CLI run gets a fresh per-run salt.

**Conclusion:** GPT's claim is **correct**. With the default
`--pii-redaction` posture (on) and no operator-supplied stable salt,
`finding.principal` for M365 / GitHub / ADO findings IS unstable
across runs. A naive `sha256(rule_id || principal || evidence)`
ticket key would generate a brand-new ticket every run — fatal for a
ticketing reporter framed as a foundation block under #16/#63.

**Locked architectural response (Option B from the consensus,
"honest stability declaration" variant):**

- The playbook reporter **does not introduce a stable principal salt** in v0.5.0 (that is a separate engine-level architectural change, deferred to its own follow-up issue — placeholder `#73`, to be filed by Maya at PR-open time).
- Instead, the reporter emits two distinct identifiers per row, derived from whatever the engine produced:
  - `ticket_key` — the dedup key used by downstream ticketing systems. Computed as `sha256(json_envelope([rule_id, principal_as_emitted, evidence_key_version]))` truncated to 32 hex chars. **Stability is per-surface and explicitly declared in the manifest**: `"stable"` for Azure (cleartext resource IDs), `"per_run"` for M365 / GitHub / ADO when `pii_redaction=true` with no stable salt.
  - `finding_revision` — `sha256(normalized_evidence_json)` truncated to 16 hex chars. Always changes when evidence shifts; allows operators to detect when an existing ticket needs an update vs. when nothing has changed.
- The manifest carries an explicit `pii_handling` block with `mode`, `ticket_key_stability_by_surface`, and a `known_limitation` string so downstream consumers cannot accidentally treat a `per_run` key as stable. The CLI emits a stderr warning when redaction is on AND non-Azure findings are present AND no stable salt was supplied.
- Mirrors the focus-aligned posture in `.squad/decisions.md:537` ("Azure-only … M365/GitHub/ADO ship in v0.6.0 once the stable-principal-salt feature lands"), but for #61 we **do not filter non-Azure findings out** — the playbook is multi-surface from day one because operators want a single JSONL stream. We just **declare honestly** what is stable and what is not.

This is the only correction to the consensus document. D1, D3, D4
and the six convergent amendments are accepted verbatim.

---

## Section 1 — Decisions locked (close all OQs and divergences)

### Research-brief OQs

| OQ | Question | Locked decision | One-line rationale |
|----|----------|-----------------|-------------------|
| **OQ-1** | Row cardinality — one row per finding, or one row per (rule, principal) aggregated? | **One row per finding.** No aggregation. | Aggregation is a rule-design concern, not a reporter concern; the reporter is a faithful projection of the engine output. |
| **OQ-2** | How is a row's identity defined when the same rule fires N times for the same principal with different evidence? | `ticket_key = sha256(json_envelope([rule_id, principal, evidence_key_version]))`. Same `(rule, principal)` collisions are disambiguated by `finding_revision = sha256(normalized_evidence)` when stability allows; otherwise treated as separate rows whose downstream dedup is the operator's responsibility. | Mirrors `advisory_finding_key` pattern in `focus_aligned.py:138-158` so consumers can join playbook to FOCUS-aligned export on `(rule_id, principal)` when stability matches. |
| **OQ-3** | Should operators be able to overlay custom templates from `~/.finops-assess/playbooks/`? | **No.** Repo-controlled templates only via `importlib.resources`. **Defer to v0.6.0** (placeholder issue `#74` to be filed by Maya at PR-open time). | Sandbox-escape risk + supply-chain risk; v0.5.0 ships only what is in the wheel. Sonnet's Noor prediction #2. |
| **OQ-4** | Should the row carry the full `evidence` dict, or just an `evidence_ref`? | **`evidence_ref` only**, plus `template_render_inputs[]` listing the evidence keys the template touched. | Keeps row size bounded; gives operators a debuggable trail without bloating the JSONL or leaking unredacted evidence into ticket bodies. |
| **OQ-5** | Missing-template policy — fail-fast, silently skip, or generic fallback? | **Fail-fast.** Raise `PlaybookTemplateNotFoundError(rule_id, expected_path)`. No silent skip, no generic fallback. | Mirrors mypy / ruff posture: a missing template is a packaging defect, not a runtime warning. Sonnet's Noor prediction #4. |

### Divergence points (D1–D4)

| D | Topic | Sonnet position | GPT position | **Locked decision** | Rationale |
|---|-------|-----------------|--------------|---------------------|-----------|
| **D1** | Payload model | Issue's row shape + `playbook_schema_version` | Neutral row + `adapter_hints.{servicenow,jira,github}` | **Both, additively.** Core row = Sonnet's shape. Optional nested `adapter_hints` object derived from `severity` + a new `rules.yaml` field `adapter_class` (defaults to `"generic"`). Ship in row v1; do not defer. | GPT is right that "vendor-ready superset" is misleading — adapters always reinterpret. The hints are a free leg-up: cheap to compute, cheap to ignore. Schema versioning means we can extend the hints object additively in v0.6.0 without a v1 break. |
| **D2** | PII stable-ID | Not addressed | BLOCKING — per-run salt makes `finding_id` non-stable | **Option B-honest** (see "Stage-3 corrections" above): emit `ticket_key` + `finding_revision`, declare per-surface stability in manifest, emit a CLI warning when redaction is on with non-Azure findings, defer the stable-salt engine change to follow-up issue `#73`. The warning is emitted from `cli.py` **before** `write_playbook_export` is invoked (so an operator piping stderr to `>/dev/null` after the export still sees it), is suppressed by `--skip-warnings`, and is **also** suppressed when the input report contains zero non-Azure findings (`m365_count == github_count == ado_count == 0`). The same condition that triggers the stderr warning ALSO populates `pii_handling.known_limitation` in the manifest as the durable, machine-readable copy. | Option A (per-run-only) breaks #16/#63 framing. Option C (introduce stable-salt mode) is a cross-cutting engine change that does not belong in a reporter PR. Option B ships honest semantics today and unblocks the stable-salt issue without coupling. |
| **D3** | Jinja2 hardening | Pre-compile templates at startup | Configure `StrictUndefined` | **Both.** A single helper `_load_playbook_environment()` builds the `Environment` with `undefined=StrictUndefined`, autoescape disabled (templates produce JSON-string fragments, not HTML), `keep_trailing_newline=False`, and pre-compiles every templated rule's `.j2` source on construction. | Complementary, not exclusive. Pre-compile catches syntax errors at export start (before any rows render); StrictUndefined catches missing-variable errors at render time. |
| **D4** | Evidence in row | `evidence_ref` only | Defers to Maya | **`evidence_ref` only**, plus `template_render_inputs: list[str]` captured by **post-render access tracking** (NOT by a Jinja2 `finalize` hook, which is wrong under `StrictUndefined` because `finalize` only fires on `Undefined` access — i.e. never under StrictUndefined except on crash). The mechanism: wrap the per-row `evidence` dict in a small `dict` subclass `_AccessTrackingEvidence` that overrides `__getitem__`, `get`, `__contains__`, `__iter__`, `keys`, `values`, and `items` to record every key access into a `set`; sort the recorded set after `template.render(...)` returns; emit as `template_render_inputs`. Only the `evidence` context key is wrapped (the other context keys — `rule`, `finding`, `principal`, `severity` — do not need tracking). The `evidence_ref` object itself carries only `report_path` (the duplicate `finding_revision` field is dropped — it is already a top-level row field). | Sonnet's call. The `template_render_inputs` list gives operators "what fed this ticket?" without re-emitting the full evidence payload. Post-render diffing was rejected: deep-equality of two evidence dicts per row is O(N×evidence-size) and noisier than tracking actual key accesses. |

### Pre-emption of Sonnet's 5 Noor predictions

| # | Prediction | Pre-emption in this plan |
|---|------------|--------------------------|
| **N1** | No schema versioning → breaks #63 drafter | `playbook_schema_version: "0.1"` declared in manifest; `Rule.evidence_key_version` (existing field at `models.py:56`) mixed into `ticket_key` envelope so a rule's evidence-shape bump bumps the ticket key. |
| **N2** | Runtime overlay sandbox escape | `importlib.resources` only; no filesystem sniffing of `~/.finops-assess/`; helper `_load_playbook_environment()` cannot accept a non-packaged loader. Documented as deferred to v0.6.0 in `docs/playbook-reporter.md`. |
| **N3** | No atomic write → partial JSONL on crash | `tempfile.mkstemp(dir=output.parent, prefix=".playbook-", suffix=".jsonl.tmp")` + `os.fsync` + `os.replace(tmp, output)`. The JSONL atomic write is followed by a manifest atomic write that is the canonical **readiness marker** for downstream consumers; the manifest also self-attests the JSONL via `output_artifacts.jsonl_sha256` + `output_artifacts.jsonl_byte_count`. A pre-flight check refuses to overwrite an orphaned JSONL (no sibling manifest) without `--cleanup-orphans`. Code + reader contract in §5.1. |
| **N4** | Missing template silent skip vs crash | Custom exception `PlaybookTemplateNotFoundError(rule_id, expected_path)` raised at export start (during pre-compile), not during row render. Tested by `test_missing_template_fails_fast`. |
| **N5** | Windows CRLF breaks downstream parsers | Files opened in **binary** mode (`"wb"`) with manual `b"\n"` between rows and trailing `b"\n"` on the final row, so no platform layer can rewrite line endings. `.gitattributes` `text eol=lf` for `examples/playbook.jsonl`, `examples/playbook.jsonl.manifest.json`, the two golden fixtures under `tests/fixtures/playbook/`, **AND `src/finops_assess/data/playbooks/**/*.j2`** (the 23 packaged Jinja2 source templates — without this line, a Windows clone with `core.autocrlf=true` rewrites the templates to CRLF, Jinja2 emits `\r` in rendered strings, `json.dumps` escapes them as `\\r`, and the byte-identical golden test fails on `windows-latest` only — same regression class Yuki patched in #58 commit `3e18275`). Yuki's #58 hardening pattern (see `.squad/skills/focus-aligned-golden-fixtures/SKILL.md`); regression net is test #16 in §6. |

---

## Section 2 — File-level changes

All paths are absolute Windows-style. LoC estimates include
docstrings + blank lines, exclude tests. Total: ~25 files,
~500 LoC of new product code (matches Sonnet's estimate).

| # | Path | Verb | Purpose | LoC |
|---|------|------|---------|----:|
| 1 | `C:\git\FinOps-assessment\src\finops_assess\reporters\playbook_reporter.py` | NEW | The reporter module: row projection, manifest assembly, atomic deterministic write, `PlaybookTemplateNotFoundError`. | ~320 |
| 2 | `C:\git\FinOps-assessment\src\finops_assess\reporters\__init__.py` | MODIFIED | Re-export `write_playbook_export`, `build_playbook_manifest`, `PlaybookTemplateNotFoundError`. Add to `__all__`. | +6 |
| 3 | `C:\git\FinOps-assessment\src\finops_assess\schemas\playbook_row.schema.json` | NEW | JSON Schema (draft 2020-12) for a single playbook row. Bundled as package-data; consumed by row-validator test. | ~140 (JSON) |
| 4 | `C:\git\FinOps-assessment\src\finops_assess\schemas\playbook_manifest.schema.json` | NEW | JSON Schema (draft 2020-12) for the sidecar manifest. Mirrors `focus_aligned_manifest.schema.json` shape. | ~150 (JSON) |
| 5 | `C:\git\FinOps-assessment\src\finops_assess\data\playbooks\__init__.py` | NEW | Empty marker so `importlib.resources.files("finops_assess.data.playbooks")` resolves at runtime. | 1 |
| 6 | `C:\git\FinOps-assessment\src\finops_assess\data\playbooks\m365\*.j2` (8 files) | NEW | One Jinja2 template per M365 rule: `M365.UNUSED_LICENSE_30D.j2`, `M365.OVER_LICENSED_VS_PERSONA.j2`, `M365.DUPLICATE_BUNDLE.j2`, `M365.DISABLED_USER_LICENSED.j2`, `M365.SHARED_MAILBOX_LICENSED.j2`, `M365.GUEST_PREMIUM_LICENSED.j2`, `M365.COPILOT_INACTIVE_60D.j2`, `M365.E5_FEATURES_UNUSED.j2`. | ~25 each |
| 7 | `C:\git\FinOps-assessment\src\finops_assess\data\playbooks\azure\*.j2` (7 files) | NEW | One per Azure rule: `AZ.IDLE_VM_14D.j2`, `AZ.UNATTACHED_DISK.j2`, `AZ.PUBLIC_IP_UNATTACHED.j2`, `AZ.OVERSIZED_VM.j2`, `AZ.RESERVATION_UNDERUTILIZED.j2`, `AZ.LOG_ANALYTICS_OVERINGEST.j2`, `AZ.DEV_TEST_SUB_MISMATCH.j2`. | ~25 each |
| 8 | `C:\git\FinOps-assessment\src\finops_assess\data\playbooks\github\*.j2` (4 files) | NEW | One per GitHub rule: `GH.INACTIVE_SEAT_90D.j2`, `GH.COPILOT_INACTIVE_30D.j2`, `GH.GHAS_OVER_PROVISIONED.j2`, `GH.RUNNER_TIER_MISMATCH.j2`. | ~25 each |
| 9 | `C:\git\FinOps-assessment\src\finops_assess\data\playbooks\ado\*.j2` (4 files) | NEW | One per ADO rule: `ADO.INACTIVE_BASIC_90D.j2`, `ADO.STAKEHOLDER_ELIGIBLE.j2`, `ADO.PARALLEL_JOBS_OVER_PROVISIONED.j2`, `ADO.TEST_PLANS_UNUSED.j2`. | ~25 each |
| 10 | `C:\git\FinOps-assessment\src\finops_assess\data\rules\*.yaml` (m365, azure, github, ado) | MODIFIED | Add optional `adapter_class` field per rule (default inferred at load time, see D1 reconciliation). Permissible values: `"generic"`, `"identity_lifecycle"`, `"resource_rightsizing"`, `"runner_capacity"`, `"licensing_rightsizing"`. | +1 line per rule, ~23 rules |
| 11 | `C:\git\FinOps-assessment\src\finops_assess\models.py` | MODIFIED | Add `adapter_class: Literal[...] = "generic"` to `Rule` model with `extra="forbid"` discipline. Mirror addition to the YAML loader's allowed-keys set. | +6 |
| 12 | `C:\git\FinOps-assessment\src\finops_assess\cli.py` | MODIFIED | Add `@export.command("playbook")` mirroring the `focus-aligned` subcommand. Help text, `--input`, `--output`, optional `--skip-warnings` flag (off by default). | +75 |
| 13 | `C:\git\FinOps-assessment\pyproject.toml` | MODIFIED | (a) Promote `Jinja2>=3.1` from optional `[pdf]` extra to a runtime dep (already required by HTML + PDF reporters; promoting it makes the runtime dep tree honest). Confirm via `import jinja2` at module top of `playbook_reporter.py` rather than lazy-loading. (b) Extend `[tool.setuptools.package-data].finops_assess` to include `"data/playbooks/**/*.j2"`. (c) Confirm `"schemas/*.json"` already covers the two new schema files (added in #58). | +3, ~0 net |
| 14 | `C:\git\FinOps-assessment\src\finops_assess\rules.py` | MODIFIED | Allow `adapter_class` key in the YAML schema; default to `"generic"` when absent so existing operator overrides continue to load. | +4 |
| 15 | `C:\git\FinOps-assessment\tests\test_playbook_reporter.py` | NEW | The 12 enumerated tests in §6, including the parametrized template-coverage matrix. | ~520 |
| 16 | `C:\git\FinOps-assessment\tests\fixtures\playbook\input-multi-surface.json` | NEW | Hand-authored canonical findings JSON: 1 Azure idle-VM + 1 M365 unused-license + 1 GitHub inactive-seat + 1 ADO inactive-basic. Drives the multi-surface stability declaration test. | ~140 (JSON) |
| 17 | `C:\git\FinOps-assessment\tests\fixtures\playbook\input-empty.json` | NEW | `{"findings": []}` — drives empty-export, manifest-still-written test. | ~25 (JSON) |
| 18 | `C:\git\FinOps-assessment\tests\fixtures\playbook\input-azure-only.json` | NEW | 2 Azure findings, distinct rule IDs, distinct evidence shapes. Drives the golden-byte test (only Azure rows have `stable` ticket keys, so this is the canonical reproducible input). | ~80 (JSON) |
| 19 | `C:\git\FinOps-assessment\tests\fixtures\playbook\golden-azure.jsonl` | NEW | Byte-identical expected JSONL for `input-azure-only.json` rendered with `SOURCE_DATE_EPOCH=0`. LF line endings, pinned via `.gitattributes`. | 2 lines |
| 20 | `C:\git\FinOps-assessment\tests\fixtures\playbook\golden-azure.jsonl.manifest.json` | NEW | Byte-identical expected manifest for the same input. | ~50 (JSON) |
| 21 | `C:\git\FinOps-assessment\tests\fixtures\playbook\golden-cli-help.txt` | NEW | Snapshot of `finops-assess export playbook --help` output. | ~14 |
| 22 | `C:\git\FinOps-assessment\.gitattributes` | MODIFIED | Append `text eol=lf` lines for: `examples/playbook.jsonl`, `examples/playbook.jsonl.manifest.json`, `tests/fixtures/playbook/golden-azure.jsonl`, `tests/fixtures/playbook/golden-azure.jsonl.manifest.json`, **AND `src/finops_assess/data/playbooks/**/*.j2`** (the 23 packaged Jinja2 source templates — see N5 in §1 for the regression mechanism this prevents on `windows-latest`). **(Yuki's hardening lesson from #58 commit `3e18275` — every byte-compared fixture AND every render INPUT that feeds a byte-compared fixture needs its own line.)** | +5 |
| 23 | `C:\git\FinOps-assessment\scripts\generate_docs.py` | MODIFIED | (a) Extend `regenerate_examples` to render `examples\playbook.jsonl` + `examples\playbook.jsonl.manifest.json` from the bundled demo report. (b) Extend the `--check` diff loop to cover the two new artefacts. (c) Export `PLAYBOOK_BASENAME = "playbook"` constant. | +35 |
| 24 | `C:\git\FinOps-assessment\examples\playbook.jsonl` | NEW (generated, committed) | Generated artefact, byte-pinned LF via `.gitattributes`. | n/a |
| 25 | `C:\git\FinOps-assessment\examples\playbook.jsonl.manifest.json` | NEW (generated, committed) | Generated artefact, byte-pinned LF via `.gitattributes`. | n/a |
| 26 | `C:\git\FinOps-assessment\docs\playbook-reporter.md` | NEW | Operator-facing user doc. Warning-banner heavy: per-surface stability table, no-API-push posture, fail-fast template policy, schema-versioning contract, `--skip-warnings` opt-out documented as expert-only. | ~190 |
| 27 | `C:\git\FinOps-assessment\README.md` | MODIFIED | One-line entry to the reports section linking to `docs/playbook-reporter.md`; reference the new CLI subcommand. | +6 |
| 28 | `C:\git\FinOps-assessment\docs\user-guide.md` | MODIFIED | New `## Exporting findings to a ticketing playbook` section after the FOCUS-aligned section; embed the help-text block; link to `docs/playbook-reporter.md`. | +35 |
| 29 | `C:\git\FinOps-assessment\docs\schema.md` | MODIFIED | Add `## Playbook reporter (v0.5.0)` subsection after the FOCUS-aligned manifest subsection: per-row schema fields + manifest fields + JSON Schema pointer. Make explicit that the playbook is a sidecar, NOT part of the canonical report envelope. | +45 |
| 30 | `C:\git\FinOps-assessment\docs\plan.md` §6 | MODIFIED | Add a `### Playbook / ticket reporter` subsection after `### FOCUS-aligned advisory export` (lines 230-235). Wording mirrors the FOCUS-aligned cross-reference — point at `docs/playbook-reporter.md` and at `finops-assess export playbook`. | +6 |
| 31 | `C:\git\FinOps-assessment\CHANGELOG.md` | MODIFIED | New entry under `## v0.5.0`: "Added: `finops-assess export playbook` — per-finding NDJSON ticketing-system payloads with sidecar manifest (foundation block under #16/#63). Templates packaged for all current rules. Multi-surface; per-surface ticket-key stability declared in manifest. See `docs/playbook-reporter.md`. (#61, epic #57)" | +5 |
| 32 | `C:\git\FinOps-assessment\.github\workflows\ci.yml` | NO CHANGE | The new export subcommand reuses existing `lint-and-test` and `catalog-validation` jobs (which run pytest + `finops-assess validate`). No new top-level CI job is introduced, so the `required-checks` summary at `ci.yml:68-79` does not need extension. **If a test in #15 turns out to need a new top-level job, the `needs:` list MUST be amended in the same PR (per copilot-instructions §11 / issue #51).** |
| 33 | `C:\git\FinOps-assessment\data\` | NO CHANGE | The `adapter_class` field is added to `src/finops_assess/data/rules/*.yaml` (the packaged copy that runs at install time). The top-level `data/` mirror is updated by an existing script — confirm `tests/test_packaged_data.py` covers parity if it does. |

---

## Section 3 — Schema contract

### 3.1 Per-row JSON Schema (`playbook_row.schema.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/martinopedal/FinOps-assessment/blob/main/src/finops_assess/schemas/playbook_row.schema.json",
  "title": "Playbook row (v0.1)",
  "description": "One JSONL row per finding. Schema_version '0.1' is additive-only: new top-level keys may be added in future releases without a version bump; consumers MUST ignore unknown keys. A breaking change increments playbook_schema_version on the sibling manifest to '0.2'.",
  "type": "object",
  "required": [
    "playbook_schema_version",
    "rule_id",
    "ticket_key",
    "finding_revision",
    "surface",
    "severity",
    "title",
    "description",
    "remediation_steps",
    "verification_checklist",
    "evidence_ref",
    "template_render_inputs"
  ],
  "additionalProperties": false,
  "properties": {
    "playbook_schema_version": { "type": "string", "const": "0.1" },
    "rule_id": { "type": "string" },
    "ticket_key": { "type": "string", "pattern": "^[0-9a-f]{32}$", "description": "sha256(json_envelope([rule_id, principal, evidence_key_version])), 32 hex chars. Stability declared per-surface in sibling manifest." },
    "finding_revision": { "type": "string", "pattern": "^[0-9a-f]{16}$", "description": "sha256(normalized_evidence_json), 16 hex chars. Always changes when evidence shifts." },
    "surface": { "type": "string", "enum": ["m365", "azure", "github", "ado"] },
    "severity": { "type": "string", "enum": ["high", "medium", "low", "info"] },
    "title": { "type": "string", "minLength": 1, "maxLength": 200 },
    "description": { "type": "string", "minLength": 1 },
    "remediation_steps": { "type": "array", "items": { "type": "string", "minLength": 1 }, "minItems": 1 },
    "verification_checklist": { "type": "array", "items": { "type": "string", "minLength": 1 }, "minItems": 1 },
    "evidence_ref": {
      "type": "object",
      "required": ["report_path"],
      "additionalProperties": false,
      "properties": {
        "report_path": { "type": ["string", "null"], "description": "Echoes report.run.input (already path-redacted upstream when pii_redaction=true). Sole field in evidence_ref; the canonical row-identity hash lives in the top-level finding_revision field." }
      }
    },
    "template_render_inputs": { "type": "array", "items": { "type": "string" }, "description": "Evidence keys the rendering template referenced. Empty array means the template referenced no evidence keys." },
    "assignee_hint": { "type": ["string", "null"], "description": "Free-form identifier (e.g. 'm365-admin', 'azure-platform-team') derived from surface + adapter_class. Operators MAY rewrite." },
    "adapter_hints": {
      "type": "object",
      "additionalProperties": true,
      "description": "Per-vendor guidance derived from rule.adapter_class. v0.1 keys: servicenow, jira, github. Consumers MUST ignore unknown sub-keys.",
      "properties": {
        "servicenow": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "table": { "type": "string", "description": "Suggested ServiceNow table. Examples: 'incident', 'sc_task', 'change_request'." },
            "category": { "type": "string" },
            "urgency": { "type": "integer", "minimum": 1, "maximum": 4 }
          }
        },
        "jira": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "issuetype": { "type": "string", "description": "Suggested Jira issue type. Examples: 'Task', 'Story', 'Bug'." },
            "labels": { "type": "array", "items": { "type": "string" } },
            "priority": { "type": "string", "enum": ["Highest", "High", "Medium", "Low", "Lowest"] }
          }
        },
        "github": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "labels": { "type": "array", "items": { "type": "string" } },
            "milestone": { "type": ["string", "null"] }
          }
        }
      }
    }
  }
}
```

**Field-order contract:** the writer emits keys in **the order
declared in `required` + the optional list above**. `json.dumps`
is invoked with `sort_keys=False` and an explicit `OrderedDict`-
equivalent input (Python 3.7+ dict insertion order is part of the
spec) so the JSONL byte stream is deterministic.

### 3.2 Manifest JSON Schema (`playbook_manifest.schema.json`)

Mirrors `focus_aligned_manifest.schema.json` with playbook-specific
fields. Required top-level keys, in declared order:

```
playbook_schema_version  : const "0.1"
tool                     : { name: const "finops-assess", version: SemVer }
generated_at             : ISO-8601 (honours SOURCE_DATE_EPOCH)
source_report            : { path, schema_version, pii_redaction }
dataset_type             : const "playbook"
row_count                : int >= 0
template_versions        : array of { rule_id, surface, template_path, sha256 }
output_artifacts         : { jsonl_path, jsonl_sha256, jsonl_byte_count }
pii_handling             : { mode, ticket_key_stability_by_surface, known_limitation }
schema_contract_url      : URL pointing at playbook_row.schema.json on main
```

`output_artifacts` shape (binding — the manifest's self-attestation
of the JSONL it accompanies; together with the manifest-as-readiness
contract in §5.1, this lets consumers detect a stale or truncated
JSONL):

```json
{
  "jsonl_path": "playbook.jsonl",
  "jsonl_sha256": "<64 hex chars — sha256 of the JSONL bytes the manifest accompanies>",
  "jsonl_byte_count": 12345
}
```

`pii_handling` shape (binding):

```json
{
  "mode": "redacted_per_run | redacted_stable | cleartext",
  "ticket_key_stability_by_surface": {
    "m365":   "stable | per_run",
    "azure":  "stable | per_run",
    "github": "stable | per_run",
    "ado":    "stable | per_run"
  },
  "known_limitation": "string | null — populated (non-null) whenever ANY surface in ticket_key_stability_by_surface is per_run; the string MUST reference issue #73 and warn that re-runs will produce duplicate tickets for non-Azure surfaces. Test #7 asserts the non-null contract."
}
```

**Algorithm-vs-input clarification (NIT-15):** the reporter computes
`ticket_key` with a single uniform algorithm (`sha256(json_envelope([
rule_id, principal, evidence_key_version]))[:32]`) for all four
surfaces. The per-surface `stability` declaration is a statement about
the **input quality** to that algorithm (Azure principals are
cleartext ARM IDs and survive across runs; M365/GitHub/ADO principals
are per-run salted hashes from `engine.RuleContext.redact()` and do
NOT survive across runs), NOT about the algorithm itself. Future
consumers reading the row payload alone MUST NOT infer per-surface
algorithmic divergence; the reporter has none.

`additionalProperties: true` at every level so v0.6.0 can extend
without a manifest version bump (same forward-compat posture as
focus-aligned).

---

## Section 3.3 — `adapter_class` per-rule mapping + `adapter_hints` derivation (binding)

Closes Noor amendments A5 + A6. The implementer picks **zero**
architectural values from this section; the tables below are binding.

### 3.3.1 Per-rule `adapter_class` assignment (23 rules)

Added as `adapter_class:` on each rule entry in
`src/finops_assess/data/rules/{m365,azure,github,ado}.yaml` (file #10
in §2). Permissible values: `generic`, `identity_lifecycle`,
`resource_rightsizing`, `runner_capacity`, `licensing_rightsizing`.

| Surface | Rule ID | `adapter_class` | Justification |
|---------|---------|-----------------|---------------|
| m365 | `M365.UNUSED_LICENSE_30D` | `licensing_rightsizing` | Action: drop a paid SKU; trigger: zero usage for 30 days. |
| m365 | `M365.OVER_LICENSED_VS_PERSONA` | `licensing_rightsizing` | Action: downgrade SKU to persona's recommended tier. |
| m365 | `M365.DUPLICATE_BUNDLE` | `licensing_rightsizing` | Action: collapse overlapping bundles to one. |
| m365 | `M365.DISABLED_USER_LICENSED` | `identity_lifecycle` | Trigger: disabled account; action sequence is identity-lifecycle (verify offboarding) before license drop. |
| m365 | `M365.SHARED_MAILBOX_LICENSED` | `licensing_rightsizing` | Action: convert to unlicensed shared mailbox. |
| m365 | `M365.GUEST_PREMIUM_LICENSED` | `identity_lifecycle` | Trigger: guest identity class; license is the symptom, not the cause. |
| m365 | `M365.COPILOT_INACTIVE_60D` | `licensing_rightsizing` | Action: drop Copilot add-on. |
| m365 | `M365.E5_FEATURES_UNUSED` | `licensing_rightsizing` | Action: downgrade E5 → E3. |
| azure | `AZ.IDLE_VM_14D` | `resource_rightsizing` | Action: stop / right-size the VM. |
| azure | `AZ.UNATTACHED_DISK` | `resource_rightsizing` | Action: delete or re-attach the disk. |
| azure | `AZ.PUBLIC_IP_UNATTACHED` | `resource_rightsizing` | Action: release the IP. |
| azure | `AZ.OVERSIZED_VM` | `resource_rightsizing` | Action: change VM size. |
| azure | `AZ.RESERVATION_UNDERUTILIZED` | `resource_rightsizing` | Action: re-scope or exchange the reservation. |
| azure | `AZ.LOG_ANALYTICS_OVERINGEST` | `resource_rightsizing` | Action: throttle ingestion / move to basic logs. |
| azure | `AZ.DEV_TEST_SUB_MISMATCH` | `generic` | Subscription-shape governance; not a per-resource size or licensing call. |
| github | `GH.INACTIVE_SEAT_90D` | `identity_lifecycle` | Trigger: user inactivity; action sequence is offboard-or-justify before seat removal. |
| github | `GH.COPILOT_INACTIVE_30D` | `licensing_rightsizing` | Action: drop GHCB seat. |
| github | `GH.GHAS_OVER_PROVISIONED` | `licensing_rightsizing` | Action: downgrade GHAS coverage. |
| github | `GH.RUNNER_TIER_MISMATCH` | `runner_capacity` | Action: change hosted-runner tier. |
| ado | `ADO.INACTIVE_BASIC_90D` | `identity_lifecycle` | Trigger: user inactivity; same shape as `GH.INACTIVE_SEAT_90D`. |
| ado | `ADO.STAKEHOLDER_ELIGIBLE` | `licensing_rightsizing` | Action: downgrade Basic → Stakeholder license tier. |
| ado | `ADO.PARALLEL_JOBS_OVER_PROVISIONED` | `runner_capacity` | Action: reduce parallel job count. |
| ado | `ADO.TEST_PLANS_UNUSED` | `licensing_rightsizing` | Action: drop the Test Plans extension. |

### 3.3.2 `adapter_hints` derivation (severity × `adapter_class`)

Two orthogonal contributions, **unioned per row**:

**Contribution A — severity → urgency / priority** (universal across `adapter_class`):

| `severity` | `servicenow.urgency` | `jira.priority` | `github.labels` adds |
|------------|---------------------:|-----------------|----------------------|
| `high`   | 2 | `High`    | `priority:high` |
| `medium` | 3 | `Medium`  | `priority:medium` |
| `low`    | 4 | `Low`     | `priority:low` |
| `info`   | 4 | `Lowest`  | `priority:info` |

**Contribution B — `adapter_class` → table / category / labels** (universal across severity):

| `adapter_class` | `servicenow.table` | `servicenow.category` | `jira.issuetype` | `jira.labels` adds | `github.labels` adds |
|-----------------|--------------------|-----------------------|------------------|--------------------|----------------------|
| `generic`               | `incident` | `cost-optimization` | `Task` | `finops` | `finops` |
| `identity_lifecycle`    | `incident` | `identity-management` | `Task` | `finops`, `identity` | `finops`, `identity` |
| `resource_rightsizing`  | `sc_task` | `cost-optimization` | `Task` | `finops`, `rightsizing` | `finops`, `rightsizing` |
| `runner_capacity`       | `sc_task` | `capacity-management` | `Task` | `finops`, `ci-cd` | `finops`, `ci-cd` |
| `licensing_rightsizing` | `sc_task` | `cost-optimization` | `Task` | `finops`, `licensing` | `finops`, `licensing` |

**Composition rule (binding):** the row-assembler computes
`adapter_hints` by taking a fresh `dict[str, dict[str, Any]]` with
empty `servicenow`, `jira`, `github` sub-dicts; applying contribution
A; then applying contribution B; for label arrays, the union is order-
preserving (B-labels first, A-label appended) and de-duplicated. The
result is a stable, deterministic dict for any `(severity,
adapter_class)` pair, which keeps `test_deterministic_reruns` (#4)
green.

`github.milestone` is always `null` in v0.5.0 (operators set it via
their own automation; surfacing a fabricated milestone here would be
dishonest).

**Stage-4 amendment (Noor):** B1 pair-atomicity contract added in §5.1; B2 `.j2` LF-pin added to file #22 in §2 + test #16 in §6; A3 CLI warning trigger location + suppression rule locked in D2 above; A4 worked example added to file #26 in §2 (see §10.3); A5 + A6 closed by the §3.3 table above; A7 explicit pre-compile statement added to §4.1 + test #17 in §6; A8 post-render access tracking locked in D4 above + §4.2; A9 duplicate `finding_revision` dropped from `evidence_ref` in §3.1; A10 `original_index` tiebreaker added to §5.2; A11 hardening tests #13–#15 enumerated in §6; A12 `known_limitation` non-null assertion added to test #7 in §6; NITs N13/N14/N15 addressed inline.

---

## Section 4 — Template architecture

### 4.1 Loading

Templates loaded **only** via `importlib.resources.files(
"finops_assess.data.playbooks") / surface / f"{rule_id}.j2"` —
mirrors `html_reporter.py:33-48`. No filesystem path arithmetic, no
overlay directories.

`_load_playbook_environment(rule_ids)` is invoked **once per
`write_playbook_export(...)` call**, scoped to the set of rule IDs
present in the input findings (`rule_ids_in_findings = {f["rule_id"]
for f in findings}`). It is **NOT cached at module-import time** and
**NOT memoised across export calls** — that would defeat the
fail-fast posture for newly-shipped rules whose templates land
between two CLI invocations in a long-running parent process. Test
#17 in §6 asserts this: a rule template added between two
`write_playbook_export` calls is picked up by the second call without
a process restart.

```python
def _load_playbook_environment(rule_ids: Iterable[str]) -> tuple[Environment, dict[str, Template]]:
    """Build a Jinja2 environment and pre-compile every requested template.

    Raises PlaybookTemplateNotFoundError on the first missing template.
    """
    env = Environment(
        loader=FunctionLoader(_load_template_source),
        undefined=StrictUndefined,
        autoescape=False,           # rows are JSON strings, not HTML
        keep_trailing_newline=False,
    )
    compiled: dict[str, Template] = {}
    for rule_id in sorted(rule_ids):
        try:
            compiled[rule_id] = env.get_template(_template_path_for(rule_id))
        except TemplateNotFound as exc:
            raise PlaybookTemplateNotFoundError(rule_id, expected=str(exc)) from exc
    return env, compiled
```

`_template_path_for(rule_id)` derives `"<surface>/<rule_id>.j2"` from
the rule prefix (`M365.*` → `m365/`, `AZ.*` → `azure/`, `GH.*` →
`github/`, `ADO.*` → `ado/`).

**`StrictUndefined` failure modes (binding):**

- **Compile-time** (typo in template body, e.g. `{{ findng.principal }}`) — raised by `env.get_template(...)` inside `_load_playbook_environment` on the FIRST template that fails. The reporter has not yet opened a tempfile, so there is nothing to clean up. Wrapped as `PlaybookTemplateRenderError` (test #8).
- **Render-time** (template references `evidence['vm_size']` but the row's evidence dict has no `vm_size` key) — `template.render(...)` raises `jinja2.UndefinedError`. The reporter is mid-stream inside the JSONL temp-file write loop. **Policy:** fail-fast (do NOT skip the row, do NOT substitute a sentinel). The temp-file `BaseException` handler unlinks the partial JSONL temp; the export crashes with `PlaybookTemplateRenderError(rule_id, principal, original=UndefinedError)`. Operators get a deterministic, debuggable failure pointing at the offending `(rule, principal, missing_key)` tuple. Test #18 in §6 covers this.

### 4.2 Template variable contract

Every `.j2` template is rendered with **exactly** this context dict
(StrictUndefined will raise on any missing-key reference):

```
{
  "rule":     Rule          (full pydantic model — id, surface, severity, summary, recommendation_template, evidence_key_version)
  "finding":  dict          (the original finding dict — principal, current_sku, recommended_sku, estimated_monthly_savings_usd, evidence)
  "evidence": _AccessTrackingEvidence (dict subclass that records key reads — see D4 lock; powers template_render_inputs)
  "principal": str          (alias for finding["principal"])
  "severity":  str
}
```

A template MUST emit a Jinja2 block named `title`, `description`,
`remediation_steps` (one step per line), and `verification_checklist`
(one item per line). The reporter uses `template.render()` to grab
each block via `get_or_select_template` + a small block-extraction
helper. Missing blocks → `PlaybookTemplateBlockMissingError`.

**JSON escaping happens at the row-assembly site, not in templates
(NIT-14):** templates emit raw Python strings (titles, descriptions,
remediation step text). The row-assembler builds a Python `dict` from
those strings and calls `json.dumps(row, ensure_ascii=False,
allow_nan=False, sort_keys=False)`. `json.dumps` is the canonical
escaping site for `"`, `\`, and control characters (including
embedded `\r` / `\n` / `\t` / NUL). Templates MUST NOT use `|tojson`
on individual fields — doing so would double-escape the eventual JSON
output. Test #2 (`test_jsonl_byte_contract`) and tests #13/#14
(NUL/Unicode hardening) verify the escaping contract end-to-end.

### 4.3 Coverage policy (Sonnet's "fail-fast" question, locked)

**Ship templates for ALL 23 currently-implemented rules in v0.5.0.**
No `--skip-missing-templates` flag. No "3-5 representative ones"
shortcut. Rationale:

1. Fail-fast is the Noor-resistant posture (Sonnet's recommendation, confirmed).
2. The rules YAML is the authoritative list — any rule that has a YAML entry SHOULD have a template. Anything else creates a long tail of "implementation incomplete" tickets we will be paying down for milestones.
3. Diego's #58 plan also shipped FOCUS support for every rule, not a representative subset; the convention is "support full coverage when shipping a new output format."
4. New rules added in future PRs MUST add a template in the same PR — covered by `test_template_for_rule[parametrized over registered_rule_ids()]` (see §6, test 1).

(Note: The user prompt referenced "18 existing rules" — repo
inventory at commit `39b3230` is actually 23 rules across the four
surfaces. The plan ships 23 templates.)

---

## Section 5 — Atomic write + determinism

### 5.1 Pair-atomic write contract (Noor predictions N3 + B1)

**Reader contract (binding, surfaced in `docs/playbook-reporter.md`
and `docs/schema.md`):**

> The sibling manifest `<output>.jsonl.manifest.json` is the
> **canonical readiness marker** for a playbook export. Its presence
> guarantees that the JSONL it accompanies is byte-complete and
> matches `manifest.output_artifacts.jsonl_sha256` /
> `jsonl_byte_count`. Consumers (#63 remediation-PR drafter,
> ServiceNow / Jira / GitHub Issues importers) MUST gate ingestion on
> the manifest's presence and SHOULD verify the JSONL's sha256
> against the manifest before trusting any row. An orphaned JSONL (no
> sibling manifest) is **undefined state** from a prior interrupted
> export; consumers MUST refuse to ingest it. The reporter itself
> refuses to overwrite an orphaned JSONL on the next run unless the
> operator passes `--cleanup-orphans` (CLI subcommand option, §7.2).

**Atomic-write strategy: Option C (two-step `os.replace` with
`os.fsync` durability, manifest-as-readiness-marker, sha256 self-
attestation, orphan pre-flight + `--cleanup-orphans` recovery).**
Option A (`os.replace` of a directory) was rejected because Windows
`MoveFileEx` cannot replace a non-empty target directory. Option B
(content-addressed JSONL filename) was rejected because it changes
the operator-facing filename. Option C ships an honest, cross-
platform-safe failure mode — the manifest is the gate; an orphaned
JSONL is detectable, refused, and recoverable.

```python
class PlaybookOrphanedJSONLError(RuntimeError):
    """Raised when a prior export's JSONL exists with no sibling manifest."""


def write_playbook_export(
    report: dict[str, Any],
    output_jsonl: Path,
    *,
    cleanup_orphans: bool = False,
) -> tuple[Path, Path]:
    """Write playbook JSONL + sidecar manifest with a manifest-as-readiness contract.

    Sequence:
      1. Pre-flight: refuse to run if a prior orphaned JSONL exists with
         no sibling manifest, unless cleanup_orphans=True.
      2. Pre-compile every required Jinja2 template (fail-fast on missing).
      3. Stream JSONL to a tempfile, hashing as we go; fsync; os.replace
         into output_jsonl.
      4. Build the manifest (including the JSONL's sha256 + byte_count).
      5. Stream manifest to a tempfile; fsync; os.replace into manifest_path.

    The manifest is the canonical readiness marker. An orphaned JSONL
    (step 3 succeeded but step 5 did not — process killed, power loss)
    is detectable on the next run by the step-1 pre-flight and is
    refused without --cleanup-orphans.
    """
    output_jsonl = Path(output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output_jsonl.with_name(output_jsonl.name + ".manifest.json")

    # Step 1: orphan pre-flight (BLOCKING B1 mitigation).
    if output_jsonl.exists() and not manifest_path.exists():
        if cleanup_orphans:
            output_jsonl.unlink()
        else:
            raise PlaybookOrphanedJSONLError(
                f"Refusing to overwrite orphaned JSONL at {output_jsonl}: "
                f"no sibling manifest at {manifest_path.name}. The prior "
                f"export was interrupted; re-run with --cleanup-orphans to "
                f"discard the orphan."
            )

    findings = report.get("findings", [])

    # Step 2: fail-fast on missing templates BEFORE opening the temp file.
    rule_ids_in_findings = {f["rule_id"] for f in findings}
    env, compiled = _load_playbook_environment(rule_ids_in_findings)

    # Step 3: JSONL atomic write with sha256 self-attestation.
    sha = hashlib.sha256()
    byte_count = 0
    fd, tmp_jsonl = tempfile.mkstemp(
        dir=output_jsonl.parent, prefix=".playbook-", suffix=".jsonl.tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:    # binary mode: no platform LE rewrite
            for finding in _sorted_findings(findings):
                row = _project_row(finding, env=env, compiled=compiled, report=report)
                payload = (
                    json.dumps(row, ensure_ascii=False, allow_nan=False, sort_keys=False)
                    + "\n"
                ).encode("utf-8")
                fh.write(payload)
                sha.update(payload)
                byte_count += len(payload)
            fh.flush()
            os.fsync(fh.fileno())          # durability before rename
        os.replace(tmp_jsonl, output_jsonl)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_jsonl)
        raise

    # Step 4: build manifest (carries jsonl_sha256 + jsonl_byte_count).
    manifest = build_playbook_manifest(
        report,
        rows=findings,
        compiled=compiled,
        jsonl_sha256=sha.hexdigest(),
        jsonl_byte_count=byte_count,
        jsonl_filename=output_jsonl.name,
    )

    # Step 5: manifest atomic write — the readiness marker.
    fd, tmp_manifest = tempfile.mkstemp(
        dir=manifest_path.parent, prefix=".playbook-", suffix=".manifest.tmp"
    )
    try:
        payload = (
            json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_manifest, manifest_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_manifest)
        raise

    return output_jsonl, manifest_path
```

Cross-platform notes:

- `os.replace` is atomic per POSIX `rename(2)` and Windows `MoveFileEx(MOVEFILE_REPLACE_EXISTING)`; both replace an existing destination atomically.
- `os.fsync` flushes file contents to disk before `os.replace`; we do not fsync the parent directory (POSIX-only and not load-bearing for our consumer contract — a missed parent-directory fsync would only lose a freshly-renamed manifest in a power-loss window the orphan pre-flight already handles on next run).
- Binary mode (`"wb"`) bypasses Python's universal newline translation entirely; we never get a `\r\n` from the platform.
- The pair is **not** strictly atomic at the filesystem level (filesystems do not support multi-file atomic commit). What the contract guarantees is that the **failure mode is safe and detectable**: an interrupted export leaves either (a) nothing, (b) a tempfile that the cleanup handler unlinks on `BaseException`, or (c) an orphaned JSONL that the next run refuses to overwrite. There is **no failure mode in which a complete-looking JSONL is shipped to a downstream consumer without the manifest's per-surface stability declaration.**

### 5.2 Determinism contract

| Requirement | Mechanism |
|-------------|-----------|
| `SOURCE_DATE_EPOCH` honoured | `manifest.generated_at` → `generated_at_iso()` from `_determinism.py`. No other timestamps in the JSONL row. |
| Sorted row order | `_sorted_findings()` returns `sorted(enumerate(findings), key=lambda pair: (pair[1]["surface"], pair[1]["rule_id"], pair[1]["principal"], finding_revision_for(pair[1]), pair[0]))` and discards the index after sorting. The `pair[0]` original-enumerate-index is the **final tiebreaker** — it guarantees a total order even if two findings collide on `(surface, rule_id, principal, finding_revision)`. Without this tiebreaker, Python's stable-sort fallback to engine insertion order is non-deterministic across runs (rule iteration × principal iteration × evidence-key-set ordering all vary), and `test_deterministic_reruns` (#4) goes flaky. Closes Noor amendment A10. |
| UTF-8 no BOM | `encoding="utf-8"` on every write. No `utf-8-sig` anywhere. |
| LF line endings on all platforms | `newline=""` on file open + manual `"\n"` writes (CSVDictWriter trick from `focus_aligned.py:361`). |
| Trailing `\n` on final row | Loop unconditionally appends `\n` after each `json.dumps`. The empty-export case (zero findings) produces a zero-byte JSONL plus a manifest with `row_count: 0`. |
| Float reproducibility | `allow_nan=False`; floats canonicalised via `repr()` (mirror `focus_aligned._canonicalise`). |
| `.gitattributes` pinning | Lines added in file #22 above for every byte-compared artefact. |

---

## Section 6 — Tests (18 enumerated)

Generative parametrization wherever possible. The fixture set is
deliberately small (3 input JSONs) — the parametrize matrix gives
the coverage breadth.

| # | Test | Input fixture | Asserts | Generated? |
|---|------|---------------|---------|-----------|
| 1 | `test_template_for_rule[rule_id]` | n/a | For every `rule_id in registered_rule_ids()`: `_template_path_for(rule_id)` resolves via `importlib.resources` AND template renders without raising against a synthesized minimal context. **This is the safety net for "new rule landed without template"** — it's the parametrize that Sonnet pushed. | parametrize over `registered_rule_ids()` |
| 2 | `test_jsonl_byte_contract` | `input-azure-only.json` | Output JSONL is valid UTF-8, has no BOM, every line ends `\n`, last line ends `\n`, no `\r` anywhere, every line is a self-contained JSON object that validates against `playbook_row.schema.json`. | no |
| 3 | `test_atomic_write_on_failure` | `input-azure-only.json` | Monkeypatch `_project_row` to raise on the second row; assert no `playbook.jsonl` AND no `playbook.jsonl.manifest.json` exists in the output dir afterward, AND no `.tmp` files remain. | no |
| 4 | `test_deterministic_reruns` | `input-multi-surface.json` | Run the export twice with `SOURCE_DATE_EPOCH=0`; assert both `.jsonl` and `.manifest.json` are byte-identical between runs. The `original_index` tiebreaker added in §5.2 must hold even when a synthetic input contains two `(surface, rule_id, principal, finding_revision)` collisions. | no |
| 5 | `test_manifest_schema_validates` | `input-multi-surface.json` | `jsonschema.validate(manifest, playbook_manifest.schema.json)` passes; `pii_handling.ticket_key_stability_by_surface` has all 4 surface keys; `output_artifacts.jsonl_sha256` matches `hashlib.sha256(jsonl_bytes).hexdigest()`; `output_artifacts.jsonl_byte_count` equals `len(jsonl_bytes)`. | no |
| 6 | `test_missing_template_fails_fast` | synthetic finding with `rule_id="FAKE.MISSING"` | `write_playbook_export` raises `PlaybookTemplateNotFoundError` before any temp file is created (assert no `.tmp` files exist in output dir afterward, AND no `playbook.jsonl`, AND no `playbook.jsonl.manifest.json`). | no |
| 7 | `test_pii_redaction_propagates` | `input-multi-surface.json` rendered from a report where `run.pii_redaction=true` | manifest's `pii_handling.mode` is `"redacted_per_run"`; `ticket_key_stability_by_surface["m365"]` is `"per_run"`; `ticket_key_stability_by_surface["azure"]` is `"stable"`; `pii_handling.known_limitation` is **non-null** (string, length > 0) and the string contains the substring `"#73"` (closes Noor A12 — the durable, machine-readable copy of the stderr warning). | no |
| 8 | `test_strict_undefined_catches_typos` | synthetic template with `{{ findng.principal }}` (typo) | Loading the env raises `PlaybookTemplateRenderError` wrapping `jinja2.UndefinedError` at PRE-COMPILE time, not at row-render time. | no |
| 9 | `test_cli_format_playbook` | `input-multi-surface.json` via tmp path | `CliRunner().invoke(main, ["export", "playbook", "--input", ..., "--output", ...])` exit code 0; stdout contains `"Wrote N playbook rows to ..."`; stderr contains the redaction warning when applicable; stderr warning fires **before** the export completes (assert via stderr capture interleaved with on-disk file appearance). | no |
| 10 | `test_cli_help_snapshot` | n/a | `CliRunner().invoke(main, ["export", "playbook", "--help"])` stdout equals `tests/fixtures/playbook/golden-cli-help.txt` byte-for-byte. | no |
| 11 | `test_golden_jsonl_byte_identical` | `input-azure-only.json` with `SOURCE_DATE_EPOCH=0` | Generated JSONL bytes equal `tests/fixtures/playbook/golden-azure.jsonl`. | no |
| 12 | `test_golden_manifest_byte_identical` | same | Generated manifest JSON bytes equal `tests/fixtures/playbook/golden-azure.jsonl.manifest.json`. | no |
| 13 | `test_evidence_with_nul_bytes_round_trips` | synthetic finding with `evidence = {"resource_id": "abc\x00def"}` referenced by template | Output JSONL row contains `"resource_id": "abc\u0000def"` (json.dumps canonical NUL escape); no truncation; row re-parses via `json.loads` to identical Python string. **Yuki #58 hardening parity, A11.** | no |
| 14 | `test_evidence_unicode_round_trips` | synthetic finding with non-ASCII (`"résumé"`, `"héllo🌍"`, RTL Arabic, CJK) in `principal` and `evidence` | Output JSONL preserves bytes (assert `ensure_ascii=False` via `"é".encode("utf-8") in jsonl_bytes`), no `\u00e9` escape; round-trip through `json.loads` preserves NFC normalization. **Yuki #58 hardening parity, A11.** | no |
| 15 | `test_long_resource_id_no_truncation` | synthetic finding with a 4 KiB-long Azure ARM resource_id in `evidence["resource_id"]` referenced by template | The full 4 KiB string appears verbatim in the rendered `description`; no template-side truncation, no row-assembler truncation. Schema's `description` field has no `maxLength`. **Yuki #58 hardening parity, A11.** | no |
| 16 | `test_packaged_j2_templates_are_lf_only` | n/a | Walk every `*.j2` under `importlib.resources.files("finops_assess.data.playbooks")`; for each, read bytes; assert `b"\r" not in template_bytes`. **Closes Noor BLOCKING B2 — guards against `core.autocrlf=true` re-rewriting the templates on a Windows clone if the `.gitattributes` rule is removed in a future PR. Yuki #58 byte-level parity, mirrors `tests/test_focus_aligned.py::test_golden_fixtures_have_lf_line_endings`.** | parametrize over discovered `.j2` files |
| 17 | `test_pre_compile_picks_up_new_template` | n/a | First `write_playbook_export` call with input findings limited to rules `{R1, R2}` succeeds. Then monkeypatch `importlib.resources.files(...)` to expose a new template `R3.j2`; second `write_playbook_export` call with input findings now including `R3` succeeds **without a process restart** (proves no module-import-time caching of `Environment` / pre-compiled templates). | no |
| 18 | `test_strict_undefined_catches_missing_evidence_key` | synthetic finding with `evidence = {}` rendered through a template that references `{{ evidence['vm_size'] }}` | `write_playbook_export` raises `PlaybookTemplateRenderError` wrapping `jinja2.UndefinedError`; the temp `.jsonl.tmp` file is unlinked (assert no `.tmp` files in output dir); no `playbook.jsonl` exists; no `playbook.jsonl.manifest.json` exists. **Closes Noor A8 render-time concern.** | no |

---

## Section 7 — CLI wiring

### 7.1 Subcommand shape

Mirrors `export focus-aligned` verbatim. The playbook is a
**standalone export subcommand**, NOT composable with `--format
all` on the `run` command, because:

1. `run` operates on a CSV input directory; `export` operates on an existing JSON report. The semantic split was locked in #58.
2. Composability with `run --format all` would require teaching the run command how to find templates AND would re-introduce coupling between the engine and the playbook templates that we deliberately avoided.
3. Operators who want a one-shot pipeline use a two-step shell invocation; this is documented in the user guide.

### 7.2 Help-text contract (verbatim — golden-snapshotted in test 10)

```
$ finops-assess export playbook --help
Usage: finops-assess export playbook [OPTIONS]

  Emit per-finding ticketing-system payloads (NDJSON) from a finops-assess
  report.

  This export is read-only. The JSONL stream is consumed out-of-band by
  the operator's ticketing platform (ServiceNow / Jira / GitHub Issues);
  finops-assess never calls a ticketing API. See docs/playbook-reporter.md
  for the per-surface ticket-key stability contract.

Options:
  --input PATH           Canonical findings JSON from `finops-assess run`.
                         [required]
  --output PATH          Destination JSONL path; manifest written
                         alongside as <output>.manifest.json.  [required]
  --skip-warnings        Suppress the stderr warning about per-run
                         ticket-key stability when redaction is on with
                         non-Azure findings. Expert use only.
  --cleanup-orphans      If a prior export was interrupted and left an
                         orphaned JSONL with no sibling manifest at the
                         output path, delete the orphan instead of
                         refusing to run. The manifest is the canonical
                         readiness marker; an orphaned JSONL is undefined
                         state. See docs/playbook-reporter.md.
  --help                 Show this message and exit.
```

### 7.3 Stderr warning text + ordering (binding)

**Trigger location:** the warning is computed and emitted from the
`@export.command("playbook")` handler in `cli.py`, **immediately
before** the call to `write_playbook_export(...)`. Operators piping
stderr to `>/dev/null` after the export will still see it printed
during the export's startup window. The reporter module itself does
not know about CLI flags and does not emit any stderr text.

**Suppression rules** (all three apply; warning is silent if any
fires):

1. The operator passed `--skip-warnings`.
2. The input report has `run.pii_redaction=false` (operator opted into cleartext; per-run instability does not apply).
3. The input report has zero non-Azure findings (`m365_count == 0 AND github_count == 0 AND ado_count == 0`); the warning text would name three zero-count surfaces and be meaningless.

**Verbatim warning text** (when emitted):

```
WARNING: pii_redaction is on and findings include surfaces without a
stable principal salt (m365=N, github=N, ado=N). Their ticket_key
values are stable WITHIN this run only and will change on the next
invocation. Downstream ticketing systems will treat re-runs as new
tickets. Track stable-salt support at issue #73.
```

**Manifest mirror:** the same condition that triggers the stderr
warning ALSO populates `pii_handling.known_limitation` in the
manifest with a string of the form:

```
"per-run ticket_key instability for surfaces: {m365,github,ado} (counts: {3,1,2}); track stable-salt at #73"
```

This is the durable, machine-readable copy of the warning for
consumers that never see stderr. Test #7 asserts the field is
non-null whenever any surface is `per_run`.

---

## Section 8 — Acceptance criteria

The PR is mergeable when ALL of the following are simultaneously
true. Stage-4 Noor will check this list verbatim.

### 8.1 Convergent amendments (consensus §1, all 6 present)

- [ ] **NDJSON byte contract** — `test_jsonl_byte_contract` (#2) is green.
- [ ] **Atomic writes** — `test_atomic_write_on_failure` (#3) is green; `tempfile.mkstemp` + `os.replace` visible in `playbook_reporter.py`.
- [ ] **Manifest sidecar** — `playbook_manifest.schema.json` exists; `test_manifest_schema_validates` (#5) green.
- [ ] **Fail-fast on missing template** — `PlaybookTemplateNotFoundError` raised; `test_missing_template_fails_fast` (#6) green.
- [ ] **Deterministic row sort** — `_sorted_findings()` keyed `(surface, rule_id, principal, finding_revision)`; `test_deterministic_reruns` (#4) green.
- [ ] **Out-of-scope items rejected** — section 9 below; no API push, no custom field mapping, no dedup, no aggregation, no runtime overlay, no cross-surface rules.

### 8.2 Noor predictions pre-empted (all 5)

- [ ] N1 — `playbook_schema_version: "0.1"` in manifest.
- [ ] N2 — No filesystem template overlay; `importlib.resources` only.
- [ ] N3 — `tempfile.mkstemp` + `os.fsync` + `os.replace` in both writes; manifest is the readiness marker (§5.1); orphan pre-flight refuses partial state without `--cleanup-orphans`.
- [ ] N4 — `PlaybookTemplateNotFoundError` raised at pre-compile, not row render.
- [ ] N5 — `.gitattributes` carries 5 new `text eol=lf` lines (4 byte-compared fixtures + 1 glob for the 23 `.j2` source templates); test #16 asserts no `.j2` carries `\r`.

### 8.3 Divergences reconciled (all 4)

- [ ] D1 — Row carries optional `adapter_hints` object derived per the binding §3.3 tables; `Rule.adapter_class` field added; per-rule mapping in §3.3.1; severity × class derivation in §3.3.2.
- [ ] D2 — `pii_handling.ticket_key_stability_by_surface` declared in manifest; CLI emits stderr warning **before** `write_playbook_export` runs (§7.3 trigger location); `pii_handling.known_limitation` is non-null whenever any surface is `per_run`; follow-up issue `#73` filed and linked.
- [ ] D3 — `_load_playbook_environment()` uses `StrictUndefined` AND pre-compiles every templated rule; pre-compile runs **once per `write_playbook_export` call**, scoped to `rule_ids_in_findings`, NOT cached at module-import time (test #17).
- [ ] D4 — Row carries `evidence_ref` (now `{report_path}` only — duplicate `finding_revision` dropped) + `template_render_inputs` (computed via `_AccessTrackingEvidence` dict subclass — see D4 lock and §4.2); NOT the full evidence dict.

### 8.4 Research OQs closed (all 5)

- [ ] OQ-1, OQ-2, OQ-3, OQ-4, OQ-5 — answers in §1 above are reflected in code/docs/tests.

### 8.5 Validation gates (all green)

- [ ] `finops-assess validate` — passes (catalog + personas + rules schema, including the new `adapter_class` field).
- [ ] `ruff check . && ruff format --check .` — passes.
- [ ] `mypy src` — passes (`--strict`); new `Rule.adapter_class` annotated; `playbook_reporter.py` is fully typed.
- [ ] `pytest` — all 18 enumerated tests green (12 originals + 3 hardening A11 + LF-pin guard A11/B2 + pre-compile no-cache A7 + render-time UndefinedError A8).
- [ ] `python scripts/generate_docs.py --check` — passes; the two new `examples/playbook.*` artefacts are byte-fresh.
- [ ] CI matrix — `{ubuntu-latest, windows-latest, macos-latest} × {3.11, 3.12}` ALL green. The `required-checks` summary context (`ci.yml:68-79`) is the gate.

### 8.6 Documentation drift (all updated, per copilot-instructions §"Documentation updates")

- [ ] `README.md` — playbook reporter mentioned in the reports section.
- [ ] `CHANGELOG.md` — entry under `## v0.5.0`.
- [ ] `docs/plan.md` §6 — playbook subsection added (file #30).
- [ ] `docs/schema.md` — playbook row + manifest documented; manifest-as-readiness contract from §5.1 documented; **schema versioning contract** lifted out of the JSON-Schema description string into a top-level "Schema versioning contract" section (closes Noor NIT N13).
- [ ] `docs/user-guide.md` — playbook section added.
- [ ] `docs/playbook-reporter.md` — operator guide created; includes (a) per-surface stability worked example showing the manifest-first consumer pattern (closes Noor amendment A4), (b) `--cleanup-orphans` recovery procedure, (c) top-level "Schema versioning contract" section (NIT N13 surfaced operator-side too).
- [ ] `examples/playbook.jsonl` + `.manifest.json` — generated and committed.

---

## Section 9 — Out of scope (reject scope creep early)

Per consensus §6, **none** of the following are in this PR. Stage-4
Noor MUST reject any PR that smuggles them in.

| # | Item | Rationale | Disposition |
|---|------|-----------|-------------|
| 1 | Direct API push to ServiceNow / Jira / GitHub Issues | Read-only posture is non-negotiable per copilot-instructions §"Hard rules" #1; #61's framing is explicit ("operators can pipe to … out-of-band"). | Permanent — would violate the read-only architecture. |
| 2 | Custom-field mapping per ticketing instance | Operator-specific; belongs in the operator's downstream adapter, not in finops-assess. | Permanent — out of charter. |
| 3 | Ticket dedup across runs | Requires stable salt + a state store; both are out of scope. The honest stability declaration (D2) tells operators which dedup is safe. | Defer to follow-up `#73` (Maya files at PR-open). |
| 4 | Multi-finding aggregation (one ticket for N findings) | Aggregation is a rule-design concern (where the rule itself emits one finding per group), not a reporter concern. | Permanent for the reporter — revisit at the rule level if requested. |
| 5 | Runtime template overlay (`~/.finops-assess/playbooks/`) | Sandbox escape + supply-chain risk. | Defer to v0.6.0 — placeholder issue `#74` (Maya files at PR-open). |
| 6 | Cross-surface rules (a "playbook rule" that fires on a join of M365 + Azure findings) | Cross-surface evaluation is an engine-level architectural change, not a reporter concern. | Defer — no follow-up filed (no operator demand surfaced yet). |
| 7 | Stable-principal-salt feature | The engine-level architectural change to make `principal` stable across runs when redacted. The honest stability declaration (D2) ships v0.5.0 without it. | Follow-up `#73` (Maya files at PR-open). |

---

## Section 10 — Stage-5 implementer guidance

**Owner:** Diego (reporter module, mirrors his #58 ownership) + Yuki
(test enumeration, golden-fixture pinning, docs sweep).

**Inheritance from #58:**

- Single module per output format (no separate `playbook_manifest.py`). The `build_playbook_manifest` helper lives inside `playbook_reporter.py` for the same reasons documented at `.squad/decisions.md` lines 85-100 of the #58 entry.
- `.gitattributes` discipline: every byte-compared fixture needs its own line. Yuki: re-apply the pattern from `.squad/skills/focus-aligned-golden-fixtures/SKILL.md`.
- Generative parametrization for breadth (test #1) + golden bytes for depth (tests #11, #12).

**Reviewer Rejection Lockout pattern:** the implementer is Diego.
On rejection, the revision MUST go to a different agent (Maya's
charter rule at `.squad/agents/lead/charter.md:33`). Diego does NOT
self-revise.

**Stage-4 Noor verdict comment:** posted by the **coordinator (Martin)** as
a PR comment using the `**Stage-4 Adversarial Review — Noor**`
marker + `VERDICT: APPROVE` line so `squad-approve.yml` (issue #47)
can submit the `github-actions[bot]` approval. **Do NOT embed the
verdict in this PR's body** — `squad-approve.yml` triggers on
`issue_comment:created`, not on PR body content.

**CI gate hygiene:** if implementation produces a need for a new
top-level CI job (it should not), the `required-checks` summary
context in `ci.yml:68-79` MUST be amended in the same PR (per
copilot-instructions §11 / issue #51). Otherwise the new job runs
ungated.

**Pre-PR commands:**

```pwsh
cd C:\git\FinOps-assessment
git checkout -b squad/61-playbook-reporter   # already created by Maya for this plan PR — Diego rebases off this
finops-assess validate
ruff check . ; ruff format --check .
mypy src
pytest
python scripts/generate_docs.py --check
```

**Pre-merge dry run** (must succeed locally before opening the
implementation PR):

```pwsh
finops-assess export playbook --input examples\demo-report.json --output .\.tmp-export\playbook.jsonl
# Confirm: .\.tmp-export\playbook.jsonl exists, .\.tmp-export\playbook.jsonl.manifest.json exists,
# row count matches manifest, manifest validates against playbook_manifest.schema.json,
# manifest.output_artifacts.jsonl_sha256 matches `Get-FileHash -Algorithm SHA256 .\.tmp-export\playbook.jsonl`,
# stderr warning fires (because demo-report.json contains M365/GitHub/ADO findings with redaction on),
# warning appears on stderr BEFORE the "Wrote N playbook rows" stdout line.
#
# Crash-recovery dry run: simulate orphan, verify the pre-flight blocks it.
Remove-Item .\.tmp-export\playbook.jsonl.manifest.json
finops-assess export playbook --input examples\demo-report.json --output .\.tmp-export\playbook.jsonl
# Expect: PlaybookOrphanedJSONLError; exit code != 0.
finops-assess export playbook --input examples\demo-report.json --output .\.tmp-export\playbook.jsonl --cleanup-orphans
# Expect: success; orphan deleted; fresh JSONL + manifest written.
```

### Section 10.3 — `docs/playbook-reporter.md` worked example outline (closes Noor amendment A4)

The operator guide MUST include a "Consuming the playbook"
subsection with a worked Python example showing the manifest-first
consumer pattern. Skeleton (Diego implements verbatim, only the
narrative prose is editorial):

```python
# Read the manifest FIRST. Its presence is the readiness signal.
import json
import hashlib
from pathlib import Path

manifest_path = Path("playbook.jsonl.manifest.json")
jsonl_path = Path("playbook.jsonl")

if not manifest_path.exists():
    raise SystemExit(
        "No manifest at playbook.jsonl.manifest.json — the export was "
        "interrupted or has not run. Refusing to consume an orphaned JSONL."
    )

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# Verify the JSONL bytes against the manifest's self-attestation.
jsonl_bytes = jsonl_path.read_bytes()
expected_sha = manifest["output_artifacts"]["jsonl_sha256"]
actual_sha = hashlib.sha256(jsonl_bytes).hexdigest()
if actual_sha != expected_sha:
    raise SystemExit(f"JSONL sha256 mismatch: expected {expected_sha}, got {actual_sha}")

# Build the per-surface stability map BEFORE iterating rows.
stability = manifest["pii_handling"]["ticket_key_stability_by_surface"]
# stability == {"m365": "per_run", "azure": "stable", "github": "per_run", "ado": "per_run"}

# Now iterate rows; bucket each by its surface's declared stability.
import_as_idempotent: list[dict] = []   # consumer can dedup on ticket_key
import_as_per_run:    list[dict] = []   # consumer MUST treat as new ticket every run
for line in jsonl_bytes.decode("utf-8").splitlines():
    row = json.loads(line)
    if stability[row["surface"]] == "stable":
        import_as_idempotent.append(row)
    else:
        import_as_per_run.append(row)
```

Narrative prose around the snippet must say:

1. **Why the manifest-first order is binding** (cite §5.1 reader contract).
2. **Why `import_as_per_run` rows duplicate on re-run** and link to issue `#73` for the eventual stable-salt fix.
3. **What to do if `manifest_path` is missing but `jsonl_path` exists** (orphaned export; either re-run with `--cleanup-orphans` or treat as undefined state).
4. **Schema versioning contract** (NIT N13 lift from JSON Schema description string): "row v0.1 is additive-only; new top-level keys may appear in future releases without bumping `playbook_schema_version`; consumers MUST ignore unknown keys; only a breaking change increments to `0.2`."

**Implementer checklist:**

- [ ] Create branch `squad/61-playbook-reporter` (already created for plan PR — implementation rebases or uses a sibling branch `squad/61-playbook-reporter-impl`).
- [ ] Add `Rule.adapter_class` to `models.py` + loader.
- [ ] Add `adapter_class` to all 23 rules in `src/finops_assess/data/rules/*.yaml` (mirror to top-level `data/` if the parity script demands).
- [ ] Author 23 `.j2` templates under `src/finops_assess/data/playbooks/{surface}/`.
- [ ] Implement `playbook_reporter.py` mirroring the structure of `focus_aligned.py`.
- [ ] Implement the two JSON Schemas under `src/finops_assess/schemas/`.
- [ ] Wire `@export.command("playbook")` in `cli.py`; help text matches §7.2 verbatim.
- [ ] Author 12 enumerated tests + Yuki's hardening tests.
- [ ] Generate `golden-cli-help.txt` from the new subcommand.
- [ ] Generate `golden-azure.jsonl` + `.manifest.json` with `SOURCE_DATE_EPOCH=0` and the canonical `input-azure-only.json` fixture.
- [ ] Append 4 lines to `.gitattributes`.
- [ ] Extend `scripts/generate_docs.py` `regenerate_examples`.
- [ ] Run `python scripts/generate_docs.py` — commit `examples/playbook.jsonl` + `.manifest.json`.
- [ ] Update README, CHANGELOG, docs/plan.md §6, docs/schema.md, docs/user-guide.md, docs/playbook-reporter.md.
- [ ] Open PR with `Closes #61`, label `squad:diego` for the implementation PR (this stage-3 PR carries `squad:maya`).

---

> **End of stage-3 plan for #61.** All four divergences closed, all
> five OQs closed, all five Noor predictions pre-empted, all six
> convergent amendments named in §8.1. Awaiting Noor's stage-4
> adversarial pass.

---

### Stage-3 Plan Revision (Yuki, post-Noor stage-4 reject)

> **Reviser:** Yuki (QA / cross-platform hardening) — model: Opus 4.7
> **Date:** 2026-05-13 (same-day revision)
> **Lockout:** Reviewer Rejection Lockout enforced. Maya, the original
> plan author, was locked out of this revision per the protocol Maya
> herself documented in §10 (lines 585–588 above). Yuki produced this
> revision independently — no consultation with Maya, no co-authorship.
> The Coordinator confirmed Yuki's eligibility (not the original author).
> **Trigger:** Noor stage-4 verdict REJECT — 2 BLOCKING / 8 AMENDMENT /
> 3 NIT (PR #72 review comment).

This revision amends mechanics, not architecture. **Every locked
architectural decision Maya made is preserved unchanged**: D1
(adapter_hints + schema versioning), D2 (Option B-honest PII), D3
(StrictUndefined + pre-compile), D4 (`evidence_ref` +
`template_render_inputs`); the 5 OQ closures (OQ-1..5); the §9
deferred-disposition table including `#73` and `#74`; the §1
"Stage-3 corrections to the consensus" stance; the §2 file-level
checklist's structural shape; the §4.3 "ship templates for ALL 23
rules" coverage policy.

**What changed (with citations to Noor's findings):**

| # | Severity | Section(s) | Status | Resolution |
|---|----------|------------|--------|------------|
| B1 | BLOCKING | §1 N3, §5.1 (rewritten) | addressed | Adopted **Option C** (two-step `os.replace` with `os.fsync` durability, manifest-as-readiness-marker, `output_artifacts.jsonl_sha256` + `jsonl_byte_count` self-attestation, orphan pre-flight + `--cleanup-orphans` recovery flag). Pair atomicity is impossible at the filesystem layer; the contract instead guarantees a **safe, detectable, recoverable** failure mode. Code snippet inline in §5.1; reader contract surfaced in `docs/playbook-reporter.md` per §10.3. |
| B2 | BLOCKING | §1 N5, §2 file #22, §6 test #16 | addressed | Added `src/finops_assess/data/playbooks/**/*.j2 text eol=lf` to the `.gitattributes` plan + added test #16 (`test_packaged_j2_templates_are_lf_only`) as the regression net. Mirrors Yuki's #58 commit `3e18275` pattern. |
| A3 | AMENDMENT | §1 D2, §7.3 | addressed | CLI warning trigger location locked: emitted from `cli.py` `@export.command("playbook")` handler **immediately before** `write_playbook_export(...)`. Suppression rules locked: (a) `--skip-warnings`, (b) `pii_redaction=false`, (c) zero non-Azure findings. Manifest mirror: same condition populates `pii_handling.known_limitation` (durable copy for stderr-blind consumers). |
| A4 | AMENDMENT | §10.3 (new), §8.6 | addressed | New §10.3 spec for the operator-doc worked example (manifest-first consumer pattern, sha256 verification, per-surface bucketing, orphan recovery, schema-versioning contract). `docs/playbook-reporter.md` acceptance bullet in §8.6 expanded. |
| A5 | AMENDMENT | §3.3.1 (new) | addressed | 23-row binding table mapping every shipped rule to its `adapter_class`. Diego picks zero values; the table is the source of truth. |
| A6 | AMENDMENT | §3.3.2 (new) | addressed | Two binding orthogonal tables: (A) severity → urgency / priority; (B) `adapter_class` → table / category / labels. Composition rule documented. `adapter_hints` SHIPS in row v0.1 (not deferred); the schema's existing `additionalProperties: true` posture handles v0.6.0 extensions. |
| A7 | AMENDMENT | §4.1 (revised), §6 test #17 | addressed | §4.1 explicitly states `_load_playbook_environment` runs **once per `write_playbook_export` call**, scoped to `rule_ids_in_findings`, NOT cached at module-import time. Test #17 (`test_pre_compile_picks_up_new_template`) proves a fresh template added between two calls is picked up without process restart. |
| A8 | AMENDMENT | §1 D4 (revised), §4.2, §6 test #18 | addressed | Locked `template_render_inputs` computation as **post-render access tracking** via `_AccessTrackingEvidence` dict subclass. Finalize-hook alternative explicitly rejected (wrong under `StrictUndefined`). §4.1 now also documents render-time `UndefinedError` policy: fail-fast, unlink temp, surface as `PlaybookTemplateRenderError`. Test #18 covers the render-time path. |
| A9 | AMENDMENT | §3.1 schema | addressed | Dropped `finding_revision` from `evidence_ref`. The top-level `finding_revision` row field is the canonical hash; `evidence_ref` now carries only `report_path`. Schema's `evidence_ref.required` updated to `["report_path"]`. |
| A10 | AMENDMENT | §5.2 sort | addressed | Added `original_index` (from a stable `enumerate(findings)`) as the FINAL tiebreaker. Sort key is now `(surface, rule_id, principal, finding_revision, original_index)`. Total order even on synthetic collisions. |
| A11 | AMENDMENT | §6 tests #13/#14/#15 | addressed | Yuki's three #58-parity hardening tests promoted from "review sweep" to required tests #13 (NUL bytes round-trip), #14 (Unicode round-trip with `ensure_ascii=False`), #15 (4 KiB resource_id no truncation). Ship in the same PR as the reporter; gate stage-5 acceptance. |
| A12 | AMENDMENT | §6 test #7 (revised) | addressed | Test #7 now asserts `pii_handling.known_limitation` is non-null (string, length > 0, contains `"#73"`) whenever any surface is `per_run`. Closes the "stderr-blind consumer" hole. |
| N13 | NIT | §8.6 docs/playbook-reporter.md bullet, §10.3 outline | addressed | Lifted the "Schema versioning contract" out of the row-schema description string into a top-level operator-doc section. Cheap (≤5 min). |
| N14 | NIT | §4.2 (added paragraph) | addressed | Added a paragraph stating JSON escaping happens at the row-assembler `json.dumps` site; templates MUST NOT use `|tojson` per-field (would double-escape). Cheap. |
| N15 | NIT | §3.2 (added paragraph) | addressed | Added the algorithm-vs-input clarification: the reporter computes `ticket_key` with one uniform algorithm; the per-surface stability declaration is a statement about input quality, not algorithmic divergence. Cheap. |

**NIT items deferred:** none. All three NITs were ≤5-minute plan
edits and are addressed inline.

**Files edited in this revision:**
- `.squad/decisions.md` (this file — Maya's plan section in place; this revision subsection appended)
- `.gitattributes` (added `src/finops_assess/data/playbooks/**/*.j2 text eol=lf` line — closes B2 at the actual config file, not just the plan)

**Decisions explicitly preserved (unchanged from Maya's plan):**

- D1 — `adapter_hints` + `playbook_schema_version` schema versioning model (only the per-rule and per-class binding tables in §3.3 are new; the model is unchanged).
- D2 — Option B-honest per-surface stability declaration; defer stable-salt to `#73`.
- D3 — `StrictUndefined` + per-export pre-compile.
- D4 — `evidence_ref` + `template_render_inputs` (only the computation method and the dropped duplicate field are new mechanics).
- OQ-1..5 closures.
- §9 deferred-disposition table including `#73` (stable-salt) and `#74` (runtime overlay).
- §4.3 coverage policy: ship templates for ALL 23 rules in v0.5.0.
- §7.1 "standalone export subcommand, NOT composable with `run --format all`" semantic split.

**No new architectural decisions were introduced. No scope was added.**
The two BLOCKING fixes are mechanics (atomic-write pattern; `.gitattributes`
glob); the eight AMENDMENT fixes either lock a value Maya left to the
implementer or close a documentation gap; the three NIT fixes are cheap
clarifications.

**Re-review trigger:** Coordinator (Martin) posts the comment on PR #72;
Noor opens a fresh stage-4 context with this revised plan as input.

> **End of Yuki revision.** Stage-5 (Diego implementation) does NOT
> start until Noor posts a fresh APPROVE verdict.

---

## Cross-Agent Notes — #61 Stage-4 Rejection & Revision Cycle

### Noor Stage-4 Verdict (2026-05-13 08:55:00 UTC)

**VERDICT: REJECT** (2 BLOCKING / 8 AMENDMENT / 3 NIT).

- **B1:** Manifest-JSONL pair-atomicity fixed by Yuki with Option C (manifest-as-readiness-marker + fsync + sha256 self-attestation + orphan pre-flight).
- **B2:** `.j2` LF-pin regression (exact #58 hardening precedent broken) fixed via `.gitattributes` entry added + test #16.

Orchest log: `.squad/orchestration-log/2026-05-13T085500Z-noor-stage4-61.md`

### Yuki Stage-3 Revision (2026-05-13 08:55:30 UTC)

Yuki (QA/hardening, Opus 4.7 xhigh exception) revised under Reviewer Rejection Lockout. All 13 findings (2B/8A/3N) closed. Zero architectural tampering — D1/D2/D3/D4, OQ-1..5, §9 deferred-disposition preserved. Atomic-write Option C precedent now established for multi-file exports. `.gitattributes` hardening applied (commit 10096cb).

Orchest log: `.squad/orchestration-log/2026-05-13T085530Z-yuki-stage3-revise-61.md`

---

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

### 2026-05-13 — Stage-4 adversarial review for #58 FOCUS-aligned advisory exporter (Noor, Opus 4.7)

**VERDICT: APPROVE**

> Reviewer: Noor (Security & Compliance) — model: Opus 4.7
> Issue: #58 (epic #57) — `release:v0.5.0`
> Artefact under review: `.squad/decisions/inbox/maya-stage3-58-focus-aligned-export.md`
> Locked inputs (not relitigated): `focus-1-3-consensus.md` D1–D7 + six blockers.

**Steelman against shipping:** Five angles considered and counter-argued:

1. **`evidence_key_version` future-cost.** Maya adds Rule.evidence_key_version: int = 1 without v0.5.0 use. Trade-off: forever-cost in schema vs retrofit risk when consumers pin AdvisoryFindingKey. Counter-wins: declaring migration contract now is cheaper than retrofitting. Acceptable.

2. **Enum extension is not strict-additive.** v0.5.0 consumer pinning pii_handling.mode enum will REJECT v0.6.0 manifests when mode values expand. Counter-wins: consumers MUST ignore unknown fields; documented in manifest schema description. Known JSON-Schema wart, not Maya's invention. Acceptable.

---

## Merged from inbox

### Cross-pollination: #61 stage-3 plan (Maya, 2026-05-13)

Issue #61 (playbook / ticket reporter, p1, v0.5.0) stage-3 plan now locked and committed at `.squad/decisions.md:6-500`. All divergences reconciled: D1 (both-additively), D2 (Option B-honest stable-ID declaration), D3 (both-complementarily pre-compile + StrictUndefined), D4 (evidence_ref + template_render_inputs). All five research OQs closed. All five Noor predictions pre-empted. Two follow-ups filed: #73 (stable-salt engine, v0.6.0 p1), #74 (runtime overlay sandbox, v0.6.0 p2). Ready for stage-4 adversarial review; Diego + Yuki assigned for stage-5 implementation.

### Triage decision: #66 + #69 paired operator-hygiene effort (2026-05-13)

Route #66 (squad-info-hygiene docs) and #69 (selective-gitignore) to squad:scribe as a paired iteration with explicit dependency ordering: #66 unblocks #69. Both address "operator-visible vs. maintainer-only" boundaries. #66 establishes the `<details><summary>` convention for squad scaffolding; #69 follows up with file-tracking discipline (mid-stream churn stays local, distilled audit trail stays tracked). Implementation sequence: (1) #66 ships first (operator-visible docs, README pointer, CHANGELOG, .squad/skills/squad-pr-discipline/SKILL.md); (2) #66 verified (squad-approve.yml regex confirmed in <details> blocks); (3) #69 unblocked (.gitignore, README maintainer-section); (4) auto-approve re-verified. Not cross-blocking #67 (multi-cloud roadmap) or #68 (FinOps backlog), both independent.

### Decision: Golden fixture byte-comparison requires `.gitattributes text eol=lf` (Yuki, 2026-05-13)

Every golden fixture file compared byte-for-byte in tests (via `read_bytes()` or equivalent) **must** have a `text eol=lf` entry in `.gitattributes`, regardless of directory (`examples/`, `tests/fixtures/`, or other). **Rationale:** Windows-hosted GitHub Actions runners default to `core.autocrlf=true`, which rewrites LF to CRLF on checkout. Production reporters write LF-only output (enforced by `lineterminator="\n"` in CSV writers and `newline=""` in `write_text` calls). Without `eol=lf`, golden fixtures checked out with CRLF fail byte-identical comparisons exclusively on Windows (Linux/macOS pass), giving false cross-platform safety. **Scope:** applies to byte-identical comparisons in `tests/fixtures/**/*.csv`, `tests/fixtures/**/*.json`, `tests/fixtures/**/*.html`. **Checklist for future reporter PRs:** (1) Does reporter write bytes deterministically (LF-only, UTF-8)? (2) Does test compare golden fixture bytes with `read_bytes()`? (3) If both: add `text eol=lf` to `.gitattributes` for every such fixture in the same PR. (4) Verify on `windows-latest` — if conditions 1–2 met but `.gitattributes` missing, Windows CI fails while Linux/macOS pass. See `.squad/skills/focus-aligned-golden-fixtures/SKILL.md` for reusable testing pattern including `newline=""` and `.gitattributes` checklist.

3. **ARM resource IDs carry resource-name PII.** ResourceId cleartext (e.g. `vm-john-test01`) encodes user names. Counter-wins: operator opted into PII redaction upstream; export echoes source_report.pii_redaction; ResourceId is the FOCUS warehouse join key — hashing defeats the purpose. Acceptable.

4. **Empty-input CI-script trap.** Zero rows exit 0, masking silent collector failures. Counter-wins: correct trade-off; clear stdout "Wrote 0 advisory rows" is the signal; failing loud would force every consumer to special-case zero. Risk R8 acknowledged.

5. **`_generated_at` lift target left ambiguous.** Plan offered two options; implementer chose _determinism.py. Counter-wins: Diego shipped the choice inline; not a blocker. Acceptable.

**Hard-rule audit: ALL PASS**
| Rule | Verdict | Note |
|------|---------|------|
| 1. Read-only | **PASS** | No API, no scope request |
| 2. No secrets | **PASS** | jsonschema dev-only, no live-scope dep |
| 3. No copyright | **PASS** | Schema is ours; warning-banner is paraphrase |
| 4. PII redaction | **PASS** (P2 tail-risk) | ARM resource ID is principal; echoes upstream flag |
| 5. Catalogue as data | **PASS** | evidence_key_version lives in code, not YAML |

**Blocker traceability: 6/6 PASS** — ListCost, conformance branding, ResourceId cleartext, CLI shape, manifest fields, golden+SOURCE_DATE_EPOCH all addressed in plan.

**D-decision traceability: 7/7 PASS** — D1–D7 all honoured.

**P2 findings (note for follow-up, not blockers):**
1. Citation drift html_reporter.py:89 → actual :96 (no semantic risk)
2. Manifest enum extension not consumer-strict-additive (industry wart; documented)
3. evidence_key_version unused in v0.5.0 (intentional; v0.6.0 will mix it in)
4. Test coverage gaps (5 enumerated, worth stage-5 follow-up but not P0)
5. _generated_at lift choice left to implementer (resolved inline)
6. D4 calendar-month derivation not explicitly described (implementer will figure it out)

**Stage-3 correction verification: ✅** — Per-run salt lives in engine.py:151, not json_reporter.py. All reference code pointers verified.

**Verdict stands: APPROVE.** The P2 items should be folded inline by Diego/Yuki without Maya revision. Strict-lockout rule does not apply — Maya is free to address P2 items if she chooses.

— Noor

### 2026-05-13 — Diego implementation: advisory_finding_key() NUL-collision fix (embedded in #58 stage-5)

**Decision:** During stage-5 implementation of #58, Diego discovered and fixed a hash-collision vulnerability in advisory_finding_key():

**Before:** The function concatenated `rule_id + '\x00' + resource_id + '\x00' + evidence_json` (NUL-byte separators).
**Vulnerability:** Evidence values containing literal NUL characters could collide with distinct (rule_id, resource_id, evidence) tuples. Example: `(X, Y, Z\x00abc)` and `(X, Y\x00a, bc)` would produce the same serialization.
**Non-deterministic in practice:** NUL characters are rare in Azure resource IDs and log evidence, so collision probability is low.
**Fix:** Switched to `sha256(json.dumps([rule_id, resource_id, evidence_json]))`. JSON serialization is lossless and guarantees unique canonical form.
**Consequence:** Bumped `Rule.evidence_key_version` from implicit 0 to explicit 1, creating forward contract. Future rule evidence changes can increment the version independently; manifest documents the algorithm string starting in v0.6.0.

**Why this matters:** The vulnerability is a protocol issue that should be corrected upstream rather than papered over. Fixing it in v0.5.0 means v0.6.0 can safely mix the version into the hash without worrying about backward-collision edge cases.

**Trade-off:** The hash format changed, so advisory keys in v0.5.0 exports will NOT match keys computed by future rule-evaluation code. This is acceptable because the exporter is read-only and does not participate in production keying — consumers who migrate v0.5.0 exports to warehouses must re-key them against v0.6.0 hash logic anyway when they adopt that version.

— Scribe (Diego's embedded decision)

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
