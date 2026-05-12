# Derived report views — architectural principle (Maya, 2026-05-12)

**Decision inbox entry — pending Scribe merge into `.squad/decisions.md`.**

## Principle

> Report sections that surface **posture** rather than **data** are
> **derived views**. They READ the canonical JSON report — they do
> not extend it. Advisory disclaimers are mandatory. Certification /
> scoring / level / rating language is forbidden in body content.

## Why this matters now

Issue #31 added the first FinOps practice-review section to the
reporter (pricing assumptions / data-quality warnings / commitment
posture / SKU-mix posture). Three of the four sub-sections are
posture cues, not new data — they reframe existing fields for an
operator answering the question *"how confident is this report?"*.
Adding even one new top-level field to canonical JSON for them would
have:

1. Bumped the schema version for a non-data change.
2. Created a competing summary surface alongside the canonical one.
3. Made every downstream consumer (CSV, PDF, future BI exporters)
   re-decide what "posture" means at their own layer.

The derived-view discipline avoids all three.

## Rules of thumb (binding for future report sections)

1. **Read-only over canonical.** The renderer takes the canonical
   report dict and returns HTML / CSV / text. No collector calls, no
   tenant I/O, no model mutation. Read-only posture (hard rule #1)
   extends to derived views: a derived view that pulls fresh data is
   no longer derived.
2. **No schema additions.** If a posture cue needs a field that
   isn't in canonical JSON, the *field* lands in its own §11 PR
   with a schema bump, and the derived view picks it up on a later
   PR. The two changes never ride together.
3. **Graceful degradation is a render contract, not an error.** When
   an upstream posture field is not yet available, the sub-section
   emits a "data not yet available" line. It does not crash, suppress
   the whole section, or fabricate a placeholder value. Tests cover
   the degraded path.
4. **Advisory disclaimer is mandatory.** Every derived posture
   section opens with a one-line disclaimer that states the advisory
   posture *positively* (what it is) before any negation (what it is
   not). The disclaimer is structurally separable from body content
   so guards can scan the body independently.
5. **Forbidden-word guard for certification language.** Tests assert
   the absence of "Level", "Score", "Certified", "Certification",
   and "Rating" in posture body content. The disclaimer is held to
   the same bar (no negations of these words allowed inside it) so
   the guard can run as an unconditional substring check.
6. **Vendor-neutral phrasing.** Posture cues describe coverage,
   completeness, or freshness. They do not name a "winner" SKU
   family, recommend a purchase action (re-litigates #28's commerce
   guardrail), or rank vendors. Data-quality warnings describe the
   *dataset*, never the customer's operational hygiene.

## Scope of this principle

Applies to:

- The practice-review section shipped in #31.
- The future commitment-coverage report section that will naturally
  fall out of #28 once Diego's contract lands — that section is the
  next concrete consumer of this principle.
- Any future "operator-confidence" or "data-completeness" section.

Does **not** apply to:

- Canonical findings rendering (per-surface tables) — those are not
  posture cues; they are the data.
- Catalogue / personas / rules dumps via `finops-assess validate`.
- Live collector output (write-side is forbidden anyway).

## Falsification

This principle gets re-opened if any of the following happen:

1. A derived-view PR forces a canonical schema change in the same
   commit to avoid an architectural ugliness. (Means rule #2 is too
   strict.)
2. The forbidden-word guard fires on a legitimate posture-cue word
   that wasn't anticipated. (Means rule #5's word list needs revision,
   not abandonment.)
3. Operators report the disclaimer is misread as the section being
   optional or unimportant. (Means rule #4's wording needs work, not
   the rule.)

— Maya, Lead Architect, 2026-05-12
