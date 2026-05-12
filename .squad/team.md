# Squad Team

> FinOps-assessment — read-only multi-surface (M365 · Azure · GitHub · ADO) FinOps audit tool.

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status | Issue label |
|------|------|---------|--------|-------------|
| Maya | Lead / FinOps PM (triage, planning, consensus) | `.squad/agents/lead/charter.md` | Active | `squad:maya` |
| Priya | M365 / Entra / Power Platform specialist | `.squad/agents/m365-specialist/charter.md` | Active | `squad:priya` |
| Diego | Azure compute / storage / SQL / Cost Mgmt specialist | `.squad/agents/azure-specialist/charter.md` | Active | `squad:diego` |
| Sam | GitHub & Azure DevOps specialist | `.squad/agents/devsurfaces-specialist/charter.md` | Active | `squad:sam` |
| Noor | Security & compliance reviewer (adversarial pass) | `.squad/agents/security-reviewer/charter.md` | Active | `squad:noor` |
| Yuki | Tester / quality / CI matrix owner | `.squad/agents/tester/charter.md` | Active | `squad:yuki` |
| Scribe | Documentation, history, decisions log | `.squad/agents/scribe/charter.md` | Active | (auto, never routed) |

## Coding Agent — `@copilot`

`@copilot` is on the team and will pick up issues whose `squad:copilot`
label is applied by the Lead. Auto-assignment is enabled via
`.github/workflows/squad-issue-assign.yml`.

### Capabilities

| Bucket | Examples in this repo |
|--------|----------------------|
| 🟢 Good fit | Adding/extending pytest fixtures or tests; fixing a YAML schema typo; updating `source_url` links; CI matrix tweaks; doc/README polish; mechanical refactors with mypy strict + ruff as guardrails. |
| 🟡 Needs review | New rule YAML (must be reviewed by the relevant surface specialist + `security-reviewer`); new collector code (must be reviewed by `security-reviewer` for scope posture); persona model edits. |
| 🔴 Not suitable | Anything that introduces a write/`*.ReadWrite.*` scope; long-lived secrets/PATs/tenant IDs; copying third-party diagrams or pricing tables; relaxing the read-only posture; schema changes without a stage-3 plan signed off in the issue. |

## Posture (since 2026-05-12)

This squad operates as a **review rubric**, not an orchestration scaffold. The shipping
workflow is `@copilot`-direct with §11 stages in the PR body — the same workflow that
shipped M0–M7 across PRs #4–#22. The roster above names the *voices* a reviewer should
channel when reading a PR adversarially:

- **Maya** for surface scope, DoD, and gap analysis
- **Diego** for Azure shape correctness and pricing-table boundaries
- **Priya** for Microsoft 365 / Graph / Entra posture
- **Sam** for GitHub & Azure DevOps billing semantics
- **Noor** for read-only posture, copyright, OIDC auth, and the five hard rules
- **Yuki** for cross-platform tests, validation gates, and CI matrix coverage

Multi-agent §11 stage-3/stage-4 spawns remain available on request for genuinely
non-trivial PRs (architecture proposals, security audits, frontier-epic kickoffs)
but are **not** the default. See `decisions.md` for the rubric deprecation decision
(issue #25) and the falsification criteria for revisiting.

## Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04
- **Last activity:** 2026-05-12 (local clear of issues #27–#35; falsification-test batch complete).
- **Roadmap:** `CHANGELOG.md` (M0–M7 + Bonus shipped) + `docs/roadmap/README.md` (frontier epics, exploratory).
- **Delivery loop:** `docs/plan.md` §11 (research → rubberduck → plan → consensus → implement). Squad members map to stages: `maya` owns stages 3–4; surface specialists (`priya`, `diego`, `sam`) own stages 1–2 and stage-5 implementation in their domain; `noor` owns the stage-4 adversarial pass; `yuki` owns stage-5 test authoring; `Scribe` records decisions across all stages.
