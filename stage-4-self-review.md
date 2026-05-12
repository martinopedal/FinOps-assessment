# Stage 4: Self-review (Noor voice)

Adversarial review against the 5 hard rules from `.github/copilot-instructions.md`:

## Hard Rule 1: Read-only by construction ✅

**Review:** The commitment models represent **OBSERVATIONS** of existing commitments, NEVER instructions to purchase/exchange/modify.

**Evidence:**
- Model names: `AzureCommitmentObservation`, `SavingsPlanEligibleSpendObservation` — explicitly "observation" pattern
- Fields are descriptive: `utilization_pct`, `coverage_pct`, `expiry_date`, `eligible_spend_usd` — all read-only signals
- No action fields: NO "recommended_action", "should_purchase", "exchange_to", etc.
- Docstrings use past-tense/descriptive language: "represents a purchased commitment", "observed utilization", "coverage signal"

**Ruling:** PASS. This is a data contract for collectors to report what exists, NOT a recommendation engine.

## Hard Rule 2: No secrets in repo (OIDC only) ✅

**Review:** Auth posture pre-committed in issue #28: "OIDC federated credentials only; no PATs, no client secrets, no tenant IDs in source."

**Evidence:**
- This PR adds pydantic models only, NO collector code, NO auth code
- Commitment IDs are opaque strings — NOT parsed for tenant boundaries
- `source` field documents provenance (`cost_management_api`, `customer_supplied`) but contains NO credentials

**Ruling:** PASS. OIDC auth is deferred to collector PRs; this PR is schema-only.

## Hard Rule 3: No copyrighted material redistribution ✅

**Review:** No Microsoft pricing tables, commitment pricing, or proprietary rate cards copied into the repo.

**Evidence:**
- Research stage (stage-1-research.md) **links** to Azure Cost Management API docs, does NOT copy
- Models define observation schema, NOT pricing constants
- Observations are customer-supplied or collector-fetched at runtime, NOT packaged

**Ruling:** PASS.

## Hard Rule 4: PII redaction on by default ✅

**Review:** Commitment IDs / GUIDs should be opaque, not parsed for tenant boundaries. Commitment names might contain customer-identifying info.

**Evidence:**
- Commitment IDs (`commitment_id`, `reservation_id`) are typed as opaque `str`, no parsing logic
- Commitment names (`commitment_name`, `reservation_name`) are optional strings — treated like any other PII-eligible field
- Default PII redaction (hard rule 4) already handles this; no special exemption requested

**Ruling:** PASS. Commitment IDs are opaque; PII redaction applies to names.

## Hard Rule 5: Catalogue is data, not code ✅

**Review:** Commitments are runtime observations, NOT catalog constants.

**Evidence:**
- Models live in `src/finops_assess/pricing.py` (observations), NOT `data/catalog/`
- No commitment SKUs, prices, or metadata added to `data/catalog/azure/*.yaml`
- This reinforces the observation-vs-catalog boundary set in #27

**Ruling:** PASS.

---

## Language-guardrail enforcement (issue #28 acceptance criteria)

Findings must be phrased as *"consider"* / *"verify and then"* — never *"purchase"* / *"exchange"*.

**Evidence:**
- Model docstrings use descriptive language: "represents", "observed", "coverage signal"
- Enum literals use states, not actions: `"reserved_instance"`, `"savings_plan_compute"` (NOT "purchase_reservation", "exchange_to_savings_plan")
- `test_commitment_language_guardrail()` enforces prohibited-verb absence in docstrings

**Prohibited verbs (as standalone action words):**
- "purchase", "buy", "exchange", "modify", "deploy", "provision", "create" (as imperative verbs in commitment context)

**Allowed (descriptive past-tense):**
- "purchased commitment" (describes existing state), "observed coverage" (describes measurement)

**Ruling:** PASS. Language guardrail test will enforce this at CI time.

---

## Summary

All 5 hard rules satisfied. Language guardrail enforced at schema docstring level + tested. This PR is data-contract-only, read-only posture preserved.
