# Security policy

This document records the security posture of `finops-assess` and the
process for reporting vulnerabilities. The maintainer hardening
checklist and the list of security-relevant files have moved to
[`docs/contributing.md`](docs/contributing.md).

## Supported versions

`finops-assess` is in active development. Security fixes are accepted
for the most recent state of `main`. Older states are not supported.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| Previous tagged releases | ❌ |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a suspected
vulnerability. Use one of:

1. **GitHub private vulnerability disclosure** (preferred). Open a
   report via the repository's **Security** tab, then *Report a
   vulnerability*. This routes to the maintainers privately and keeps
   the disclosure auditable.
2. If GitHub private vulnerability disclosure is unavailable, contact
   the repository owner directly via their public GitHub profile.

We will acknowledge within 5 working days and aim to provide a
remediation plan within 30 days for confirmed vulnerabilities.

## Security posture (the read-only contract)

`finops-assess` is **read-only by construction**. Every collector and
every CLI command in this repository must satisfy the following
properties. Deviations are vulnerabilities and should be reported via
the channel above.

1. **No write or admin scopes.** Microsoft Graph, ARM, GitHub, and
   Azure DevOps collectors only ever request read scopes
   (`*.Read.All`, `Reader`, `repo:read`, etc.). Any code path that
   requests, accepts, or documents a `*.ReadWrite.*` or write-tier
   scope is a defect. The CLI is also designed to refuse to start
   when a credential carrying a write scope is detected. Until that
   introspection is fully implemented, operators are responsible for
   provisioning read-only credentials.
2. **No remediation actions.** The tool only emits advisory findings.
   It never mutates the systems it inspects. There is no "apply",
   "remediate", or "fix" code path and there will not be one in v1.
3. **No long-lived secrets in the repository.** Live-mode auth uses
   GitHub Actions **OIDC federated credentials** for Microsoft and
   GitHub surfaces. Long-lived PATs, client secrets, tenant IDs, and
   subscription IDs must never be committed. Use `${{ secrets.* }}`
   in workflows or environment variables at runtime exclusively.
4. **PII redaction on by default.** Every user-identifying field in
   a report is salted-hashed unless the operator opts in with
   `--no-pii-redaction`. Rule implementations route every emitted
   `principal` through `RuleContext.redact()`.
5. **No third-party copyrighted material.** Aaron Dinnage's M365
   Maps diagrams, Microsoft pricing pages, and similar sources are
   linked and credited via `source_url` but never copied into this
   repository. The feature taxonomy used in `data/catalog/` is our
   own paraphrase.
6. **Outbound-network discipline.** `validate`, `info`, and `demo`
   are fully offline. Live collectors and `catalog refresh` are the
   only commands that perform outbound network calls, and they only
   reach documented Microsoft and GitHub APIs over HTTPS.

## Scope of this policy

This policy covers code, configuration, packaged data, and CI
workflows in this repository. It does not cover:

- Operator-side misconfiguration (for example assigning an Entra app
  a write-tier role contrary to the install instructions). Report
  such issues to the operator's own security team.
- The customer's tenants, subscriptions, or repositories. We never
  receive customer data; everything happens locally to the operator.
- Vulnerabilities in third-party dependencies. Those are tracked via
  Dependabot (`.github/dependabot.yml`) and GitHub Advanced Security.
  Please report upstream.

## Acknowledgements

We credit researchers who follow this policy in the repository's
release notes when a fix ships, unless the reporter requests
anonymity.
