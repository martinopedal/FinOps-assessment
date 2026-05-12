---
updated_at: 2026-05-12T08:35:00.000Z
focus_area: Squad reframed as review rubric (#25 closed); routing #27 (D.4 Azure pricing) to @copilot-direct
active_issues: [27, 28, 29, 30, 31, 32, 35]
---

# What We're Focused On

**Squad orchestration deprecated, replaced by review-rubric framing.** Issue #25 closed with the verdict in `decisions.md`: 22/22 shipped PRs since bootstrap have used the `@copilot`-direct path, and the squad scaffold's value lives in the *rubric* (Maya's gap analyses, Noor's adversarial passes) and per-agent voices, not in formal multi-agent orchestration. `.squad/team.md` now has a Posture section making this explicit. Multi-agent §11 stage-3/stage-4 spawns remain available on request for genuinely non-trivial PRs but are not the default.

**Next on the wire:** #27 (D.4 — Azure pricing intelligence data contract) is being routed to `@copilot`-direct via the `squad:copilot` label, with Diego's and Noor's voices channeled in the PR body and code review. §11 stages 1–5 live in the PR body. After #27 lands, #28–#30 (D.5/D.6/D.7) follow the same routing pattern. #31/#32/#35 are p3 backlog.

**Falsification trip-wires for the rubric reframe** (full text in `decisions.md`): two consecutive frontier-epic PRs ship with substantive defects a stage-4 spawn would have caught; a single PR accumulates >5 review cycles before merge; or a squad member's domain expertise is consistently absent from PRs in their surface. Any fire → re-open #25.

Updated by Coordinator on the #25 closure / #27 routing transition.

