# §11 Stage-3 Plan — Reporter template overlay with sandbox + manifest provenance (#74)

**Author:** Maya (Lead / FinOps PM) — model: **Opus 4.7**
**Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
**Issue:** #74 — `release:v0.6.0`, `priority:p2`
**Predecessor:** #61 (playbook reporter, v0.5.0) — PR #72 stage-3 plan deferred overlay as OQ-3
**Dependency:** lands after #73 (tenant-stable salt, merged as PR #95)
**Implementer (planned):** Diego (reporter module) + Yuki (tests + docs + golden-fixture pinning)

> This document is the stage-3 plan only. No product code is changed in
> this PR. The implementation PR is a sibling on
> `squad/74-impl-reporter-template-overlay` (Diego, after Noor's stage-4
> verdict).

---

## §1 Research brief

### 1.1 Current wheel-loading path

The v0.5.0 playbook reporter loads templates exclusively from package
data shipped inside the wheel:

| Component | Location | Citation |
|-----------|----------|----------|
| Template root resolver | `_playbook_env.py:57-66` | `_playbook_templates_root()` — uses `importlib.resources.files("finops_assess").joinpath("data").joinpath("playbooks")` |
| Environment factory | `_playbook_env.py:69-104` | `_build_env()` — `FileSystemLoader(root)`, `StrictUndefined`, `autoescape=False`, `keep_trailing_newline=False` |
| Module-level cache | `_playbook_env.py:54,107-117` | `_ENV: Environment | None`, lazy init on first `get_playbook_env()` call |
| Pre-compilation loop | `_playbook_env.py:89-102` | Iterates `playbooks_root.rglob("*.j2")`, calls `env.parse(source)` then `env.get_template(rel)` |
| Template source reader | `playbook.py:295-312` | `_template_source_for_rule()` — reads `.j2` file via `importlib.resources` |
| Render entry point | `playbook.py:359-435` | `render_row()` — builds context, renders, parses sections |
| Manifest builder | `playbook.py:443-513` | `build_playbook_manifest()` — emits `"templates_source": "importlib.resources:finops_assess.data.playbooks"` |
| Template variable extractor | `_playbook_env.py:120-132` | `extract_template_vars()` — AST walk for `Name` nodes |
| Memoised var cache | `playbook.py:339-351` | `_template_vars_cached()` — keyed on `(rule_id, template_source)` to future-proof for overlay |

**Template count (v0.5.0):** 27 shipped `.j2` files across 4 surfaces
(`m365/` × 8, `azure/` × 11, `github/` × 4, `ado/` × 4).

**Template contract:** Section-delimited plaintext/Markdown:
`[TITLE]`, `[DESCRIPTION]`, `[REMEDIATION_STEPS]`,
`[VERIFICATION_CHECKLIST]`, `[REFERENCES]` — parsed by
`playbook.py:226-279` (`_parse_template_output`).

### 1.2 Current manifest schema

The playbook manifest schema is at
`src/finops_assess/schemas/playbook_manifest.schema.json` (v0.1,
`additionalProperties: true`). Key fields:

- `templates_source` (string) — currently the literal
  `"importlib.resources:finops_assess.data.playbooks"`.
- No `template_sources[]` array exists yet.
- No per-template SHA-256 is recorded.

The `additionalProperties: true` policy means adding a new
`template_sources` array key is **additive** and does not require
bumping `playbook_schema_version` from `"0.1"` to `"0.2"`.

### 1.3 Current sandbox posture

**There is no sandbox.** The v0.5.0 `_build_env()` uses
`jinja2.Environment` (not `jinja2.sandbox.SandboxedEnvironment`).
This is safe in v0.5.0 because templates are loaded exclusively from
trusted package data. An operator cannot inject templates at runtime.

### 1.4 Jinja2 sandbox: capabilities and known CVEs

**`jinja2.sandbox.SandboxedEnvironment`** restricts template execution:

- Attribute access is filtered through `is_safe_attribute()` /
  `is_safe_callable()`.
- By default, blocks access to internal attributes (`__subclasses__`,
  `__globals__`, `__builtins__`, etc.) that enable sandbox escape.
- `unsafe_undefined` is available but we will use `StrictUndefined`
  (stricter — raises on any missing variable).

**CVE-2016-10745** (Jinja2 < 2.8.1): sandbox escape via
`str.__class__.__mro__[2].__subclasses__()` chain leading to
`os.popen()`. Fixed by blocking `__subclasses__` attribute access.
Ref: <https://nvd.nist.gov/vuln/detail/CVE-2016-10745>

**CVE-2019-8341** (Jinja2 < 2.10.1): sandbox escape via
`string.Formatter` and `format_map` that bypassed the sandbox's
attribute filter. Fixed by adding `Formatter` to the sandbox deny
list. Ref: <https://nvd.nist.gov/vuln/detail/CVE-2019-8341>

**Mitigation for this project:**

1. Pin `jinja2 >= 3.1.6` (latest stable as of 2025, all CVEs patched).
2. Use `SandboxedEnvironment` for ALL template rendering when overlay
   is enabled (not just overlay templates — avoids a mixed-trust
   environment).
3. Override `is_safe_callable()` to return `False` for everything
   except whitelisted filters — disabling arbitrary callable invocation
   from template expressions entirely.

### 1.5 Disambiguation table

| Term | Definition | Scope |
|------|-----------|-------|
| **Wheel template** | A `.j2` file shipped under `src/finops_assess/data/playbooks/{surface}/{rule_id}.j2` as package data. Trusted. Loaded via `importlib.resources`. | Always available. |
| **Overlay template** | A `.j2` file supplied by the operator at `<overlay_dir>/{surface}/{rule_id}.j2`. Semi-trusted (sandbox-restricted). Loaded via `pathlib.Path` only when `--allow-template-overlay <dir>` is passed. | Opt-in only. |
| **Sandboxed render** | Template rendering via `jinja2.sandbox.SandboxedEnvironment` — blocks attribute introspection, callable invocation, and filesystem access from inside template expressions. Active when overlay is enabled. | When `--allow-template-overlay` flag is present. |
| **Unsandboxed render** | Template rendering via standard `jinja2.Environment` — no runtime restrictions on template expressions. This is v0.5.0 default behavior. | When `--allow-template-overlay` flag is absent. |
| **`template_sources[]`** | New additive manifest array recording every template loaded during export. Each entry has `rule_id`, `surface`, `source` (`"wheel"` or `"overlay"`), and `sha256` (hex digest of the raw `.j2` body). | Present in manifest when overlay enabled; absent (backward-compat) when overlay disabled. |
| **`adapter_hints`** | Per-row nested dict mapping severity to ServiceNow/Jira/GitHub fields. Operator customisation point for ITSM routing — **not** a template concept. | Always present in every playbook row. Unrelated to overlay. |

---

## §2 Rubberduck walkthrough

### 2.1 Approach summary

When `--allow-template-overlay <dir>` is passed:

1. **CLI layer** validates `<dir>` exists and is a directory (fail-fast).
2. **`_playbook_env.py`** builds a `SandboxedEnvironment` instead of
   a plain `Environment`. The `FileSystemLoader` search path is
   `[overlay_dir, wheel_dir]` — overlay first, wheel fallback.
   Jinja2's `FileSystemLoader` natively supports multiple search
   paths with first-match precedence — no custom loader needed.
3. **Pre-flight validation** compiles every `.j2` found in the
   overlay directory and renders each against a fixture `Finding`
   (a synthetic row per surface). Any syntax error or
   `UndefinedError` aborts the entire export before any JSONL is
   written.
4. **`render_row()`** is unchanged — it calls `env.get_template(rel_path)`
   which now resolves through the overlay-first search path.
5. **Manifest** gains an optional `template_sources[]` array.
   Each entry records `rule_id`, `surface`, `source`, and the
   `sha256` of the `.j2` source body that was actually loaded.
6. **`docs/security.md`** (new file) documents the threat model.

When `--allow-template-overlay` is **absent**, behavior is
byte-identical to v0.5.0: plain `Environment`, single-path
`FileSystemLoader`, no `template_sources[]` in manifest.

### 2.2 Edge cases

**E1 — Overlay file has same name but different section markers.**
The template contract requires `[TITLE]`, `[DESCRIPTION]`, etc.
`_parse_template_output` parses whatever is rendered. If an overlay
template omits a section, that field is an empty string — same as
v0.5.0 behavior for a wheel template that happens to omit a section.
Pre-flight catches `StrictUndefined` errors but cannot enforce
section presence at compile time. **Mitigation:** pre-flight render
against fixture finding checks that all 5 sections are non-empty.
If any section is empty, emit a WARNING (not a hard failure) —
an operator may intentionally leave `[REFERENCES]` empty.

**E2 — Overlay directory contains `.j2` files that don't match any
shipped rule_id.** Ignored. Only templates that match a
`{surface}/{rule_id}.j2` pattern for a rule_id actually present in
the findings are loaded. Extra files are inert. Pre-flight logs a
DEBUG for each unmatched overlay template.

**E3 — Overlay directory is empty.** Valid. All templates fall through
to wheel. No `template_sources[]` entries with `source: "overlay"`.

**E4 — Overlay directory contains a symlink to outside the overlay
root.** `pathlib.Path.resolve()` follows symlinks. This is acceptable
because the operator explicitly opted in with
`--allow-template-overlay`. The sandbox prevents the *template
content* from escaping; the *file location* is the operator's
responsibility.

**E5 — Operator templates reference variables not in the render
context.** `StrictUndefined` raises `UndefinedError`. Pre-flight
catches this at export start. Fail-fast.

**E6 — Two operators share a machine with different overlay dirs.**
Each CLI invocation takes its own `--allow-template-overlay <dir>`.
No persistent state. No cross-invocation leakage.

**E7 — Overlay template attempts `{% import os %}` or
`{{ ''.__class__.__mro__[2].__subclasses__() }}`.**
`SandboxedEnvironment` blocks both. Pre-flight render would raise
`SecurityError`. Export aborts.

**E8 — Race condition: overlay file changes between pre-flight and
render.** Templates are loaded into the `FileSystemLoader` cache on
first access. Pre-flight triggers the cache fill. Subsequent
`get_template()` calls hit the cache (Jinja2's `auto_reload=False`
by default when `debug=False`). **Mitigation:** explicitly set
`auto_reload=False` on the `SandboxedEnvironment` so filesystem
changes after pre-flight are ignored for the duration of the export.

**E9 — Overlay template produces extremely large output (DoS).**
Not mitigated in v0.6.0. The sandbox does not limit output size.
Operator-supplied templates are semi-trusted (operator controls both
the template and the CLI invocation). A resource-limit extension is
out of scope.

**E10 — Cross-rule isolation.** Templates are isolated by Jinja2's
per-render scope. One template cannot read variables from another
template's render. No cross-rule data leakage.

### 2.3 Security review — threat model

#### What the operator opts INTO by passing `--allow-template-overlay`:

| Risk | Mitigation |
|------|-----------|
| **Sandbox-restricted code execution** — operator-authored Jinja2 expressions run inside `SandboxedEnvironment`. | Blocks attribute introspection (`__subclasses__`, `__globals__`), `import` statements, and arbitrary callable invocation. `StrictUndefined` prevents accessing unbound variables. |
| **Supply-chain responsibility** — the operator is responsible for the provenance of `.j2` files in `<overlay_dir>`. | Manifest `template_sources[].sha256` provides an immutable record of what was loaded. The operator can audit post-hoc. |
| **No content validation beyond structure** — the sandbox does not validate that the operator's text is accurate, compliant, or non-misleading. | Out of scope. The tool renders what the operator provides. |
| **Template-body hash in manifest** — reveals that an overlay was used and which templates were overridden. | This is intentional (auditability). If confidentiality of the overlay directory is needed, the operator controls manifest distribution. |

#### What the operator does NOT opt into:

| Non-risk | Rationale |
|----------|----------|
| **No signature verification for operator templates.** | OOS per issue #74. There is no certificate chain, HMAC, or GPG signature check. The operator trusts their own filesystem. |
| **No template marketplace / sharing.** | OOS. Templates are local files. |
| **No `{% extends %}` across overlay/wheel boundary.** | OOS. An overlay template replaces the wheel template entirely; it cannot inherit from it. |
| **No env-var or implicit default for overlay dir.** | The flag is CLI-only, no `FINOPS_TEMPLATE_OVERLAY_DIR` env var. This forces explicit opt-in per invocation. |
| **No write paths.** | The tool reads `.j2` files from `<overlay_dir>`. It never writes to that directory. Hard rule #1 holds. |

#### PII guarantee (Hard Rule #4):

Overlay templates render over **the same render context** as wheel
templates. That context is built at `playbook.py:387-398`
(`render_row`), where `principal` is already the engine-redacted value
(salted hash or cleartext depending on `--no-pii-redaction`). The
overlay template cannot access raw PII because it was never present in
the render context — redaction happens in the engine before findings
reach the reporter. **No new PII exposure path.**

#### Cross-rule isolation matrix:

| Scenario | Overlay disabled | Overlay enabled |
|----------|-----------------|-----------------|
| Template loaded from wheel | ✅ v0.5.0 identical | ✅ Same (fallback path) |
| Template loaded from overlay | N/A | ✅ Sandboxed, SHA-256 recorded |
| Manifest `templates_source` field | `"importlib.resources:…"` | `"importlib.resources:…"` (legacy field unchanged) |
| Manifest `template_sources[]` array | **Absent** (backward-compat) | Present with per-template entries |
| Row schema | Unchanged | Unchanged |
| Pre-flight validation | Yes (wheel only) | Yes (wheel + overlay) |

**v0.5.0 backward compatibility:** With overlay disabled, zero code
paths change. The plain `Environment` is used, `template_sources[]` is
not emitted, and the manifest `templates_source` scalar remains
`"importlib.resources:…"`. Byte-identical output.

### 2.4 False-positive risks of pre-flight render

Pre-flight renders each overlay template against a **synthetic fixture
finding** (one per surface). Risks:

- **Fixture finding may lack evidence keys that real findings carry.**
  Mitigation: the fixture includes the superset of all evidence keys
  used by shipped templates (extracted via `extract_template_vars`
  across all wheel templates). Overlay templates referencing novel
  evidence keys will fail pre-flight — this is correct behavior
  (`StrictUndefined`).
- **Fixture finding may carry evidence keys that some real findings
  lack.** Not a risk — `StrictUndefined` only fires on *missing*
  keys, not extra keys.
- **Performance:** Pre-flight compiles + renders ≤ N overlay templates
  (N = number of `.j2` files in overlay dir). Even at 100 templates,
  this is sub-second. No performance concern.

---

## §3 Implementation plan

### 3.1 File-level changes

| # | File | Change | Notes |
|---|------|--------|-------|
| F1 | `src/finops_assess/reporters/_playbook_env.py` | Add `build_sandboxed_env(wheel_root, overlay_root)` function. Returns `SandboxedEnvironment` with `FileSystemLoader([overlay_root, wheel_root])`, `StrictUndefined`, `auto_reload=False`. Override `is_safe_callable()` to whitelist only built-in Jinja2 filters. | New function; existing `_build_env()` and `get_playbook_env()` unchanged. |
| F2 | `src/finops_assess/reporters/_playbook_env.py` | Add `get_playbook_env(overlay_dir: Path | None = None)` parameter. When `overlay_dir` is `None`, behavior is identical to v0.5.0. When non-`None`, calls `build_sandboxed_env()`. Cache keyed on `(overlay_dir,)` so re-invocations with same dir reuse the env. | Backward-compatible signature change (default `None`). |
| F3 | `src/finops_assess/reporters/_playbook_env.py` | Add `preflight_validate(env, overlay_dir, fixture_findings)` function. Compiles + renders every `.j2` in overlay_dir against fixture findings. Returns `list[PreflightResult]` with pass/fail per template. Raises on any failure (fail-fast). | New function. |
| F4 | `src/finops_assess/reporters/playbook.py` | Add `overlay_dir: Path | None = None` parameter to `render_row()` and `write_playbook_export()`. Thread overlay_dir through to `get_playbook_env()`. | Backward-compatible (default `None`). |
| F5 | `src/finops_assess/reporters/playbook.py` | In `write_playbook_export()`, call `preflight_validate()` before rendering any rows when `overlay_dir` is not `None`. | New code block before the render loop. |
| F6 | `src/finops_assess/reporters/playbook.py` | Add `_build_template_sources(rows, env, overlay_dir)` helper that iterates rendered rule_ids, reads each template source, computes SHA-256, and records `source: "wheel" | "overlay"` based on which search path resolved. | New helper. |
| F7 | `src/finops_assess/reporters/playbook.py` | In `build_playbook_manifest()`, accept optional `template_sources: list[dict] | None`. When non-`None`, include in manifest. When `None`, omit (backward-compat). | Additive parameter, backward-compatible. |
| F8 | `src/finops_assess/schemas/playbook_manifest.schema.json` | Add optional `template_sources` property (array of objects with `rule_id`, `surface`, `source`, `sha256`). No change to `required` list. `additionalProperties: true` already permits this. | Additive schema change. |
| F9 | `src/finops_assess/cli.py` | Add `--allow-template-overlay` option (type `click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True)`) to `export` command. Thread `overlay_dir` to `write_playbook_export()`. | New CLI flag. |
| F10 | `docs/security.md` | New file. Threat model from §2.3 above, expanded with operator guidance: how to audit `template_sources[]`, how to pin overlay templates via sha256 in CI, what the sandbox blocks, what it doesn't. | New doc. |
| F11 | `docs/user-guide.md` | Add "Template overlay" section: CLI usage, directory layout, pre-flight behavior, manifest provenance. | Doc update. |
| F12 | `CHANGELOG.md` | v0.6.0 entry for template overlay feature. | Doc update. |
| F13 | `README.md` | One-line mention in features list. | Doc update if needed. |
| F14 | `tests/test_playbook_overlay.py` | New test file (see §3.4 test plan). | New test file. |
| F15 | `tests/fixtures/overlay/` | Fixture overlay templates for tests (valid, invalid-syntax, sandbox-escape-attempt, missing-section). | New fixture directory. |

### 3.2 Schema changes (additive only)

**Manifest `template_sources[]`** — new optional array:

```json
{
  "template_sources": [
    {
      "rule_id": "M365.UNUSED_LICENSE_30D",
      "surface": "m365",
      "source": "overlay",
      "sha256": "a1b2c3d4..."
    },
    {
      "rule_id": "AZ.IDLE_VM_14D",
      "surface": "azure",
      "source": "wheel",
      "sha256": "e5f6a7b8..."
    }
  ]
}
```

Schema additions to `playbook_manifest.schema.json`:

```json
"template_sources": {
  "type": "array",
  "description": "Per-template provenance. Present only when --allow-template-overlay is used. Each entry records which template was loaded and its SHA-256 body hash.",
  "items": {
    "type": "object",
    "required": ["rule_id", "surface", "source", "sha256"],
    "additionalProperties": false,
    "properties": {
      "rule_id": { "type": "string" },
      "surface": { "type": "string" },
      "source": { "type": "string", "enum": ["wheel", "overlay"] },
      "sha256": {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$",
        "description": "SHA-256 hex digest of the raw .j2 template body (UTF-8 bytes)."
      }
    }
  }
}
```

**No changes to `playbook_schema_version`** — this is additive under
the `additionalProperties: true` contract documented in the schema
description.

**No changes to `playbook_row.schema.json`** — the row schema is
unchanged; overlay only affects which template renders the row.

### 3.3 Sandbox configuration detail

```python
from jinja2.sandbox import SandboxedEnvironment

class _RestrictedSandbox(SandboxedEnvironment):
    """SandboxedEnvironment with additional restrictions for operator templates."""

    def is_safe_callable(self, obj: object) -> bool:
        """Block all callables except Jinja2 built-in filters."""
        # SandboxedEnvironment.is_safe_callable already blocks most
        # dangerous callables. We further restrict to deny all callables
        # that are not Jinja2 filters registered on this environment.
        return False

    def call(__self, __context, __obj, *args, **kwargs):  # type: ignore[override]
        """Override call to enforce is_safe_callable on every invocation."""
        if not __self.is_safe_callable(__obj):
            raise SecurityError(f"Calling {__obj!r} is not permitted in sandboxed templates.")
        return super().call(__context, __obj, *args, **kwargs)
```

Configuration:

- `undefined=StrictUndefined`
- `autoescape=False` (matches v0.5.0 — plaintext output)
- `keep_trailing_newline=False`
- `auto_reload=False` (freeze after pre-flight)
- `loader=FileSystemLoader([overlay_dir, wheel_dir], encoding="utf-8")`

### 3.4 Test plan

All tests in `tests/test_playbook_overlay.py`:

| # | Test | Acceptance criterion | Notes |
|---|------|---------------------|-------|
| T1 | `test_overlay_precedence` | Overlay template shadows wheel template for same `{surface}/{rule_id}.j2`. Rendered output uses overlay content. | AC (a) |
| T2 | `test_overlay_missing_falls_through_to_wheel` | If overlay dir exists but lacks a template for a rule_id, wheel template is used. | AC (d) |
| T3 | `test_sandbox_blocks_import` | Overlay template with `{% import os %}` raises `SecurityError` at pre-flight. Export aborts. | AC (b) |
| T4 | `test_sandbox_blocks_file_io` | Overlay template with `{{ ''.__class__.__mro__[2].__subclasses__() }}` raises `SecurityError`. | AC (b) |
| T5 | `test_sandbox_blocks_callable` | Overlay template with `{{ lipsum() }}` or custom callable is blocked by `is_safe_callable() → False`. | AC (b) extension |
| T6 | `test_syntax_error_fail_fast` | Overlay template with `{% if %}` (invalid syntax) raises `TemplateSyntaxError` at pre-flight. Export does not write any JSONL. | AC (c) |
| T7 | `test_undefined_var_fail_fast` | Overlay template referencing `{{ nonexistent_var }}` raises `UndefinedError` at pre-flight render. | AC (c) extension |
| T8 | `test_manifest_provenance_overlay` | When overlay is used, manifest contains `template_sources[]` with correct `source: "overlay"` and `sha256` matching the overlay `.j2` body. | AC (e) |
| T9 | `test_manifest_provenance_wheel` | When overlay is used but a specific rule_id has no overlay, `template_sources[]` records `source: "wheel"` with correct sha256. | AC (e) |
| T10 | `test_manifest_absent_without_overlay` | When `--allow-template-overlay` is not passed, manifest does NOT contain `template_sources` key. | Invariant #5 |
| T11 | `test_default_behavior_byte_identical` | Run export without overlay; output is byte-identical to v0.5.0 (same fixture input, same `SOURCE_DATE_EPOCH`, same `--no-pii-redaction`). | Invariant #5 |
| T12 | `test_overlay_dir_not_exists_fails` | Passing `--allow-template-overlay /nonexistent` fails at CLI validation (Click `exists=True`). | Fail-fast |
| T13 | `test_pii_not_leaked_through_overlay` | Overlay template accessing `{{ principal }}` gets the redacted value (salted hash), not raw UPN. Verified by checking rendered output against engine redact output. | Invariant #2 (Hard Rule #4) |
| T14 | `test_preflight_empty_overlay_dir` | Empty overlay dir: all templates fall through to wheel, export succeeds, no `source: "overlay"` entries in manifest. | E3 |
| T15 | `test_overlay_section_warning` | Overlay template missing `[REFERENCES]` section: pre-flight emits WARNING, export proceeds (not a hard failure). | E1 |

### 3.5 Pre-flight validation flow

```
CLI parses --allow-template-overlay <dir>
  → validate dir exists (Click type=Path)
  → build SandboxedEnvironment with [overlay_dir, wheel_dir]
  → for each .j2 in overlay_dir:
      1. env.parse(source)           # syntax check
      2. tmpl = env.get_template(rel) # cache fill
      3. rendered = tmpl.render(**fixture_finding)  # StrictUndefined check
      4. parsed = _parse_template_output(rendered)  # section presence check
      5. if any required section empty: log WARNING
  → if any step 1-3 raised: raise PlaybookPreflightError (fail-fast)
  → proceed to normal render loop
```

**Fail-fast alignment:** v0.5.0 raises `PlaybookTemplateNotFoundError`
if a shipped rule has no template. v0.6.0 extends this: pre-flight
failures for overlay templates also abort the entire export. The
operator's contract is: if you supply an overlay dir, every `.j2` in
it must compile and render cleanly, or the export does not proceed.

### 3.6 Doc-regen impact

| Doc | Update needed? | What changes |
|-----|---------------|--------------|
| `docs/security.md` | **New file** | Threat model from §2.3 |
| `docs/user-guide.md` | Yes | Template overlay section |
| `CHANGELOG.md` | Yes | v0.6.0 entry |
| `README.md` | Maybe | Feature mention |
| `docs/plan.md` | Yes | One-line summary in appropriate section |
| `docs/schema.md` | Yes if exists | `template_sources[]` schema |
| `docs/rules.md` | No | Rules unchanged |
| Sample reports | No | Samples don't use overlay |

### 3.7 Out of scope

| Item | Rationale | Disposition |
|------|-----------|-------------|
| Operator template marketplace / sharing | Complexity, security surface | Deferred indefinitely |
| Signing / verification chain for operator templates | sha256 in manifest is audit, not verification | Future issue if demand arises |
| `{% extends %}` across overlay/wheel boundary | Partial inheritance complicates sandbox, template contract | Rejected per issue #74 |
| Env-var for overlay dir (`FINOPS_TEMPLATE_OVERLAY_DIR`) | Forces explicit per-invocation opt-in | Rejected by design |
| Output size limits in sandbox | Operator is semi-trusted; DoS against oneself | Future hardening |
| Direct API push / remediation | #63 territory | Separate issue |
| Sandbox for wheel templates in default mode | Unnecessary (wheel templates are trusted) | Rejected |

### 3.8 Decision summary

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use `SandboxedEnvironment` ONLY when overlay is enabled | Avoids performance overhead for default path; wheel templates are trusted. |
| D2 | `FileSystemLoader([overlay, wheel])` for overlay precedence | Jinja2's native multi-path search eliminates custom loader code. |
| D3 | `auto_reload=False` to freeze templates after pre-flight | Prevents TOCTOU between pre-flight and render. |
| D4 | `template_sources[]` is optional in manifest schema | Backward-compat: absent when overlay disabled, present when enabled. |
| D5 | SHA-256 of raw `.j2` body (UTF-8 bytes), not rendered output | Raw body is deterministic; rendered output varies per finding. |
| D6 | Pre-flight renders against synthetic fixture findings | Tests real Jinja2 execution, not just syntax. Catches `StrictUndefined` errors. |
| D7 | No env-var, no implicit overlay path | Explicit opt-in per invocation. Security posture. |
| D8 | Override `is_safe_callable() → False` | Maximum restriction. Operator templates use variable substitution and filters only. |
| D9 | New `docs/security.md` for threat model | Separates security documentation from user guide. Referenced from `--help` text. |

---

## §4 Plan invariants (Noor verification checklist)

These invariants are numbered to match the task specification. Noor
MUST verify each one in the stage-4 adversarial review.

| # | Invariant | How the plan satisfies it |
|---|-----------|--------------------------|
| I1 | **Hard Rule #1 (read-only) holds** | Overlay loading reads `.j2` files from `<overlay_dir>` via `pathlib.Path.read_text()`. No write paths. `write_playbook_export()` only writes to the output JSONL/manifest — same as v0.5.0. CLI flag type `Path(exists=True, file_okay=False)` prevents directory creation. |
| I2 | **Hard Rule #4 (PII redaction) holds** | Overlay templates receive the same render context as wheel templates (`playbook.py:387-398`). `principal` is already redacted by the engine before it reaches the reporter. No new PII exposure path. Test T13 verifies this. |
| I3 | **Sandbox is real** | `SandboxedEnvironment` with `StrictUndefined`, `is_safe_callable() → False`, no `import_module`. Tests T3, T4, T5 verify sandbox enforcement. |
| I4 | **Manifest provenance is byte-accurate** | `sha256` is computed from `template_source.encode("utf-8")` (raw `.j2` body). Computed for EVERY loaded template, wheel or overlay. Tests T8, T9 verify provenance correctness. |
| I5 | **Default behavior unchanged** | When `--allow-template-overlay` is absent: plain `Environment` (not sandboxed), single-path `FileSystemLoader`, no `template_sources[]` in manifest. Test T10, T11 verify byte-identical output. |
| I6 | **Threat model documented** | `docs/security.md` (F10) contains the threat model from §2.3. |
| I7 | **Pre-flight validation** | `preflight_validate()` (F3) compiles + renders every overlay `.j2` before export proceeds. Fail-fast on syntax error, undefined variable, or sandbox violation. Tests T6, T7, T3 verify. |
| I8 | **Test plan covers all 5 acceptance criteria** | T1 (precedence), T3+T4 (sandbox-blocks), T6 (syntax-error-fail-fast), T2 (missing-overlay-falls-through), T8+T9 (manifest-provenance). |

---

## §5 Stage-5 implementer guidance (Diego)

1. Start from `_playbook_env.py` (F1-F3) — the sandbox environment
   factory is the foundation.
2. Thread `overlay_dir` through `playbook.py` (F4-F7) — keep the
   `None` default path exercising v0.5.0 code exclusively.
3. Wire CLI flag (F9) last — the reporter must work before the CLI
   exposes it.
4. Pre-flight fixture: build a `_FIXTURE_FINDINGS` dict in
   `_playbook_env.py` containing one synthetic `Finding`-shaped dict
   per surface, with all evidence keys extracted from shipped
   templates via `extract_template_vars`. This makes pre-flight
   independent of the operator's actual findings.
5. Golden-fixture regeneration: if manifest structure changes (even
   additive), regenerate golden fixtures per the squad decision on
   PR #95.
6. `jinja2 >= 3.1.6` version pin: add to `pyproject.toml`
   `[project.dependencies]` if not already pinned.
7. Reviewer Rejection Lockout applies: if Noor stage-4 rejects the
   implementation PR, Diego is locked out and Yuki picks up revision.
