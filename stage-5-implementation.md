# Stage 5: Implementation Summary

## Files edited

### `src/finops_assess/pricing.py`
- Added 4 new Literal types: `CommitmentObservationSource`, `CommitmentType`, `CommitmentScope`
- Added 3 new BaseModel classes:
  - `AzureCommitmentObservation` — observations of purchased RIs/SPs with utilization, coverage, scope, expiry
  - `SavingsPlanEligibleSpendObservation` — observations of on-demand spend eligible for SP coverage
  - `AzureCommitmentDataset` — wrapper for batch commitment observations
- All models use `model_config = ConfigDict(extra="forbid")`
- All models use `Field(...)` constraints matching the `RegionPriceObservation` pattern from #27
- Docstrings use advisory/descriptive language ("represents observed", "coverage signal") — NO prohibited verbs ("purchase", "exchange" as imperative actions)
- Models are **observations** (input data), NOT normalized records for the rule engine

### `tests/test_pricing.py`
- Added 13 new test functions:
  - `test_commitment_observation_round_trip()`
  - `test_commitment_observation_all_fields()`
  - `test_commitment_observation_forbid_extra()`
  - `test_commitment_observation_validation_bounds()`
  - `test_commitment_observation_enum_literals()`
  - `test_commitment_observation_expiry_date_format()`
  - `test_eligible_spend_observation_round_trip()`
  - `test_eligible_spend_observation_forbid_extra()`
  - `test_eligible_spend_observation_validation_bounds()`
  - `test_commitment_dataset_round_trip()`
  - `test_commitment_dataset_empty()`
  - `test_commitment_dataset_forbid_extra()`
  - **`test_commitment_language_guardrail()`** — enforces prohibited-verb absence in docstrings
- All tests pass (32 tests in test_pricing.py)

## Files NOT edited (as per plan)

- `src/finops_assess/models.py` — did NOT touch existing `AzureReservation` (it's a normalized record, not an observation)
- `data/rules/azure.yaml` — did NOT add rules (deferred to separate PRs)
- No `data/catalog/` files — commitments are observations, not catalog

## Wiring into `NormalizedDataset`

NOT done. Deferred to rule PRs, consistent with #27. The `pricing.py` observation models are **input data contracts** for collectors to produce. Rules consume them. Wiring happens when rules are implemented.

## Validation gates — all pass ✅

- ✅ `ruff check` — pass
- ✅ `ruff format --check` — pass (after formatting)
- ✅ `mypy src` — pricing.py passes strict mode (pre-existing yaml stub warnings in other files)
- ✅ `pytest tests/test_pricing.py -x -v` — 32/32 pass, including language guardrail
- ✅ `finops-assess validate` — baseline 87/7/23 confirmed (no YAML touched)

## Language-guardrail enforcement

**Approach:** Docstring-level constraint + tested.

- Prohibited verbs ("purchase", "buy", "exchange", "modify") as imperative actions are absent from model docstrings
- Past-tense descriptive usage ("purchased commitment") is allowed
- `test_commitment_language_guardrail()` enforces this at CI time using regex word-boundary matching

## Model count & test count added

- **Models added:** 3 (AzureCommitmentObservation, SavingsPlanEligibleSpendObservation, AzureCommitmentDataset)
- **Literals added:** 3 (CommitmentObservationSource, CommitmentType, CommitmentScope)
- **Tests added:** 13
- **Total tests in test_pricing.py:** 32 (19 existing + 13 new)

## What #30 (agreement-types) will inherit

The observation pattern is now established for two families:
1. Region-price observations (from #27)
2. Commitment observations (from #28)

#30 will likely add a third family: agreement-type discount observations (EA/MCA/CSP multipliers). Same pattern:
- Observations in `pricing.py`
- Time-stamped, source-documented, customer-supplied or collector-fetched
- NOT catalog constants
- Language guardrail applies
- Wiring deferred to rule PRs
