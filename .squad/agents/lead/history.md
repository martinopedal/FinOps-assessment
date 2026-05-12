# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent lead initialized for the FinOps-assessment squad. See `.squad/agents/lead/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **All M0–M7 shipped via the `@copilot`-direct PR path, not Squad orchestration.** Every numbered PR (#1–#22) is copilot-authored and copilot-merged. Squad members have authored zero PRs and triaged zero issues 8 days post-bootstrap. The §11 loop is being executed inside PR bodies (clearest example: #22), not via labelled `squad:*` issues. The scaffold is unproven on real work — either we pilot it on the next frontier epic or we accept the simpler workflow as the workflow.
- **Issue tracker is empty despite a rich label taxonomy.** `squad:*`, `type:*`, `priority:p0..p2`, `release:v0.4.0..v1.0.0`, `release:backlog`, `go:yes/needs-research/no`, `feedback` all exist; zero issues use any of them. The 9 frontier epics in `docs/roadmap/README.md` and 13 reserved rule IDs have never been reduced to issues — they live entirely in docs.
- **Stale references inside `.squad/`.** `.squad/routing.md` "Issue Routing" table points at `milestone:M1..M7` labels that do not exist; the real release labels are `release:v0.4.0..v1.0.0` / `release:backlog`. `.squad/identity/now.md` is still pinned to "Initial setup" from 2026-05-04. `.squad/identity/wisdom.md`, `.squad/decisions.md`, and every agent's `history.md` Learnings are seed boilerplate. `.squad/decisions/inbox/` did not exist until this session created it.
- **Project convention: "name the work before shipping it."** The pattern across PRs #18–#22 is to land docs / boundary / roadmap / mapping PRs that reserve names and document guardrails before any schema, rule, or collector edit. Reserved rule IDs in `docs/roadmap/README.md` are explicitly **not** to be added to `data/rules/` until their own §11 PR lands.
- **`CHANGELOG.md` Unreleased is the project's drift detector.** Every behaviour-touching PR adds an entry; docs-only PRs add one too (see #22). Reviewers can scan Unreleased for un-promised work.
- **PR #22 is the model §11-in-PR-body artefact.** Body documents stages 1–4 and the consensus call inline. If we keep the copilot-direct path, this is the template to lean on. If we move to Squad, that artefact moves to `.squad/decisions/inbox/`.
- **The repo's load-bearing invariant is read-only posture**, repeated verbatim across `plan.md` §1, `copilot-instructions.md` hard rules, every roadmap epic guardrail column, and the Hubs/FOCUS/triage boundary docs. Any proposal that touches scopes, secrets, schemas, or third-party diagrams hits 🔴 by default and must route to Noor.
- **`.squad/skills/project-conventions/SKILL.md` is still the placeholder template** despite `.github/copilot-instructions.md` being a rich, authoritative source. That's a 1-PR fix (route to Yuki) and it materially improves what every future agent reads at session start.
- 2026-05-12T08:26Z — Backlog batch complete: #24 (Yuki, SKILL.md rewrite, PR #34 merged) and #26 (Sam, squad-cli audit, closed with intentional-drift verdict). Next gate is D.2 pilot (#25) before frontier epics D.4–D.7 proceed.

