# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent tester initialized for the FinOps-assessment squad. See `.squad/agents/tester/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **2026-05-12** — Issues #24 (D.1: SKILL rewrite—project-conventions docs-to-code sync), #32 (D.9: first runbook—automated triage & reporting) now in backlog. Review test coverage for incoming D.4–D.8 collector PRs as they land; these spikes are gated on stage-4 falsification criteria per the pilot frame.
- **2026-05-12** — Issue #24 completed (PR #34): `.squad/skills/project-conventions/SKILL.md` rewritten from placeholder template by paraphrasing copilot-instructions.md (hard rules 1–5, tech stack, validation gates) and docs/plan.md §1 (guiding principles, catalogue/package model). Agents now read authoritative convention guidance at session start instead of template noise. All validation gates passed (finops-assess validate ✓, ruff ✓, mypy ✓, pytest 121/125 ✓).
