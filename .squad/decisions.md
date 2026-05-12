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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- The drop-box pattern: agents write to `.squad/decisions/inbox/{name}-{slug}.md`; Scribe merges into this file at session end and clears the inbox (which is gitignored)
