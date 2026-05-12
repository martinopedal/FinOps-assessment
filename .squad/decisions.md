# Squad Decisions

## Active Decisions

### 2026-05-12T10:51Z  ,  User directive  ,  local-spawn preference when repo is open (Coordinator)

**By:** martinopedal (via Squad Coordinator)

**Decision:** When the local checkout is active and the user is at the keyboard, default to **local squad-member spawns** for follow-up work, not `@copilot`-direct bot routing. The `@copilot`-direct posture applies to **async/cloud/away-from-keyboard** work. Multi-agent fan-out stays on-request.

**Why:** Martin observed that routing #44 to @copilot when the local checkout was already open added GitHub round-trip latency and bot-cooking time without saving cost  ,  we'd rubric-review the bot's PR anyway, so we may as well spawn the right squad member locally and ship faster.

**Routing matrix update:**

| Context | Default routing |
|---------|----------------|
| User at local keyboard, repo open | Local squad spawn (Lightweight/Standard mode) |
| Async / cloud / away-from-keyboard | `@copilot`-direct (rubric review on PR) |
| Frontier-epic kickoff (architecture, security audit) | Multi-agent fan-out (on-request exception) |
| Routine work, no local session | `@copilot`-direct (rubric review on PR) |

**Supersedes/refines:** The 2026-05-12 rubric reframe entry (issue #25). The reframe still stands; this clarifies the trigger for local vs bot routing within the rubric posture.

### 2026-05-12  ,  Squad-PR auto-approve workflow for Noor-verdict comments (issue #47, PR #48)

**By:** Maya & Coordinator (design + implementation)

**Decision:** Squad PRs on `main` no longer require the `enforce_admins` toggle dance to bypass branch protection. Implement `.github/workflows/squad-approve.yml` that listens for the Stage-4 verdict comment (Noor's **`VERDICT: APPROVE`** line with the **`Stage-4 Marker`** tag). When both are present, the workflow submits a `github-actions[bot]` approval, satisfying branch protection's review-count rule.

**Design choice:** **Option A  ,  Workflow approval via `github-actions[bot]`** (implemented in #48).
- Trigger: PR comment by repo owner matching the verdict pattern.
- Action: Workflow runs, parses the comment, posts `github-actions` as a 2nd approver.
- Pros: Lightweight, no additional secrets, uses GitHub Actions permissions already granted, decouples verdict logic from GitHub API calls.
- Cons: Adds one more workflow file to the CI/CD surface; requires comment text discipline.

**Rejected alternatives (with one-line reasons):**
- **Option B  ,  Separate `noor-bot` GitHub App/PAT identity.** Highest-fidelity presentation (review genuinely shows under "Noor"), but requires creating + rotating a second identity. Deferred; A is async-friendly today with zero new credentials.
- **Option C  ,  Carve `squad/*` branches out of protection.** Rejected  ,  squad PRs are *more* sensitive, not less. Large security hole.
- **Option D  ,  Rulesets with owner-bypass.** Still requires manual owner action per merge; only marginally less janky than the toggle dance.
- **Option E  ,  Document the toggle dance as the official protocol.** Legitimises the workaround instead of fixing it; not async-friendly.

**Trust model gates:**
- Workflow triggers only on **exact match** of Noor's verdict marker (case-sensitive, full string).
- Approval is **only** submitted by `github-actions[bot]` (no human bot account).
- Comment author **must** be the repo owner (Martin) or admin.
- Workflow is **read-only** on the GitHub API  ,  only creates an approval, never closes/cancels PRs or modifies other resources.

**Rollback path:** If `github-actions[bot]` approval doesn't satisfy `required_approving_review_count` in practice (e.g. counted as same identity as Coordinator, or disallowed by org policy), pivot to **Option B (separate `noor-bot` identity)** and file a follow-up issue. Workflow is idempotent; no data loss.

**Status:** Merged in PR #48. Coordinator followed up with `fix(squad): restore main's line endings` to correct Maya's editor (LF → CRLF) so the diff is clean.

### 2026-05-12  ,  Squad-memory bootstrap & label-drift cleanup (issue #23)

**Decision:** Land the 🟢-trivial squad-state cleanup from Maya's gap analysis (`.squad/decisions/inbox/maya-gap-analysis-2026-05-12.md`, §C) in a single PR closing #23, after Noor's stage-4 sign-off (`.squad/decisions/inbox/noor-stage4-2026-05-12.md`).

**Scope (in this decision, no others):**
1. Refresh `.squad/identity/now.md` (was pinned to "Initial setup" since 2026-05-04).
2. Seed `.squad/identity/wisdom.md` with the five Noor-approved patterns (PR archeology). Pattern (f) was rejected as a duplicate of (c) and pattern (d) was reworded per Noor's E.2.
3. Replace the `milestone:M1`–`milestone:M7` row in `.squad/routing.md` with the actual `release:v0.4.0`–`release:v1.0.0` and `release:backlog` rows. Hard replace, no redirect (Noor's E.3 audit confirmed no historical link expects the `milestone:Mx` shape).
4. Fix `Issue label` column drift in `.squad/team.md` and the `Route To` column in `.squad/routing.md`: actual labels are `squad:maya`/`squad:priya`/`squad:diego`/`squad:sam`/`squad:noor`/`squad:yuki`  ,  not the role-based names the docs assumed.
5. Update `.squad/team.md` Project Context: add `Last activity: 2026-05-12`; replace `Roadmap: docs/plan.md §2 (M0–M7)` with `Roadmap: CHANGELOG.md (shipped) + docs/roadmap/README.md (frontier)`.
6. Append Learnings to `.squad/agents/lead/history.md` and `.squad/agents/security-reviewer/history.md`.

**Out of scope (deferred to backlog issues filed separately):**
- Rewriting `.squad/skills/project-conventions/SKILL.md` from `copilot-instructions.md` (🟡, Yuki).
- Pilot vs deprecate decision for Squad orchestration (🟡, spike).
- Auditing `.github/agents/squad.agent.md` against upstream `@bradygaster/squad-cli` (🟡, Sam).
- Frontier epic spikes (D.4–D.9 in Maya's plan)  ,  each gets its own §11 PR.

**Why:** 8 days post-bootstrap, Squad memory was empty (no `decisions.md` entries, no `inbox/`, every agent history seed boilerplate, `now.md` stale, `wisdom.md` empty, `project-conventions` skill was the placeholder). Routing references labels that do not exist. Land the trivial cleanup as one PR; punt anything 🟡/🔴 to its own issue + §11 loop.

### 2026-05-12  ,  PR #22 (FOCUS 1.2 mapping) merge clearance

**Decision:** PR #22 (`docs(roadmap): add exploratory FOCUS 1.2 correlation mapping`) cleared for squash-merge with a non-contract banner ([commit `e453265`](https://github.com/martinopedal/FinOps-assessment/commit/e453265)) inserted at the top of `docs/roadmap/focus-mapping.md`.

**Why:** Noor's stage-4 review (E.1) confirmed all five hard rules in `.github/copilot-instructions.md` are preserved. Residual risk was *expectation drift* from the doc's "Source field" column reading like a soft schema-stability contract. The banner collapses that risk to zero.

**Implication:** The doc explicitly does **not** commit the project to ship a FOCUS exporter, a Hubs connector, or any specific CLI surface, and does **not** freeze the current `Finding`/`run` field set. Any future field rename moves the doc in the same PR.

### 2026-05-12  ,  Pilot frontier epic D.4 if/when Squad orchestration is activated

**Decision:** If Martin elects to pilot the Squad-orchestrated §11 loop on a frontier epic (Maya's D.2 spike outcome), the pilot is **D.4  ,  Azure pricing intelligence (region/SKU/meter variance)**, not D.5/D.6/D.7.

**Why (Noor's E.4):** D.4 is spike + data-contract only (no rule YAML, no collector  ,  read-only posture cannot be at risk); it exercises the full §11 loop because it has multiple natural reviewers baked in (Diego for surface, Yuki for tests, Noor for copyright + schema); it avoids the PII / sovereign-cloud complications of D.6 and the commercial-terms complications of D.5/D.7.

**Falsification criteria  ,  Squad is parked if any two fire at pilot merge:**
1. **Cycle time regression.** Pilot PR takes ≥ 2× the median wall-clock time of the last five `@copilot`-direct docs PRs (#18–#22).
2. **No multi-author signal.** Fewer than three distinct squad members contribute substantive content (a routing acknowledgement comment does not count).
3. **No catch the direct path would have missed.** Stage-4 produces zero amendments to the stage-3 plan **and** code review surfaces zero issues a single-author `@copilot` review would not have caught.
4. **Squad memory does not accumulate.** Post-pilot, `.squad/decisions.md` still has fewer than two merged entries from `inbox/`, or `wisdom.md` gains no pattern.

**Rollback condition:** If two or more fire, the next decision is "Squad is parked": future frontier epics route through `@copilot`-direct with §11 in the PR body; `.squad/team.md` is reframed as a *review rubric* (whose voice to channel when adversarial-reading a PR), not an *orchestration scaffold*; squad workflows stay in place because they are cheap, but no new epic is required to traverse them. Revisit after two more shipped epics.

**Status:** Pending Martin's input on D.2 (the meta-spike). Until then, the `@copilot`-direct path remains the workflow that's actually shipping.

### 2026-05-12  ,  squad-cli upstream audit (issue #26)

**Verdict:** Local `.github/agents/squad.agent.md` stamps v0.8.25; upstream npm latest is v0.9.4 (2 minor versions ahead). **Do NOT wholesale re-align.** The ~7.4 KB of local divergence is intentional and justified:
- Inlined skill content (vs upstream's delegated pattern)  ,  keeps coordinator self-contained
- Removed TypeScript SDK Mode  ,  project doesn't use the SDK
- Removed Azure DevOps support  ,  project is GitHub-only  
- Added local `squad-pr-route.yml`  ,  fills a gap upstream didn't have at v0.8.25

Workflow drift (4 of 5 core workflows modified) is intentional, not re-aligned. **Instead:** File separate issues to evaluate upstream improvements *worth* adopting  ,  e.g., routing enforcement refusal rule from upstream PR #890 (v0.9.4).

**Meta-finding:** Coordinator session-start governance stamps v0.9.1, but on-disk `.github/agents/squad.agent.md` stamps v0.8.25. Third installation channel (likely user-level `~/.copilot/` or CLI-bundled copy) exists beyond what local repo pins. This is not a contradiction  ,  the on-disk repo file is project governance; the session-start governance is the active runtime. They drift independently. Future agents should know the difference.

### 2026-05-12  ,  Squad reframed as review rubric (issue #25)

**Decision:** The squad-orchestrated §11 pilot on a frontier epic (proposed in the *Pilot frontier epic D.4* decision above) is **not** being run. Instead, the squad scaffold is reframed as a **review rubric**: the workflow that ships work remains `@copilot`-direct with §11 stages documented in the PR body  ,  the same workflow that shipped M0–M7 across PRs #4–#22. The roster in `.squad/team.md` documents whose voice a reviewer should channel adversarially when reading any PR.

**Why:** 22 of 22 shipped PRs since project bootstrap have used the `@copilot`-direct path. Two squad-orchestrated batches this session  ,  the bootstrap PR #33 (Maya stage-3 + Noor stage-4) and the followup batch (Yuki on #24, Sam on #26 in parallel)  ,  produced quality results. But every productive moment was either a single-agent task with full ceremony or Coordinator-as-router; the promised value of multi-agent fan-out on a real epic was never tested. Falsification criterion (2) from the D.4 pilot decision  ,  *no multi-author signal in shipped work*  ,  was already true before the pilot started. The squad scaffold's value lives in the *rubric* (Maya's gap analyses and Noor's adversarial passes  ,  both real wins) and in the per-agent voices, not in formal orchestration.

**Implications:**
- Frontier epics #27–#30 (D.4–D.7) ship via `@copilot`-direct with §11 in the PR body. No formal squad-orchestrated stage-3/stage-4 spawns.
- Multi-agent stage-3/stage-4 spawns remain available on request for genuinely non-trivial PRs (architecture proposals, security audits, frontier-epic kickoffs) but are not the default.
- `.squad/team.md` gains a Posture section (this PR) making the rubric framing explicit.
- The squad workflows (`squad-triage`, `squad-pr-route`, `squad-issue-assign`) stay in place because they are cheap, useful for label routing, and channel the rubric automatically.
- `.squad/decisions.md`, `wisdom.md`, and agent histories continue to accumulate  ,  the rubric still produces and consumes squad memory.

**Falsification  ,  re-open issue #25 if any of these fire:**
1. Two consecutive frontier-epic PRs (D.4–D.7) ship with substantive defects that a stage-4 adversarial spawn would have caught.
2. Reviewer fatigue: a single `@copilot`-direct PR accumulates more than five review cycles before merge.
3. A squad member's domain expertise is consistently absent from PRs in their surface  ,  the rubric voices are not actually being channeled.

If any fire, re-run issue #25 with fresh evidence and re-evaluate the pilot.

**Status:** Closes #25.

### 2026-05-12  ,  Azure pricing module  ,  observation/profile family contract (issues #27, #28, #30)

**Decision:** `pricing.py` module (introduced in #27, extended in #28 and #30) is the canonical owner of the observation/profile family for Azure pricing data. Observations are **runtime data** supplied by collectors or customers (customer-specific EA/MCA/CSP rates), not catalog constants. The **hard boundary** is: `data/catalog/` holds vendor list prices (published, versioned); `src/finops_assess/pricing.py` defines the data contract and collectors populate it with customer-observed rates and agreements.

**Scope (all in this decision, no others):**
- #27 introduces `PricingObservation` model for region-specific pricing observations (base rates by region and meter ID)
- #28 extends with `CommitmentDiscount` and commitment-agreement subtypes (RI/Savings Plans, one-year/three-year term contracts)
- #30 adds `AgreementMultiplier` for agreement-type cost modifiers (Enterprise, MCA, CSP tier-specific rates)

**Why:** Separating observations from catalog prevents hard-coding of tenant-specific agreements into source control (security + compliance boundary). Allows the tool to operate with list prices (default) or customer-specific effective rates without repository mutation. Future pricing extensions (e.g., spot-instance discounts, reservation exchanges, hybrid-benefit pricing) belong in this module unless justified otherwise.

**Source/Linked PRs:** #39 (D.4 pricing intelligence  ,  stage 1 research + data contract), #42 (D.5 commitments  ,  stage 1 research + contract addenda), #43 (D.7 agreement types  ,  stage 1 research + contract addenda).

**Inbox file:** `.squad/decisions/inbox/diego-pricing-observation-contract.md` (proposed in #27, addended in #28 and #30).

### 2026-05-12  ,  M365 SKU-mix aggregate-summary contract (issue #29)

**Decision:** `M365FamilySummary` model (introduced in #29) is aggregate-only; tenant-id and per-principal fields are explicitly rejected by `extra='forbid'`. The 15-family `Literal` enum (`m365_e1_tier`, `m365_e3_tier`, `m365_e5_tier`, `office365`, `entra_p1`, `entra_p2`, `ems_e3`, `ems_e5`, `defender_o365_p1`, `defender_o365_p2`, `defender_cloud_apps`, `copilot_m365`, `copilot_pro`, `copilot_studio`, `gsa`) is the schema contract. Fields are aggregate counts and optional feature-usage signal counts; no user IDs, tenant IDs, or per-principal identifiers are permitted (preserves hard rule 4: PII redaction by construction).

**Why:** M365 pricing and licensing rules naturally operate on family-level aggregates (E1/E3/E5 tier fragmentation, Entra P2 feature usage vs assignment, security-addon overlap). The model enforces this at validation time: any attempt to leak per-principal data (a common data-governance drift vector in compliance audits) fails fast with a clear error. `extra="forbid"` makes future field additions explicit decisions.

**Source/Linked PR:** #40 (D.6 SKU-mix intelligence  ,  stage 1 research + data contract).

**Inbox file:** `.squad/decisions/inbox/priya-m365-family-summary.md` (proposed in #29).

### 2026-05-12  ,  Derived report views  ,  architectural principle (issue #31)

**Decision:** Report sections that surface **posture** rather than **data** are **derived views**  ,  they read the canonical JSON report and do NOT extend it. Advisory disclaimers are mandatory. Certification, scoring, level, rating language is forbidden in body content. Six binding rules (read-only over canonical, no schema additions, graceful degradation, mandatory advisory disclaimer, forbidden-word guard, vendor-neutral phrasing) enforce this contract in future reporter sections.

**Why:** The practice-review section in #31 added four posture cues (pricing assumptions, data-quality warnings, commitment posture, SKU-mix posture) without mutating the canonical report schema. Deriving them from existing fields avoids schema version bumps for non-data changes and prevents competing summary surfaces. The discipline generalizes to future confidence/completeness sections.

**Source/Linked PR:** #41 (D.8 reporter multi-cloud section  ,  includes FinOps practice-review posture layer).

**Inbox file:** `.squad/decisions/inbox/maya-derived-report-views-2026-05-12.md`.

### 2026-05-12  ,  Local-clear batch outcome  ,  falsification-test data on multi-agent fan-out

**Context:** On 2026-05-12 morning, the rubric reframe (issue #25) concluded that squad-orchestrated §11 was parked  ,  the shipping workflow remained `@copilot`-direct with §11 stages in PR bodies, same as M0–M7. By afternoon, Martin invoked the on-request exception for a **full local clear** of all 7 open backlog issues (#27–#32, #35) as a falsification test: does multi-agent fan-out beat the `@copilot`-direct baseline the rubric deprecated?

**Empirical outcome:**

- **7/7 issues closed via local squad**  ,  All issues routed to squad members; all merged within the batch window.
- **Head-to-head data point (#27 Diego vs #36 bot collision):** Diego's pricing contract (PR #39) won on §11-stage discipline (all 5 stages explicitly articulated), dedicated module placement (`pricing.py` as canonical owner), and pattern-setting for #28/#30 extensibility. Bot's #36 PR had no equivalent stage-3 plan or stage-4 adversarial pass before opening.
- **Lockout-revision chain (#28 commitments):** Diego round-1 rejected (scope gap + test coverage gap) → Yuki revised & resubmitted (round 2) → Yuki rejected (regex `\b` snake_case bug in language guardrail test) → Diego revised (round 3 with explicit lookahead) → Approved. Three-round review added orchestration cost a pure-autonomous bot might not trigger; concretely justified by catching a regex security boundary bug that round-1 and round-2 missed.
- **Five single-round approvals** (#29, #30, #31, #32, #35)  ,  Priya's M365 contract, Diego's agreement-types extension, Maya's derived-views principle, Sam's runbook, Yuki's routing-enforcement rule all approved on first submission.
- **Net cycle time: all 7 issues closed from initial spawn to final merge.** Coordinator ran the §11 loop hands-off after Martin's option-E choice.

**Falsification verdict  ,  Does multi-agent beat `@copilot`-direct baseline?**

*Signals where multi-agent won:*
- **§11-stage discipline:** No agent skipped a stage or hand-waved a plan. All PRs opened with stage-3 checklist in body; stage-4 adversarial reviews were live (not performative). Bot's #36 had no equivalent gate.
- **Pattern-setting consistency:** Diego's pricing decision was weaponized across #28 and #30 via the single `diego-pricing-observation-contract.md` decision document  ,  §11 stage-3 output was reused, not re-negotiated. Bot baseline has no equivalent multi-PR decision inheritance.
- **Noor's security catch (round 2 of #28):** The regex `\b` snake_case bug in the language guardrail test  ,  a boundary case that historically required manual audit. Noor's stage-4 adversarial pass caught it; bot's autonomous review on #36 did not surface an equivalent self-check.
- **Parallel throughput:** Four Wave-A agents in parallel (Priya, Diego, Maya, Sam) finished faster than four sequential single-agent passes would have. Yuki's round-2 revision on #28 was asynchronous, not a blocker on the other 6.

*Signals where multi-agent was costly:*
- **Three-round review on #28:** Lockout-revision cycle added overhead an autonomous bot wouldn't trigger, because the bot wouldn't have written the language-guardrail regex test in the first place  ,  that's a quality concession the baseline trades to avoid review latency.
- **Opus 4.7 tier costs:** Noor's stage-4 reviews consumed premium reasoning capacity; `@copilot`-direct on M0–M7 baseline ran at free tier. This batch spent more compute on adversarial review than a fast-path baseline.

*Net verdict:*
- **This batch produced higher-quality contracts with traceable design rationale** (3 promoted decisions from stage-3 plans). The rubric reframe is **VINDICATED**.
- **The per-call review costs justify themselves on frontier-epic kickoffs** (#27 pricing, #29 M365) where pattern-setting rationale matters for downstream extensions. They're overkill for routine work (#32 runbook, #35 routing rule) where the baseline suffices.
- **Noor's security catch on #28 (regex bug) is a concrete example** of multi-agent thoroughness the baseline historically missed  ,  but it was a function of the *specific test design*, not the orchestration model. The bot could have caught it if its test author had written the guardrail; the squad model surfaced it because Noor was asked to read adversarially.

**Action  ,  Keep rubric reframe as default; allow on-request exceptions (today's batch was a clean example); don't re-open #25.**

---

## 2026-05-12  ,  Wave: Protection-fix shipped + standing directive

### 2026-05-12  ,  Required-checks summary job replaces "CI" context (issue #51)

**By:** Maya (Lead / FinOps PM)

**Decision:** Replace the brittle branch-protection contract `contexts: ["CI"]` with a single summary job that publishes the literal context `required-checks`. The job lives at the end of `.github/workflows/ci.yml`, `needs: [lint-and-test, catalog-validation]`, runs `if: always()`, and asserts every upstream `needs.*.result == 'success'` via `actions/github-script@v9`  ,  failing the summary (and therefore the protection check) if any matrix shard or sibling job failed or was skipped.

**Why this matters:** Branch protection required the context name `CI`, but `name: CI` at the workflow level is *not* a published check context  ,  only job names (and matrix expansions) are. So `gh api PUT .../merge` returned `HTTP 405 Required status check 'CI' is expected` on every squad PR (#46, #48, #50) even with all checks green. This was the last remaining trigger for the `enforce_admins` toggle-dance after #47/#48 made review-count async-friendly.

**Trade-offs considered:**
- **Option A  ,  list every matrix context in protection** (`Lint, type-check, test (ubuntu-latest / py3.11)` × 6, plus `Validate YAML catalog & rules`): strongest correctness, but every matrix dimension change (add Python 3.13, drop macOS, etc.) silently breaks merge until protection is re-edited. Rejected on brittleness.
- **Option B  ,  summary `required-checks` job** (chosen): one stable contract; matrix changes invisible to protection; cost is one extra runner-minute per PR. The `if: always()` + explicit `needs.*.result` check is the canonical GitHub Actions summary-job idiom and handles `failure`, `cancelled`, and `skipped` correctly (only `'success'` passes).
- **Option C  ,  rename a job to `CI`**: cheapest but couples the protection contract to a generic, easy-to-rename job name and gives no aggregation guarantee. Rejected.
- **Option D  ,  drop `required_status_checks` entirely**: lets red CI merge. Rejected outright.

**Operator handoff (Coordinator, post-merge):** After this PR merges to `main`, swap the protection contract:

```
gh api --method PATCH \
  repos/martinopedal/FinOps-assessment/branches/main/protection/required_status_checks \
  --raw-field 'contexts[]=required-checks' \
  --field 'strict=true'
```

Until that PATCH lands, this PR itself still requires one final `enforce_admins` toggle-dance to merge  ,  it is the bootstrap cost, identical in shape to the #47/#48 cutover. All subsequent squad PRs become fully async-mergeable: open → squad label → Stage-4 Noor verdict comment → bot approval → all-green CI → `gh pr merge --squash` (no `--admin`, no toggle).

**Forward gotcha (binding on every future contributor):** Every new top-level job added to `.github/workflows/ci.yml` MUST be appended to the `required-checks` job's `needs:` list. Otherwise the summary will report success while the new job runs ungated by branch protection. The §11 Stage-4 reviewer is responsible for catching this on any PR that touches `ci.yml`.

**Related:** issue #47, #51; PRs #48 (auto-approve workflow), #50 (auto-approve inaugural test).

### 2026-05-12  ,  Standing directive: write everything to squad so sessions can break off cleanly

**By:** Martin Opedal (via Coordinator)

**What:** Every coordinator turn that produces durable state (decisions, scope, audit findings, in-flight PR ceremony, open follow-ups) MUST write that state into the squad system (`.squad/` files committed via PR, or GitHub issues) BEFORE the session ends. Local-only scratch (session-state plan.md, SQL todos, chat memory) is insufficient for handoff because it lives only on the active machine and disappears with the session.

**Why this matters:** Sessions end without warning (rate limits, token expiry, network drop, machine sleep, user pivots). The next session  ,  possibly a different agent on a different machine  ,  has no access to local scratch. The squad system (`.squad/decisions.md`, `.squad/identity/now.md`, `.squad/agents/{name}/history.md`, GitHub issues) IS the durable cross-session memory. Anything not written there is lost.

**Operational rules:**
1. **In-flight PR ceremony state** must be captured in either: (a) the PR body checklist, (b) a GitHub issue body if multi-PR, or (c) `.squad/identity/now.md` if single-session.
2. **Open scope decisions** awaiting user input must be filed as a GitHub issue with full context, audit findings, and a numbered list of decisions needed. Bare chat questions are not durable.
3. **Standing directives** (rules of the form "always X" / "never Y" / "from now on Z") must be promoted to `.squad/decisions.md` via the inbox. Capture in chat is not enough.
4. **Audit findings** that block work must be captured in the issue or PR that owns the work, not in chat.
5. **At session end**, Coordinator's final user-visible message must include the GitHub URL(s) (PR or issue) where the durable state lives.

**Trade-offs considered:**
- **Lighter alternative  ,  only write to squad when "important":** rejected. The threshold for "important" drifts; in practice things get lost.
- **Heavier alternative  ,  write every turn to squad:** rejected. Generates noise; not every chat turn produces durable state. The rule is: durable STATE writes to squad, not durable chat.
- **Status quo (this directive's predecessor):** plan.md in session-state + SQL todos + chat memory. Worked when sessions ran end-to-end on one machine, but fails on session breaks.

**Related:** PR #52 (the work that prompted this directive  ,  Coordinator was wrapping #52 ceremony when user reminded), Issue #53 (the pending docs-voice work that triggered the "log everything" reminder), `.github/copilot-instructions.md` Session Protocol Start & End (existing session-bookend rules).

**Scope:** Binding on Squad (Coordinator) on every session start AND every session end. Reviewers must check that any user directive in chat was captured to inbox before approving the wrap PR.

---

## 2026-05-13  ,  Wave: Docs-voice SKILL adopted

### 2026-05-13  ,  Docs-voice scope: emoji + em-dash + AI-language + skill location (issue #53, PR #55)

**By:** Maya (Lead), encoding the four scope decisions Martin set on issue #53 before PR #55 opened.

**Decisions:**

1. **Emoji policy: pragmatic, keep role badges.** Permitted across docs of record: ✅ and ❌ for binary status; squad role badges (🏗️ ⚛️ 🔧 🧪 📋 🔄) because they are functional UI in routing tables and rosters; capability traffic-lights (🟢 🟡 🔴) only inside `.squad/team.md`, `.squad/routing.md`, and the capability columns they feed. Strip every other emoji.

2. **Em-dash policy: full sweep, except historical logs.** Remove every em-dash and en-dash from docs of record. Replace with a comma, a period, or "and" per the news-fetcher rule. Skip `.squad/orchestration-log/` and `.squad/log/` because rewriting historical artifacts rewrites history.

3. **AI-language scope: full news-fetcher blacklist.** Apply the full blacklist (leverage, unlock, comprehensive, robust, seamless, holistic, cutting-edge, journey, delve, empower, streamline, furthermore, moreover, additionally, on the other hand, in conclusion, in today's world, it is worth noting, and the rest of the list inside the SKILL). The four hits found during audit were a starting point, not the whole scope. Replace abstract verbs and vague qualifiers with concrete nouns and specific verbs.

4. **Voice profile location: skill only.** The anonymized voice profile lives only at `.squad/skills/docs-voice/SKILL.md`. No duplicate at `docs/voice/`, no copy in `docs/style.md`. The SKILL is the canonical source; agents auto-read it through the normal skill-loading path.

**Scope of "docs of record":** all `.md` files under `.github/`, `docs/`, `.squad/` (except `orchestration-log/` and `log/` subfolders), the project README and CHANGELOG, AND the catalogue YAML `summary` and `recommendation_template` fields under `data/catalog/` and `data/rules/`. Those YAML prose fields render verbatim into `docs/rules.md` (via `scripts/generate_docs.py`) and into every JSON / HTML / CSV / PDF report, so they ARE docs of record.

**Operational consequence (from PR #55 follow-up fix):** When a `summary` or `recommendation_template` in `data/rules/{surface}.yaml` changes, the docs-voice SKILL applies. Re-run `python scripts/generate_docs.py` to regenerate `docs/rules.md` and `examples/demo-report.{json,html,csv}`, and commit those alongside the YAML in the same PR. Forgetting this trips both the docs-freshness gate (`tests/test_generate_docs.py::test_check_mode_passes_for_committed_artifacts`) and the SKILL contract. PR #55 caught one such miss (`additionally-assigned` in `M365.DUPLICATE_BUNDLE`) on the post-merge sweep at commit `f54177a`; the fix was to edit the YAML, regenerate, and re-push.

**Trade-offs considered:**

- **Voice page in `docs/`** vs skill: rejected. Docs of record describe the product. The voice rule belongs to the agent system that produces the docs, not the docs themselves.
- **Soft em-dash policy** (allow in long-form prose): rejected. Operators of an enterprise FinOps tool read in scan-mode; a comma reads cleanly there and an em-dash is the strongest single-character "this was generated" signal in our corpus.
- **Emoji-zero policy:** rejected because role badges and ✅/❌ are functional UI in routing tables and status surfaces, not decoration.
- **Strip catalogue YAML prose from scope:** rejected. The fields render unchanged into reports; exempting them would mean the docs-voice contract dies at the first regenerate.

**Related:** issue #53, PR #55, `.squad/skills/docs-voice/SKILL.md`, the `M365.DUPLICATE_BUNDLE` follow-up fix in commit `f54177a`.

**Scope:** Binding on every PR that touches docs of record OR catalogue YAML prose fields. Stage-4 reviewer (Noor) checks both.

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- The drop-box pattern: agents write to `.squad/decisions/inbox/{name}-{slug}.md`; Scribe merges into this file at session end and clears the inbox (which is gitignored)
