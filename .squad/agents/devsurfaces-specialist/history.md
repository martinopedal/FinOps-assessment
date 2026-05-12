# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent devsurfaces-specialist initialized for the FinOps-assessment squad. See `.squad/agents/devsurfaces-specialist/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **2026-05-12** — Issue #26 (D.3: squad-cli upstream audit) now in backlog; label drift `squad:devsurfaces-specialist`→`squad:sam` is fixed. This is a maintenance spike to verify no breaking changes in @bradygaster/squad-cli before rolling out squad to other orgs.


## 2026-05-12 Learnings

- **Squad-cli upstream audit (issue #26)** — Local v0.8.25, npm latest v0.9.4. Substantive intentional drift: inlined skills (vs delegated), no SDK mode, no ADO support, local squad-pr-route.yml addition. All four core workflows also drifted. Filed as "no PR needed" — drift is justified architectural choice for this project. Recorded in decisions inbox.
- **Routing enforcement refusal rule (issue #35)** — Mechanical follow-up to #26 audit. Successfully fetched upstream squad.agent.md from `https://raw.githubusercontent.com/bradygaster/squad/main/.github/agents/squad.agent.md` (not `/install/agents/` path). Added anti-pattern #6: "Never inline domain work to avoid the spawn" — emphasizes that when a task needs agent expertise, the spawn IS the work, no shortcut even when answer feels "small". Version stamp convention: v0.8.25+local (not v0.9.4 — cherry-pick, not wholesale upgrade). PR #38. No other mechanical audit follow-ups remain from #26; next surface is M5 GitHub collector when those issues arrive.