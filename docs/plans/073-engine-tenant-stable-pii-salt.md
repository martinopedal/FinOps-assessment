# §11 Stage-3 Plan: Engine tenant-stable PII salt mode (#73)

> **Author:** Maya (Lead / FinOps PM), model: **Opus 4.7**
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #73, release `release:v0.6.0`, priority `priority:p1`
> **Branch (this plan):** `squad/73-plan-tenant-stable-pii-salt`
> **Branch (implementation):** `squad/73-impl-tenant-stable-pii-salt` (Diego, post-Noor)
> **Implementer:** Diego (primary), Yuki backup
> **Adversarial reviewer:** Noor (stage-4)
> **Producer-path SHA:** current `main` at time of writing

This plan covers the **engine-level** architectural change that introduces
a tenant-stable PII salt mode.  Today, `RuleContext.redact()` uses a
per-run `secrets.token_hex(16)` salt, making principal hashes unstable
across runs.  Issue #73 adds an operator-controlled salt path so that
principal hashes are deterministic across reruns for the same tenant.

**Headlines:**

1. The default behaviour (per-run random salt) is **unchanged**.
   Operators must explicitly opt in via `--pii-salt-file <path>` or
   `FINOPS_PII_SALT` env var.
2. **No new scopes** — hard rule #1 upheld; this is pure engine logic.
3. **Backward-compatible** — no schema breaking changes, existing tests
   continue to pass, existing CSVs and reports load without modification.
4. Unblocks #16 (cross-run idempotency) and #63 (remediation-PR drafter)
   for M365/GitHub/ADO surfaces.
5. Rotate-without-breaking-tickets (`previous_salts[]`) is **out of scope**
   per issue #73 body.

---

## Section 1: Stage-1 Research brief

### 1.1 Disambiguation: salt modes

This section disambiguates the four modes that can coexist after this
change, binding each to a concrete code path.

| # | Mode | Salt source | Principal stability | When active | Code path (current or proposed) |
|---|------|-------------|--------------------|----|-----|
| S1 | **Per-run rotation** (current default) | `secrets.token_hex(16)` | Same within a run; different across runs | `--pii-salt-file` not set AND `FINOPS_PII_SALT` not set | `engine.py:151` — `salt_value = salt if salt is not None else secrets.token_hex(16)` |
| S2 | **Tenant-stable** (new) | File contents from `--pii-salt-file` or `FINOPS_PII_SALT` env var | Identical across runs for same tenant (same salt) | Operator opts in via CLI flag or env var | Proposed: `cli.py` resolves salt → passes to `run_rules(salt=resolved)` |
| S3 | **Operator-supplied salt** (test/programmatic) | `run_rules(salt="...")` API kwarg | Deterministic (caller controls) | Direct API usage (tests, scripts) | `engine.py:137` — `salt: str | None = None` parameter |
| S4 | **No redaction** | N/A | Cleartext principals (no hashing) | `--no-pii-redaction` | `engine.py:72` — `if not self.redact_pii: return principal` |

**Key invariant:** S1 and S2 are mutually exclusive at the CLI level.
S3 is the underlying API mechanism that both S1 and S2 use.  S4 bypasses
the salt path entirely.

**Precedence rule (highest to lowest):**
1. `--no-pii-redaction` → mode S4 (no hashing at all)
2. `--pii-salt-file <path>` → mode S2 (file contents are the salt)
3. `FINOPS_PII_SALT` env var → mode S2 (env var value is the salt)
4. Neither set → mode S1 (per-run random, current default)

If both `--pii-salt-file` and `FINOPS_PII_SALT` are present,
`--pii-salt-file` wins (explicit flag over ambient env).

### 1.2 Current `RuleContext.redact()` implementation

**File:** `src/finops_assess/engine.py:70-75`

```python
def redact(self, principal: str) -> str:
    """Return either the raw principal or a salted SHA-256 of it."""
    if not self.redact_pii:
        return principal
    digest = hashlib.sha256(f"{self.salt}:{principal}".encode()).hexdigest()
    return f"sha256:{digest[:16]}"
```

- Hash algorithm: SHA-256, truncated to first 16 hex chars (64 bits of output).
- Format: `sha256:<16-hex-chars>`.
- Salt is concatenated with `:` separator before the principal.
- The 64-bit truncation is a deliberate collision-tolerance vs readability
  tradeoff; it yields ~2^32 birthday-bound, which is well beyond any
  realistic tenant size.  No change proposed.

**File:** `src/finops_assess/engine.py:151`

```python
salt_value = salt if salt is not None else secrets.token_hex(16)
```

- `salt` parameter is `str | None`, defaulting to `None`.
- When `None`, a 16-byte (128-bit) random hex string is generated.
- The salt is never logged, never included in the report (only the
  `pii_redaction: true/false` flag surfaces in the JSON report).

### 1.3 Callsite survey: `ctx.redact(...)` across all rule implementations

Every callsite passes either a `principal` (UPN/username), a
`resource_id` (ARM path), or an `org` name to `ctx.redact()`.

| Surface | File | Line(s) | Redacted value | Notes |
|---------|------|---------|----------------|-------|
| M365 | `rules_impl/m365_rules.py` | 103, 108, 158, 166, 202, 207, 239, 244, 276, 281, 309, 314, 348, 353, 416, 422 | `assignment.principal` or `principal` (UPN) | 16 callsites across 8 rule impls. All pass UPNs. |
| Azure | `rules_impl/azure_rules.py` | 42, 47, 79, 84, 115, 120, 143, 149, 181, 186, 218, 222, 281, 286, 360, 365, 368, 377, 431, 436, 538, 543, 634, 642, 647, 652 | `resource.resource_id`, `reservation.reservation_id`, `workspace.workspace_id`, `rec.scope`, `sub_id` | 26 callsites across 10 rule impls. All pass Azure resource paths, not UPNs. |
| GitHub | `rules_impl/github_rules.py` | 58, 63, 103, 108, 143, 202 | `seat.principal` (username) or `org.org` | 6 callsites across 4 rule impls. |
| ADO | `rules_impl/ado_rules.py` | 57, 62, 102, 107, 145, 193, 199 | `seat.principal` or `org.org` | 7 callsites across 4 rule impls. |
| Reporters | `reporters/focus_aligned.py` | 290 (docstring only) | N/A | Documents the contract, no call. |
| Reporters | `reporters/playbook.py` | 458 (docstring only) | N/A | Documents the contract, no call. |

**Total:** 55 `ctx.redact()` callsites in rule implementations.  Zero
callsites need to change — the salt-source change is entirely in the
engine and CLI layers.

### 1.4 Implications for stable-vs-rotating semantics

**Azure surface:** `resource_id` is an ARM path like
`/subscriptions/.../resourceGroups/.../providers/...`.  When salt is
tenant-stable, the redacted `resource_id` becomes stable across runs.
This is *desirable* — it enables the FOCUS-aligned reporter's
`AdvisoryFindingKey` to be a cross-run join key.

**M365 / GitHub / ADO surfaces:** `principal` is a UPN or username.
When salt is tenant-stable, the redacted principal becomes stable across
runs.  This is the *primary motivation* for #73 — it enables cross-run
ticket dedup for these surfaces.

**Cross-surface isolation:** All surfaces share the same salt instance
within a run (a single `RuleContext.salt` value).  This is correct —
the salt's purpose is to prevent rainbow-table reversal, not to isolate
surfaces from each other.  A finding's `surface` field already
distinguishes origin.

### 1.5 Existing test coverage (redaction-related)

| Test file | Test name | What it covers |
|-----------|-----------|----------------|
| `tests/test_engine.py:108` | `test_pii_redaction_hashes_principals` | Verifies no raw UPNs leak under `redact_pii=True` with explicit salt |
| `tests/test_az_commitment_under_covered.py:373` | `test_commitment_under_covered_redacted_principal_unstable_across_runs` | Two runs with no shared salt → different principals (regression gate) |
| `tests/test_az_savings_plan_eligible.py:202` | `test_savings_plan_redacts_principal_by_default` | Redacted principals start with `sha256:` |
| `tests/test_az_commitment_renewal_review.py:244` | `test_renewal_review_redacts_principal_by_default` | Same pattern |
| `tests/test_az_reservation_scope_mismatch.py:449` | `test_pii_redaction_hashes_sub_ids` | Sub IDs are hashed |
| `tests/test_cli_run.py:32` | `test_run_default_redaction_hashes_principals` | CLI-level: default redaction works |
| `tests/test_playbook_cross_run_stability.py:140` | `test_azure_ticket_key_per_run_under_default_redaction` | Playbook ticket_key rotates under default redaction |
| `tests/test_playbook_cross_run_stability.py:176` | `test_azure_ticket_key_stable_when_redaction_off` | Playbook ticket_key stable when redaction off |
| `tests/test_playbook_pii_warning.py:178` | `test_no_pii_warning_when_redaction_off` | No stderr warning when redaction off |
| `tests/test_playbook_pii_warning.py:250` | `test_manifest_pii_mode_cleartext_when_redaction_off` | Manifest `pii_handling.mode` = `cleartext` |
| `tests/test_focus_aligned_reporter.py:448` | `test_manifest_echoes_source_pii_redaction_flag` | FOCUS manifest echoes pii_redaction |

**Impact:** All existing tests pass unchanged because the default path
(no salt file, no env var) still produces a per-run random salt.  The
cross-run-instability regression tests
(`test_commitment_under_covered_redacted_principal_unstable_across_runs`)
continue to verify the per-run default.

---

## Section 2: Stage-2 Rubberduck walkthrough

### 2.1 Plain-English walkthrough

The change is a three-layer stack:

1. **CLI layer** (`cli.py`): Add a `--pii-salt-file` option and read
   the `FINOPS_PII_SALT` environment variable.  Resolve the salt string
   from whichever source has precedence (§1.1 table).  Pass the
   resolved salt (or `None` for per-run) into `_execute_assessment()`.

2. **Engine layer** (`engine.py`): `_execute_assessment()` threads the
   salt through to `run_rules(salt=...)`.  The existing
   `salt_value = salt if salt is not None else secrets.token_hex(16)`
   at line 151 already does the right thing — if a salt is provided,
   it's used; otherwise a random one is generated.

3. **Reporter layer** (`reporters/playbook.py`, `reporters/focus_aligned.py`):
   Update the `pii_handling` manifest block to reflect `salt_mode`:
   `"tenant_stable"` when an operator-supplied salt is in effect,
   `"per_run"` when the default random salt is used.  Update
   `ticket_key_stability_by_surface` accordingly and clear the
   `known_limitation` string when tenant-stable.

4. **Logging:** When tenant-stable mode is active, emit a single
   `INFO`-level log line: `"PII salt mode: tenant_stable (source:
   {file|env})"`.  When per-run: `"PII salt mode: per_run"`.  Never
   log the salt value itself.

### 2.2 Edge cases

| # | Edge case | Behaviour | Rationale |
|---|-----------|-----------|-----------|
| E1 | `--pii-salt-file` points to a nonexistent path | `click.BadParameter` — CLI refuses to run | Fail-fast; operator must fix before assessment runs |
| E2 | Salt file exists but is empty (0 bytes) | `click.BadParameter` — CLI refuses to run | Empty salt = no entropy = effectively no protection |
| E3 | Salt file contains < 32 hex chars of entropy | Warning to stderr: "Salt has low entropy (< 128 bits); consider regenerating with `python -c 'import secrets; print(secrets.token_hex(32))'`" | Not a hard error — operator may have a reason, but we warn |
| E4 | Salt file contains newlines / trailing whitespace | Strip all leading/trailing whitespace; use the stripped content | Common foot-gun when operators `echo secret > file` |
| E5 | `FINOPS_PII_SALT` env var is set but empty | Treated as unset → fall through to per-run mode | Empty string has no entropy; safer to ignore |
| E6 | Both `--pii-salt-file` and `FINOPS_PII_SALT` are set | `--pii-salt-file` wins; env var ignored; INFO log notes the override | Explicit flag beats ambient environment |
| E7 | `--pii-salt-file` and `--no-pii-redaction` both set | `--no-pii-redaction` wins; salt file is unused; WARNING log: "Salt file is ignored because PII redaction is disabled" | No-redaction is the strongest opt-out; salt has no effect |
| E8 | Salt file permissions are world-readable (Unix) | Warning to stderr: "Salt file is world-readable; consider restricting to owner-only (chmod 600)" | Advisory only — we can't enforce on Windows; cross-platform compromise |
| E9 | Salt file is > 1 MiB | `click.BadParameter` — refuse to read | Prevents accidental `--pii-salt-file /dev/urandom` or similar |
| E10 | Operator rotates salt between runs | Expected: all principal hashes change. No migration path in this PR. Documented in user-guide. | Rotation is a follow-on (#73 OOS "rotate-without-breaking-tickets") |

### 2.3 False-positive risks

This change does not alter any rule logic.  Rules see `ctx.redact()`
and `ctx.salt` exactly as before — the only difference is who chose
the salt value.  Therefore:

- **No new false positives** — rule evaluation is salt-independent.
- **No changed findings** — same input → same findings (different
  principal hashes unless salt is identical, but the finding set
  is identical by rule_id + evidence).

### 2.4 Cross-rule isolation matrix

| Rule surface | `principal` source | Stable under S2? | Breaking change? |
|---|---|---|---|
| M365 (all 8 rules) | UPN from `assignment.principal` | ✅ Yes — same salt → same hash | No — rules never compare principals across runs |
| Azure (10 rules) | ARM resource ID | ✅ Yes — already stable semantically; hash now also stable | No |
| GitHub (4 rules) | Username from `seat.principal` or `org.org` | ✅ Yes | No |
| ADO (4 rules) | Username from `seat.principal` or `org.org` | ✅ Yes | No |

**No rule implementation reads `ctx.salt` directly** — they all go
through `ctx.redact()`.  The salt-source change is invisible to rules.

### 2.5 Security review: threat model

#### Current threat model (S1 — per-run rotation)

- **Salt is ephemeral** — 128 bits of `secrets.token_hex(16)`, lives only
  in process memory for the duration of a run, never persisted.
- **If the report leaks:** an attacker sees `sha256:xxxxxxxxxxxxxxxx`
  prefixes.  Without the salt, they cannot reverse the hash even for a
  known-plaintext UPN set (the tenant's directory).
- **If the salt leaks (somehow):** the attacker can reconstruct the
  principal→hash mapping for that single run.  But the salt is never
  persisted, so "leaking" requires memory dump or a compromised process.

#### New threat model (S2 — tenant-stable)

- **Salt is persistent** — stored in a file or environment variable
  controlled by the operator.  Lives on disk or in the process
  environment across runs.
- **If the report leaks:** same as S1 — without the salt, reversal
  requires brute force against the truncated 64-bit hash space (feasible
  for a known-directory enumeration, but the salt adds 128+ bits of
  pre-image resistance).
- **If the salt leaks:** an attacker with salt + report can reconstruct
  the full `principal → hash` mapping for *every run that used that
  salt*.  This is strictly worse than S1, where a salt leak only exposes
  one run.
- **Mitigation:** The salt file is a *tenant secret* — the operator must
  protect it as they would a database encryption key:
  - Store it in a secrets manager (Key Vault, GitHub Secrets) and inject
    at runtime.
  - On-disk files: restrict to owner-read-only (`chmod 600` on Unix;
    ACL on Windows).
  - Never commit to source control.
  - Rotate periodically (follow-on issue from #73).
- **Residual risk accepted:** an operator who opts into tenant-stable mode
  is making an informed trade: cross-run idempotency in exchange for a
  wider blast radius if the salt is compromised.  The default remains
  per-run rotation, which is strictly safer for one-off assessments.

#### "If salt leaks, what's exposed" summary

| What leaks | S1 (per-run) | S2 (tenant-stable) |
|---|---|---|
| Report only | Pseudonymised — safe | Pseudonymised — safe |
| Report + salt | De-pseudonymise ONE run's principals | De-pseudonymise ALL runs' principals for that salt |
| Report + salt + tenant directory | Full re-identification for one run | Full re-identification for all runs |

**Conclusion:** The threat-model delta is real but bounded.  The operator
explicitly opts in, the default is unchanged, and the docs must clearly
state the tradeoff.

### 2.6 Reporter manifest impact

The playbook and FOCUS-aligned reporters both embed a `pii_handling`
block that currently hard-codes `"per_run"` stability for all surfaces
when PII redaction is on.  After this change:

- When salt mode is S2 (tenant-stable): `ticket_key_stability_by_surface`
  → `"stable"` for all surfaces; `known_limitation` → `None`.
- When salt mode is S1 (per-run): behaviour unchanged; `"per_run"` for
  all surfaces; `known_limitation` references #73 as today.
- A new `salt_mode` field is added: `"per_run"` or `"tenant_stable"`.

### 2.7 Wording decisions

- The CLI flag is `--pii-salt-file` (not `--tenant-salt`, not
  `--salt-file`).  Rationale: anchors the flag to the PII redaction
  feature namespace; `--tenant-salt` implies tenant-ID which is wrong.
- The env var is `FINOPS_PII_SALT` (not `FINOPS_TENANT_SALT`).
  Rationale: same namespace consistency.
- The manifest field is `salt_mode` with values `"per_run"` or
  `"tenant_stable"`.

---

## Section 3: Implementation plan

### 3.1 File-level changes

| # | File | Change | Lines (est.) |
|---|------|--------|-------------|
| F1 | `src/finops_assess/cli.py` | Add `--pii-salt-file` option to `run` and `demo` commands; resolve salt from file / env var / default; thread through `_execute_assessment(salt=...)` | ~40 |
| F2 | `src/finops_assess/cli.py` | Add `_resolve_pii_salt()` helper: precedence logic, file read, validation (E1–E9), entropy warning | ~50 |
| F3 | `src/finops_assess/engine.py` | No functional change. Add `salt_mode` to the `summary` dict returned by `run_rules()`: `"tenant_stable"` when caller provides salt, `"per_run"` when engine generates one. Log the mode at INFO. | ~8 |
| F4 | `src/finops_assess/reporters/json_reporter.py` | Surface `salt_mode` from summary in the report's `run` block | ~3 |
| F5 | `src/finops_assess/reporters/playbook.py` | Read `salt_mode` from report; when `"tenant_stable"`, set stability → `"stable"`, clear `known_limitation` | ~15 |
| F6 | `src/finops_assess/reporters/focus_aligned.py` | Same as F5 for the FOCUS-aligned manifest | ~15 |
| F7 | `tests/test_engine.py` | Add: `test_salt_mode_reported_as_tenant_stable_when_salt_provided`, `test_salt_mode_reported_as_per_run_when_no_salt` | ~25 |
| F8 | `tests/test_pii_salt_resolution.py` (new) | Unit tests for `_resolve_pii_salt()`: E1–E10 edge cases, precedence logic, entropy warning | ~120 |
| F9 | `tests/test_playbook_cross_run_stability.py` | Add: `test_ticket_key_stable_across_runs_with_tenant_stable_salt` — two `run_rules()` calls with same salt → identical principals | ~30 |
| F10 | `tests/test_playbook_cross_run_stability.py` | Add: `test_manifest_salt_mode_tenant_stable` — manifest reflects mode | ~15 |
| F11 | `tests/test_focus_aligned_reporter.py` | Add: `test_focus_manifest_salt_mode_tenant_stable` | ~15 |
| F12 | `tests/test_cli_run.py` | Add: `test_run_with_pii_salt_file_produces_stable_hashes`, `test_run_with_pii_salt_env_produces_stable_hashes` | ~40 |
| F13 | `docs/user-guide.md` | New section: "Tenant-stable PII salt mode" — setup, threat model summary, rotation guidance | ~40 lines prose |
| F14 | `docs/schema.md` | Document `run.salt_mode` field in report schema | ~5 |
| F15 | `README.md` | Update PII section: mention `--pii-salt-file` and env var | ~8 |
| F16 | `CHANGELOG.md` | v0.6.0 entry: tenant-stable PII salt mode | ~3 |

### 3.2 Schema / CLI changes

#### CLI additions

```
--pii-salt-file PATH   Path to a file containing the PII salt (high-entropy
                       secret, ≥ 32 hex chars recommended). When set, principal
                       hashes are stable across runs for the same tenant.
                       Overrides FINOPS_PII_SALT env var. Ignored if
                       --no-pii-redaction is set.
```

Environment variable: `FINOPS_PII_SALT` — inline salt value (same
semantics as file contents).

#### Report schema addition (additive, non-breaking)

```json
{
  "run": {
    "salt_mode": "per_run" | "tenant_stable",
    ...existing fields...
  }
}
```

#### Playbook manifest addition (additive, non-breaking)

```json
{
  "pii_handling": {
    "mode": "salted_hash",
    "salt_mode": "per_run" | "tenant_stable",
    "ticket_key_stability_by_surface": { ... },
    "known_limitation": null | "..."
  }
}
```

#### FOCUS manifest addition (additive, non-breaking)

```json
{
  "pii_handling": {
    "mode": "...",
    "salt_mode": "per_run" | "tenant_stable",
    "known_limitation": null | "..."
  }
}
```

### 3.3 `_resolve_pii_salt()` pseudocode

```python
def _resolve_pii_salt(
    pii_salt_file: Path | None,
    no_pii_redaction: bool,
) -> tuple[str | None, str]:
    """Resolve the PII salt and return (salt_or_none, mode_label).

    Returns (None, "per_run") when no stable salt is configured.
    Returns (salt_string, "tenant_stable") when a salt is found.
    Raises click.BadParameter on validation failure.
    """
    if no_pii_redaction:
        if pii_salt_file is not None:
            logger.warning("--pii-salt-file is ignored because --no-pii-redaction is set")
        return None, "disabled"

    # 1. Explicit file flag (highest precedence)
    if pii_salt_file is not None:
        return _read_salt_file(pii_salt_file), "tenant_stable"

    # 2. Environment variable
    env_salt = os.environ.get("FINOPS_PII_SALT", "").strip()
    if env_salt:
        return env_salt, "tenant_stable"

    # 3. Default: per-run rotation
    return None, "per_run"
```

### 3.4 `_execute_assessment()` signature change

```python
def _execute_assessment(
    *,
    input_dir: Path,
    redact_pii: bool,
    salt: str | None = None,        # NEW — threaded from _resolve_pii_salt()
) -> tuple[dict[str, Any], dict[str, int]]:
```

The `salt` parameter is passed through to `run_rules(salt=salt)`.
When `None`, the engine uses its existing `secrets.token_hex(16)` path.

### 3.5 `run_rules()` summary addition

```python
# After existing summary dict construction:
summary["salt_mode"] = "tenant_stable" if salt is not None else "per_run"
```

### 3.6 Test plan

| # | Test | File | Asserts |
|---|------|------|---------|
| T1 | `test_salt_mode_per_run_by_default` | `test_engine.py` | `summary["salt_mode"] == "per_run"` when no salt passed |
| T2 | `test_salt_mode_tenant_stable_when_salt_provided` | `test_engine.py` | `summary["salt_mode"] == "tenant_stable"` when salt passed |
| T3 | `test_tenant_stable_produces_identical_principal_across_runs` | `test_playbook_cross_run_stability.py` | Two `run_rules(salt="fixed")` calls → same principal for same input |
| T4 | `test_per_run_produces_different_principal_across_runs` | existing test | Already covered by `test_commitment_under_covered_redacted_principal_unstable_across_runs` |
| T5 | `test_salt_mode_observable_in_summary` | `test_engine.py` | `summary` dict contains `salt_mode` key |
| T6 | `test_resolve_salt_file_not_found` | `test_pii_salt_resolution.py` | `click.BadParameter` raised |
| T7 | `test_resolve_salt_file_empty` | `test_pii_salt_resolution.py` | `click.BadParameter` raised |
| T8 | `test_resolve_salt_file_strips_whitespace` | `test_pii_salt_resolution.py` | Trailing newline stripped |
| T9 | `test_resolve_salt_file_too_large` | `test_pii_salt_resolution.py` | `click.BadParameter` for > 1 MiB |
| T10 | `test_resolve_env_var_empty_falls_through` | `test_pii_salt_resolution.py` | Empty `FINOPS_PII_SALT` → per_run |
| T11 | `test_resolve_file_overrides_env` | `test_pii_salt_resolution.py` | File takes precedence over env |
| T12 | `test_no_redaction_ignores_salt_file` | `test_pii_salt_resolution.py` | `--no-pii-redaction` + salt file → salt unused |
| T13 | `test_low_entropy_warning` | `test_pii_salt_resolution.py` | Salt < 32 chars → warning logged |
| T14 | `test_manifest_salt_mode_tenant_stable` | `test_playbook_cross_run_stability.py` | Manifest `pii_handling.salt_mode` = `"tenant_stable"` |
| T15 | `test_manifest_known_limitation_cleared` | `test_playbook_cross_run_stability.py` | `known_limitation` is `None` under tenant-stable |
| T16 | `test_focus_manifest_salt_mode` | `test_focus_aligned_reporter.py` | FOCUS manifest `pii_handling.salt_mode` correct |
| T17 | `test_cli_run_with_salt_file` | `test_cli_run.py` | End-to-end: salt file → stable principals |
| T18 | `test_cli_run_with_env_salt` | `test_cli_run.py` | End-to-end: env var → stable principals |

### 3.7 Documentation regeneration impact

| Doc | Change needed |
|-----|---------------|
| `docs/user-guide.md` | New section on tenant-stable salt setup |
| `docs/schema.md` | Document `run.salt_mode` field |
| `README.md` | Update PII redaction section |
| `CHANGELOG.md` | v0.6.0 entry |
| `docs/rules.md` | No change — rules are unaffected |
| `docs/plan.md` | One-line entry in the v0.6.0 section |
| Sample reports | Regenerate via `finops-assess demo` — salt_mode appears in output |

### 3.8 Out of scope

1. **Salt rotation with ticket migration** (`previous_salts[]` lookup) —
   follow-on issue per #73 body.
2. **Secret manager integration** (Key Vault, GitHub Secrets) — layer
   above; operators inject via env var.
3. **Per-surface salt** — no use case identified; single salt suffices.
4. **Salt derivation from OIDC tenant ID** — considered and rejected:
   tenant ID is public knowledge (discoverable from any AAD login page),
   so using it as a salt provides zero pre-image resistance.  A proper
   salt must be a secret.
5. **Windows ACL checking** — permission checks are Unix-only advisory;
   Windows equivalent would require `pywin32` dependency.

### 3.9 Decision summary

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | CLI flag `--pii-salt-file` (not `--tenant-salt`) | Anchored to PII namespace; "tenant" in a flag name implies tenant-ID which is wrong |
| D2 | Env var `FINOPS_PII_SALT` (not `FINOPS_TENANT_SALT`) | Same as D1 |
| D3 | File flag overrides env var | Explicit CLI > ambient environment (standard convention) |
| D4 | `--no-pii-redaction` overrides salt file | No-redaction is the strongest opt-out; passing both is a config error but we handle gracefully |
| D5 | Empty salt → per-run fallback (not error) | Empty env vars are common in CI; fail-open to per-run is safer than crashing |
| D6 | No OIDC-derived salt | Tenant ID is public; salt must be secret |
| D7 | Report schema `salt_mode` is additive | No breaking change to existing consumers |
| D8 | Manifest `known_limitation` cleared under tenant-stable | The limitation (per-run instability) no longer applies |
| D9 | Low-entropy warning threshold: 32 hex chars (128 bits) | Matches the engine's default `secrets.token_hex(16)` entropy level |
| D10 | Salt file max size: 1 MiB | Prevents accidental foot-guns; real salts are < 1 KiB |

---

## Plan invariants (Noor verification checklist)

| # | Invariant | How this plan satisfies it |
|---|-----------|---------------------------|
| N1 | Hard Rule #1 (read-only) holds | No new scopes anywhere. Change is pure engine/CLI logic. |
| N2 | Hard Rule #4 (PII redaction on by default) holds | Default remains per-run random salt. Operator must explicitly opt in to tenant-stable. `--no-pii-redaction` still required to disable hashing entirely. |
| N3 | Backward compatibility | No schema breaking changes. Existing tests pass (per-run path unchanged). New `salt_mode` field is additive. Existing CSVs load without modification. |
| N4 | Threat model stated explicitly | §2.5 covers S1 vs S2, "if salt leaks" matrix, residual risk acceptance, mitigation guidance. |
| N5 | CLI surface change is minimal and backward-compatible | One new optional flag (`--pii-salt-file`), one new env var (`FINOPS_PII_SALT`). No existing flags changed or removed. |
| N6 | Operator failure modes specified | §2.2 edge cases E1–E10 cover: missing file, empty file, low entropy, conflicting flags, oversized file, world-readable permissions, salt rotation. |
| N7 | Test plan covers required scenarios | T1–T2: salt_mode in summary. T3: tenant-stable → identical principals. T4 (existing): per-run → different principals. T5: mode observable in logs/summary. T6–T13: edge cases. T14–T18: manifests and CLI integration. |

---

## Producer-path citation index

| # | Claim | File:Line | What it establishes |
|---|-------|-----------|---------------------|
| P1 | `RuleContext.redact()` implementation | `engine.py:70-75` | SHA-256 truncated to 16 hex chars with `salt:principal` format |
| P2 | Default salt generation | `engine.py:151` | `secrets.token_hex(16)` when no salt provided |
| P3 | `salt` parameter on `run_rules()` | `engine.py:137` | `salt: str \| None = None` — already supports caller-supplied salt |
| P4 | `redact_pii` parameter on `run_rules()` | `engine.py:136` | `redact_pii: bool = True` — default is on |
| P5 | CLI `--no-pii-redaction` flag | `cli.py:290-293` | `is_flag=True, default=False` — opt-in to disable |
| P6 | `_execute_assessment()` signature | `cli.py:42-46` | `redact_pii: bool` — no salt parameter today |
| P7 | `_execute_assessment()` calls `run_rules()` | `cli.py:57-64` | Threads `redact_pii` through |
| P8 | Playbook manifest `pii_handling` | `reporters/playbook.py:490-494` | Hard-codes `"per_run"` stability |
| P9 | Playbook `_KNOWN_LIMITATION_PER_RUN` | `reporters/playbook.py:110-117` | References #73 as the fix |
| P10 | FOCUS manifest `pii_handling` | `reporters/focus_aligned.py:300-308` | Same pattern, references #73 |
| P11 | FOCUS `join_keys` stability | `reporters/focus_aligned.py:336-348` | `"per_run"` when `pii_redaction` is on |
| P12 | Existing test: per-run instability | `tests/test_az_commitment_under_covered.py:373-407` | Two runs → different principals (regression gate) |
| P13 | Existing test: redaction hashes principals | `tests/test_engine.py:108-127` | No raw UPNs leak; `sha256:` prefix verified |
| P14 | Playbook cross-run stability tests | `tests/test_playbook_cross_run_stability.py:140,176` | Per-run rotates; redaction-off is stable |
| P15 | M365 rules callsites (16 total) | `rules_impl/m365_rules.py:103,108,158,166,202,207,239,244,276,281,309,314,348,353,416,422` | All pass `assignment.principal` or `principal` |
| P16 | Azure rules callsites (26 total) | `rules_impl/azure_rules.py:42,47,...,652` | All pass resource IDs, not UPNs |
| P17 | GitHub rules callsites (6 total) | `rules_impl/github_rules.py:58,63,103,108,143,202` | All pass `seat.principal` or `org.org` |
| P18 | ADO rules callsites (7 total) | `rules_impl/ado_rules.py:57,62,102,107,145,193,199` | All pass `seat.principal` or `org.org` |
| P19 | `_STABLE_SURFACES_WHEN_CLEARTEXT` | `reporters/playbook.py:108` | All 4 surfaces listed |
| P20 | JSON reporter `pii_redaction` in run block | `reporters/json_reporter.py:59` | `"pii_redaction": redact_pii` |
