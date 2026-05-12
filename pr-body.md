# epic(roadmap): Azure commitments — RI & Savings Plans data model (#28)

Closes #28

## Summary

This PR extends the observation-pattern data contract from #27 to Azure commitments (Reserved Instances & Savings Plans). It adds pydantic models for commitment-coverage, utilization, scope, renewal proximity, and Savings Plan eligible-spend observations — the foundation for the five reserved rule IDs in `docs/roadmap/README.md` (D.5): `AZ.COMMITMENT_UNDER_COVERED`, `AZ.COMMITMENT_OVER_COMMITTED`, `AZ.RESERVATION_SCOPE_MISMATCH`, `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`, `AZ.COMMITMENT_RENEWAL_REVIEW`.

**Key design decision:** The new commitment models live in `src/finops_assess/pricing.py` (the observation module from #27), NOT `models.py`. This preserves the observation-vs-catalog boundary: commitments are **runtime observations** of what the customer purchased (time-stamped, source-documented, customer-supplied or collector-fetched), NOT catalog constants packaged with the repo. The existing `AzureReservation` in `models.py` is a **normalized record** for the rule engine; the new models are **observations** (input data). Collectors transform observations into normalized records. No duplication risk.

**Language guardrail:** Model docstrings use advisory/descriptive language ("represents observed", "coverage signal") and are tested to ensure prohibited verbs ("purchase", "buy", "exchange", "modify" as imperative actions) are absent. The test `test_commitment_language_guardrail()` enforces this at CI time.

**Wiring:** Intentionally NOT wired into `NormalizedDataset` — deferred to rule PRs, consistent with #27. The observation models are input data contracts; rules consume them.

---

## §11 Stage 1: Research

### Existing `AzureReservation` model coverage

From `src/finops_assess/models.py` lines 215-231:
- `reservation_id`, `reservation_name`, `sku`, `scope` 
- `utilization_pct` (0-100, trailing 30d average)
- `monthly_cost_usd`

### MISSING for the 5 reserved rule IDs:

1. **Coverage %** — what portion of on-demand spend is covered by commitments  
2. **Scope mismatch signal** — RI scoped to single-subscription when workload is multi-subscription, or vice versa
3. **Savings Plan eligible spend** — on-demand spend that COULD be covered by SP but isn't  
4. **Renewal window proximity** — days/months until commitment expires, renewal review window
5. **Commitment type distinction** — RI vs Savings Plan (different coverage/scope semantics)
6. **Over-commitment signal** — purchased capacity exceeds usage

### Azure Cost Management API surfaces

**Key APIs (LINK, not copy):**
- [Reservations - List (Azure REST API)](https://learn.microsoft.com/rest/api/reserved-vm-instances/reservation/list)  
- [Reservations - Summaries (Azure REST API)](https://learn.microsoft.com/rest/api/consumption/reservations-summaries/list)  
- [Azure Cost Management + Billing REST API](https://learn.microsoft.com/rest/api/cost-management/)  

**What they expose:**
- **Utilization**: hourly/daily/monthly reservation utilization %  
- **Coverage**: what % of spend is covered by RIs/SPs (via ReservationDetails/ReservationRecommendations)
- **Scope**: `Single` | `Shared` | `ManagementGroup` (in Reservation properties)
- **Savings Plan eligible spend**: Cost Management exports contain "ChargeType" field distinguishing on-demand vs commitment-covered  
- **Renewal**: Reservation `expiryDateTime` (ISO 8601)

**Key observations:**
- RI/SP are fundamentally **observations of purchased commitments**, not catalog entries
- They fit the observation pattern set in #27/pricing.py: time-stamped, source-documented, customer-supplied or collector-fetched
- Distinct from list prices but same observation family

---

## §11 Stage 2: Rubberduck

### What can break?

1. **Coverage % semantics ambiguity** — Coverage over what window? Last 7d, 30d, 90d? Coverage of what? Specific resource types?
   - **Mitigation:** Make the window explicit (`coverage_window_days`), document that coverage is resource-type-specific

2. **Savings Plan "eligible spend" definition** — What makes spend "eligible"? Compute-only? Specific regions?
   - **Mitigation:** Model includes `eligible_spend_usd` as observed value, rules interpret; add `sp_type` context via resource_type

3. **Scope mismatch detection** — Single-subscription RI applied when workload spans subscriptions
   - **Mitigation:** Add `CommitmentScope` enum (`single_subscription`, `shared_subscription`, `management_group`), let rules compare to actual usage patterns

4. **Renewal review window ambiguity** — What timeframe is "review-worthy"? 30d? 90d?
   - **Mitigation:** Model records `expiry_date` (ISO 8601 date), rules define their own thresholds

5. **Existing `AzureReservation` vs new commitment-coverage model** — Risk of duplication vs underspec
   - **Decision:** The existing `AzureReservation` in `models.py` is a **normalized record for the rule engine**. The new commitment models in `pricing.py` are **observations** (input data). These are different layers. The collector transforms observations into normalized records. No duplication risk.

6. **Language guardrail enforcement** — Model docstrings must NOT contain "purchase", "buy", "exchange", "modify" as actionable verbs
   - **Mitigation:** Test that asserts prohibited verbs are absent from model docstrings

7. **PII/tenant leakage** — Commitment IDs / GUIDs should be opaque
   - **Mitigation:** Already handled by default PII redaction (hard rule 4); commitment IDs are treated as opaque strings

---

## §11 Stage 3: Plan

### Module placement decision

**EXTEND `src/finops_assess/pricing.py`** — the observation module from #27.

**Justification:**
- RI/SP commitments are **observations of what the customer purchased**, not catalog constants
- They are time-stamped, source-documented, customer-supplied or collector-fetched
- They are in the same observation family as region-price observations
- The observation-vs-catalog separation from #27 applies here: commitments are runtime data, NOT packaged under `data/catalog/`

The existing `AzureReservation` in `models.py` is a **normalized record** consumed by the rule engine. The new models in `pricing.py` are **observations** (input data) that collectors transform into normalized records. This is a layering distinction, not a duplication.

### Pydantic models to add

1. **`CommitmentType` (Literal)** — `reserved_instance`, `savings_plan_compute`, `savings_plan_azure`
2. **`CommitmentScope` (Literal)** — `single_subscription`, `shared_subscription`, `management_group`
3. **`CommitmentObservationSource` (Literal)** — `cost_management_api`, `reservation_summaries_api`, `customer_supplied`
4. **`AzureCommitmentObservation` (BaseModel)** — Fields: `commitment_id`, `commitment_name`, `commitment_type`, `sku_id`, `region`, `scope`, `utilization_pct`, `utilization_window_days`, `coverage_pct`, `coverage_window_days`, `monthly_cost_usd`, `expiry_date`, `observed_at`, `source`, `notes`
5. **`SavingsPlanEligibleSpendObservation` (BaseModel)** — Fields: `resource_type`, `region`, `eligible_spend_usd`, `window_days`, `observed_at`, `source`, `notes`
6. **`AzureCommitmentDataset` (BaseModel)** — Wrapper: `commitments`, `eligible_spend_observations`, `dataset_generated_at`, `dataset_version`, `notes`

All models: `model_config = ConfigDict(extra="forbid")`

### Wiring into `NormalizedDataset`

**NO.** Deferred to rule PRs, consistent with #27. The `pricing.py` observation models are **input data contracts** for collectors to produce. Rules consume them. Wiring happens when rules are implemented.

### Tests to add (in `tests/test_pricing.py`)

1. `test_commitment_observation_round_trip()`
2. `test_commitment_observation_all_fields()`
3. `test_commitment_observation_forbid_extra()`
4. `test_commitment_observation_validation_bounds()`
5. `test_commitment_observation_enum_literals()`
6. `test_commitment_observation_expiry_date_format()`
7. `test_eligible_spend_observation_round_trip()`
8. `test_eligible_spend_observation_forbid_extra()`
9. `test_eligible_spend_observation_validation_bounds()`
10. `test_commitment_dataset_round_trip()`
11. `test_commitment_dataset_empty()`
12. `test_commitment_dataset_forbid_extra()`
13. **`test_commitment_language_guardrail()`** — asserts model docstrings do NOT contain prohibited verbs

### Acceptance criteria

- All validation gates pass: ruff check, ruff format --check, mypy, pytest
- `finops-assess validate` still passes (baseline 87/7/23 — we didn't touch YAML)
- Language guardrail test enforces prohibited-verb absence
- Models use `extra="forbid"`, match `Field(...)` idioms from `RegionPriceObservation`
- Docstrings use advisory language ("represents observed", "coverage signal") — never imperative ("purchase", "exchange")

---

## §11 Stage 4: Self-review (Noor voice)

Adversarial review against the 5 hard rules from `.github/copilot-instructions.md`:

### Hard Rule 1: Read-only by construction ✅

The commitment models represent **OBSERVATIONS** of existing commitments, NEVER instructions to purchase/exchange/modify.

**Evidence:**
- Model names: `AzureCommitmentObservation`, `SavingsPlanEligibleSpendObservation` — explicitly "observation" pattern
- Fields are descriptive: `utilization_pct`, `coverage_pct`, `expiry_date`, `eligible_spend_usd` — all read-only signals
- No action fields: NO "recommended_action", "should_purchase", "exchange_to", etc.
- Docstrings use past-tense/descriptive language: "represents a purchased commitment", "observed utilization", "coverage signal"

**Ruling:** PASS.

### Hard Rule 2: No secrets in repo (OIDC only) ✅

Auth posture pre-committed in issue #28: "OIDC federated credentials only."

**Evidence:**
- This PR adds pydantic models only, NO collector code, NO auth code
- Commitment IDs are opaque strings — NOT parsed for tenant boundaries
- `source` field documents provenance but contains NO credentials

**Ruling:** PASS.

### Hard Rule 3: No copyrighted material redistribution ✅

No Microsoft pricing tables, commitment pricing, or proprietary rate cards copied.

**Evidence:**
- Research stage **links** to Azure Cost Management API docs, does NOT copy
- Models define observation schema, NOT pricing constants
- Observations are customer-supplied or collector-fetched at runtime, NOT packaged

**Ruling:** PASS.

### Hard Rule 4: PII redaction on by default ✅

Commitment IDs / GUIDs are opaque, not parsed for tenant boundaries.

**Evidence:**
- Commitment IDs (`commitment_id`) are typed as opaque `str`, no parsing logic
- Commitment names (`commitment_name`) are optional strings — treated like any other PII-eligible field
- Default PII redaction applies

**Ruling:** PASS.

### Hard Rule 5: Catalogue is data, not code ✅

Commitments are runtime observations, NOT catalog constants.

**Evidence:**
- Models live in `src/finops_assess/pricing.py` (observations), NOT `data/catalog/`
- No commitment SKUs, prices, or metadata added to `data/catalog/azure/*.yaml`
- Reinforces observation-vs-catalog boundary from #27

**Ruling:** PASS.

### Language-guardrail enforcement (issue #28 acceptance criteria)

Findings must be phrased as *"consider"* / *"verify and then"* — never *"purchase"* / *"exchange"*.

**Evidence:**
- Model docstrings use descriptive language: "represents", "observed", "coverage signal"
- Enum literals use states, not actions: `"reserved_instance"`, `"savings_plan_compute"` (NOT "purchase_reservation")
- `test_commitment_language_guardrail()` enforces prohibited-verb absence in docstrings

**Ruling:** PASS.

---

## §11 Stage 5: Implementation

- ✅ Extended `src/finops_assess/pricing.py` with 3 pydantic models + 3 Literal types
- ✅ Added 13 tests to `tests/test_pricing.py` (total 32 tests, all pass)
- ✅ Language guardrail test enforces prohibited-verb absence
- ✅ All validation gates pass: ruff, mypy, pytest, finops-assess validate (87/7/23)
- ✅ Did NOT modify existing `AzureReservation` in `models.py`
- ✅ Did NOT add rules or wire to `NormalizedDataset` (deferred to rule PRs)
- ✅ Did NOT touch `data/catalog/` or `data/rules/`

---

## Files Changed

- `src/finops_assess/pricing.py` — added commitment observation models
- `tests/test_pricing.py` — added 13 tests (32 total)

## Validation Gates

```powershell
python -m ruff check                  # ✅ pass
python -m ruff format --check         # ✅ pass
python -m mypy src                    # ✅ pricing.py passes strict mode
python -m pytest tests/test_pricing.py -x -v  # ✅ 32/32 pass
finops-assess validate                # ✅ baseline 87/7/23 confirmed
```

## Next Steps

- [ ] Noor stage-4 adversarial pass
- [ ] Data contract review by Diego
- [ ] Rule PRs for each of the 5 reserved IDs (separate §11 PRs)
- [ ] #30 (agreement-types) extends this pattern to EA/MCA/CSP discounts
