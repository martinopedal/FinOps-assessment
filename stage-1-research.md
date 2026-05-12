# Stage 1: Research

## Existing `AzureReservation` model coverage

From `src/finops_assess/models.py` lines 215-231:
- `reservation_id`, `reservation_name`, `sku`, `scope` 
- `utilization_pct` (0-100, trailing 30d average)
- `monthly_cost_usd`

## MISSING for the 5 reserved rule IDs:

1. **Coverage %** — what portion of on-demand spend is covered by commitments  
2. **Scope mismatch signal** — RI scoped to single-subscription when workload is multi-subscription, or vice versa
3. **Savings Plan eligible spend** — on-demand spend that COULD be covered by SP but isn't  
4. **Renewal window proximity** — days/months until commitment expires, renewal review window
5. **Commitment type distinction** — RI vs Savings Plan (different coverage/scope semantics)
6. **Over-commitment signal** — purchased capacity exceeds usage

## Azure Cost Management API surfaces

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

## Key observations:

- RI/SP are fundamentally **observations of purchased commitments**, not catalog entries
- They fit the observation pattern I set in #27/pricing.py: time-stamped, source-documented, customer-supplied or collector-fetched
- Distinct from list prices but same observation family
