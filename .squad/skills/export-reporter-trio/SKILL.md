# Export-reporter trio

> **Confidence:** low (pattern observed once on `#58` FOCUS-aligned exporter; promote when a second exporter validates it)

## Pattern

Every output reporter that emits an interoperability artefact for a
third-party consumer ships as a **trio**:

1. **Reporter module** under `src/finops_assess/reporters/<name>.py`
   that produces both the primary artefact (CSV, Parquet, JSON) and
   a sidecar `manifest.json` declaring conformance level, schema
   version, join keys, and any non-obvious limitations. Public
   surface is two functions: `write_<name>_export(report, output)`
   and `build_<name>_manifest(report)`. The writer always calls
   the manifest builder so the two artefacts cannot disagree.

2. **JSON Schema** under
   `src/finops_assess/schemas/<name>_manifest.schema.json` (Draft
   2020-12), bundled as package-data via `pyproject.toml`. Validated
   by a test that uses `pytest.importorskip("jsonschema")` so the
   skip is loud when a contributor forgets `[dev]` extras.

3. **Golden fixture trio** under `tests/fixtures/<name>/`:
   `golden-*.csv`, `golden-*.manifest.json`, `golden-cli-help.txt`.
   All pinned to LF via `.gitattributes`. All regenerated
   deterministically by `SOURCE_DATE_EPOCH=0`.

## Mandatory determinism contract

- Every `write_text(...)` uses `encoding="utf-8", newline=""`.
- The reporter calls a shared `_generated_at()` helper (lifted from
  `json_reporter.py`) for any timestamp; never reimplements
  `SOURCE_DATE_EPOCH` parsing.
- `scripts/generate_docs.py` regenerates the committed example
  alongside the existing `examples/demo-report.*` artefacts;
  `--check` covers the new files for free via the existing
  `_diff_examples` loop.

## Mandatory schema-versioning posture

- `<artefact>_schema_version: "0.1"` is the FIRST field. Frozen
  until a breaking change forces a major bump.
- Additive changes stay at the current version. Consumers MUST
  ignore unknown fields.
- Every nested object that may grow new fields in v0.x+ ships as a
  *one-key object* in v1, never as a scalar — so future fields are
  type-compatible additions, not breaking changes.

## Test floor (do not ship without all of these)

| # | Test                                                          |
|---|---------------------------------------------------------------|
| 1 | golden artefact byte-identical                                |
| 2 | golden manifest byte-identical                                |
| 3 | `SOURCE_DATE_EPOCH` determinism (artefact + manifest)         |
| 4 | manifest validates against bundled JSON Schema                |
| 5 | negative test for any field that MUST stay empty by design    |
| 6 | CLI `--help` snapshot                                         |
| 7 | cross-platform line endings (no `\r` in the bytes)            |
| 8 | packaged-data drift (resource path bytes == source-tree bytes)|
| 9 | `generate_docs.py --check` covers the new artefacts           |

## Adversarial-pass checklist (Noor, stage-4)

Every export-reporter / sidecar-manifest plan MUST walk through the
following before stage-4 sign-off. Missing any one is grounds for
REQUEST_CHANGES; surfacing them in P2 is acceptable when the rest of
the plan is sound.

1. **v+1 additive-evolution walkthrough.** For every nested manifest
   object, write out the v0.6.0 (or next) shape. Verify v0.5.0
   consumers still parse it. Specifically: distinguish *adding keys*
   (consumer-strict-additive) from *extending enum values on existing
   keys* (NOT consumer-strict-additive — old strict validators reject).
   Any enum field that will grow MUST ship with a `description` on the
   schema entry signalling "value set will expand under additive
   `manifest_schema_version` bumps; widen your accepted set."
2. **PII-cleartext rationale anchored to a downstream join.** If any
   field ships in cleartext for an export reporter, the manifest MUST
   carry a typed `pii_handling` mode field signalling it explicitly,
   AND the rationale must be "downstream join requires the cleartext
   value", NOT "we forgot to hash it". Any redaction toggle on the
   upstream report MUST be echoed verbatim into the manifest
   (`source_report.pii_redaction`) so consumers can reason about
   trust.
3. **Hash-input versioning declared up front.** If the export
   computes a join key (e.g. `AdvisoryFindingKey`) from rule output,
   ship a `<thing>_key_version` field on the relevant model NOW with
   default `1`, even if it is not mixed into the hash payload in v1.
   Document the migration path in the manifest's algorithm-string
   field. Cheaper than retrofitting after warehouses have indexed.
4. **Docs-freshness gate covers the new artefact.** Verify the new
   committed example file is picked up by
   `scripts/generate_docs.py --check`'s `_diff_examples` loop and
   `.gitattributes` pins it to LF.
5. **Branch-protection regression check.** Verify the plan does NOT
   add a new top-level CI job that needs registering in the
   `required-checks` summary's `needs:` list (lesson from issue
   #51/#52). Bonus points if new tests live inside an existing job.

## Citations

- Stage-3 plan: `.squad/decisions/inbox/maya-stage3-58-focus-aligned-export.md` (FOCUS-aligned exporter, v0.5.0)
- Cross-platform reporter pattern: `src/finops_assess/reporters/json_reporter.py:97`, `src/finops_assess/reporters/html_reporter.py:89`, `src/finops_assess/reporters/csv_reporter.py:101-110`
- Determinism helper: `src/finops_assess/reporters/json_reporter.py:15-38`
- Docs-freshness gate: `scripts/generate_docs.py:266-278`, `.github/workflows/docs.yml`
- LF-pinning convention: `.gitattributes`
