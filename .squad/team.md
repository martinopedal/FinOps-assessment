# Squad Team

> FinOps-assessment — read-only multi-surface (M365 · Azure · GitHub · ADO) FinOps audit tool.

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status | Issue label |
|------|------|---------|--------|-------------|
| Maya | Lead / FinOps PM (triage, planning, consensus) | `.squad/agents/lead/charter.md` | Active | `squad:lead` |
| Priya | M365 / Entra / Power Platform specialist | `.squad/agents/m365-specialist/charter.md` | Active | `squad:m365-specialist` |
| Diego | Azure compute / storage / SQL / Cost Mgmt specialist | `.squad/agents/azure-specialist/charter.md` | Active | `squad:azure-specialist` |
| Sam | GitHub & Azure DevOps specialist | `.squad/agents/devsurfaces-specialist/charter.md` | Active | `squad:devsurfaces-specialist` |
| Noor | Security & compliance reviewer (adversarial pass) | `.squad/agents/security-reviewer/charter.md` | Active | `squad:security-reviewer` |
| Yuki | Tester / quality / CI matrix owner | `.squad/agents/tester/charter.md` | Active | `squad:tester` |
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

## Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04
- **Roadmap:** `docs/plan.md` §2 (M0–M7).
- **Delivery loop:** `docs/plan.md` §11 (research → rubberduck → plan → consensus → implement). Squad members map to stages: `lead` owns stages 3–4; surface specialists own stages 1–2 and stage 5 implementation in their domain; `security-reviewer` owns the stage-4 adversarial pass; `tester` owns stage-5 test authoring; `scribe` records decisions across all stages.
