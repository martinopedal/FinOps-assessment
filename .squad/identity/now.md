---
updated_at: 2026-05-13T11:59:00.000Z
focus_area: PR #78 (#61 playbook reporter) REJECTED — Yuki revises; PR #79 housekeeping awaits Martin; PR #80 Noor history housekeeping
active_issues: [61, 73, 75, 76]
open_prs: [78, 79, 80]
locked_out_for_61_revision: [diego, maya]
---

# What We're Focused On

## TL;DR for next coordinator session

Three open PRs, three distinct gates blocking each:

- **PR #78** (`squad/61-impl-diego` @ `eef9b10`) — Diego's stage-5 implementation of the playbook/ticket reporter (#61). 49 files, +3583/−122, 11/11 CI green. **Noor REJECTED** at 11:56 — 1 BLOCKING + 3 AMENDMENT + 2 NIT. Verdict comment posted: PR #78 comment 4439705231 (workflow markers `**Stage-4 Adversarial Review — Noor**` + `VERDICT: REJECT`). Yuki's hardening review still running at session end (~14 min, 0 output files yet).
- **PR #79** (`squad/post-pr72-rescue-housekeeping` @ `9af52a3`) — coordinator rescue commit surfacing the 6 `.squad/` files Scribe orphaned after the PR #72 cycle. NIT-only. CI green. Awaiting Martin's manual approval (his choice — see PR #79 below).
- **PR #80** (`squad/noor-pr78-stage4-housekeeping`, draft) — Noor's own `.squad/agents/security-reviewer/history.md` learnings entry (+2 lines). Same gate situation as PR #79.

Local main is clean at `f96a5e9`. PR #72 (locked stage-3 plan for #61) merged earlier this session.

## PR #78 — REJECTED, Yuki revises

**Noor's verdict on disk:** `.squad/decisions/inbox/noor-pr78-stage4.md` (12 KB, full diagnostic). Also posted as PR #78 comment 4439705231.

**The BLOCKING (#1)** — manifest contract violation:
- Diego implemented the locked plan literally: `_STABLE_SURFACES = frozenset({"azure"})`, manifest emits `azure: stable` regardless of `pii_redaction`.
- But `engine.py:70-75` `RuleContext.redact()` per-run-salts ANY principal when `redact_pii=True` (default). Azure principals reach the reporter as `sha256:<16-hex>` strings hashed with the per-run salt.
- Empirical proof in Noor's verdict: two runs produced different `ticket_key` for the same Azure finding while manifest claimed `azure: stable`.
- Visible in shipped demo `examples/playbook.jsonl.manifest.json`: three statements (`mode: salted_hash`, `pii_redaction: true`, `azure: stable`) cannot all be true given current engine.
- **Defect origin (Noor's self-note):** plan-level. "Yuki's revision and my consensus pass both assumed Azure principals were cleartext at the reporter boundary; neither traced through `redact()`. Diego implemented the locked plan faithfully."

**Fix Path A (Noor's recommended, in-PR):**

```python
stability = {
    "azure":  "stable" if not pii_redaction else "per_run",
    "ado":    "stable" if not pii_redaction else "per_run",
    "github": "stable" if not pii_redaction else "per_run",
    "m365":   "stable" if not pii_redaction else "per_run",
}
```

Plus: update `_STABLE_SURFACES` comment, the `pii_handling.note`, and add a regression test that re-runs the engine end-to-end (NOT a hand-crafted cleartext fixture — that's the test gap that let it slip past, see Noor's NIT #1).

**Other findings (ship in same revision commit):**

- AMENDMENT #1 — `extract_template_vars()` re-parses every render → memoize on `rule_id` (perf cliff at 10K findings)
- AMENDMENT #2 — `**evidence` spread overrides reserved render-context keys → spread evidence FIRST then reserved keys, OR namespace as `ctx["evidence"]`
- AMENDMENT #3 — `_playbook_env.py` docstring claims module-import init but `get_playbook_env()` is lazy → either change docstring or call at import
- NIT #1 — fix the test coverage gap that allowed BLOCKING #1 to slip
- NIT #2 — same false assumption in `focus_aligned.py` (PR #70 inheritance) → fold into BLOCKING #1 fix or file follow-up

**Reviewer Rejection Lockout — STRICT.** Diego is locked out. Maya is also locked out from this artifact (she owned the original stage-3 plan with the false assumption, then was locked out by Noor's first reject; the Yuki-revised plan also carried the assumption). **Yuki owns the revision** — deepest plan-revision context AND her hardening review at session end may surface related issues.

**Spawn for next session (template):**

```
agent_type: general-purpose
model: claude-opus-4.7-xhigh   # surgical correctness on PII contract
mode: background
description: "🧪 Yuki: Revise PR #78 per Noor REJECT (BLOCKING #1 + 3 amendments)"
prompt: "You are Yuki. Read .squad/decisions/inbox/noor-pr78-stage4.md (or
  decisions.md if Scribe merged). Diego is locked out. Maya is locked out.
  Apply Fix Path A on branch squad/61-impl-diego. Add regression test that
  uses a real engine run (not hand-crafted fixture) and asserts cross-run
  ticket_key stability under default redaction. Address all 3 amendments.
  Update _STABLE_SURFACES comment + pii_handling.note. Commit + push to
  the same branch — PR #78 picks up the new commit. Then post a comment on
  PR #78 summarizing the revision so Noor's re-review has context."
```

## PR #79 — Housekeeping rescue, awaiting Martin's approval

NIT-only `.squad/` diff (52 lines added). The 6 files Scribe orphaned: `.squad/decisions.md` §11 subsection, `.squad/log/2026-05-13T085500Z-61-stage4-reject-revise-cycle.md`, four agent history entries.

**Martin's choice:** approve manually rather than have the coordinator post a fake-Noor verdict (impersonating a reviewer for a PR she never reviewed feels wrong). Once approved + CI green: `gh pr merge 79 --squash --delete-branch`.

If Martin hasn't approved by session start, gentle nudge: *"PR #79 still needs your approval — NIT-only docs rescue."*

## PR #80 — Noor's history.md housekeeping

Single-file diff: `.squad/agents/security-reviewer/history.md` (+2 lines, +0 deletions). Branch `squad/noor-pr78-stage4-housekeeping`, draft. Opened by Noor at end of stage-4 review for her own learnings entry. Same approval gate as PR #79.

## Background agents at session end

| ID | Status | Action for next session |
|---|---|---|
| `noor-stage4-78` | IDLE — done at 11:58, full result captured (REJECT, comment posted, PR #80 opened) | Nothing — fully done |
| `yuki-hardening-78` | RUNNING (~14 min, 0 output files yet) | `read_agent yuki-hardening-78` once on session start; if BLOCKER, fold into Yuki revision scope |

If Yuki produces a hardening BLOCKER on top of Noor's REJECT, fold both findings into the same Yuki revision spawn. If Yuki finds nothing or only NITs, just do the BLOCKING #1 fix.

## Decision-inbox state at session end

```
.squad/decisions/inbox/
  noor-61-stage4-rereview.md                    (1.5 KB, 11:04 — orphan from earlier #61 cycle, Scribe missed)
  noor-pr78-stage4.md                           (12 KB, 11:56 — NEW, Noor's REJECT verdict on PR #78)
  copilot-session-handoff-2026-05-13T1158Z.md   (NEW, this handoff record)
```

**First action for next coordinator:** spawn Scribe to merge inbox into `decisions.md` so Yuki on revision can read it from the canonical ledger. Or just point Yuki at the inbox file directly — the verdict is too important to risk Scribe missing it again.

Note: `now.md` (this file) and `wisdom.md` were also discovered IN `.squad/decisions/inbox/` during the status check — they're misplaced. Coordinator may want to investigate why; not blocking.

## Other in-flight backlog (parked)

After PR #78 ships, these are queued (Maya's triage from earlier in v0.5.0 cycle):

- #59 Azure commitment-discount rules (next v0.5.0 work)
- #62 unit-economics card (v0.5.0)
- #66, #67, #68, #69, #71 — labeled and queued for v0.6.0+
- #73 (engine tenant-stable PII salt) — explicitly the architectural fix Noor's BLOCKING #1 defers to; PR #78's fix is a temporary honest-declaration band-aid until #73 lands
- #74 (runtime template overlay), #75 (Scribe-vs-Stage-4 race), #76 (Scribe charter branch-handling)

## Squash log of recent merges (this cycle)

- PR #55 → `23da547` — docs-voice SKILL (closed #53)
- PR #70 → focus_aligned reporter for #58
- PR #72 → `f96a5e9` — locked stage-3 plan for #61 (Maya base + Yuki revision after Noor REJECT)
- PR #78, #79, #80 — open (this session)

## Lessons promoted (already in decisions.md from earlier batches)

- **Reviewer Rejection Lockout binds to artifact, not role** — Maya was the locked-out plan author; Yuki revised; Noor approved on re-review. Same pattern now applies to implementation: Diego implemented, Yuki revises.
- **Multi-file reporter outputs use Option C atomic-write contract** — manifest as readiness marker, `os.fsync` before `os.replace`, sha256 self-attestation, `--cleanup-orphans` for crash recovery. Diego's PR #78 implements this faithfully (Noor's review confirms).
- **Stage-4 must prove per-surface invariants empirically** — Noor's self-note in the verdict: when a plan asserts a per-surface invariant, prove it with a two-run end-to-end fixture, not a single-fixture spot check. This is the lesson from PR #78 BLOCKING #1.

## Next entry point for new session

1. `gh pr view 78 --comments` → confirm Noor's REJECT comment is visible
2. `gh pr view 79` → check if Martin approved
3. `gh pr view 80` → understand Noor's housekeeping PR scope (already inspected: +2 lines in security-reviewer/history.md)
4. `read_agent yuki-hardening-78` once → collect her verdict; if BLOCKER, fold into Yuki revision scope
5. Spawn Scribe to merge the 3 inbox files into `decisions.md`
6. Spawn Yuki on Opus 4.7 xhigh for the PR #78 revision per spawn template above
7. Once #79 approved by Martin + CI green: `gh pr merge 79 --squash --delete-branch`
8. Once #80 approved by Martin + CI green: `gh pr merge 80 --squash --delete-branch`
