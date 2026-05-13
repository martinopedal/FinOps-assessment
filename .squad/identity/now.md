---
updated_at: 2026-05-13T13:30:00.000Z
focus_area: PR #78 Yuki revision pushed (5bf48e8) — awaiting Noor stage-4 re-review; PR #79/#80 still pending Martin's manual approval
active_issues: [61, 73, 75, 76, 81, 82]
open_prs: [78, 79, 80]
locked_out_for_61_revision: [diego, maya]
---

# What We're Focused On

## TL;DR for next coordinator session

PR #78 stage-4 reject-revise cycle COMPLETED on Yuki's side. Revision commit `5bf48e8` on `squad/61-impl-diego` addresses Noor's BLOCKING #1 + 3 amendments + 2 NITs AND Yuki's own 7 amendments + 3 NITs (the latter partially deferred to follow-ups #81/#82). All 10 CI checks green. Test count 444 to 476 (+32). Now awaiting **Noor's stage-4 re-review** to clear the gate.

Three PRs still open, three different gates:

- **PR #78** (`squad/61-impl-diego` @ `5bf48e8`) — Yuki's stage-5 lockout revision. CI 10/10 green. Awaiting Noor re-review (use the Stage-5 Revision marker to trigger her). PR comment 4440148120 has Yuki's revision summary.
- **PR #79** (`squad/post-pr72-rescue-housekeeping` @ `9af52a3`) — coordinator rescue commit, NIT-only. CI green. Awaiting Martin's manual approval.
- **PR #80** (`squad/noor-pr78-stage4-housekeeping`) — squad-housekeeping bundle (Noor history + Yuki hardening + handoff snapshots + Yuki revision learnings + post-revision focus snapshot). CI green. Awaiting Martin's manual approval. Now broader than just Noor's +2 lines — see commits.

Local main is clean at `f96a5e9`. PR #72 merged earlier in prior session.

## PR #78 — Yuki revision pushed, Noor re-review next

**What Yuki delivered (commit `5bf48e8`):**

- BLOCKING #1 fix: `pii_handling.ticket_key_stability_by_surface` is now pii-aware in BOTH `playbook.py` and `focus_aligned.py`. All four surfaces emit `per_run` when `pii_redaction=True`, `stable` when `pii_redaction=False`.
- Regression test `tests/test_playbook_cross_run_stability.py` runs the real engine TWICE and asserts manifest claim matches actual cross-run ticket_key behaviour. This is the test that would have caught the bug before merge.
- AMEND #1 (perf): `@functools.cache`-wrapped `_template_vars_cached(rule_id, source)` — AST parse once per rule, not once per finding.
- AMEND #2 (render boundary): evidence dict spread FIRST, reserved keys spread SECOND, so reserved wins on conflict. 3 regression tests in `test_playbook_render_context_boundary.py`.
- AMEND #3: `_playbook_env.py` docstring matches the lazy-init reality.
- NIT #1 (Noor) + B2 (Yuki own): `pii_handling.note` renamed to `pii_handling.known_limitation` per plan A12. Schema updated.
- B7 scope (a): only Yuki-authored files are LF. Repo-wide hygiene deferred to **#81 (squad:maya, go:needs-research)**.
- B8/B9/B10 NITs deferred to **#82 (squad:yuki, go:needs-research)**.
- Examples + golden manifests regenerated from honest semantics.

**Locked-plan deviations carried forward** (not re-litigated):
- A8 `_AccessTrackingEvidence` to static AST walk (cheaper plan-compliant path; documented).
- A12 field name reverted to plan (`known_limitation`).

**False-assumption norm proposed by Yuki:** "Any plan that claims a manifest field's value MUST cite the producer code path (file:line) that establishes it." This should be promoted to a stage-1 brief checklist item in future plans. Worth a Maya stage-3 amendment or a SKILL.md.

**Spawn template for Noor re-review:**

```
agent_type: general-purpose
model: claude-opus-4.7-xhigh
mode: background
description: "🛡️ Noor: Stage-4 re-review of PR #78 revision (commit 5bf48e8)"
prompt: |
  You are Noor. Read your prior verdict at .squad/decisions.md (Scribe should
  have merged it from inbox/noor-pr78-stage4.md). Diego still locked out.
  Maya still locked out. Yuki authored the revision (5bf48e8 on squad/61-impl-diego).
  Re-review against your original BLOCKING #1 + 3 amendments + 2 NITs:
    - BLOCKING #1: did the manifest stability dict become pii-aware?
    - Did the NEW regression test prove cross-run behaviour matches the claim?
    - Was the focus_aligned mirror applied?
    - Were AMEND #1/#2/#3 addressed?
  Read PR #78 comment 4440148120 (Yuki's revision summary) for context.
  Post stage-4 verdict comment using markers:
    **Stage-4 Adversarial Review — Noor**
    VERDICT: APPROVE | APPROVE_WITH_CHANGES | REJECT
  If APPROVE, the squad-approve workflow auto-applies github-actions[bot]
  approval and Martin can `gh pr merge 78 --squash --delete-branch`.
```

## PR #79 — Housekeeping rescue, awaiting Martin's approval

NIT-only `.squad/` diff. Martin's choice: approve manually (no fake-Noor verdict).

## PR #80 — Squad-housekeeping bundle (broader now)

This branch's commits (NIT-only `.squad/` housekeeping):
- `b472b9b` — Noor's stage-4 verdict on PR #78 history entry
- `a2858ac` — Yuki PR #78 hardening entry + handoff snapshot rescue
- `7eca300` — Yuki PR #78 stage-5 lockout revision learnings
- (this snapshot) — post-Yuki-revision focus update + Scribe wrap

Awaiting Martin's manual approval.

## Decision-inbox state

```
.squad/decisions/inbox/
  noor-61-stage4-rereview.md                    (1.5 KB, 11:04 — orphan from earlier #61 cycle)
  noor-pr78-stage4.md                           (12 KB, 11:56 — Noor's REJECT verdict)
  copilot-session-handoff-2026-05-13T1158Z.md   (handoff record from prior session)
  yuki-pr78-revision.md                         (5.6 KB, 12:48 — Yuki's revision drop file)
```

Scribe spawn this session is responsible for merging all four into decisions.md and clearing the inbox.

## Other in-flight backlog

After PR #78 ships, queued (Maya's triage from v0.5.0 cycle):

- #59 Azure commitment-discount rules (next v0.5.0 work)
- #62 unit-economics card (v0.5.0)
- #66, #67, #68, #69, #71 — labeled and queued for v0.6.0+
- #73 (engine tenant-stable PII salt) — the architectural fix that PR #78's manifest band-aid defers to
- #74 (runtime template overlay), #75 (Scribe-vs-Stage-4 race), #76 (Scribe charter branch-handling)
- **#81 NEW** Repo-wide CRLF hygiene (Maya, go:needs-research)
- **#82 NEW** Playbook nit cleanups (Yuki, go:needs-research)

## Lessons promoted

- **Reviewer Rejection Lockout binds to artifact, not role** — Maya was the locked-out plan author; Yuki revised stage-3; Noor approved on re-review. Same pattern now applies at stage-5: Diego implemented, Yuki revised under Opus xhigh exception, Noor re-reviews.
- **Multi-file reporter outputs use Option C atomic-write contract** — implemented faithfully in PR #78 per Noor's clean-record.
- **Stage-4 must prove per-surface invariants empirically** — caught its first false-assumption in PR #78 BLOCKING #1.
- **NEW (Yuki) — Stage-3 plans must cite producer code paths.** Any plan claiming a manifest field's value MUST cite the producer code path (file:line) that establishes it. Both PR #72 (Maya) and PR #72 revision (Yuki) failed this discipline; Noor caught it at stage-4 against the engine's `redact()` reality. Promote to stage-3 checklist or new SKILL.md.

## Next entry point for new session

1. `gh pr view 78 --comments` to confirm Yuki's revision comment landed; check if Noor has re-reviewed
2. If Noor has not yet re-reviewed: spawn Noor on Opus 4.7 xhigh per the template above
3. If Noor APPROVED: auto-approve workflow should fire; then `gh pr merge 78 --squash --delete-branch` (Martin or coordinator)
4. If Martin approved PR #79 + #80: merge with `gh pr merge {N} --squash --delete-branch`
5. After PR #78 ships, pick next v0.5.0 work — likely #59 (Azure commitment-discount rules to Diego)
