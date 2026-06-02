# ADR 0001 — PowerShell side-by-side engine (additive §1.7 + §1.7a gate)

- **Status:** Accepted (side-by-side, additive); full transition
  Proposed / Deferred — gated by §1.7a + a fresh stage-4 review.
- **Date:** 2026-06-02
- **Owner:** Maya (Lead / FinOps PM)
- **Approver:** Martin (repo owner, `martinopedal`)
- **Adversarial reviewer:** Noor (Security & compliance reviewer) —
  CONDITIONAL APPROVE-TO-PLAN for side-by-side; DISSENTING on full
  transition (see *Dissent* below).
- **Supersedes:** none. Tightens the original `docs/plan.md` §1.7
  ("Python is the engine language") without removing it.
- **Related issues / PRs:** this ADR ships in the docs-only gating PR
  on branch `squad/powershell-side-by-side-docs`.

## Status

**Accepted** — the project admits a native PowerShell engine as a
governed second runtime that ships *alongside* Python. Python remains
the reference / conformance-oracle engine.

**Proposed / Deferred** — full transition to a PS-only engine
(retiring Python). This ADR sets the falsification gate (`docs/plan.md`
§1.7a) but explicitly does **not** pre-approve crossing it. Crossing
requires a fresh §11 cycle culminating in a fresh stage-4 adversarial
review, and Noor's current stage-4 REJECT on full transition stands
until that fresh review reverses it.

## Context

`docs/plan.md` §1.7 originally read "Python is the engine language"
and the `.github/copilot-instructions.md` hard rule reinforces it:
*"Do not introduce a second runtime (PowerShell, Node, Go) unless
`docs/plan.md` is updated to justify it."* That language collides with
a real, recurring operator request: the M365 / Entra / Defender /
Purview / Intune admin population lives in `pwsh` natively, and a
"install Python first" friction barrier suppresses adoption with
exactly the audience the tool is built for.

Martin (repo owner) requested a path that admits a native PS engine
as a peer of Python without weakening any of the read-only / PII /
no-secrets / no-third-party-copyright hard rules, and without silently
authorising "drop Python later" as a fait accompli.

The §11 delivery loop produced:

1. **Stage-1 research** (prior session): API / SDK coverage in PS
   (Microsoft Graph SDK for PowerShell, Az modules, Octokit-PS,
   Az.DevOps), `pwsh` 7.2+ cross-platform posture (Linux containers
   incl. Linux GitHub runners), prior-art on dual-runtime FinOps
   tooling, gaps (PDF rendering parity, `pydantic`-equivalent schema
   rigor, supply-chain controls).
2. **Stage-2 rubberduck**: maintenance-cost concern (every rule
   written twice), false-positive risk if conformance is "best-effort
   compatible" rather than byte-deterministic, security risk if the
   read-only scope-guard is ported by description instead of by
   actual-token claim introspection, PII byte-parity risk under
   different hash / encoding stacks.
3. **Stage-3 plan** (Maya, this ADR + the §1.7 / §1.7a edits): admit
   PS as a peer engine with PDF delegated, gate full transition
   behind a falsifiable criteria set, codify dual-maintenance
   governance.
4. **Stage-4 adversarial review** (Noor): CONDITIONAL APPROVE-TO-PLAN
   for the side-by-side scope of *this* PR; REJECT full transition as
   scoped here; impose two BLOCKING preconditions on any engine code
   landing (see *Consequences* below).

Martin signed off on four gating questions
(`.squad/decisions/inbox/copilot-martin-signoff-ps-side-by-side.md`,
2026-06-02T15:05Z):

1. Dual-maintenance is **PERMANENT**, funded — §7a governance is
   ACCEPTED and binding.
2. Transition intent is a **REAL COMMITMENT** — invest in §1.7a so
   Python *can* eventually be retired once the gate is met.
3. PDF stays **Python-only / delegated**, possibly permanent.
4. **PowerShell 7.2+ only**; Windows PowerShell 5.1 is dropped.

## Decision

1. **Rewrite `docs/plan.md` §1.7** to be additive: Python remains the
   reference / conformance-oracle engine; a native PowerShell engine
   (pwsh ≥ 7.2 only) is admitted as a deliberately-justified, governed
   second runtime that ships alongside Python. PDF reporting is
   explicitly delegated to Python — possibly permanently. The PS
   engine is held to the same read-only / PII / no-secrets /
   no-third-party-copyright hard rules and the same §11 delivery loop.
2. **Add `docs/plan.md` §1.7a "Go-full-PowerShell phase gate"** with
   eight capability-parity criteria, eight Noor security-falsification
   gates, the four Martin sign-off decisions recorded as binding
   inputs, and an explicit process clause: even if every criterion is
   met, retiring Python requires a fresh §11 cycle and a fresh
   stage-4 review.
3. **Make dual-maintenance the default end-state** (`docs/plan.md`
   §7a, governance rule mirrored into
   `.github/copilot-instructions.md`): no new Python rule, collector,
   or reporter reaches stable unless (a) PS parity lands in the same
   PR / release, or (b) the PS module explicitly declares the feature
   unsupported with a dated compatibility note and the conformance
   harness is updated to skip it intentionally. The conformance job
   mechanically enforces this; reviewers do not chase it manually.
4. **Adopt the gating PR sequence** (see *Consequences*) so engine
   code lands only after the two BLOCKING security-contract PRs
   merge.

## Consequences

### Positive

- The hard rule in `.github/copilot-instructions.md` ("no second
  runtime unless `docs/plan.md` is updated to justify it") is
  satisfied verbatim by the §1.7 / §1.7a rewrite.
- Operator adoption barrier for PS-native admins drops materially
  without weakening any hard rule.
- Dual-maintenance is *named* as the default end-state, not as a
  transition phase that quietly tolerates drift.
- Retiring Python requires a fresh adversarial review — there is no
  "no objections within X" path past Noor's REJECT.

### Negative / cost

- Every new rule, collector, and reporter is *expected* to ship
  twice. §7a governance accepts this cost as permanent (Martin D1).
- Conformance harness, shared PII test vectors, and shared
  scope-guard adversarial corpus add CI surface area that must be
  maintained.
- PDF stays Python-only; PS-only operators who want PDF must shell
  out to the Python CLI (or skip PDF). This trade-off is explicitly
  re-ratified by §1.7a criterion 3 if full transition is ever
  proposed.

### Gating PR sequence (binding order)

This ADR ships in **PR A — docs-only** (this PR; the one introducing
this file). Engine code does not land in this PR.

Then, in order, before any rule / reporter / normaliser code merges:

1. **PR #1 — read-only scope-guard parity (HR-1)**: PS implementation
   of the §9 scope-guard that performs *actual-token claim
   introspection* (not static config matching) and rejects any
   write / admin scope, with a shared adversarial-token corpus that
   the Python guard already passes. Noor's BLOCKING precondition.
2. **PR #2 — PII salt byte-parity (HR-4)**: PS implementation of the
   salted-hash redaction algorithm reproducing byte-for-byte outputs
   for the shared test-vector suite. Noor's BLOCKING precondition.
3. **PR — conformance harness**: produces byte-deterministic
   diff between Python and PS reporter outputs across the shared
   fixture corpus; wired into the single `required-checks` summary
   context (§11) — never as an ungated parallel job.
4. **PR(s) — first PS rules / reporters**: only after PRs #1 and #2
   merge and the conformance harness is green on a non-empty rule
   subset.

Each gating PR requires human (not bot, not `@copilot`) sign-off to
merge. The §7a governance rule is enforced from the moment this docs
PR merges.

## Dissent — Noor (Security & compliance reviewer)

Noor's stage-4 verdict on this initiative is **CONDITIONAL
APPROVE-TO-PLAN for side-by-side; REJECT for full transition as
scoped here.** Recorded here verbatim-in-spirit so future
contributors can reconstruct the disagreement without rummaging
through inbox archives:

- **Preferred end-state (Noor's first preference):** *Wrapper-only* —
  keep Python as the sole engine and ship a thicker, idiomatic PS
  wrapper around its CLI. This minimises maintenance cost, eliminates
  the scope-guard / PII / schema-rigor parity risks at the source,
  and is what the original §1.7 already permitted.
- **Acceptable fallback (this ADR):** *Permanent dual-maintenance
  side-by-side* with §7a governance binding from day one. The PS
  engine is a peer; Python is the conformance oracle; neither is
  retired.
- **Rejected scope:** *Full transition to PS-only* with retirement
  of Python. Noor REJECTS pre-approving this even contingent on
  §1.7a; in her ranking, even meeting all 16 §1.7a criteria does not
  make PS-only the right end-state, because the conformance oracle
  itself disappears at that point. She concedes only that meeting
  §1.7a unlocks a *fresh* stage-4 in which the trade-off can be
  re-litigated — she does not commit in advance to approving it.
- **Ranked end-states (Noor):** (1) wrapper-only, (2) permanent
  side-by-side (this ADR), (3) PS-only — strictly dispreferred.
- **BLOCKING preconditions (binding regardless of dissent):** PR #1
  scope-guard parity with actual-token claim introspection, PR #2
  PII salt byte-parity with shared test vectors. No rule, reporter,
  or normaliser code merges before both.
- **Documentation requirement met by this ADR:** Noor must be
  recorded as DISSENTING on full transition; the §1.7 rewrite must
  default to PERMANENT dual-maintenance with a sunset clause gated
  by her §1.7a falsification criteria.

The author (Maya) accepts the dissent without amending the decision:
this ADR adopts Noor's *acceptable fallback* (permanent
side-by-side), preserves her dissent on full transition, and binds
the project to the gating PR sequence above.

## References

- `docs/plan.md` §1.7 (additive rewrite) and §1.7a (phase gate).
- `.github/copilot-instructions.md` §7a governance rule
  (dual-maintenance enforcement, mirrored from `docs/plan.md` §7a).
- `.squad/decisions/inbox/copilot-martin-signoff-ps-side-by-side.md`
  — Martin's four sign-offs (D1–D4), 2026-06-02T15:05Z.
- §11 of `docs/plan.md` — five-stage delivery loop the future
  retirement decision must complete afresh.
