---
updated_at: 2026-05-13T22:15:00.000Z
focus_area: "#59 epic shipping cycle wrapped (rules 1-3 plans MERGED, rule 1 impl MERGED via lockout, Reviewer Rejection Lockout protocol canonicalized, discriminator-vs-ARN pattern binding); rules 2-5 impl pending; rule 2 impl Diego queued, rule 3 impl Diego assigned"
active_issues: [59, 73, 74, 75, 76, 81, 82]
open_prs: []
---

# What We're Focused On

## TL;DR for next coordinator session

The #59 epic shipping cycle is complete (5 inbox drops folded, 4 agent histories updated, decisions ledger canonicalized). All three rule plans and rule 1 implementation shipped.

State as of this checkpoint:

- **PR #83** (rule 1 plan, `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`) -- MERGED.
- **PR #84** (rule 2 plan, `AZ.COMMITMENT_UNDER_COVERED`) -- MERGED.
- **PR #85** (rule 1 impl, `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`) -- MERGED via Reviewer Rejection Lockout (Diego blocked M1/M2/M3, Yuki revised all 3 BLOCKING items + 5 NITs, Noor re-approved).
- **PR #86** (rule 3 plan, `AZ.COMMITMENT_RENEWAL_REVIEW`) -- MERGED.
- **Reviewer Rejection Lockout precedent** (PR-#78) now binding: when stage-4 verdict stems from false assumptions in stage-3 brief (not implementer drift), plan author is locked out and revision routes to backup implementer (Yuki). Pattern prevents confirmation bias and catches brief false positives before they lock implementation.
- **Rules 2-5** -- rule 2 impl (Diego) queued pending Noor stage-4 on PR #84 plan (now merged); rule 3 impl (Diego) assigned; rules 4-5 not yet planned.

## Norms reinforced this session

- **Reviewer Rejection Lockout protocol binding precedent:** when stage-4 rejects stem from plan-rooted false assumptions (not implementer drift), lock out plan author (prevents confirmation bias, routes revision to backup implementer with fresh eyes).
- **Discriminator-vs-ARN disambiguation rule:** when stage-3 brief enumerates API field discriminators (e.g., `Single`/`Shared`), prose must disambiguate by naming both the discriminator field and the actual identifier source ("the discriminator field whose values are X; the actual ARN comes from Y", not just "the scope (X/Y)").
- **Cross-rule isolation signal-based framing:** preferred terminology is "disjoint by signal" (rules read different fields, may co-fire but are orthogonal) over "disjoint by gate" (one rule excludes the other's signal via explicit logic).
- **CSV strict-column backward-compat guarantee (implicit, now binding):** legacy CSV fixtures missing new optional columns load via `csv.DictReader` + pydantic field defaults to None; two rules (rule 3 + future rule 4) depend on this.
- **Procedural pattern (local sync required for main merge):** PRs #84 and #86 required local merge with main on feature branch (GitHub's mergeability check does not honour custom merge drivers) before final merge; future multi-file YAML PRs should expect this.
- **Stage-3 producer-path citation tables operationalised:** all three rule plans (PR #83, #84, #86) used §3.7 citation tables (file:line evidence) to anchor material claims; verification effort scales linearly with table size, not plan length.
- **Working-tree contamination resolution:** Noor directly edited her own history.md during PR #85 first review (unstaged append, violating "gh-only, drop only to inbox" constraint); resolved via stash → main pull → stash pop. Subsequent Noor instances given explicit "do not write to any tracked file" constraint and complied. Contamination preserved in consolidated wrap because it represents accurate stage-4 work.

## Outstanding for next session

1. Merge PR #84 (AZ.COMMITMENT_UNDER_COVERED plan) if not already merged (verify with `gh pr view 84 --json state`).
2. Merge PR #86 (AZ.COMMITMENT_RENEWAL_REVIEW plan) if not already merged (verify with `gh pr view 86 --json state`).
3. Spawn Noor stage-4 on PR #85 rule 1 implementation if not already approved/merged (verify with `gh pr view 85 --json state`).
4. Spawn Noor stage-4 on PR #84 (rule 2 plan) verdict so Diego can begin rule 2 implementation (PR #84 now merged, stage-4 needed).
5. Spawn Maya stage-3 plan for rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`) if not already assigned; PR #86 is the plan, now merged; rule 3 impl Diego assigned.
6. Spawn Maya stage-3 plan for rule 4 (`AZ.RESERVATION_SCOPE_MISMATCH`) and rule 5 (`AZ.AHB_ELIGIBLE`).
7. Schedule issue #59 epic retrospective (Friday end-of-week) to document five-rule multi-agent loop learnings and update roadmap for M0–M7 surface expansion.

## Other open work

- **#73** engine tenant-stable PII salt -- referenced in plans as engine-level fix; does not block rule shipping.
- **#74** runtime template overlay; **#75** Scribe-vs-Stage-4 race; **#76** Scribe charter branch-handling.
- **#81** repo-wide CRLF hygiene (Maya, go:needs-research).
- **#82** playbook nit cleanups (Yuki, go:needs-research).
- **#62** unit-economics card (v0.5.0 follow-on, go:yes).
- **#60** read-only MCP server (Maya, go:yes).
- **#59 epic retrospective** (Friday end-of-week, 90-min session, Maya + Diego + Yuki + Noor + Scribe): document five-rule multi-agent loop learnings, canonicalize any additional pattern learnings, update roadmap for M0–M7 surface expansion (M365, GitHub, ADO, GCP/AWS scope if applicable).
