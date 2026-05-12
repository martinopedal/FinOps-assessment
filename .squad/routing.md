# Work Routing

How to decide who handles what. The Lead (Maya) triages every
`squad`-labelled issue and applies the right `squad:{member}` label.

## Routing Table

| Work Type | Route To | Examples |
|-----------|----------|----------|
| Roadmap, milestone exit criteria, plan/§11 stage-3 sign-off | `squad:maya` | Update `docs/plan.md`, edit milestone status, decide between two competing rules. |
| M365 / Entra / EMS / Defender / Purview / Power Platform | `squad:priya` | New SKU in `data/catalog/m365/`, persona tweak, M365 rule, M4 Graph collector. |
| Azure compute / storage / SQL / network / Cost Management | `squad:diego` | New SKU in `data/catalog/azure/`, Azure rule, M5 ARM/CostMgmt collector. |
| GitHub Enterprise / Copilot / GHAS / Azure DevOps seats / runners | `squad:sam` | New SKU in `data/catalog/{github,ado}/`, GH/ADO rule, M6 collector. |
| Read-only scope review, secrets/PII/copyright review, repo hardening, §11 stage-4 adversarial pass | `squad:noor` | New collector PR, anything touching auth, CodeQL findings triage. |
| Tests, fixtures, CI matrix, mypy/ruff config, M3 synthetic tenant | `squad:yuki` | New `tests/` file, golden-file test for a rule, CI matrix tweak. |
| Async, well-defined, bounded tasks (🟢 in `team.md`) | `squad:copilot` (`@copilot` 🤖) | Doc polish, mechanical refactor, fixture add, schema-typo fix. |
| Session logging, decisions merge | `Scribe` | Automatic — never needs routing. |

## Issue Routing

| Label | Action | Who |
|-------|--------|-----|
| `squad` | Triage: analyze issue, evaluate `@copilot` fit, assign `squad:{member}` label | Maya (Lead) |
| `squad:{name}` | Pick up issue and complete the work | Named member |
| `squad:copilot` | Assign to `@copilot` for autonomous work | `@copilot` 🤖 |
| `release:v0.4.0` … `release:v1.0.0` | Release bucket — orthogonal to the routing label, applied by Maya at triage for work targeting a shipped or imminent release | (label only) |
| `release:backlog` | Backlog bucket — applied by Maya at triage for work that is not yet scheduled into a release | (label only) |

### How Issue Assignment Works

1. A new issue gets the `squad` label (the inbox).
2. **Maya** triages within one working day: assigns one `squad:{member}` label, one `milestone:Mx` label, and a 🟢/🟡/🔴 fit comment for `@copilot`.
3. If 🟢 and the change is bounded, Maya may instead apply `squad:copilot` and the workflow auto-assigns `@copilot` on the issue.
4. The named member picks the issue up in their next session.
5. Members reassign by removing their label and adding another.
6. PRs reference the issue (`Closes #N`) and use the `squad/{issue-number}-{slug}` branch convention.

### How PR Routing Works (cloud agents + labels)

Squad runs **on cloud agents** via GitHub Actions (`squad-triage`,
`squad-issue-assign`, `squad-pr-route`, `squad-heartbeat`,
`sync-squad-labels`). Labels work identically on issues and pull
requests:

1. Apply a `squad:{member}` label to a PR (e.g. `squad:security-reviewer`
   for a security-relevant PR, `squad:tester` for a test-only PR).
2. `squad-pr-route.yml` reacts on `pull_request_target: labeled`,
   resolves the member from `.squad/team.md`, and posts a routing
   acknowledgment comment on the PR.
3. `squad:copilot` on a PR routes review/follow-up work to `@copilot`.
4. `sync-squad-labels` ensures every `squad:{member}` label exists in
   the repo before any of these workflows fire.

### Lead Triage Guidance for `@copilot`

When triaging, ask:

1. **Is this well-defined?** Clear title, repro/AC, bounded scope → likely 🟢.
2. **Does it follow existing patterns?** Adding a test, fixing a known bug, updating a dependency → likely 🟢.
3. **Does it need design judgment?** Architecture, API design, UX decisions → likely 🔴.
4. **Is it security-sensitive?** Scopes, auth, PII, copyright → always 🔴 (Noor must review).
5. **Is it a schema or catalogue-pricing change?** → 🔴 unless a stage-3 plan is already signed off in the issue.
6. **Medium complexity with specs?** Feature with clear requirements, refactor with tests → likely 🟡 (proceed but flag for surface-specialist review).

## Rules

1. **Eager by default** — spawn all agents who could usefully start work, including anticipatory downstream work (e.g., `tester` writes the failing test while the surface specialist drafts the rule).
2. **Scribe always runs** after substantial work, always as `mode: "background"`. Never blocks.
3. **Quick facts → coordinator answers directly.** Don't spawn an agent for "what does the `family` field mean?".
4. **When two agents could handle it**, pick the one whose domain is the primary concern (e.g., a Copilot rule touching both M365 and GitHub Copilot routes to whichever surface owns the *billing relationship*, not the feature name).
5. **"Team, ..." → fan-out.** Spawn all relevant agents in parallel as `mode: "background"`.
6. **§11 stage gates are non-negotiable.** Maya rejects any PR that skipped stages 1–4 for a non-trivial change, even under time pressure.
7. **`@copilot` routing** — only `squad:copilot` triggers auto-assign. 🟡 work stays with squad members but `@copilot` may be tagged for review-only assist.
