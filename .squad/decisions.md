# Squad Decisions

## Active Decisions

### 2026-05-12 — Squad-memory bootstrap & label-drift cleanup (issue #23)

**Decision:** Land the 🟢-trivial squad-state cleanup from Maya's gap analysis (`.squad/decisions/inbox/maya-gap-analysis-2026-05-12.md`, §C) in a single PR closing #23, after Noor's stage-4 sign-off (`.squad/decisions/inbox/noor-stage4-2026-05-12.md`).

**Scope (in this decision, no others):**
1. Refresh `.squad/identity/now.md` (was pinned to "Initial setup" since 2026-05-04).
2. Seed `.squad/identity/wisdom.md` with the five Noor-approved patterns (PR archeology). Pattern (f) was rejected as a duplicate of (c) and pattern (d) was reworded per Noor's E.2.
3. Replace the `milestone:M1`–`milestone:M7` row in `.squad/routing.md` with the actual `release:v0.4.0`–`release:v1.0.0` and `release:backlog` rows. Hard replace, no redirect (Noor's E.3 audit confirmed no historical link expects the `milestone:Mx` shape).
4. Fix `Issue label` column drift in `.squad/team.md` and the `Route To` column in `.squad/routing.md`: actual labels are `squad:maya`/`squad:priya`/`squad:diego`/`squad:sam`/`squad:noor`/`squad:yuki` — not the role-based names the docs assumed.
5. Update `.squad/team.md` Project Context: add `Last activity: 2026-05-12`; replace `Roadmap: docs/plan.md §2 (M0–M7)` with `Roadmap: CHANGELOG.md (shipped) + docs/roadmap/README.md (frontier)`.
6. Append Learnings to `.squad/agents/lead/history.md` and `.squad/agents/security-reviewer/history.md`.

**Out of scope (deferred to backlog issues filed separately):**
- Rewriting `.squad/skills/project-conventions/SKILL.md` from `copilot-instructions.md` (🟡, Yuki).
- Pilot vs deprecate decision for Squad orchestration (🟡, spike).
- Auditing `.github/agents/squad.agent.md` against upstream `@bradygaster/squad-cli` (🟡, Sam).
- Frontier epic spikes (D.4–D.9 in Maya's plan) — each gets its own §11 PR.

**Why:** 8 days post-bootstrap, Squad memory was empty (no `decisions.md` entries, no `inbox/`, every agent history seed boilerplate, `now.md` stale, `wisdom.md` empty, `project-conventions` skill was the placeholder). Routing references labels that do not exist. Land the trivial cleanup as one PR; punt anything 🟡/🔴 to its own issue + §11 loop.

### 2026-05-12 — PR #22 (FOCUS 1.2 mapping) merge clearance

**Decision:** PR #22 (`docs(roadmap): add exploratory FOCUS 1.2 correlation mapping`) cleared for squash-merge with a non-contract banner ([commit `e453265`](https://github.com/martinopedal/FinOps-assessment/commit/e453265)) inserted at the top of `docs/roadmap/focus-mapping.md`.

**Why:** Noor's stage-4 review (E.1) confirmed all five hard rules in `.github/copilot-instructions.md` are preserved. Residual risk was *expectation drift* from the doc's "Source field" column reading like a soft schema-stability contract. The banner collapses that risk to zero.

**Implication:** The doc explicitly does **not** commit the project to ship a FOCUS exporter, a Hubs connector, or any specific CLI surface, and does **not** freeze the current `Finding`/`run` field set. Any future field rename moves the doc in the same PR.

### 2026-05-12 — Pilot frontier epic D.4 if/when Squad orchestration is activated

**Decision:** If Martin elects to pilot the Squad-orchestrated §11 loop on a frontier epic (Maya's D.2 spike outcome), the pilot is **D.4 — Azure pricing intelligence (region/SKU/meter variance)**, not D.5/D.6/D.7.

**Why (Noor's E.4):** D.4 is spike + data-contract only (no rule YAML, no collector — read-only posture cannot be at risk); it exercises the full §11 loop because it has multiple natural reviewers baked in (Diego for surface, Yuki for tests, Noor for copyright + schema); it avoids the PII / sovereign-cloud complications of D.6 and the commercial-terms complications of D.5/D.7.

**Falsification criteria — Squad is parked if any two fire at pilot merge:**
1. **Cycle time regression.** Pilot PR takes ≥ 2× the median wall-clock time of the last five `@copilot`-direct docs PRs (#18–#22).
2. **No multi-author signal.** Fewer than three distinct squad members contribute substantive content (a routing acknowledgement comment does not count).
3. **No catch the direct path would have missed.** Stage-4 produces zero amendments to the stage-3 plan **and** code review surfaces zero issues a single-author `@copilot` review would not have caught.
4. **Squad memory does not accumulate.** Post-pilot, `.squad/decisions.md` still has fewer than two merged entries from `inbox/`, or `wisdom.md` gains no pattern.

**Rollback condition:** If two or more fire, the next decision is "Squad is parked": future frontier epics route through `@copilot`-direct with §11 in the PR body; `.squad/team.md` is reframed as a *review rubric* (whose voice to channel when adversarial-reading a PR), not an *orchestration scaffold*; squad workflows stay in place because they are cheap, but no new epic is required to traverse them. Revisit after two more shipped epics.

**Status:** Pending Martin's input on D.2 (the meta-spike). Until then, the `@copilot`-direct path remains the workflow that's actually shipping.

### 2026-05-12 — squad-cli upstream audit (issue #26)

**Verdict:** Local `.github/agents/squad.agent.md` stamps v0.8.25; upstream npm latest is v0.9.4 (2 minor versions ahead). **Do NOT wholesale re-align.** The ~7.4 KB of local divergence is intentional and justified:
- Inlined skill content (vs upstream's delegated pattern) — keeps coordinator self-contained
- Removed TypeScript SDK Mode — project doesn't use the SDK
- Removed Azure DevOps support — project is GitHub-only  
- Added local `squad-pr-route.yml` — fills a gap upstream didn't have at v0.8.25

Workflow drift (4 of 5 core workflows modified) is intentional, not re-aligned. **Instead:** File separate issues to evaluate upstream improvements *worth* adopting — e.g., routing enforcement refusal rule from upstream PR #890 (v0.9.4).

**Meta-finding:** Coordinator session-start governance stamps v0.9.1, but on-disk `.github/agents/squad.agent.md` stamps v0.8.25. Third installation channel (likely user-level `~/.copilot/` or CLI-bundled copy) exists beyond what local repo pins. This is not a contradiction — the on-disk repo file is project governance; the session-start governance is the active runtime. They drift independently. Future agents should know the difference.

### 2026-05-12 — Squad reframed as review rubric (issue #25)

**Decision:** The squad-orchestrated §11 pilot on a frontier epic (proposed in the *Pilot frontier epic D.4* decision above) is **not** being run. Instead, the squad scaffold is reframed as a **review rubric**: the workflow that ships work remains `@copilot`-direct with §11 stages documented in the PR body — the same workflow that shipped M0–M7 across PRs #4–#22. The roster in `.squad/team.md` documents whose voice a reviewer should channel adversarially when reading any PR.

**Why:** 22 of 22 shipped PRs since project bootstrap have used the `@copilot`-direct path. Two squad-orchestrated batches this session — the bootstrap PR #33 (Maya stage-3 + Noor stage-4) and the followup batch (Yuki on #24, Sam on #26 in parallel) — produced quality results. But every productive moment was either a single-agent task with full ceremony or Coordinator-as-router; the promised value of multi-agent fan-out on a real epic was never tested. Falsification criterion (2) from the D.4 pilot decision — *no multi-author signal in shipped work* — was already true before the pilot started. The squad scaffold's value lives in the *rubric* (Maya's gap analyses and Noor's adversarial passes — both real wins) and in the per-agent voices, not in formal orchestration.

**Implications:**
- Frontier epics #27–#30 (D.4–D.7) ship via `@copilot`-direct with §11 in the PR body. No formal squad-orchestrated stage-3/stage-4 spawns.
- Multi-agent stage-3/stage-4 spawns remain available on request for genuinely non-trivial PRs (architecture proposals, security audits, frontier-epic kickoffs) but are not the default.
- `.squad/team.md` gains a Posture section (this PR) making the rubric framing explicit.
- The squad workflows (`squad-triage`, `squad-pr-route`, `squad-issue-assign`) stay in place because they are cheap, useful for label routing, and channel the rubric automatically.
- `.squad/decisions.md`, `wisdom.md`, and agent histories continue to accumulate — the rubric still produces and consumes squad memory.

**Falsification — re-open issue #25 if any of these fire:**
1. Two consecutive frontier-epic PRs (D.4–D.7) ship with substantive defects that a stage-4 adversarial spawn would have caught.
2. Reviewer fatigue: a single `@copilot`-direct PR accumulates more than five review cycles before merge.
3. A squad member's domain expertise is consistently absent from PRs in their surface — the rubric voices are not actually being channeled.

If any fire, re-run issue #25 with fresh evidence and re-evaluate the pilot.

**Status:** Closes #25.

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- The drop-box pattern: agents write to `.squad/decisions/inbox/{name}-{slug}.md`; Scribe merges into this file at session end and clears the inbox (which is gitignored)
