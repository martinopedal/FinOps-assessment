# Stage 3: Plan

## Module placement decision

**EXTEND `src/finops_assess/pricing.py`** — the observation module I set up in #27.

**Justification:**
- RI/SP commitments are **observations of what the customer purchased**, not catalog constants
- They are time-stamped, source-documented, customer-supplied or collector-fetched
- They are in the same observation family as region-price observations
- The observation-vs-catalog separation I set in #27 applies here: commitments are runtime data, NOT packaged with the repo under `data/catalog/`

The existing `AzureReservation` in `models.py` is a **normalized record** consumed by the rule engine. The new models in `pricing.py` are **observations** (input data) that collectors transform into normalized records. This is a layering distinction, not a duplication.

## Pydantic models to add

### 1. `CommitmentType` (Literal)
```python
CommitmentType = Literal[
    "reserved_instance",    # VM, SQL, etc. RIs
    "savings_plan_compute", # Compute Savings Plan
    "savings_plan_azure",   # Azure Savings Plan (broader)
]
```

### 2. `CommitmentScope` (Literal)
```python
CommitmentScope = Literal[
    "single_subscription",
    "shared_subscription",
    "management_group",
]
```

### 3. `AzureCommitmentObservation` (BaseModel)

Fields:
- `commitment_id: str` — reservation ID or savings plan ID (min_length=1)
- `commitment_name: str | None` — optional human-readable name
- `commitment_type: CommitmentType` — RI or SP variant
- `sku_id: str | None` — SKU covered (e.g., "Standard_D2s_v3" for RI; None for SPs)
- `region: str | None` — region (for region-scoped RIs; None for global SPs)
- `scope: CommitmentScope` — single/shared/mgmt group
- `utilization_pct: float | None` — Field(default=None, ge=0, le=100), trailing window utilization
- `utilization_window_days: int | None` — Field(default=None, ge=1), e.g., 7, 30, 90
- `coverage_pct: float | None` — Field(default=None, ge=0, le=100), what % of eligible spend is covered
- `coverage_window_days: int | None` — Field(default=None, ge=1)
- `monthly_cost_usd: float | None` — Field(default=None, ge=0), commitment cost
- `expiry_date: str | None` — ISO 8601 date (YYYY-MM-DD), min/max_length=10
- `observed_at: str` — ISO 8601 date (YYYY-MM-DD), min/max_length=10, required
- `source: CommitmentObservationSource` — provenance
- `notes: str | None` — optional collector/operator notes

Docstring: Must describe this as an **observation** of an existing commitment, NOT an instruction. Use language like "represents a purchased commitment", "observed utilization", "coverage signal". Absolutely NO "purchase", "buy", "exchange", "modify" verbs.

### 4. `CommitmentObservationSource` (Literal)
```python
CommitmentObservationSource = Literal[
    "cost_management_api",       # Azure Cost Management REST API
    "reservation_summaries_api", # Reservations Summaries API
    "customer_supplied",         # Operator-provided CSV/JSON
]
```

### 5. `SavingsPlanEligibleSpendObservation` (BaseModel)

For `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` rule — tracks on-demand spend that COULD be covered by SP.

Fields:
- `resource_type: str` — e.g., "virtualMachine", "sqlDatabase" (min_length=1)
- `region: str | None` — optional region filter
- `eligible_spend_usd: float` — Field(ge=0), monthly on-demand spend eligible for SP
- `window_days: int` — Field(ge=1), e.g., 30, 90
- `observed_at: str` — ISO 8601 date (YYYY-MM-DD), min/max_length=10
- `source: CommitmentObservationSource`
- `notes: str | None`

Docstring: "Represents on-demand spend eligible for Savings Plan coverage." NO purchase verbs.

### 6. `AzureCommitmentDataset` (BaseModel)

Wrapper for batch observations (like `AzureRegionPriceDataset`):
- `commitments: list[AzureCommitmentObservation]` — Field(default_factory=list)
- `eligible_spend_observations: list[SavingsPlanEligibleSpendObservation]` — Field(default_factory=list)
- `dataset_generated_at: str | None` — ISO 8601 timestamp
- `dataset_version: str | None`
- `notes: str | None`

All models: `model_config = ConfigDict(extra="forbid")`

## Wiring into `NormalizedDataset`

**NO.** Deferred to rule PRs, consistent with #27. The `pricing.py` observation models are **input data contracts** for collectors to produce. Rules consume them. Wiring happens when rules are implemented.

## Tests to add (in `tests/test_pricing.py`)

1. `test_commitment_observation_round_trip()` — minimal commitment serializes/deserializes
2. `test_commitment_observation_all_fields()` — full commitment with all optional fields
3. `test_commitment_observation_forbid_extra()` — extra fields rejected
4. `test_commitment_observation_validation_bounds()` — utilization/coverage ∈ [0, 100], negative cost rejected, zero cost allowed
5. `test_commitment_observation_enum_literals()` — invalid `commitment_type`, `scope`, `source` rejected
6. `test_commitment_observation_expiry_date_format()` — ISO 8601 date validation (exactly 10 chars)
7. `test_eligible_spend_observation_round_trip()` — minimal eligible spend
8. `test_eligible_spend_observation_forbid_extra()` — extra fields rejected
9. `test_eligible_spend_observation_validation_bounds()` — negative spend rejected, zero allowed
10. `test_commitment_dataset_round_trip()` — dataset with mixed observations
11. `test_commitment_dataset_empty()` — empty dataset valid
12. `test_commitment_dataset_forbid_extra()` — extra fields rejected
13. **`test_commitment_language_guardrail()`** — asserts model docstrings do NOT contain prohibited verbs: "purchase", "buy", "exchange", "modify" (as standalone words, not as parts of "purchased" which is past-tense descriptive)

## Files to edit

- `src/finops_assess/pricing.py` — add commitment models (extend existing file)
- `tests/test_pricing.py` — add commitment tests (extend existing file)

## Files NOT to edit

- `src/finops_assess/models.py` — do NOT touch existing `AzureReservation`
- `data/rules/azure.yaml` — do NOT add rules (deferred to separate PRs)
- Any `data/catalog/` files — commitments are observations, not catalog

## Acceptance criteria

- All validation gates pass: ruff check, ruff format --check, mypy, pytest
- `finops-assess validate` still passes (baseline 87/7/23 — we didn't touch YAML)
- Language guardrail test enforces prohibited-verb absence
- Models use `extra="forbid"`, match `Field(...)` idioms from `RegionPriceObservation`
- Docstrings use advisory language ("represents observed", "coverage signal") — never imperative ("purchase", "exchange")
