# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent security-reviewer initialized for the FinOps-assessment squad. See `.squad/agents/security-reviewer/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- 2026-05-12 — Stage-4 pass on Maya's gap analysis: PR #22 (FOCUS 1.2 mapping) is read-only-posture-clean against hard rules 1–5; only residual risk is *expectation drift* from the "Source field" column, mitigated by a non-contract banner. The repo's docs-only roadmap PRs are a robust pattern — they let us reason about future contracts without committing schema or auth surface.
- Routing-table drift (`milestone:M1..M7` → `release:*`) is pure stale documentation: the labels never existed, no historical link expects them, no external reference relies on them. Hard replace, no redirect — confirmed by `gh label list`, `git log -p`, and a repo-wide `rg "milestone:M"`.
- Biggest second-order risk I flagged for the backlog: D.4–D.7 spike issues should pre-commit the eventual implementer to OIDC-only auth in the issue body, so hard rule 2 is not re-litigated in the collector PR. And sovereign-cloud / tenant-id leakage is *not* solved by default PII redaction — keep that distinction sharp when M365 SKU-mix collector work eventually lands.
- Bias check passed: I set a falsification criterion ("stage-4 produces zero amendments") that specifically indicts my own role, and the rollback path preserves my function as a review rubric rather than a workflow gate.

