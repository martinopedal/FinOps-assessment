# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent azure-specialist initialized for the FinOps-assessment squad. See `.squad/agents/azure-specialist/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **2026-05-12** — Issues #27 (D.4: Azure pricing intelligence—Noor's recommended pilot), #28 (D.5: CapEx/OpEx commitments), #30 (D.7: agreement-types triage) now in backlog. Pre-commit to OIDC-only auth in issue bodies per stage-4 review so hard rule 2 is not re-litigated in collector PR.
- **2026-05-12** — PR #39 (issue #27): Azure region-price observation contract. File/module placement: observations in `src/finops_assess/pricing.py` (separate from `models.py`) to reinforce observation-vs-catalog boundary. Key pydantic choices: `currency: Literal["USD"]` (explicit single-currency baseline, expandable later), `observed_at: str` constrained to ISO 8601 date (min/max_length=10), `source: Literal[...]` for auditable provenance. Wiring into `NormalizedDataset` intentionally deferred to rule PRs (#28, #30) to avoid speculative design. Open questions for #28/#30: Should commitment pricing (RI/SP) be a subclass or separate model? Should agreement discounts (EA/MCA/CSP) be applied at collection time or rule-evaluation time? Sovereign-cloud support requires security/compliance review first. The observation-vs-catalog separation pattern set here is the foundation for #28 (RI/SP) and #30 (agreement-types) to extend cleanly.
- **2026-05-12** — PR #42 (issue #28): Azure commitment-coverage data model. Extended `pricing.py` observation pattern to RI/SP commitments: separate models for `AzureCommitmentObservation` (utilization, coverage, scope, expiry) and `SavingsPlanEligibleSpendObservation`. Language-guardrail enforcement: docstring-level constraint tested via `test_commitment_language_guardrail()` to block prohibited verbs ("purchase", "buy", "exchange" as imperative actions). Commitment models are **observations** (input data), NOT normalized records — the existing `AzureReservation` in `models.py` is the normalized-record layer consumed by rules; collectors transform observations into normalized records. This layering distinction answers the #27 open question "Should commitment pricing be a subclass or separate model?": it's a separate observation family in `pricing.py`, NOT a subclass of catalog entries. Wiring to `NormalizedDataset` deferred to rule PRs (consistent with #27). #30 (agreement-types) will inherit this pattern: EA/MCA/CSP multipliers as a third observation family. Test count: 13 new tests (32 total in test_pricing.py). All validation gates pass.
