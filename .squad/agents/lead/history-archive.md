# Lead Agent History Archive

Archived learnings from .squad/agents/lead/history.md. Entries pre-2026-05-12 moved here to keep the primary history under 12 KB for fast session load.

## Core Context

Agent lead initialized for the FinOps-assessment squad. See .squad/agents/lead/charter.md for role, boundaries, and voice.

## Archived Learnings

- **Stale references inside `.squad/`.** `.squad/routing.md` "Issue Routing" table points at `milestone:M1..M7` labels that do not exist; the real release labels are `release:v0.4.0..v1.0.0` / `release:backlog`. `.squad/identity/now.md` is still pinned to "Initial setup" from 2026-05-04. `.squad/identity/wisdom.md`, `.squad/decisions.md`, and every agent's `history.md` Learnings are seed boilerplate. `.squad/decisions/inbox/` did not exist until this session created it.
- **Project convention: "name the work before shipping it."** The pattern across PRs #18–#22 is to land docs / boundary / roadmap / mapping PRs that reserve names and document guardrails before any schema, rule, or collector edit. Reserved rule IDs in `docs/roadmap/README.md` are explicitly **not** to be added to `data/rules/` until their own §11 PR lands.
- **`CHANGELOG.md` Unreleased is the project's drift detector.** Every behaviour-touching PR adds an entry; docs-only PRs add one too (see #22). Reviewers can scan Unreleased for un-promised work.
- **PR #22 is the model §11-in-PR-body artefact.** Body documents stages 1–4 and the consensus call inline. If we keep the copilot-direct path, this is the template to lean on. If we move to Squad, that artefact moves to `.squad/decisions/inbox/`.
- **The repo's load-bearing invariant is read-only posture**, repeated verbatim across `plan.md` §1, `copilot-instructions.md` hard rules, every roadmap epic guardrail column, and the Hubs/FOCUS/triage boundary docs. Any proposal that touches scopes, secrets, schemas, or third-party diagrams hits 🔴 by default and must route to Noor.
- **`.squad/skills/project-conventions/SKILL.md` is still the placeholder template** despite `.github/copilot-instructions.md` being a rich, authoritative source. That's a 1-PR fix (route to Yuki) and it materially improves what every future agent reads at session start.