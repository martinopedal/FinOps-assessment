# 2026-05-12 — Rubric Pivot: Squad Reframed (Issue #25)

**Goal:** Execute Martin's approval of the deprecation-to-rubric reframe. The squad-orchestrated §11 pilot is shelved; the scaffold becomes a *review rubric* documenting whose adversarial voice should be channeled in PR review. Frontier epics route direct to `@copilot` (stage-3/4 spawns on request for non-trivial work only).

**Coordinator:** Coordinator only (no agent spawns). Issue #25 already consensus'd on the decision path.

**Actions landed:**
1. `.squad/team.md` — added `## Posture (since 2026-05-12)` section naming per-member rubric voices (Maya: surface/DoD/gap; Diego: Azure shape; Priya: M365/Graph/Entra; Sam: GitHub & ADO billing; Noor: read-only posture/hard rules; Yuki: tests/CI matrix).
2. `.squad/decisions.md` — appended full *2026-05-12 — Squad reframed as review rubric* decision with implications and three falsification trip-wires.
3. `.squad/identity/now.md` — refreshed `focus_area` and `active_issues` for #25 closure / #27 routing handoff.
4. GitHub labels — created `squad:copilot` (color B392F0).
5. Issue #25 — posted verdict comment, closed `completed`.
6. Issue #27 (D.4 — Azure pricing) — routed to `@copilot`-direct: added `squad:copilot` label, assigned Copilot, posted routing comment reinterpreting acceptance criteria for the @copilot-direct path. Squad-issue-assign workflow (run `25723555354`) fired and posted standard "🤖 Routed to @copilot" comment.

**Shipped artefacts:**
- `.squad/team.md` section documenting rubric voices (6 members × 1 voice each; role-to-voice mapping stable).
- `.squad/decisions.md` entry with full rationale, implications (frontier epics #27–#30 direct, multi-agent spawns on-request only, workflows stay cheap), and falsification.
- GitHub routing: #27 picked up by @copilot with rubric-informed acceptance criteria (stage-4 self-review channeling Noor; stage-3 plan channeling Diego).

**Verdict:** Squad scaffold successfully reframed as review rubric. The workflow that ships work remains `@copilot`-direct (§11 in PR body). The squad roster documents *whose voice to channel*, not *who orchestrates*. Frontier epic D.4 (#27) is first epic to ship under the new framing.

**Next gate:** #27 picks up under the rubric framing; #28/#29/#30 follow the same pattern when routed.
