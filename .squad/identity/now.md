---
updated_at: 2026-05-13T15:30:00.000Z
focus_area: "#59 stage-3 plan in flight (Maya); PR #80 + PR #79 closed; awaiting Noor stage-4 on AZ.SAVINGS_PLAN_ELIGIBLE_SPEND"
active_issues: [59, 73, 75, 76, 81, 82]
open_prs: [TBD-59-plan]
---

# What We're Focused On

## TL;DR for next coordinator session

🎉 **PR #78 + PR #79 + PR #80 all closed/merged.** Local main is `0942872`. CI green on every workflow.

Now in flight: **§11 stage-3 plan for `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`** (Maya, Opus 4.7) — the **first** of five rules in the #59 commitment-discount epic. One rule, one PR. Plan committed at `docs/plans/059-az-savings-plan-eligible-spend.md` and pasted into the PR body. Branch `squad/59-plan-maya-savings-plan-eligible`. Awaiting Noor stage-4 verdict.

## What shipped this session

This session executed Maya's planning loop for #59 (epic) → first child rule:

1. **Loaded full context.** CI green on `main` (latest run on `0942872` succeeded across CI / Demo report / Documentation freshness). Read `.github/copilot-instructions.md`, `docs/plan.md` §11, recent decisions on the post-PR-#78 producer-path-citation norm, and the existing Azure rule patterns.
2. **Authored stage-1 (research) + stage-2 (rubberduck) + stage-3 (plan)** in a single artefact at `docs/plans/059-az-savings-plan-eligible-spend.md` (~36 KB, LF-pinned). The plan covers:
   - Benefit Recommendations API surface (Microsoft Learn URL cited; no copyrighted content bundled).
   - Edge cases E1-E8, false-positive risks, conservative wording.
   - File-level changes: new `AzureBenefitRecommendation` pydantic model, new CSV file, new ARM collector method, new YAML rule, new rule impl, new playbook `.j2` template, samples, doc regen.
   - **Producer-path citations** (§3.7 binding table) — every claim about a value the rule emits anchored to file:line.
   - 11 enumerated tests including an **e2e regression test** that uses real `run_rules` (not a mocked rule callable) — pattern reference `tests/test_playbook_cross_run_stability.py`.
   - Stage-4 ask: Noor steelmans 10 invariants.
   - Stage-5 plan: Diego primary, Yuki backup.
3. **Created branch** `squad/59-plan-maya-savings-plan-eligible`.
4. **Wrote inbox drop** at `.squad/decisions/inbox/maya-59-stage3-plan.md` for Scribe to fold into `decisions.md` next wrap.
5. **Updated this file** + appended to `.squad/agents/lead/history.md`.
6. **Opened draft PR** with labels `squad`, `squad:maya`, `type:plan` (new label created via `gh label create`).

## Outstanding for next session

### PR (this one)

Awaiting Noor stage-4 verdict. On `APPROVE`, the auto-approve workflow fires and the plan PR squash-merges. On `REQUEST_CHANGES`, Reviewer Rejection Lockout applies (Maya is locked out; revision routes to a different agent — likely Yuki or Diego).

### After this PR merges

The implementation PR opens on `squad/59-impl-savings-plan-eligible` (Diego primary). **Then** Maya authors stage-3 plans for the remaining four rules in #59:

- `AZ.COMMITMENT_UNDER_COVERED` — needs Cost Mgmt sibling-scope query; collector additions.
- `AZ.COMMITMENT_RENEWAL_REVIEW` — needs `AzureReservation.expiry_date` field (small schema change).
- `AZ.RESERVATION_SCOPE_MISMATCH` — needs reservation scope joined to consuming subscription; mostly evaluable from existing data.
- `AZ.AHB_ELIGIBLE` — needs `AzureResource.os_type` and `license_type` (schema change for VMs / SQL VMs).

Each is its own stage-3 plan / PR.

### Other open work

- **#73** engine tenant-stable PII salt — referenced in this plan as the engine-level fix; does not block.
- **#74** runtime template overlay; **#75** Scribe-vs-Stage-4 race; **#76** Scribe charter branch-handling.
- **#81** repo-wide CRLF hygiene (Maya, go:needs-research).
- **#82** playbook nit cleanups (Yuki, go:needs-research).
- **#62** unit-economics card (v0.5.0 follow-on).

## Norms reinforced this session

- **Stage-3 plans must cite producer code paths.** This is the third stage-3 plan to follow the post-PR-#78 norm (§3.7 producer-path citation table). Now operationalised — the table format is reusable for every future stage-3 plan that asserts a value the rule/reporter emits.
- **One rule, one PR.** The #59 epic body says so; this session honoured it. Future epic decompositions should follow.
- **Plan-PR convention `docs/plans/NNN-<slug>.md`.** New convention this session — folder did not exist before. The plan PR becomes the canonical archive of stage-1/2/3 reasoning, separate from `.squad/decisions.md` (which the Scribe folds in async).

## Next entry point for new session

1. `gh pr list --state open --label squad:maya` → confirm the #59 plan PR is still open and check Noor's verdict status.
2. If Noor APPROVED, drive the merge (auto-approve workflow handles it).
3. If Noor REQUESTed CHANGES, route revision to a different agent (Yuki or Diego) under Reviewer Rejection Lockout.
4. After merge, hand off to Diego on `squad/59-impl-savings-plan-eligible` for stage-5.
5. Then queue Maya's next stage-3 plan: `AZ.COMMITMENT_UNDER_COVERED` (the natural next rule because it shares the existing `AzureReservation` row shape).
