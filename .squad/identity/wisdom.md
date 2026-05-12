---
last_updated: 2026-05-12T07:30:00.000Z
---

# Team Wisdom

Reusable patterns and heuristics learned through work. NOT transcripts — each entry is a distilled, actionable insight.

## Patterns

**Pattern: §11 loop documented inside the PR body works for the solo `@copilot`-direct flow.**
**Context:** The PR *is* the shared memory across stateless agent invocations. Body documents stages 1–5 (research → rubberduck → plan → consensus → implement) with one or two lines of evidence per stage. PR #22 is the canonical example. For Squad-orchestrated work the same artefacts live in the PR body **plus** `.squad/decisions/inbox/`.

**Pattern: docs-only frontier PRs are the safest first slice of any new capability.**
**Context:** A PR under `docs/roadmap/` that names the contract, the guardrails, and the reserved follow-ups before any code lands stays inside the read-only posture by construction and gives reviewers a cheap object to argue about. PRs #18–#22 are the existing precedent: triage contract, FinOps Hubs boundary, frontier roadmap index, FOCUS 1.2 mapping.

**Pattern: every behaviour-changing PR adds a line under `CHANGELOG.md` → `Unreleased`.**
**Context:** Docs-only PRs add an Unreleased entry too when they introduce a new operator-visible artefact (e.g. a new roadmap doc). The Unreleased section is the project's drift detector — reviewers can scan it for un-promised work.

**Pattern: read-only posture is a load-bearing invariant, not a style preference.**
**Context:** Every roadmap doc restates it verbatim — no writes, no `*.ReadWrite.*`, no admin scopes, no Hubs upload, OIDC-only auth, PII redaction default-on. Treat any PR that would relax any of these as 🔴 and route to Noor regardless of label. Anchored to hard rules 1, 2, 4 of `.github/copilot-instructions.md`.

**Pattern: reserve rule IDs in `docs/roadmap/README.md` before adding the YAML.**
**Context:** Format is `SURFACE.SHORT_NAME`, screaming-snake-case. This is the project's anti-tunnel-vision pattern: it forces the surface taxonomy decision into a reviewable doc PR ahead of the rule PR. Reserved IDs do **not** appear in `data/rules/` until their own §11 PR lands.
