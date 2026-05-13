# Stage-3 Plan — Serialize Scribe behind Stage-4 verdict (#75)

> **Issue:** [#75](https://github.com/martinopedal/FinOps-assessment/issues/75)
> **Reproduction:** [PR #72](https://github.com/martinopedal/FinOps-assessment/pull/72)
> **Author:** Maya (Lead)
> **Stage:** 3 — Plan (ready for Stage-4 adversarial review)

---

## §1 Research

### 1.1 Branch protection state on `main`

```json
{
  "dismiss_stale_reviews": true,
  "require_code_owner_reviews": false,
  "require_last_push_approval": false,
  "required_approving_review_count": 1
}
```

The critical setting is `dismiss_stale_reviews: true`. Any push after an
approval automatically dismisses that approval, regardless of who pushed
or what changed.

### 1.2 Race timeline from PR #72

| Time (UTC)     | Actor               | Event                                              | Commit   |
|----------------|----------------------|----------------------------------------------------|----------|
| 08:37:52       | martinopedal         | Stage-4 verdict posted: **REJECT** (round 1)       | —        |
| 08:56:04       | martinopedal         | Stage-3 revision by Yuki (post-Noor reject)        | —        |
| **09:03:51**   | martinopedal         | Stage-4 verdict posted: **APPROVE** (round 2)      | `10096cb`|
| **09:04:07**   | github-actions[bot]  | `squad-approve.yml` fires → bot APPROVED            | `10096cb`|
| **09:04:28**   | Scribe (parallel)    | Housekeeping commit pushed                          | `cc1e466`|
| ~09:04:28      | branch protection    | Stale approval dismissed (new commit on PR)         | —        |
| 09:06:52       | martinopedal         | Manual re-trigger: verdict re-posted against HEAD   | `cc1e466`|
| 09:07:05       | github-actions[bot]  | `squad-approve.yml` fires again → bot APPROVED      | `cc1e466`|

**Root cause:** The coordinator spawned Noor (Stage-4 reviewer) and
Scribe in parallel. Scribe's housekeeping commit landed ~21 seconds
after the bot approval, advancing HEAD and triggering
`dismiss_stale_reviews`. The PR returned to `REVIEW_REQUIRED`.

**Mitigation applied:** The coordinator manually re-posted the verdict
comment to re-trigger `squad-approve.yml` against the new HEAD. This
worked but is manual and fragile.

### 1.3 Current Scribe-spawn ordering in `.squad/routing.md`

Rule 1 (line 67): *"Eager by default — spawn all agents who could
usefully start work, including anticipatory downstream work."*

Rule 2 (line 68): *"Scribe always runs after substantial work, always
as `mode: "background"`. Never blocks."*

These two rules together encourage parallel Scribe spawn. Neither rule
accounts for the interaction with `dismiss_stale_reviews`.

### 1.4 Current Scribe-spawn ordering in `squad.agent.md`

Line 425: *"Scribe: Cannot fire-and-forget. Batch Scribe as the LAST
subagent in any parallel group."*

Line 692–707: Post-work turn guidance says: "(1) present compact
results, (2) spawn Scribe." Scribe is spawned after results are
collected, but the guidance does not mention waiting for the bot
approval to land before Scribe pushes.

Line 786: `squad.agent.md` is **authoritative governance** — only
the repo maintainer (human) may write to it.

### 1.5 `squad-approve.yml` workflow analysis

The workflow (lines 35–150):
- **Trigger:** `issue_comment.created` (NOT `.edited`)
- **Gate 1:** Comment is on a PR (`issue.pull_request != null`)
- **Gate 2:** Comment author is repo owner
- **Gate 3:** Comment body contains `Stage-4 Adversarial Review` + `Noor`
- **Gate 4:** `VERDICT: APPROVE` extracted from body
- **Gate 5:** PR carries a `squad:*` label
- **Gate 6:** Fork guard (head repo == base repo)
- **Gate 7:** Idempotency — skip if `github-actions[bot]` already APPROVED

**Notable gap:** No `commit_id == HEAD` check. The workflow approves
against whatever HEAD is current when it runs, not against the commit
Noor actually reviewed. If HEAD has moved (Scribe push), the approval
targets the new commit — but that only works if Scribe hasn't already
caused the first approval to be dismissed.

### §1.1 Disambiguation table

| Concept | Actor | Mechanism | Semantics | Dismissable? |
|---------|-------|-----------|-----------|--------------|
| **(a) Stage-4 review verdict** | Noor (adversarial reviewer, Opus 4.7) | PR comment posted by coordinator (as repo owner) | Contains `Stage-4 Adversarial Review — Noor` marker + `VERDICT: APPROVE/REJECT` line. This is the *intellectual* review signal. | N/A — it's a comment, not a review |
| **(b) Bot approval** | `github-actions[bot]` via `squad-approve.yml` | `pulls.createReview` with `event: APPROVE` | Triggered by (a) landing as a new `issue_comment`. This is the *mechanical* review that satisfies branch protection's `required_approving_review_count: 1`. | **Yes** — dismissed by any new push if `dismiss_stale_reviews: true` |
| **(c) Housekeeping commit** | Scribe (background agent, Haiku) | `git add .squad/ && git commit && git push` | Logs orchestration entries, merges decision inbox, updates agent histories. Advances HEAD on the PR branch. | N/A — it's a push, but it *causes* (b) to be dismissed |
| **(d) Human re-trigger** | Coordinator (repo owner) | New PR comment re-posting the verdict text | Same shape as (a) but explicitly states it is mechanical, not a fresh review. Re-fires `squad-approve.yml` against the new HEAD. | N/A — it produces a new (b) |

**Key insight:** (a) is a comment (not dismissable). (b) is a review
(dismissable by push). (c) is a push (causes dismissal of (b)). The
fix must ensure (c) completes before (b) is submitted, or (c) does not
happen at all until (b) has served its purpose (merge).

---

## §2 Rubberduck — walkthrough and edge cases

### Proposed serialization

**Before (current, racy):**
```
Coordinator spawns [Noor, Scribe] in parallel
  → Noor posts verdict → squad-approve.yml fires → bot approves
  → Scribe pushes housekeeping commit (races against bot approval)
  → dismiss_stale_reviews dismisses bot approval
```

**After (proposed, serialized):**
```
1. Coordinator spawns Noor alone (Stage-4 reviewer)
2. Coordinator waits for Noor's verdict
3. If APPROVE:
   a. Coordinator posts verdict comment (triggers squad-approve.yml)
   b. Coordinator waits for bot approval to land (poll PR reviews)
   c. Coordinator spawns Scribe (housekeeping)
   d. Scribe pushes → approval dismissed → but PR is already merged
      OR: Scribe pushes → coordinator re-triggers approval
4. If REJECT:
   a. Coordinator spawns Scribe immediately (no approval to dismiss)
   b. Lockout protocol proceeds normally
```

**Wait — step 3d still has the race.** If the PR is not yet merged
when Scribe pushes, the approval is dismissed again. Two sub-options:

- **Option A (recommended): Scribe pushes, then coordinator re-posts
  verdict.** This is the same manual mitigation from PR #72 but
  automated. The coordinator waits for Scribe to finish, then posts
  the verdict comment (which triggers bot approval against the final
  HEAD). One extra comment, but deterministic.

- **Option B: Coordinator merges before Scribe pushes.** Not viable —
  the coordinator doesn't have merge authority, and Scribe's logs are
  part of the PR's value.

- **Option C: Scribe pushes to a separate branch.** Overcomplicates
  the git model for marginal benefit.

**Refined sequence (Option A):**
```
1. Coordinator spawns Noor alone
2. Noor posts verdict
3. If APPROVE:
   a. Coordinator spawns Scribe (let it push housekeeping)
   b. Coordinator waits for Scribe to complete
   c. Coordinator posts verdict comment (triggers squad-approve.yml
      against final HEAD including Scribe's commit)
   d. Bot approves final HEAD — no further pushes to dismiss it
4. If REJECT:
   a. Coordinator spawns Scribe immediately (safe — no approval at stake)
   b. Lockout protocol proceeds
```

This is cleaner: the verdict comment is always posted against the
final HEAD, so the bot approval is never stale.

### Edge cases

**E1: Noor REJECTS — does serialization handle this?**
Yes. On REJECT, there is no bot approval to protect. Scribe can run
immediately (parallel or sequential — doesn't matter). The lockout
protocol proceeds: original implementer is locked out, a backup agent
picks up the revision, and the cycle restarts. Scribe logging the
round is safe because no approval exists to dismiss.

**E2: `squad-approve.yml` fails to fire (workflow error)**
The coordinator must not block forever waiting for bot approval. Since
the refined sequence (Option A) posts the verdict comment *after*
Scribe, the wait is for `squad-approve.yml` to process the comment.
Define:
- **Timeout:** 120 seconds after posting the verdict comment.
- **Escalation:** If no bot approval appears within timeout, the
  coordinator posts a warning comment: *"⚠️ squad-approve.yml did not
  fire within 120s. Manual merge approval may be required."* and tags
  the repo owner.
- **No infinite block:** The coordinator proceeds with its post-work
  summary regardless. The PR remains in `REVIEW_REQUIRED` but the
  human can approve manually.

**E3: Scribe push for unrelated reasons (cross-agent history note)**
Same problem, same fix. The routing rule must be general: *any* push
to a PR branch after bot approval dismisses the approval. Therefore
the rule is: **no agent may push to a PR branch between bot approval
and merge.** Scribe is the most common offender, but the rule covers
any agent. In practice, only Scribe pushes `.squad/` changes to PR
branches, so the scope is narrow.

**E4: Multiple Stage-4 cycles (round 2+ after revision)**
Each revision cycle follows the same sequence: Noor reviews → Scribe
logs → coordinator posts verdict. The serialization rule applies
identically on every cycle. The idempotency guard in
`squad-approve.yml` (line 122–131) checks for an existing
`github-actions[bot]` APPROVED review — but `dismiss_stale_reviews`
will have dismissed any prior bot approval when the revision was
pushed, so the idempotency check won't block the re-approval.
Confirmed: each cycle is independent.

**E5: Race between coordinator's verdict post and Noor's direct post**
In the current squad model, Noor does not post directly to the PR.
The coordinator collects Noor's verdict via `read_agent` and posts it
as the repo owner (required by `squad-approve.yml` gate 2). There is
no race because there is only one poster. If a future change allows
Noor to post directly (e.g., via a GitHub Action), the workflow's
owner-gate would reject Noor's comment anyway (Noor is not the repo
owner). No action needed.

---

## §3 Implementation plan

### 3.1 File changes

#### Change 1: `.squad/routing.md` — add explicit Scribe-after-Stage-4 ordering rule

**Location:** Rules section (after current rule 2, line 68)

**Add new rule 2a** (renumber existing rules):

```markdown
2a. **Scribe-after-Stage-4 (branch-protection safety).** When a PR is in
    Stage-4 review, the coordinator MUST NOT spawn Scribe (or any agent
    that pushes commits) until after the verdict comment has been posted
    and the bot approval has landed — or, if using the deferred-verdict
    pattern, until Scribe has finished pushing and the verdict comment
    is posted against final HEAD. See `docs/plans/075-serialize-scribe-behind-stage4.md`
    for the refined sequence. On REJECT, Scribe may run immediately
    (no approval to protect).
```

**Also amend rule 2** to add a caveat:

```markdown
2. **Scribe always runs** after substantial work, always as
   `mode: "background"`. Never blocks. **Exception:** during Stage-4
   approval flow, Scribe is serialized per rule 2a.
```

#### Change 2: `.squad/routing.md` — document the deferred-verdict pattern

**Location:** New subsection after the Rules section

```markdown
### Deferred-verdict pattern (Stage-4 → Scribe → approve)

When the coordinator receives an APPROVE verdict from Noor:

1. Spawn Scribe to log the orchestration cycle (background, wait for
   completion).
2. After Scribe's commit lands, post the verdict comment (which
   triggers `squad-approve.yml`).
3. The bot approval now targets final HEAD (including Scribe's commit).
   No subsequent push will dismiss it.
4. If Scribe fails or times out (>180s), post the verdict comment
   anyway and note the Scribe failure in the PR.

On REJECT: spawn Scribe immediately (no approval at stake). Post the
reject verdict at any time — `squad-approve.yml` ignores non-APPROVE
verdicts.
```

#### Change 3 (optional, belt-and-braces): `.github/workflows/squad-approve.yml`

Add a `commit_id == HEAD` validation step after the existing gates.
This prevents a stale verdict comment (posted against an older commit)
from approving a HEAD that Noor never reviewed.

**Location:** After the idempotency check (line ~131), before `createReview`:

```javascript
// HEAD-match guard: the verdict comment must have been posted
// after (or concurrent with) the current HEAD. We check that
// the PR's current head SHA is reachable from the comment's
// creation timestamp. As a simpler proxy: compare the comment's
// associated commit (if the API exposes it) or skip this guard
// if the deferred-verdict pattern is in use (the comment is
// always posted against final HEAD by construction).
//
// NOTE: issue_comment events do not carry a commit_id field.
// The comment is on the issue (PR) level, not on a specific
// commit. Therefore this guard must fetch the PR's head SHA
// and compare it to the SHA mentioned in the verdict body
// (if Noor includes it). This is advisory, not blocking.
```

**Decision:** This change is **genuinely optional**. The base fix
(Change 1 + Change 2) eliminates the race by construction. The
`commit_id == HEAD` check is defense-in-depth for scenarios where the
routing rules are not followed (e.g., a manual verdict post). We
recommend implementing it as a follow-up PR, not in the same PR as
the routing fix, to keep the scope minimal.

#### Change 4: No change to `.github/agents/squad.agent.md`

The `squad.agent.md` file is **authoritative governance** (line 786)
and may only be written by the repo maintainer. The Scribe-spawn
ordering is a **routing policy**, not a governance change. The fix
lives entirely in `.squad/routing.md`, which the coordinator owns.

**Self-development rule compliance:** Since we are NOT editing
`squad.agent.md`, no restart guidance is needed. The coordinator will
pick up the new routing rules on the next session by reading
`.squad/routing.md` (which it already does per the session-start
protocol).

However, note that `squad.agent.md` line 425 says *"Batch Scribe as
the LAST subagent in any parallel group"* and line 707 says *"Spawn
Scribe"* in the post-work turn. These are compatible with the new
routing rule (Scribe is still last), but they don't explicitly call
out the Stage-4 serialization. A future governance update could add a
cross-reference, but that is out of scope for this PR.

### 3.2 Test plan

This is a process/documentation change, not a code change. There are
no unit tests to write. Verification is:

1. **Manual replay of PR #72 pattern.** After merging this plan's
   implementation PR, the next PR that goes through Stage-4 review
   should follow the deferred-verdict pattern. The coordinator should:
   - Spawn Noor alone (no parallel Scribe)
   - Wait for verdict
   - On APPROVE: spawn Scribe, wait for completion, then post verdict
   - Confirm bot approval lands against final HEAD
   - Confirm no dismissal occurs

2. **PR #72 post-mortem check.** The PR #72 timeline should be
   cited in the implementation PR as the "before" state. The "after"
   state is the next Stage-4 cycle.

3. **Negative test (REJECT path).** On the next REJECT verdict,
   confirm Scribe runs immediately and no approval-related issues
   occur (there should be no bot approval to dismiss).

### 3.3 Acceptance criteria (from issue #75)

- [x] Plan documents Scribe-after-Stage-4 ordering in `.squad/routing.md`
- [x] Default Scribe spawn timing is post-verdict, not parallel-with-reviewer
- [x] Failure mode specified (timeout + escalation for bot approval)
- [x] `squad-approve.yml` `commit_id == HEAD` check documented as optional follow-up
- [x] Self-development rule compliance confirmed (no `squad.agent.md` edit)
- [x] Re-review cycles (round 2+) covered — same serialization per cycle

---

## Plan invariants (for Noor's Stage-4 verification)

| # | Invariant | Status |
|---|-----------|--------|
| 1 | **Default-state PR experience improves** — documented default is "Scribe runs after verdict comment is posted against final HEAD" | ✅ Deferred-verdict pattern in §3.1 Change 2 |
| 2 | **Failure modes specified** — timeout (120s) + escalation (warning comment + owner tag) if bot approval never arrives | ✅ Edge case E2 in §2 |
| 3 | **No breakage of existing pattern** — Scribe still gets all data (orchestration manifest built before Scribe spawns regardless of timing) | ✅ Scribe prompt is unchanged; only spawn timing changes |
| 4 | **Self-development rule compliance** — no edit to `squad.agent.md` | ✅ Confirmed in §3.1 Change 4 |
| 5 | **Optional workflow hardening is genuinely optional** — base fix works without `commit_id == HEAD` check | ✅ Explicitly deferred to follow-up PR in §3.1 Change 3 |
| 6 | **Plan covers re-review cycles (round 2+)** — same serialization on every revision cycle | ✅ Edge case E4 in §2 |
