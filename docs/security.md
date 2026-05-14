# Security posture

`finops-assess` is **read-only by construction**. This document is the
single anchor for security-relevant decisions and controls — the source of
truth that other docs link to rather than restate.

## Read-only contract

The tool inspects licensing, identity, usage, and cost across the Microsoft
ecosystem (Microsoft 365, Azure, GitHub, Azure DevOps). It does not, and is
not designed to, modify anything in those systems.

- **No write scopes anywhere.** Microsoft Graph, Azure ARM, GitHub, and
  Azure DevOps collectors request read-only scopes only. Scope strings
  ending in `.ReadWrite.*` or any administrative-action equivalent are
  rejected at the credential-validation layer.
- **CLI refuses to run** if a credential carrying a write scope is
  detected — see `docs/plan.md` §9 and the collector implementations
  under `src/finops_assess/collectors/`.
- **Mutation paths are explicitly out of scope** for this tool. Any
  remediation lives in adjacent operator workflows or the separate
  agentic-finops effort (issue #65), never in this codebase.

## Authentication: OIDC federated credentials

Live-mode authentication uses **OIDC federated credentials in GitHub
Actions**. There are no long-lived tokens, PATs, client secrets, or
tenant IDs in source.

- CI uses `${{ secrets.* }}` and federated identity exclusively.
- Local development uses `az login` / `gh auth login` against the
  operator's own identity.
- See `.github/workflows/` for the canonical OIDC pattern.

## PII redaction (default-on)

Any user-identifying field in a report is **salted-hashed unless the
operator opts in with `--no-pii-redaction`**.

- Default redaction uses a per-run salt; `ticket_key` and similar
  cross-run join keys degrade to per-run scope and cannot be deduped
  across runs (issue #73 tracks the optional tenant-stable salt).
- The opt-out is a deliberate, named action — passing
  `--no-pii-redaction` writes cleartext UPNs / GitHub logins / ADO emails
  into the report and the operator owns the downstream handling.
- See `docs/schema.md` for the `pii_handling.mode` enum and how it is
  recorded in the FOCUS-aligned manifest sidecar.

## Overlay template threat model (reporters)

`finops-assess` supports operator-supplied Jinja2 overlay templates for
report customisation (playbook export). Overlays are operator-controlled
inputs to a code-generation surface, so they get the same defensive
posture as any other untrusted-template scenario.

The threat model and the controls that mitigate it are documented in
[`docs/user-guide.md` § Security sandbox](user-guide.md#security-sandbox)
and remain authoritative there. In summary:

- Overlay templates run in `jinja2.sandbox.SandboxedEnvironment` with
  `is_safe_callable → False` (no callable invocation from template
  expressions).
- `{% include %}`, `{% import %}`, and `{% extends %}` are rejected at
  AST parse time before the template is cached
  (`_reject_include_import_nodes` in
  `src/finops_assess/reporters/_playbook_env.py`).
- Templates are loaded **from the file system only** via
  `FileSystemLoader(overlay_dir)`; the exporter never calls
  `from_string()` on operator-supplied content.
- The manifest sidecar records `template_sources[].source` (`wheel` or
  `overlay`) and SHA-256 for every rendered template, so any deviation
  from bundled templates is traceable in the audit trail.

These controls mirror Noor's Stage-4 review conditions C1 / C2 / C3 from
PR #101 (and the C-Extends follow-up from PR #107). Do not relax them
without a new security review.

## Reporter / output guarantees

- **Determinism.** Reports are byte-deterministic when
  `SOURCE_DATE_EPOCH` is set. The docs-freshness CI gate enforces this
  for committed example artefacts.
- **Manifest sidecars are atomic.** Multi-file reporters (data file +
  manifest) follow the Option-C atomic-write protocol: data file written
  via `tempfile.mkstemp` + `os.fsync` + `os.replace`, manifest written
  last with `output_artifacts.{data_filename}_sha256` self-attestation,
  recovery via `--cleanup-orphans`. Manifest presence is the canonical
  readiness marker. See `src/finops_assess/reporters/_determinism.py`
  and `.squad/decisions.md` § 5.1.

## What is intentionally out of scope

- **Mutation / remediation paths.** Adding a write capability to this
  tool requires a new dedicated security review and a separate scope of
  work (likely a sibling repo per issue #65).
- **Non-Microsoft SaaS audits** (AWS, GCP, Workday) are out of scope for
  the read-only contract documented here. Adding them would require
  fresh per-cloud read-only-scope analysis.
- **Bundling third-party copyrighted material.** Aaron Dinnage's M365
  Maps diagrams, Microsoft pricing pages, etc., are linked and credited
  but never copied into the repo. The feature taxonomy in
  `data/catalog/` is our own paraphrase.

## Reference index

| Topic | Authoritative location |
|---|---|
| Read-only scope enforcement | `src/finops_assess/collectors/`, `docs/plan.md` §9 |
| OIDC auth pattern | `.github/workflows/ci.yml`, `pyproject.toml` `[live]` extra |
| PII redaction CLI | `src/finops_assess/cli.py` (`--no-pii-redaction`), `docs/schema.md` (`pii_handling.mode`) |
| Overlay sandbox controls | `src/finops_assess/reporters/_playbook_env.py`, `docs/user-guide.md` § Security sandbox |
| Atomic-write contract | `src/finops_assess/reporters/_determinism.py`, `.squad/decisions.md` § 5.1 |
| Stage-4 review precedent | PR #101 (overlay sandbox), PR #107 (`{% extends %}` follow-up) |

## Change-management

Future security-relevant additions (new scope refusals, PII handling
modes, sandbox tightenings, OIDC posture changes) belong here — extend
this document rather than fragmenting controls across user-guide,
plan, and per-feature docs. Cross-link from the implementation site
back to the relevant section here so reviewers have one place to start.
