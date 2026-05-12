# Stage 2: Rubberduck

## What can break?

### 1. Coverage % semantics ambiguity
- Coverage over what window? Last 7d, 30d, 90d?
- Coverage of what? Specific resource types? All on-demand compute?
- **Mitigation**: Make the window explicit in the model (`coverage_window_days`), document that coverage is resource-type-specific (VM vs SQL vs other)

### 2. Savings Plan "eligible spend" definition
- What makes spend "eligible"? Compute-only? Specific regions?
- Could vary by SP type (Compute SP vs Azure SP)
- **Mitigation**: Model includes `eligible_spend_usd` as observed value, rules interpret; add `sp_type` field

### 3. Scope mismatch detection
- Single-subscription RI applied when workload spans subscriptions
- Or shared RI when workload is actually isolated
- **Mitigation**: Add `CommitmentScope` enum (`single_subscription`, `shared_subscription`, `management_group`), let rules compare to actual usage patterns

### 4. Renewal review window ambiguity
- What timeframe is "review-worthy"? 30d? 90d?
- **Mitigation**: Model records `expiry_date` (ISO 8601 date), rules define their own thresholds

### 5. Existing `AzureReservation` vs new commitment-coverage model
- Risk of duplication: existing model has `utilization_pct`, new one might too
- Risk of underspec: if we only extend existing model, we lose the observation-pattern separation
- **Decision**: The existing `AzureReservation` in `models.py` is a **normalized record for the rule engine** (like `AzureResource`, `UserRecord`). The new commitment models in `pricing.py` are **observations** (input data). These are different layers. The collector transforms observations into normalized records. No duplication risk.

### 6. Language guardrail enforcement
- Model docstrings and enum values must NOT contain "purchase", "buy", "exchange", "modify" as actionable verbs
- Only descriptive states: "covered", "underutilized", "scope_mismatch", "approaching_renewal"
- **Mitigation**: Test that asserts prohibited verbs are absent from model docstrings and Literal enums

### 7. PII/tenant leakage
- Commitment IDs / GUIDs are opaque, should not be parsed for tenant boundaries
- Reservation names might contain customer-identifying info
- **Mitigation**: Already handled by default PII redaction (hard rule 4); commitment IDs are treated as opaque strings
