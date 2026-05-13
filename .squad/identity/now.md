---
updated_at: 2026-05-13T22:15:00.000Z
focus_area: "#59 epic continuing (rules 1-3 plans MERGED, rule 1 impl MERGED via lockout; rule 2 impl IN FLIGHT on PR #88; rule 3 impl Diego assigned; rule 4 plan IN FLIGHT on PR #89 awaiting Noor stage-4); discriminator-vs-identifier disambiguation pattern now binding across two rules"
active_issues: [59, 73, 74, 75, 76, 81, 82]
open_prs: [88, 89]
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
- **PR #88** (rule 2 impl, `AZ.COMMITMENT_UNDER_COVERED`) -- IN FLIGHT (Diego). Awaiting Noor stage-4 verdict (inbox drop `noor-pr88-stage4.md` not yet folded).
- **PR #89** (rule 4 plan, `AZ.RESERVATION_SCOPE_MISMATCH`) -- IN FLIGHT (Maya). Draft, awaiting Noor stage-4. Plan adds ONE field (`applied_scope_subscription_ids: list[str] | None`) to `AzureReservation`; keeps existing `scope` as the `appliedScopeType` discriminator. Two stage-3 corrections surfaced (Shared->Single does NOT save cost; one field not two). Resolves rule 2's E11 over-count as a side-effect (rule-2 amendment is OUT of scope, follow-up issue at impl time).
- **Rules 2-5** -- rule 2 impl in flight on PR #88; rule 3 impl (Diego) assigned and not yet started; rule 4 plan in flight on PR #89 with rule 4 impl awaiting plan merge; rule 5 not yet planned.

## Norms reinforced this session

- **Reviewer Rejection Lockout protocol binding precedent:** when stage-4 rejects stem from plan-rooted false assumptions (not implementer drift), lock out plan author (prevents confirmation bias, routes revision to backup implementer with fresh eyes).
- **Discriminator-vs-identifier disambiguation rule (binding across two rules now):** when stage-3 brief enumerates API field discriminators (e.g., `Single`/`Shared`), prose must disambiguate by naming both the discriminator field AND the actual identifier source via a side-by-side table in §1.1. PR #85 instance: `family_name` discriminator vs `arn` identifier. PR #89 (rule 4) instance: `appliedScopeType` discriminator string (`Single`/`Shared`/`ManagementGroup`) vs `appliedScopes` identifier list (subscription/MG ARNs). Pattern is now binding for any rule that reads an enum + corresponding identifier.
- **Schema-extension stage-3 plans (binding from PR #89):** when an existing field already carries a discriminator string and a new rule needs the corresponding identifier list, add ONE new identifier-list field and document the discriminator-vs-identifier relationship in §1.1; do NOT bundle a discriminator-rename into the same PR. Model-cleanup is a separate concern with its own backward-compat ceremony for both ARM and CSV.
- **Savings-claim verification (binding from PR #89 Correction A):** when an epic body asserts a savings angle, stage-3 plans must independently verify the assertion is cost-impacting (changes a unit price, term length, or covered-vs-uncovered spend), not merely organisational (preference, governance, visibility). Organisational findings are info-severity at most and ship as separate rules.
- **Cross-rule isolation signal-based framing:** preferred terminology is "disjoint by signal" (rules read different fields, may co-fire but are orthogonal) over "disjoint by gate" (one rule excludes the other's signal via explicit logic).
- **CSV strict-column backward-compat guarantee (implicit, now binding):** legacy CSV fixtures missing new optional columns load via `csv.DictReader` + pydantic field defaults to None; two rules (rule 3 + future rule 4) depend on this.
- **Procedural pattern (local sync required for main merge):** PRs #84 and #86 required local merge with main on feature branch (GitHub's mergeability check does not honour custom merge drivers) before final merge; future multi-file YAML PRs should expect this.
- **Stage-3 producer-path citation tables operationalised:** all three rule plans (PR #83, #84, #86) used §3.7 citation tables (file:line evidence) to anchor material claims; verification effort scales linearly with table size, not plan length.
- **Working-tree contamination resolution:** Noor directly edited her own history.md during PR #85 first review (unstaged append, violating "gh-only, drop only to inbox" constraint); resolved via stash → main pull → stash pop. Subsequent Noor instances given explicit "do not write to any tracked file" constraint and complied. Contamination preserved in consolidated wrap because it represents accurate stage-4 work.

## Outstanding for next session

1. Spawn Noor stage-4 on **PR #88** (rule 2 impl, `AZ.COMMITMENT_UNDER_COVERED`) -- inbox drop `noor-pr88-stage4.md` already in `.squad/decisions/inbox/` (created 2026-05-13 17:23, not yet folded by Scribe); coordinator should fold then route verdict.
2. Spawn Noor stage-4 on **PR #89** (rule 4 plan, `AZ.RESERVATION_SCOPE_MISMATCH`). Plan ships at `docs/plans/059-az-reservation-scope-mismatch.md`. Stage-4 invariants enumerated in §4 (14 of them); §3.7 has 16 producer-path citations to re-verify against `main` SHA `a549a1d`. Inbox drop at `.squad/decisions/inbox/maya-59-rule4-stage3-plan.md`.
3. Spawn Diego (or Yuki backup) for **rule 3 impl** (`AZ.COMMITMENT_RENEWAL_REVIEW`) -- plan PR #86 merged; rule 3 impl assigned to Diego; can run in parallel with PR #88 rule 2 impl and (post-merge) PR #89 rule 4 plan (trivial textual conflict on `models.py` + `tests/test_engine.py:23`).
4. After PR #89 merges, spawn **Diego (primary) / Yuki (backup) for rule 4 impl** (`AZ.RESERVATION_SCOPE_MISMATCH`). Diego is NOT locked out (PR #85 lockout was per-PR).
5. Spawn Maya stage-3 plan for **rule 5 (`AZ.AHB_ELIGIBLE`)** -- last child of #59 epic.
6. File **follow-up issue at rule 4 impl time:** amend rule 2 (`AZ.COMMITMENT_UNDER_COVERED`) to consume the new `applied_scope_subscription_ids` field and close E11 over-count limitation. Out of scope for PR #89 / rule 4 impl PR (one rule, one PR).
7. Schedule issue #59 epic retrospective (Friday end-of-week) to document five-rule multi-agent loop learnings and update roadmap for M0–M7 surface expansion.

## Other open work

- **#73** engine tenant-stable PII salt -- referenced in plans as engine-level fix; does not block rule shipping.
- **#74** runtime template overlay; **#75** Scribe-vs-Stage-4 race; **#76** Scribe charter branch-handling.
- **#81** repo-wide CRLF hygiene (Maya, go:needs-research).
- **#82** playbook nit cleanups (Yuki, go:needs-research).
- **#62** unit-economics card (v0.5.0 follow-on, go:yes).
- **#60** read-only MCP server (Maya, go:yes).
- **#59 epic retrospective** (Friday end-of-week, 90-min session, Maya + Diego + Yuki + Noor + Scribe): document five-rule multi-agent loop learnings, canonicalize any additional pattern learnings, update roadmap for M0–M7 surface expansion (M365, GitHub, ADO, GCP/AWS scope if applicable).
