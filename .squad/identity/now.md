---
updated_at: 2026-05-13T16:30:00.000Z
focus_area: "#59 epic: rules 1-2 plans MERGED (#83, #84); rule 3 plan in flight (#86, awaiting Noor stage-4); rule 1 impl in flight on Diego/Noor cycle (#85); rules 4-5 not yet planned"
active_issues: [59, 73, 75, 76, 81, 82]
open_prs: [85, 86]
---

# What We're Focused On

## TL;DR for next coordinator session

The §11 multi-agent loop is humming on the #59 epic (Azure commitment-discount rule suite, 5-rule decomposition, one rule per PR).

State as of this checkpoint:

- **PR #83** (rule 1 plan, `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`) -- MERGED (squash `2445870`).
- **PR #84** (rule 2 plan, `AZ.COMMITMENT_UNDER_COVERED`) -- APPROVED by Noor, awaiting merge after this branch sync push lands.
- **PR #85** (rule 1 impl, `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`) -- Diego shipped, CI green across the matrix, awaiting Noor stage-4.
- **Rules 3-5** -- not started. Rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`) is the next Maya plan.

## Norms reinforced this session

- **Stage-3 plans must cite producer code paths.** Operationalised via the §3.7 producer-path citation table. Any value the rule emits is anchored file:line.
- **One rule, one PR.** The #59 epic body says so; this session honoured it across rule 1 and rule 2.
- **Plan-PR convention `docs/plans/NNN-<slug>.md`.** New convention this session. Plan PRs become canonical archives of stage-1/2/3 reasoning.
- **Stage-3 corrections surface explicitly.** Maya called out that `arm_collector.py` does NOT call Cost Management on main SHA `0942872` despite the epic body framing. Coordinator posted issue #59 correction comment.
- **Cross-rule isolation triple-check.** Rule 2 documents intentional dual-fire with `AZ.RESERVATION_UNDERUTILIZED`, disjoint-by-gate from rule 3, disjoint-by-signal from rule 4.

## Outstanding for next session

1. Verify the squad-approve workflow re-fires on PR #84 after this sync push (push dismisses prior approval).
2. Merge PR #84 (squash, delete branch).
3. Spawn Noor stage-4 on PR #85 (Diego rule 1 impl).
4. Spawn Maya stage-3 plan for rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`).
5. Continue down rules 4 (`AZ.RESERVATION_SCOPE_MISMATCH`) and 5 (`AZ.AHB_ELIGIBLE`).

## Other open work

- **#73** engine tenant-stable PII salt -- referenced in plans as engine-level fix; does not block rule shipping.
- **#74** runtime template overlay; **#75** Scribe-vs-Stage-4 race; **#76** Scribe charter branch-handling.
- **#81** repo-wide CRLF hygiene (Maya, go:needs-research).
- **#82** playbook nit cleanups (Yuki, go:needs-research).
- **#62** unit-economics card (v0.5.0 follow-on, go:yes).
- **#60** read-only MCP server (Maya, go:yes).