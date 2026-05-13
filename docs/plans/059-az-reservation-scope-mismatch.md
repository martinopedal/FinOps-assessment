# §11 Stage-3 Plan: `AZ.RESERVATION_SCOPE_MISMATCH` (#59, child 4 of 5)

> **Author:** Maya (Lead / FinOps PM), model: **Opus 4.7**
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #59 (epic), release `release:v0.5.0`, priority `priority:p1`
> **Branch (this plan):** `squad/59-plan-maya-reservation-scope-mismatch`
> **Branch (implementation):** `squad/59-impl-reservation-scope-mismatch` (Diego, post-Noor)
> **Implementer:** Diego (primary, Azure specialist), Yuki backup if Diego is at capacity
> **Adversarial reviewer:** Noor (stage-4)
> **Sibling plans:** `docs/plans/059-az-savings-plan-eligible-spend.md` (rule 1/5, plan + impl MERGED PRs #83 + #85), `docs/plans/059-az-commitment-under-covered.md` (rule 2/5, plan MERGED PR #84, impl in flight on PR #88), `docs/plans/059-az-commitment-renewal-review.md` (rule 3/5, plan MERGED PR #86, impl assigned to Diego).
> **Producer-path SHA:** `a549a1d` (current `main` after PR #87 merge)

This plan covers **one** rule from the five-rule epic: `AZ.RESERVATION_SCOPE_MISMATCH`. Rules 1, 2, and 3 are already through stage-3 (PRs #83, #84, #86 merged). Rule 5 (`AZ.AHB_ELIGIBLE`) gets its own stage-3 plan and PR. One rule, one PR, confirmed by the epic body.

The plan format mirrors the rule-1, rule-2, and rule-3 plans and the binding norms canonicalised in `.squad/decisions.md` post-PR-#78 + post-PR-#85: **every claim about a value the rule emits MUST cite the producer code path (file:line) that establishes it**, and **§1.1 briefs touching polymorphic API surfaces MUST disambiguate the discriminator field from the identifier-list field by name** (binding lesson from PR #85 stage-4 lockout).

**Headlines (vs rules 1, 2, and 3):**

1. This rule introduces **one** schema change on `AzureReservation`: a new optional `applied_scope_subscription_ids: list[str] | None` field. Existing `scope: str | None` is **kept** (already stores the `appliedScopeType` discriminator per `arm_collector.py:690`). See §1.1 + Correction B in §1.4.
2. The rule resolves **rule 2's E11 over-count limitation**. When `applied_scope_subscription_ids` is populated, a future amendment to rule 2 can exclude owner subs from its sibling tally. That amendment is **out of scope** for this PR (per the "one rule, one PR" cadence); this PR ships the schema field rule 2 documented as the cleaner fix in `docs/plans/059-az-commitment-under-covered.md` §2.7 R1.
3. **Two stage-3 corrections** vs the framing carried in the epic body / Lead handoff brief. Both surfaced explicitly in §1.4 so they can be inspected and rejected if Noor disagrees, never silently overridden (§11 ground rule).

---

## Section 1: Stage-1 Research brief (Maya, ground-truth read)

### 1.1 What the Microsoft.Capacity reservations LIST endpoint actually returns (discriminator vs identifier list)

I read the Microsoft Learn reference for the `reservation list-all` operation directly (URL below) before writing this section. The ARM collector already calls this exact endpoint at the api-version this rule needs.

- **Endpoint:** `GET https://management.azure.com/providers/Microsoft.Capacity/reservations?api-version=2022-11-01`
- **Source:** <https://learn.microsoft.com/en-us/rest/api/reserved-vm-instances/reservation/list-all>
- **Required scope:** `Reservation Reader` (or `Reader` on the reservation order). Already implicit in the existing ARM collector posture; **no new scope, no new audience, hard rule #1 upheld** (`src/finops_assess/collectors/arm_collector.py:31`).

**Two distinct fields on `properties` carry the scope information; this plan disambiguates them by name to avoid the failure mode PR #85 stage-4 caught (Diego mistook a discriminator for an ARN in rule 1's stage-3 brief and the lockout protocol fired).**

| API field | Type | Semantics | Example values |
|---|---|---|---|
| `properties.appliedScopeType` | enum string (the **discriminator**) | Tells the consumer which scope family this reservation is in. Three legal values per the 2022-11-01 spec: `"Single"`, `"Shared"`, `"ManagementGroup"`. **Not an ARN.** | `"Single"` / `"Shared"` / `"ManagementGroup"` |
| `properties.appliedScopes` | list of strings (the **identifier list**) | The actual scope ARNs / IDs the discount is applied to. Populated when `appliedScopeType == "Single"` (one or more subscription ARNs) or `"ManagementGroup"` (one MG resource ID); the API returns this as `null` or an empty list when `appliedScopeType == "Shared"`. **Not a discriminator.** | `["/subscriptions/00000000-0000-0000-0000-000000000001"]` (Single) / `null` or `[]` (Shared) / `["/providers/Microsoft.Management/managementGroups/finops-mg"]` (ManagementGroup) |

The current `AzureReservation.scope` field (`models.py:249`) is loosely typed (`str | None`) and the ARM collector writes `props.get("appliedScopeType") or ""` into it (`arm_collector.py:690`). **Functionally `scope` already IS the discriminator string**, despite the misleading name. The samples CSV uses lowercase `single` / `shared` (`samples/azure_reservations.csv:2-3`); the live ARM collector emits whatever the API returns (mixed case). The rule must defensively normalise via `(reservation.scope or "").strip().lower()`.

The schema **does not currently carry the identifier-list field** — `appliedScopes` is dropped on the floor in the existing reservation row builder. Rule 4 adds it as `applied_scope_subscription_ids: list[str] | None`. See §3.2 + §3.4 + Correction B (§1.4).

**Other reservation `properties` fields, not consumed by rule 4 (referenced for Noor's API spec cross-check):**

- `displayProvisioningState` -- e.g. `"Succeeded"`, `"Cancelled"`, `"Failed"`, `"Expired"`. Rule 3's plan adds a `Succeeded`-only filter at the collector (`docs/plans/059-az-commitment-renewal-review.md` §3.4); rule 4 inherits that filter when rule 3's impl lands. If rule 3's impl lands first (likely; Diego is assigned), rule 4 inherits the filter for free. If rule 4's impl lands first, rule 4 does not add the filter (out of scope; rule 3 owns it).
- `expiryDate`, `renew` -- rule 3's territory. Rule 4 does not read either.
- `term` -- not consumed by rule 4 directly; could appear in evidence as a future enhancement.

### 1.2 What the existing schema and collector already give us

I read the producer code on `main` SHA `a549a1d` end-to-end before writing this section. The bullets below are **producer-grounded**, not API-spec-grounded:

- `AzureReservation` (`src/finops_assess/models.py:236-251`): carries `reservation_id` (PK), `reservation_name`, `sku`, `scope` (the discriminator string, see §1.1), `utilization_pct` (0-100, nullable), `monthly_cost_usd` (nullable). **No `applied_scope_subscription_ids`** -- the identifier list from the API is dropped today.
- `AzureResource` (`src/finops_assess/models.py:207-233`): carries `resource_id`, `resource_type`, `sku`, `subscription_id` (`models.py:231`), `monthly_cost_usd`. **The `(subscription_id, monthly_cost_usd)` join surface is the same one rule 2 already uses** (`docs/plans/059-az-commitment-under-covered.md` §3.5). Rule 4 reuses this join but with the inverse semantics: rule 2 looks for sibling-sub on-demand spend; rule 4 looks at the partition between owner-sub spend and non-owner-sub spend.
- The ARM collector calls the right endpoint at the right api-version. `_API_VERSIONS["reservations"] = "2022-11-01"` at `src/finops_assess/collectors/arm_collector.py:40`, and `_collect_reservations` issues `GET .../providers/Microsoft.Capacity/reservations?api-version=2022-11-01` at `arm_collector.py:243-252`. The response body `props` is already in scope at the row builder (`arm_collector.py:670-694`); we only need to read **one** more key (`props.get("appliedScopes")`) and write **one** more CSV column.
- The CSV collector reads `azure_reservations.csv` into `AzureReservation` rows at `src/finops_assess/collectors/csv_collector.py:146`. The strict-column loader at `csv_collector.py:54-107` already handles `list[str]` columns: line 103-104 splits the cell on `|` and strips each item. **A pipe-separated single column** is the existing convention for list fields in this CSV format. Adding one column is a backward-compatible change (legacy CSVs without the column load with `applied_scope_subscription_ids = None` per the strict-column docstring at `csv_collector.py:59-63`). See §3.3 + §3.7.

### 1.3 Catalogue SKUs the rule references

- **None.** Reservations cut across many catalogue SKUs and have no `list_price_usd_month` we can publish without redistributing Microsoft pricing pages (hard rule #3 / #5). Same posture as `AZ.RESERVATION_UNDERUTILIZED` (`azure_rules.py:163-190`), `AZ.COMMITMENT_UNDER_COVERED` (rule 2), and `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3). No `data/catalog/azure/*.yaml` change in this PR.

### 1.4 Stage-3 corrections vs prior framings

Two corrections to assertions carried into this stage. Surfacing them rather than silently picking one (§11 ground rule); Noor adjudicates.

#### Correction A: re-scoping Shared -> Single does NOT reduce reservation cost

The epic body says: "a Shared-scope reservation that could be Single-scope for cost reasons; a Single-scope reservation when Shared would yield more usage". My read of the Microsoft Reservations pricing model (linked in §1.1, plus the FinOps practitioner consensus the team has been operating from in the rule-1 plan): **a reservation has the same monthly cost regardless of `appliedScopeType`. Scope only changes which subs the discount applies to, not the price the operator pays.** Re-scoping Shared -> Single therefore does NOT save money; it only narrows where the discount lands (and risks losing coverage on subs that were previously absorbing on-demand spend).

The cost-impacting cases are the **other** direction:

- **(C1) Single-scope, owner-sub idle, sibling-sub paying on-demand for compatible SKUs.** Widening Single -> Shared lets the existing reservation absorb the sibling spend. This is a real cost lever (the sibling sub stops paying on-demand for SKUs the reservation could cover for free).
- **(C2) Single-scope, owner-sub fully idle, no sibling has compatible workloads.** The reservation is effectively stranded; the operator should consider exchange or release at next renewal. This signal already partially fires via `AZ.RESERVATION_UNDERUTILIZED` (utilisation low) and `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3, near expiry). Rule 4 adds the scope-aware angle.

V1 of rule 4 fires only on **case C1**. C2 is covered by the existing `AZ.RESERVATION_UNDERUTILIZED` rule plus rule 3. The "Shared could be Single" angle from the epic body is **explicitly rejected as a savings signal**; it could be re-introduced as an info-severity "billing visibility" rule in a separate issue (R5 in §2.7), but it does not belong in the cost-savings playbook this epic is shipping.

This narrows rule 4's scope and aligns it with the playbook's "real-money lever" charter. Stage-4 reviewer: confirm or reject.

#### Correction B: ONE schema field, not two; do NOT rename existing `scope`

The Lead handoff brief said: "Schema decision: rule 4 likely needs ONE schema change -- a new field on `AzureReservation` like `applied_scope_subscription_ids: list[str] | None` (None = not loaded; empty list = Shared scope). Consider also `applied_scope_type: Literal["Single", "Shared"] | None`. Walk alternatives in §2.7."

I walked the alternatives (R1-R5 in §2.7). The chosen design is:

- **Add ONE field:** `applied_scope_subscription_ids: list[str] | None = None`.
- **Keep existing `scope: str | None` as-is.** It already stores `appliedScopeType` per the producer at `arm_collector.py:690`. Renaming to `applied_scope_type` is a breaking change for every operator with a legacy `azure_reservations.csv`; adding a parallel typed `applied_scope_type` field creates two ways to read the same data and a drift risk if the collector populates one but not the other.

The downside is that `scope` is a misleading field name (it is a discriminator string, not a scope ARN). I document the legacy semantics in the model docstring (`§3.2`) and leave a `# TODO(rule-cleanup-issue)` comment so a future renaming refactor has a citation handle.

**Two-field alternative (R3 in §2.7) is rejected**, not silently dropped. Stage-4 reviewer: steelman this rejection.

The empty-cell encoding caveat: the strict-column CSV loader treats an empty cell as "use field default" (`csv_collector.py:88-91`). With `applied_scope_subscription_ids` defaulting to `None`, an empty cell loads as `None`. **There is no way to encode "Shared scope (empty list)" via an empty cell.** The collector therefore distinguishes Shared from "not loaded" by reading the existing `scope` column: `scope == "Shared"` (or any case-insensitive variant) means the row is Shared and the empty `applied_scope_subscription_ids` is intentional, not missing. **The rule's gate explicitly checks `scope` first**, then optionally consumes `applied_scope_subscription_ids`. See §3.5 for the gate logic.

---

## Section 2: Stage-2 Rubberduck (Maya, plain-English walkthrough)

### 2.1 What the rule is supposed to say

> "Reservation `{principal}` is Single-scope (owner subs: `{owner_subs}`) but `${non_owner_spend_usd}/mo` of compatible on-demand spend is in subs the reservation cannot cover (`{sibling_subs}`). Verify the SKU compatibility, then consider re-scoping the reservation to Shared so the existing commitment can absorb the sibling on-demand spend. If re-scoping is not appropriate (e.g. cross-billing-scope, chargeback boundary), capture the rationale and review again at next renewal."

That is verb-conservative ("verify ... then consider ... if not appropriate ... capture ... review"); names the operator-side checks (SKU compatibility, billing-scope alignment); never tells the operator a single answer. Mirrors the wording register from rule 1, rule 2, rule 3, and the existing `AZ.RESERVATION_UNDERUTILIZED`.

### 2.2 What could go wrong (edge cases)

| # | Edge | Behaviour required |
|---|------|---|
| E1 | Dataset has no reservations | Rule emits no finding (vacuous loop). |
| E2 | Reservation row has `scope is None` or empty | Abstain. The discriminator is missing; we cannot make the "Single-scope" claim. |
| E3 | Reservation `scope` (lowercased) is not `"single"` (i.e. it is `"shared"`, `"managementgroup"`, or anything else) | Abstain. Rule 4 V1 fires only on Single-scope mismatches per Correction A (§1.4). |
| E4 | Reservation `applied_scope_subscription_ids is None` (CSV-mode operator left it blank, or live ARM collector exception) | Abstain. Without the owner-sub list we cannot partition spend into owner vs non-owner. **Same posture as rule 3 abstaining on `auto_renew is None`** (`docs/plans/059-az-commitment-renewal-review.md` §2.2 row E5). |
| E5 | Reservation `applied_scope_subscription_ids` is the empty list `[]` AND `scope == "single"` | Abstain. The combination is contradictory (Single must list at least one sub per the 2022-11-01 spec) and indicates dirty data. Log WARN and skip the row. |
| E6 | No `azure_resources` row populates `subscription_id` OR `monthly_cost_usd` (legacy CSV without per-sub spend) | Rule abstains across the board (no signal exists to compute non-owner spend). Same posture as rule 2 E10 (`docs/plans/059-az-commitment-under-covered.md` §2.2). |
| E7 | All on-demand spend is in owner subs (no sibling spend) | Abstain. There is no scope mismatch to surface. |
| E8 | Non-owner sibling-spend total `< _RESERVATION_SCOPE_MIN_NON_OWNER_USD` (default $50/mo, mirrors rule 2's threshold at `azure_rules.py:_COMMITMENT_UNDER_COVERED_MIN_USD`) | Abstain. Below noise floor. |
| E9 | Non-owner sibling-spend total `>= $50/mo` AND `scope == "single"` AND `applied_scope_subscription_ids` non-empty | **FIRE.** One finding per reservation, evidence aggregates per-sibling-sub spend. |
| E10 | Multiple Single-scope reservations all have non-owner spend signal | One finding per reservation. No dedup across reservations -- each commitment is its own decision. |
| E11 | Two reservations share the same owner-sub list and overlap on SKU family | Out of scope for V1. Fires twice; the operator inspects the evidence to decide whether one re-scope action covers both. **Documented limitation** -- a future rule could group by `(owner_sub, sku_family)` and emit one consolidated finding. |
| E12 | Owner-sub list contains a sub that is itself absent from `azure_resources` (the operator narrowed the resource collection scope but the reservation still references the wider sub) | The owner sub contributes `$0` to "owner spend"; non-owner spend is computed from the subs that ARE in `azure_resources`. Rule still fires if the non-owner spend exceeds threshold. **The recommendation_template explicitly says "verify the sibling's on-demand SKUs are compatible"; a missing-owner-sub case surfaces during operator verification.** |
| E13 | Reservation `scope == "single"` AND non-owner spend exists AND reservation `utilization_pct < 80%` (rule 2's gate also triggers) | **Both rule 2 (`AZ.COMMITMENT_UNDER_COVERED`) and rule 4 fire on the same reservation.** Intentional: rule 2's wording focuses on "rebalance the under-utilised reservation"; rule 4's wording focuses on "re-scope so the reservation reaches the on-demand sub". Different remediations, both correct. See §2.4. |
| E14 | SKU-family mismatch: reservation is `Standard_D4s_v5`, sibling spend is on `Standard_E32_v5` | Rule has **no SKU-compatibility check** today. Mitigation: wording, "verify the sibling's on-demand SKUs are compatible". Same posture as `AZ.RESERVATION_UNDERUTILIZED` and rule 2. SKU-compat is an operator-owned verification step. |
| E15 | Same reservation observed in two collector runs producing two CSV rows with the same `reservation_id` | Out of scope for the rule (that is a collector / dataset-builder bug). The strict-column loader would accept both rows; the rule would emit two findings. Dedup is the dataset-shape contract's job, not rule 4's. |

### 2.3 False-positive risks

- **Cross-billing-scope siblings.** A "sibling sub" outside the reservation's billing scope cannot legally absorb the discount even if rule 4 widens the scope (Microsoft Reservations are limited to the same Enterprise Agreement / billing profile / etc.). The rule has no billing-scope visibility today (no model field). Mitigation: the recommendation_template explicitly names the "billing-scope alignment" verification step. The operator catches the case during the verify stage; the false-positive cost is one operator skim per finding, not a silent bad action. Documented as a `docs/rules.md` caveat.
- **Dev/test sub on the sibling list.** If the sibling sub is a Dev/Test offer and the reservation is on a Production EA, widening the scope is not appropriate (separate billing). Same mitigation as above; the operator's verify step catches it. Future enhancement: cross-reference `subscription_offer` from `AzureResource.subscription_offer` (`models.py:232`) to suppress dev/test siblings; **out of scope for V1**, captured as R6 in §2.7.
- **Reservation about to expire.** A re-scope decision is moot if the reservation is expiring next week; the operator should focus on the renewal decision (rule 3). Mitigation: rule 3 will co-fire on near-expiry reservations, and the operator chooses which lever to pull. **No exclusion logic** between rule 3 and rule 4 -- they describe complementary remediations. See §2.4.
- **SKU-family mismatch silently inflates non-owner spend.** Without a SKU-compatibility check (E14), we count `Standard_E32_v5` on-demand spend as if a `Standard_D4s_v5` reservation could cover it. Mitigation: wording. Future enhancement: SKU-family normalisation (R4 in §2.7).

### 2.4 Cross-rule isolation

| Rule | Gate | Co-fire with rule 4? | Boundary |
|------|------|----------------------|----------|
| `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1, MERGED PR #83 plan + PR #85 impl) | `AzureBenefitRecommendation.cost_without_benefit_usd >= $50` AND `net_savings_usd > 0` AND `lookback_period in {Last30Days, Last60Days}` | Independent. Different model (`AzureBenefitRecommendation` vs `AzureReservation`), different join surface. No co-fire interaction. | **Disjoint by model.** |
| `AZ.COMMITMENT_UNDER_COVERED` (rule 2, MERGED PR #84 plan, impl in flight on PR #88) | `utilization_pct < 80%` AND sibling on-demand spend `>= $50/mo` | Yes -- a Single-scope reservation can be both under-utilised AND scope-mismatched. Both findings emit; rule 2's wording focuses on rebalancing the under-utilised reservation, rule 4's wording focuses on re-scoping so the existing reservation reaches the sibling spend. **Different remediations, both correct.** Rule 2's plan §2.4 explicitly endorses dual-fire framing. | **Disjoint by signal.** Rule 2 reads `utilization_pct` + sibling spend; rule 4 reads `applied_scope_subscription_ids` partition + sibling spend. Different fields drive each gate. **Rule 4 RESOLVES rule 2's E11 over-count limitation as a side-effect** by exposing the owner-sub list -- a future amendment to rule 2 can exclude owner subs from its sibling tally. That amendment is out of scope for this PR (one rule, one PR); see §3.15 cross-cutting decision 4. |
| `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3, MERGED PR #86 plan, impl assigned to Diego) | `expiry_date` within 60 days AND `auto_renew == False` | Yes -- a Single-scope reservation can be both scope-mismatched AND near expiry. Both findings emit; the operator gets two complementary recommendations ("re-scope" + "decide on renewal"). | **Disjoint by signal.** Rule 3 reads `expiry_date` + `auto_renew`; rule 4 reads `applied_scope_subscription_ids` + spend partition. Different fields. |
| `AZ.RESERVATION_UNDERUTILIZED` (existing, `azure_rules.py:163-190`) | `utilization_pct < 80%` | Yes -- same logic as rule 2 above. Complementary. | **Disjoint by signal.** Different field. |
| `AZ.AHB_ELIGIBLE` (rule 5, FUTURE) | License posture (Linux vs Windows) on `AzureResource.os_type` / `license_type` (schema fields not yet on main) | Independent. Rule 5's gate is about Hybrid Benefit eligibility on individual resources; it does not consult reservation scope. | **Disjoint by model field** (planned). |

**Stage-4 reviewer:** do not request consolidation across these rules. The cross-rule independence -- "same reservation, multiple complementary findings" -- is what makes the playbook useful. Rule 4's specific contribution is the scope-rebalance lever; it does not subsume the others.

### 2.5 Conservative recommendation wording (drafted)

> "Reservation `{principal}` is Single-scope (owner subs: `{owner_subs}`) but `${non_owner_spend_usd}/mo` of compatible on-demand spend is in subs the reservation cannot cover (`{sibling_subs}`). Verify the SKU compatibility and the billing-scope alignment, then consider re-scoping the reservation to Shared so the existing commitment can absorb the sibling on-demand spend. If re-scoping is not appropriate (cross-billing-scope, chargeback boundary, or the sibling workload is intentionally separated), capture the rationale and review again at next renewal."

Verb-conservative ("verify ... then consider ... if not appropriate ... capture ... review"); names two operator-side checks (SKU compatibility, billing-scope alignment); never says "re-scope" / "widen" / "change" as imperatives. Matches rule 1, rule 2, rule 3 voice; matches `AZ.RESERVATION_UNDERUTILIZED` register.

### 2.6 Security implications

- **No new scope.** `Reservation Reader` (or `Reader` on the reservation order) is implicit in the existing ARM collector audience; `_ARM_SCOPES` at `arm_collector.py:31` is unchanged.
- **PII redaction posture.** The rule emits `principal = ctx.redact(reservation.reservation_id)` and **also redacts every owner-sub and sibling-sub identifier** that appears in `Finding.principal`, the rendered template, and the evidence dict. **`ctx.redact()` call sites in §3.5: SIX total** -- one for `Finding.principal`, one for `principal` arg to `render`, one collection comprehension for the owner-sub list arg to `render`, one collection comprehension for the sibling-sub list arg to `render`, one collection comprehension for the owner-sub list in evidence, one collection comprehension for the sibling-sub list in evidence. Stage-4 reviewer counts call sites in the diff and rejects if any of the six is missing. **This mirrors rule 2's four-call-site precedent (`docs/plans/059-az-commitment-under-covered.md` §3.5) and extends it to two-list-of-IDs symmetry.**
- **No third-party copyrighted material.** All numbers come from the operator's own tenant data (`scope`, `applied_scope_subscription_ids`, `subscription_id`, `monthly_cost_usd` are operator-owned). The Microsoft Learn URL is linked, never copied.

### 2.7 Alternatives considered (rejected)

- **(R1) Reuse `AzureReservation.scope` field by overloading it to be a pipe-separated list ("`single|sub-001|sub-002`").** Rejected: bakes a parser into every consumer, breaks the existing `scope: str | None` contract for all current operators (legacy CSVs would become invalid the moment the rule starts splitting on `|`), and conflates two semantically distinct values (discriminator + identifier list) into one field. The strict-column loader's `list[str]` handler at `csv_collector.py:103-104` already exists for the orthogonal use case; introducing a new field is the lower-risk path.
- **(R2) Add a new `AzureReservationScope` model** with `(reservation_id, scope_kind, subscription_ids)` and a `list[AzureReservationScope]` field on `NormalizedDataset`. Rejected: that is a 1-to-1 relation to `AzureReservation`, so the join overhead is purely overhead. Inline fields on `AzureReservation` give the same expressive power with no extra model and no extra CSV file.
- **(R3) Add TWO fields: `applied_scope_type: Literal["Single", "Shared", "ManagementGroup"] | None` AND `applied_scope_subscription_ids: list[str] | None`.** Rejected for THIS PR: the existing `scope: str | None` field already stores `appliedScopeType` per `arm_collector.py:690`. Adding a typed `applied_scope_type` creates a second source of truth for the same value; either the collector populates both (drift risk) or only the new one (legacy-CSV breakage). The cleaner refactor -- rename `scope` -> `applied_scope_type` in a follow-up issue -- belongs to a separate model-cleanup PR (out of scope here). V1 of rule 4 reads `scope` defensively (`(reservation.scope or "").strip().lower()`) and accepts the misleading legacy field name. **Stage-4 reviewer: steelman this rejection** -- is the per-PR cleanliness of one new field worth the lasting field-name confusion? My answer is yes (one rule, one PR cadence; cleanup is its own concern), but I want it on the record.
- **(R4) Add SKU-family compatibility check** so the rule only counts sibling spend in compatible families. Rejected for V1: there is no SKU-family taxonomy in the codebase today; building one is a multi-week effort and conflates two epics (rule 4 and a hypothetical SKU-family normalisation epic). Rule 1, rule 2, rule 3, and `AZ.RESERVATION_UNDERUTILIZED` all defer SKU-compat to operator verification; V1 of rule 4 follows the same posture. Future enhancement, separate issue.
- **(R5) Add a "Shared scope could be Single for billing visibility" sub-case** as the epic body suggested. Rejected per Correction A (§1.4): re-scoping Shared -> Single does NOT save money; it only narrows where the discount lands. The signal could be useful for chargeback / cost-allocation use cases but is not a savings rule. If operators ask, ship it as a separate `info`-severity rule in a separate issue (a follow-up, not blocking this PR).
- **(R6) Cross-reference `AzureResource.subscription_offer` ("Pay-As-You-Go" / "Dev/Test" / "EA") to suppress dev/test siblings.** Rejected for V1: `subscription_offer` is populated only when the live ARM collector runs (see `arm_collector.py:497`); CSV-mode operators rarely populate it. Filtering on a frequently-absent signal would over-suppress findings for the majority of operators. Future enhancement once the field is reliably populated.
- **(R7) Compute on-demand spend per `(subscription_id, sku_family)` and use that as the sibling-spend signal**, instead of the per-sub `monthly_cost_usd` aggregate. Rejected for V1: the current `AzureResource` rows do not carry SKU family in a normalised way; rolling up `sku` to `sku_family` requires the same taxonomy R4 rejected. V1 uses per-sub `monthly_cost_usd` aggregation (the same join surface rule 2 uses), which over-counts on SKU mismatch -- mitigated by the recommendation's explicit "verify the sibling's on-demand SKUs are compatible" wording.

---

## Section 3: Stage-3 Plan (Maya, Opus 4.7)

### 3.1 Files touched

```
docs/plans/059-az-reservation-scope-mismatch.md          (this file, plan PR only)
docs/plan.md                                              (impl PR: §6 add one line)
docs/rules.md                                             (impl PR: regen by scripts/generate_docs.py)
docs/schema.md                                            (impl PR: note the new AzureReservation field)
src/finops_assess/models.py                               (impl PR: +1 field on AzureReservation, docstring update)
src/finops_assess/collectors/arm_collector.py             (impl PR: +1 dict key in row builder, +1 column in header)
src/finops_assess/rules_impl/azure_rules.py               (impl PR: +1 rule registration ~50 LOC)
src/finops_assess/data/rules/azure.yaml                   (impl PR: +1 rule entry, packaged mirror)
src/finops_assess/data/playbooks/azure/AZ.RESERVATION_SCOPE_MISMATCH.j2  (impl PR: NEW playbook template, LF-pinned)
data/rules/azure.yaml                                     (impl PR: +1 rule entry, source mirror)
samples/azure_reservations.csv                            (impl PR: +1 column, populate fires-row)
samples/azure_resources.csv                               (impl PR: +1 sibling-sub row to make rule fire on synthetic tenant)
tests/test_az_reservation_scope_mismatch.py               (impl PR: NEW, ~14 cases per §3.8)
tests/test_engine.py                                      (impl PR: extend REQUIRED_RULES at line 23)
tests/test_csv_collector.py                               (impl PR: extend round-trip + legacy-CSV backward-compat case)
examples/demo-report.{json,html,csv}                      (impl PR: regen)
examples/demo-triage.{json,csv}                           (impl PR: regen)
examples/playbook.jsonl{,.manifest.json}                  (impl PR: regen)
examples/focus-aligned.csv{,.manifest.json}               (impl PR: regen)
CHANGELOG.md                                              (impl PR: one-line entry)
```

**This plan PR ships only `docs/plans/059-az-reservation-scope-mismatch.md`.** Implementation files land in the sibling impl PR.

### 3.2 Schema, `src/finops_assess/models.py`

Extend `AzureReservation` (`models.py:236-251`):

```python
class AzureReservation(BaseModel):
    """A normalised Azure Reservation / Savings Plan snapshot.

    ``utilization_pct`` is the average utilization over the trailing 30 days
    (0-100). Rules abstain when the signal is absent rather than assuming
    zero utilization.

    ``scope`` carries the API's ``appliedScopeType`` discriminator string
    (``"Single"`` / ``"Shared"`` / ``"ManagementGroup"``, case-insensitive
    in CSV mode). The field name is a legacy from the M5 Azure rules; a
    future issue may rename it to ``applied_scope_type``.

    ``applied_scope_subscription_ids`` is the operator-owned list of
    subscription ARNs the discount is applied to (``Microsoft.Capacity``
    reservations API ``properties.appliedScopes``). ``None`` means the
    signal is absent (CSV-mode operators may leave the column blank);
    ``AZ.RESERVATION_SCOPE_MISMATCH`` abstains on ``None``. An empty list
    on a ``Single``-scope row is contradictory; the rule logs WARN and
    abstains on that row.
    """

    model_config = ConfigDict(extra="forbid")

    reservation_id: str = Field(..., min_length=1)
    reservation_name: str | None = None
    sku: str | None = None
    scope: str | None = None
    utilization_pct: float | None = Field(default=None, ge=0, le=100)
    monthly_cost_usd: float | None = Field(default=None, ge=0)
    applied_scope_subscription_ids: list[str] | None = None
```

`extra="forbid"` is preserved (hard rule + binding norm #9). The existing fields keep their definitions verbatim.

**If rule 3's impl PR has merged before rule 4's impl PR**, rule 3's two new fields (`expiry_date`, `auto_renew`) appear in the model between `monthly_cost_usd` and `applied_scope_subscription_ids`; rule 4's impl PR resolves the textual conflict by preserving rule 3's fields and appending its own. **No semantic conflict** (different fields, different rules). If rule 4's impl PR merges first, rule 3 follows the same pattern.

`NormalizedDataset.azure_reservations` (`models.py:412`) is **unchanged** -- the same list field carries the extended row.

### 3.3 CSV collector, `src/finops_assess/collectors/csv_collector.py`

**No code change required.** The strict-column loader at `csv_collector.py:54-107` already handles `list[str]` columns:

- Empty cell -> `None` (default), per the docstring at lines 59-63.
- Non-empty cell -> split on `|`, strip each item, drop empties (line 103-104).

The docstring at `csv_collector.py:9` (`* ``azure_reservations.csv`` -- :class:`AzureReservation` fields.`) is already accurate -- it points at the model, which now declares the new field. **No docstring update needed.**

Backward compatibility for legacy `azure_reservations.csv` (no `applied_scope_subscription_ids` column): missing column -> `csv.DictReader` returns `None` for the key -> strict-column loader skips it (`csv_collector.py:80-83`) -> pydantic field default applies -> `applied_scope_subscription_ids = None`. **Rule abstains on legacy CSVs (E4).** Tested by §3.8 test #15(b).

### 3.4 ARM collector, `src/finops_assess/collectors/arm_collector.py`

Two localised changes:

1. **Read `props.get("appliedScopes")` and serialise as pipe-separated** in the reservation row builder. Edit the dict literal at `arm_collector.py:685-694`:

   ```python
   reservation_rows.append(
       {
           "reservation_id": rid,
           "reservation_name": props.get("displayName") or "",
           "sku": sku_info.get("name") or "",
           "scope": props.get("appliedScopeType") or "",
           "utilization_pct": "" if util is None else str(round(float(util), 2)),
           "monthly_cost_usd": "",
           "applied_scope_subscription_ids": _scope_ids_to_csv(props.get("appliedScopes")),
       }
   )
   ```

2. **Add a tiny helper** for the list-to-CSV-cell conversion (private to `arm_collector.py`):

   ```python
   def _scope_ids_to_csv(value: object) -> str:
       """Render the API's appliedScopes list as a pipe-separated CSV cell.

       The strict-column CSV loader expects ``list[str]`` columns to be
       pipe-separated single cells (``csv_collector.py:103-104``). ``None``
       maps to the empty string (signal absent on Shared scope or when the
       API returned no list); a non-empty list maps to ``"|"``-joined ARNs.
       """
       if value is None:
           return ""
       if isinstance(value, list):
           items = [str(item).strip() for item in value if str(item).strip()]
           return "|".join(items)
       return ""
   ```

3. **Extend the CSV header** at `arm_collector.py:719-730` (the `_write_csv` call for `azure_reservations.csv`) to add one column at the end:

   ```python
   _write_csv(
       output_dir / "azure_reservations.csv",
       [
           "reservation_id",
           "reservation_name",
           "sku",
           "scope",
           "utilization_pct",
           "monthly_cost_usd",
           "applied_scope_subscription_ids",
       ],
       reservation_rows,
   )
   ```

**No new `_API_VERSIONS` entry, no new `_ARM_SCOPES` entry.** The api-version `2022-11-01` (`arm_collector.py:40`) already returns `appliedScopes` (verified against Microsoft Learn in §1.1).

**Coordination with rule 3's impl:** if rule 3's impl lands first, the row builder dict will already contain `expiry_date` and `auto_renew` keys, the header will already contain those columns, and the helper module will already define `_renew_to_str`. Rule 4's impl appends `applied_scope_subscription_ids` after; the diffs commute.

### 3.5 Rule implementation, `src/finops_assess/rules_impl/azure_rules.py`

Add at the end of the file (after `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` at line 300; line numbers from `main` SHA `a549a1d`):

```python
# ---------------------------------------------------------------------------
# AZ.RESERVATION_SCOPE_MISMATCH
# ---------------------------------------------------------------------------
import logging
from collections import defaultdict

_RESERVATION_SCOPE_MIN_NON_OWNER_USD = 50.0
_logger = logging.getLogger(__name__)


@register("AZ.RESERVATION_SCOPE_MISMATCH")
def reservation_scope_mismatch(ctx: RuleContext) -> Iterable[Finding]:
    """Flag Single-scope reservations with material on-demand spend in non-owner subs."""
    threshold = ctx.rule.min_uncovered_usd or _RESERVATION_SCOPE_MIN_NON_OWNER_USD

    # Pre-aggregate per-sub on-demand spend once (used for every reservation).
    spend_by_sub: dict[str, float] = defaultdict(float)
    for resource in ctx.dataset.azure_resources:
        if resource.subscription_id is None:
            continue
        if resource.monthly_cost_usd is None:
            continue
        spend_by_sub[resource.subscription_id] += resource.monthly_cost_usd
    if not spend_by_sub:
        return  # E6

    for reservation in ctx.dataset.azure_reservations:
        scope_norm = (reservation.scope or "").strip().lower()
        if scope_norm == "":
            continue  # E2
        if scope_norm != "single":
            continue  # E3 (V1 fires only on Single-scope per Correction A in plan §1.4)
        if reservation.applied_scope_subscription_ids is None:
            continue  # E4
        if not reservation.applied_scope_subscription_ids:
            _logger.warning(
                "AZ.RESERVATION_SCOPE_MISMATCH: reservation %s is Single-scope but "
                "applied_scope_subscription_ids is empty; abstaining",
                reservation.reservation_id,
            )
            continue  # E5

        owner_subs = set(reservation.applied_scope_subscription_ids)
        non_owner_total = 0.0
        sibling_subs: list[str] = []
        for sub_id, sub_spend in spend_by_sub.items():
            if sub_id in owner_subs:
                continue
            if sub_spend <= 0.0:
                continue
            non_owner_total += sub_spend
            sibling_subs.append(sub_id)

        if not sibling_subs:
            continue  # E7
        if non_owner_total < threshold:
            continue  # E8

        owner_sub_list = sorted(owner_subs)
        sibling_subs_sorted = sorted(sibling_subs)
        redacted_owner_subs = [ctx.redact(s) for s in owner_sub_list]
        redacted_sibling_subs = [ctx.redact(s) for s in sibling_subs_sorted]
        non_owner_total_rounded = round(non_owner_total, 2)

        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(reservation.reservation_id),
            current_sku=reservation.sku,
            estimated_monthly_savings_usd=non_owner_total_rounded,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(reservation.reservation_id),
                owner_subs=", ".join(redacted_owner_subs),
                sibling_subs=", ".join(redacted_sibling_subs),
                non_owner_spend_usd=non_owner_total_rounded,
            ),
            evidence={
                "reservation_name": reservation.reservation_name,
                "sku": reservation.sku,
                "scope": reservation.scope,
                "owner_subscription_ids": redacted_owner_subs,
                "sibling_subscription_ids": redacted_sibling_subs,
                "non_owner_spend_usd": non_owner_total_rounded,
                "utilization_pct": reservation.utilization_pct,
                "monthly_cost_usd": reservation.monthly_cost_usd,
            },
        )
```

**SIX `ctx.redact(...)` call sites** (counted above per §2.6): `Finding.principal`, `principal` arg to `render`, two list comprehensions for owner/sibling subs to render args, two list-comprehension references in evidence (the `redacted_owner_subs` / `redacted_sibling_subs` variables are re-used to keep the single redaction symmetric across template args and evidence). Stage-4 reviewer: confirm by reading the diff.

`estimated_monthly_savings_usd` carries `non_owner_total_rounded` -- the projected savings if the reservation were widened to absorb the sibling on-demand spend (assuming SKU compatibility holds). Mirrors rule 2's `_round(sibling_spend)` precedent (`docs/plans/059-az-commitment-under-covered.md` §3.5). Same caveat: the value is an UPPER BOUND, not a guarantee; the recommendation_template's "verify the SKU compatibility" gate names this explicitly.

The `defaultdict(float)` pre-aggregation is O(R) over `azure_resources`; the outer reservation loop is O(N) over `azure_reservations`; the inner `spend_by_sub.items()` loop is O(S) per reservation. Total: O(R + N*S) where S is "distinct subs in the dataset". For typical operators (R ~10k, N ~100, S ~20), this is well within the engine's per-rule budget.

`logging` import goes at the top of the module per ruff `I` rule; the `from collections import defaultdict` import stays grouped with other stdlib imports. The threshold constant is module-private (underscore-prefixed) per the repo convention.

### 3.6 YAML rule entry, `data/rules/azure.yaml` (and packaged mirror)

Append to `data/rules/azure.yaml`:

```yaml
- id: AZ.RESERVATION_SCOPE_MISMATCH
  surface: azure
  severity: medium
  summary: Single-scope reservation with material on-demand spend in non-owner subs.
  recommendation_template: >
    Reservation {principal} is Single-scope (owner subs: {owner_subs}) but
    ${non_owner_spend_usd}/mo of compatible on-demand spend is in subs the
    reservation cannot cover ({sibling_subs}). Verify the SKU compatibility
    and the billing-scope alignment, then consider re-scoping the reservation
    to Shared so the existing commitment can absorb the sibling on-demand
    spend. If re-scoping is not appropriate (cross-billing-scope, chargeback
    boundary, or the sibling workload is intentionally separated), capture
    the rationale and review again at next renewal.
  min_uncovered_usd: 50.0
```

`min_uncovered_usd: 50.0` reuses the existing `Rule.min_uncovered_usd` field (defined on `Rule` per `models.py`; same field rule 2 uses for its sibling-spend threshold). No new YAML schema field needed. Rule body reads `ctx.rule.min_uncovered_usd or 50.0` as the default fallback.

Severity choice: `medium`. Rationale: real-money lever (a Single-scope reservation leaking sibling on-demand spend is a cost burn the operator can stop), but not a critical alert. Same tier as `AZ.COMMITMENT_UNDER_COVERED` (rule 2), `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3), and `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1). Not `high` (no immediate outage risk), not `low` (decision is genuinely material).

**Sync the packaged mirror** at `src/finops_assess/data/rules/azure.yaml` in the same commit (catalogue YAML is shipped with the wheel; the mirror must stay byte-equal). Pattern reference: rule 1 plan §3.6, rule 2 plan §3.6, rule 3 plan §3.6.

### 3.7 Producer-path citations (BINDING per post-PR-#78 norm)

Every claim this rule makes about a value is anchored to the producer code path that establishes the value, on `main` SHA `a549a1d`. Stage-4 reviewers reject the plan if any cell below is wrong.

| Claim | Producer (file:line) | What the producer does |
|---|---|---|
| `principal` is salted-hashed by default | `src/finops_assess/engine.py:70-75` (`RuleContext.redact`) | `if redact_pii: return f"sha256:{sha256(salt+':'+principal)[:16]}"`. The rule MUST call `ctx.redact(...)` SIX times in §3.5 (Finding.principal, render arg `principal`, render arg `owner_subs` via list comprehension, render arg `sibling_subs` via list comprehension, evidence `owner_subscription_ids` via reused list, evidence `sibling_subscription_ids` via reused list). |
| `principal` is **not stable across runs** with default redaction | `src/finops_assess/engine.py:151` (`run_rules`) | `salt_value = salt if salt is not None else secrets.token_hex(16)`. The CLI does not flow a stable salt today. Per-run salt instability is the existing Azure-surface posture; no new reporter contract is introduced by this rule. Issue #73 is the engine-level fix; this plan does not block on it. |
| `principal` is the **reservation ARM ID**, not a user identifier | `src/finops_assess/models.py:246` (`reservation_id: str`) and `azure_rules.py:175` (`AZ.RESERVATION_UNDERUTILIZED` precedent) | Same convention: reservation ID is treated as a redactable principal even though it is not user-PII, because the rule pipeline treats every `principal` as redactable. |
| `scope` field already stores the `appliedScopeType` **discriminator string** (NOT an ARN) | `src/finops_assess/collectors/arm_collector.py:690` (`"scope": props.get("appliedScopeType") or ""`) | The producer writes the API's `appliedScopeType` enum string ("Single" / "Shared" / "ManagementGroup") into the `scope` column. The rule consumes it via `(reservation.scope or "").strip().lower()` to handle the lower-cased samples convention (`samples/azure_reservations.csv:2-3`). **Disambiguation pattern from PR #85 stage-4 lockout: discriminator is `appliedScopeType` (already in `scope` field); the actual identifier list is `appliedScopes` (this plan adds `applied_scope_subscription_ids`).** |
| `applied_scope_subscription_ids` is a tri-state list (`None` / `[]` / non-empty) | This plan adds `applied_scope_subscription_ids: list[str] | None = None` on `AzureReservation` | `None` semantics are "signal absent" -- abstain (E4). `[]` on a `Single`-scope row is contradictory -- WARN + abstain (E5). Non-empty -- partition spend by owner vs non-owner. Same abstain posture as `utilization_pct is None` at `azure_rules.py:167-168`. |
| The ARM collector's reservation list endpoint already returns `appliedScopes` at api-version `2022-11-01` | `src/finops_assess/collectors/arm_collector.py:40` (`"reservations": "2022-11-01"`) and `arm_collector.py:243-252` (`_collect_reservations`) | The endpoint URL is already correct; the row builder at `arm_collector.py:670-694` only needs to read one more `props.get(...)` key (`appliedScopes`). No new API call, no new scope. Verified against Microsoft Learn in §1.1. |
| The ARM collector uses **read-only** scopes | `src/finops_assess/collectors/arm_collector.py:31` (`_ARM_SCOPES = ["https://management.azure.com/.default"]`) | This plan does not modify `_ARM_SCOPES`. Hard rule #1 upheld. |
| Reservation row builder pattern this implementation extends | `src/finops_assess/collectors/arm_collector.py:685-694` | Existing dict literal writes `scope` from `appliedScopeType` (line 690); this plan adds one key (`applied_scope_subscription_ids`) sourced from `props.get("appliedScopes")` via the new `_scope_ids_to_csv` helper. |
| CSV header for `azure_reservations.csv` | `src/finops_assess/collectors/arm_collector.py:719-730` | This plan adds one column at the end: `applied_scope_subscription_ids`. Order matters because `_write_csv` writes a header row in the order given. |
| CSV strict-column loader is backward-compatible for new optional fields | `src/finops_assess/collectors/csv_collector.py:54-107` (`_coerce_row`), specifically the docstring at lines 59-63 | Rows with fewer cells than the header default missing keys to `None`. Legacy `azure_reservations.csv` files (no `applied_scope_subscription_ids` column) load unchanged; the rule abstains on those rows (E4). |
| CSV strict-column loader handles `list[str]` columns via pipe-separated single cells | `src/finops_assess/collectors/csv_collector.py:103-104` | `if "list" in annotation_str: out[key] = [item.strip() for item in value.split("|") if item.strip()]`. The new column uses this loader path; the new `_scope_ids_to_csv` helper in §3.4 emits `"|"`-joined ARNs to match. Empty cell short-circuits at line 88-91 (use field default) -> `None`. |
| Rule abstain pattern when signal is absent | `src/finops_assess/rules_impl/azure_rules.py:167-168` (`AZ.RESERVATION_UNDERUTILIZED`) | Precedent: `if reservation.utilization_pct is None: continue`. Rule 4's body at §3.5 mirrors this for `scope is None/empty`, `scope != "single"`, and `applied_scope_subscription_ids is None`. |
| `Rule.min_uncovered_usd` field carries the dollar-floor idiom | `src/finops_assess/models.py:Rule` definition + rule 2's plan §3.6 (`min_uncovered_usd: 50.0`) | Same field reused for rule 4's non-owner-spend threshold. No new YAML schema field. |
| Per-sub spend pre-aggregation is consistent with rule 2's join surface | `docs/plans/059-az-commitment-under-covered.md` §3.5 (rule 2's spend-by-sub aggregation) | Rule 4 reuses the `(subscription_id, monthly_cost_usd)` join surface rule 2 documented; both rules read the same source-of-truth columns on `AzureResource`. |
| `Finding.evidence` is a free-form dict surfaced verbatim by reporters | `src/finops_assess/models.py:Finding` definition + `src/finops_assess/reporters/json_reporter.py` | All evidence values in §3.5 are non-PII numerical values, API-derived strings, booleans, OR lists of `ctx.redact(...)`-wrapped IDs. Owner/sibling sub IDs in evidence MUST be redacted (per §2.6); see test #11. |
| Yuki-net pattern (real `run_rules` engine, NOT mocked rule callable) | `tests/test_playbook_cross_run_stability.py:1-80` | Test #12 in §3.8 mirrors this pattern. Caught BLOCKING #1 in PR #78 and is the binding norm for all rule e2e tests. |

If any of these citations is wrong at implementation time, the implementer flags it back to Maya and the plan is amended -- never silently overridden (§11 ground rule).

### 3.8 Test plan

| # | Test name | File | Asserts |
|---|---|---|---|
| 1 | `test_scope_mismatch_fires_on_single_scope_with_sibling_spend` | `tests/test_az_reservation_scope_mismatch.py` | One Single-scope reservation with `applied_scope_subscription_ids=["sub-A"]`, one resource in `sub-B` with `monthly_cost_usd=200` -> exactly one finding with `rule_id="AZ.RESERVATION_SCOPE_MISMATCH"` and `severity="medium"` and `estimated_monthly_savings_usd=200.0`. |
| 2 | `test_scope_mismatch_abstains_when_scope_missing` | same | `scope=None` -> no finding (E2). |
| 3 | `test_scope_mismatch_abstains_on_shared_scope` | same | `scope="Shared"` -> no finding (E3); confirms Correction A (§1.4). |
| 4 | `test_scope_mismatch_abstains_on_managementgroup_scope` | same | `scope="ManagementGroup"` -> no finding (E3). |
| 5 | `test_scope_mismatch_abstains_when_scope_subs_unknown` | same | `scope="Single"`, `applied_scope_subscription_ids=None` -> no finding (E4). |
| 6 | `test_scope_mismatch_warns_on_empty_single_scope_list` | same | `scope="Single"`, `applied_scope_subscription_ids=[]` -> no finding + WARN log captured (E5). |
| 7 | `test_scope_mismatch_abstains_when_no_resources_have_cost_data` | same | All resources have `monthly_cost_usd=None` -> no finding (E6). |
| 8 | `test_scope_mismatch_abstains_when_all_spend_in_owner_subs` | same | Resources only in owner subs -> no finding (E7). |
| 9 | `test_scope_mismatch_abstains_below_threshold` | same | Sibling spend `$25/mo` (< $50 threshold) -> no finding (E8). |
| 10 | `test_scope_mismatch_one_finding_per_reservation` | same | Two Single-scope reservations both have sibling spend -> two findings (E10). |
| 11 | `test_scope_mismatch_redacts_principal_and_sub_ids` | same | With `redact_pii=True` (default): `finding.principal.startswith("sha256:")`, every entry in `evidence["owner_subscription_ids"]` and `evidence["sibling_subscription_ids"]` starts with `"sha256:"`, and the `recommendation` text contains no raw sub-ID substring. **Cites `engine.py:70-75` in the test docstring.** |
| 12 | `test_scope_mismatch_e2e_through_run_rules` | same | End-to-end regression: build `NormalizedDataset` with one fires-row + one abstains-row, call real `run_rules(...)`, assert exactly one finding. **Pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`** -- uses real engine, not a mocked rule callable. Yuki-net invariant from PR #78. |
| 13 | `test_scope_mismatch_co_fires_with_underutilized` | same | One Single-scope reservation: `utilization_pct=40`, `applied_scope_subscription_ids=["sub-A"]`, `$200/mo` sibling spend in `sub-B` -> two findings (one `AZ.RESERVATION_UNDERUTILIZED`, one `AZ.RESERVATION_SCOPE_MISMATCH`). Pins the §2.4 disjoint-by-signal claim. |
| 14 | `test_scope_mismatch_emits_cleartext_with_redaction_off` | same | With `redact_pii=False`, `finding.principal == reservation.reservation_id` exactly AND `evidence["owner_subscription_ids"]` contains the raw sub-IDs. Symmetry with test #11. |
| 15 | extend `tests/test_engine.py:REQUIRED_RULES` (line 23) AND `tests/test_csv_collector.py` | `tests/test_engine.py`, `tests/test_csv_collector.py` | (a) Add `"AZ.RESERVATION_SCOPE_MISMATCH"` to the `REQUIRED_RULES` set so the synthetic-tenant smoke test asserts the rule is registered. (b) Round-trip `azure_reservations.csv` with the new column populated as `"sub-A|sub-B"`. (c) Round-trip a legacy `azure_reservations.csv` WITHOUT the new column; assert all rows load with `applied_scope_subscription_ids=None`. Backward-compat invariant. |

**Fixtures:** all synthetic rows constructed in-test (no on-disk fixture files required for tests 1-14). The on-disk `samples/azure_reservations.csv` and `samples/azure_resources.csv` are for `finops-assess run --inputs samples/` and the demo-report regen.

### 3.9 Doc regen

The implementer runs `python scripts/generate_docs.py` once and commits **all** regenerated artefacts in the same PR:

- `docs/rules.md` -- auto-generated from `data/rules/azure.yaml`. Will gain a new entry for `AZ.RESERVATION_SCOPE_MISMATCH`.
- `examples/demo-report.{json,html,csv}` -- will gain a finding row if the demo dataset includes a Single-scope reservation with sibling spend. The implementer updates `samples/azure_reservations.csv` to populate `applied_scope_subscription_ids` on the existing `ri-002` row (Single-scope) AND adds a sibling-sub `azure_resources.csv` row with `monthly_cost_usd >= $50` so the rule fires deterministically (§3.11 below).
- `examples/demo-triage.{json,csv}` -- same.
- `examples/playbook.jsonl{,.manifest.json}` -- same; the playbook reporter renders any rule with a registered `.j2` template. **A new template** `src/finops_assess/data/playbooks/azure/AZ.RESERVATION_SCOPE_MISMATCH.j2` is required (LF-pinned by `.gitattributes` rule `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`). Template body is a paraphrase of the recommendation; no new schema.
- `examples/focus-aligned.csv{,.manifest.json}` -- the FOCUS-aligned exporter is Azure-only today and will pick up the new finding automatically; bytes regenerate.

`python scripts/generate_docs.py --check` is the docs-freshness gate (`.github/workflows/docs.yml`); it WILL fail without the regen commit.

### 3.10 `data/personas.yaml` impact

**None.** Personas inherit licensing rules (`M365.*` and `GH.COPILOT_*`). Cost-discipline rules like `AZ.*` apply to resources, not user identities. Same posture as every existing `AZ.*` rule. No `data/personas.yaml` change in this PR.

### 3.11 `samples/azure_reservations.csv` and `samples/azure_resources.csv`

Add `applied_scope_subscription_ids` column to `samples/azure_reservations.csv`. Existing row at line 3 (`ri-002`, `single`, `92.0%`) is well-suited: lower the utilisation to ~50% so it does NOT trigger `AZ.RESERVATION_UNDERUTILIZED`'s 80% gate (kept clear) but still satisfies rule 4's gate via the scope mismatch:

```
reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd,applied_scope_subscription_ids
/subscriptions/00000000/providers/Microsoft.Capacity/reservationOrders/ro-001/reservations/ri-001,RI-VM-D4s-EastUS,Standard_D4s_v5,shared,45.0,500.00,
/subscriptions/00000000/providers/Microsoft.Capacity/reservationOrders/ro-002/reservations/ri-002,RI-SQL-WestUS,GP_Gen5_8,single,82.0,800.00,/subscriptions/sub-owner-001
```

Row 1 abstains (Shared scope, E3). Row 2 fires only if a sibling-sub resource exists with `monthly_cost_usd >= $50`. The implementer adds one row to `samples/azure_resources.csv`:

```
res-sib-001,virtualMachine,Standard_D2s_v5,eastus,,,,,,,,,200.00,,/subscriptions/sub-sibling-001,,
```

(field order matches the existing `azure_resources.csv` header at `arm_collector.py:697-718`; the implementer verifies the column count). Alternatively, retarget an existing resource row to `subscription_id=sub-sibling-001` and `monthly_cost_usd=200.00`. Implementer's call.

**Co-fire interaction with rule 2's synthetic tenant change:** rule 2's plan §3.11 adjusted `samples/azure_reservations.csv` to ensure `ri-001` triggers `AZ.COMMITMENT_UNDER_COVERED`. Rule 4's change to `ri-002` is orthogonal (different row). The implementer verifies the synthetic tenant fires both rules correctly after the change.

### 3.12 `docs/plan.md` §6 update

Add to the Azure rules block (after `AZ.COMMITMENT_RENEWAL_REVIEW` once that lands, OR alphabetically near the other reservation rules):

```
- `AZ.RESERVATION_SCOPE_MISMATCH`: Single-scope reservation with material on-demand spend in non-owner subs.
```

Keep the §6 entry one line; the full rule body is `docs/rules.md` (auto-generated).

### 3.13 `docs/schema.md` update

Add a note for the new `AzureReservation.applied_scope_subscription_ids` field. The schema doc tracks every field on the normalised models; this is required by `.github/copilot-instructions.md` ("Documentation updates" section: "schemas" is enumerated).

### 3.14 Out of scope (and why)

- **Rule 2 amendment to consume `applied_scope_subscription_ids`** so rule 2's E11 over-count goes away. Belongs to a follow-up issue (one rule per PR; rule 2's impl is in flight on PR #88 and an in-flight schema-consumer change would force a stage-3 amendment). When the follow-up lands, rule 2 reads `reservation.applied_scope_subscription_ids` (if not None) and excludes owner subs from its sibling tally; behaviour for legacy CSVs (field == None) is unchanged. **File the issue at impl time.**
- **`applied_scope_type: Literal["Single", "Shared", "ManagementGroup"]` typed-discriminator field.** Belongs to a separate model-cleanup issue (R3 in §2.7). V1 reads the loosely typed `scope` field defensively.
- **SKU-family compatibility check.** R4 in §2.7. Out of scope for V1; same posture as `AZ.RESERVATION_UNDERUTILIZED` and rule 2.
- **`AzureResource.subscription_offer` based dev/test sibling suppression.** R6 in §2.7. Out of scope for V1.
- **"Shared could be Single" billing-visibility sub-case.** R5 in §2.7 + Correction A in §1.4. Not a savings rule; out of scope for the cost-savings playbook.
- **Live ARM call against a real tenant.** Stage 5 is unit + e2e with synthetic data. Live verification is the operator's job at `finops-assess run --collector arm`; the test plan does not require a live call.
- **Rule 5 (`AZ.AHB_ELIGIBLE`).** Gets its own stage-3 plan; will need `AzureResource.os_type` + `license_type` (larger schema change).

### 3.15 Cross-cutting decisions worth flagging

1. **One new schema field on an existing model**, not a new model and not a renamed field. Confirmed in §1.4 Correction B + §3.2. The Scribe should canonicalise this so the next "do we add a field, a model, or rename?" question can short-circuit.
2. **The "scope mismatch" question resolves to a first-class API field (`appliedScopes`)**, not a heuristic. Confirmed in §1.4 Correction B + §1.1.
3. **Cross-rule isolation is disjoint by signal** (different fields drive each gate), not disjoint by gate (no exclusion logic between rules). Confirmed in §2.4. Co-firing with rule 2, rule 3, and `AZ.RESERVATION_UNDERUTILIZED` is desirable.
4. **Rule 4 RESOLVES rule 2's E11 over-count limitation as a side-effect** by exposing the owner-sub list. The cleanup amendment to rule 2 is **out of scope** for this PR but should be filed as a follow-up issue at impl time. Documented in §2.4 + §3.14.
5. **No new ARM scope, no new collector method, no new endpoint.** Confirmed in §1.1 + §3.4. The api-version `2022-11-01` already returns the field we need; we just read one more key from the existing response. Hard rule #1 upheld via `arm_collector.py:31` citation.
6. **No catalogue change.** Reservations are not catalogue SKUs (R5 / R7 in §2.7).
7. **No engine change.** The rule is a pure additive registration; `RuleContext` is consumed unchanged.
8. **Disambiguation pattern from PR #85 stage-4 lockout is operationalised in §1.1.** `appliedScopeType` (discriminator) and `appliedScopes` (identifier list) are named explicitly in a side-by-side table; the existing `scope` field's hidden-discriminator semantics are documented in §3.2 model docstring; the rule defensively normalises (`(reservation.scope or "").strip().lower()`).

---

## Section 4: Stage-4 ask (Noor, adversarial reviewer)

**Reviewer:** Noor (squad:noor), model **Opus 4.7** mandatory (per §11; never downgrade).

**Specific invariants Noor must verify (steelman against the plan, do not just agree):**

1. **Producer-path citations are correct.** Open every cell in §3.7 against the repo at `main` SHA `a549a1d`. Reject if any line number is wrong or any claim is not what the producer actually does. (This is the fourth consecutive stage-3 plan from Maya where this norm applies; the bar is "all cells correct or reject".) Particular focus: `arm_collector.py:690` (`"scope": props.get("appliedScopeType") or ""`) -- confirm the existing `scope` field really IS the discriminator string; the entire §1.1 disambiguation rests on this.
2. **Disambiguation pattern (§1.1) is sharp enough.** Independently verify against Microsoft Learn that `properties.appliedScopeType` (enum string) and `properties.appliedScopes` (list of ARNs) are the exact field names; reject if the API spec uses different names. Confirm the side-by-side table is unambiguous so a stage-5 implementer cannot mistake one for the other (the failure mode PR #85 stage-4 caught for rule 1).
3. **Stage-3 corrections (§1.4) are accurate.**
   - Correction A: independently verify that re-scoping Shared -> Single does NOT reduce reservation cost. If Microsoft Learn or Cost Mgmt docs contradict this, reject the V1 scoping.
   - Correction B: independently verify the existing `scope` field already stores `appliedScopeType` (`arm_collector.py:690`); confirm that adding a parallel `applied_scope_type` field (R3 in §2.7) is correctly rejected.
4. **Rule abstains on E1-E8 negative paths.** Walk each edge in §2.2 against the rule body in §3.5; assert the rule short-circuits via the documented gate. Specifically:
   - `scope is None or empty` -> abstain (E2).
   - `scope.lower() != "single"` -> abstain (E3).
   - `applied_scope_subscription_ids is None` -> abstain (E4).
   - `applied_scope_subscription_ids == []` (Single + empty list) -> WARN log + abstain (E5).
   - No `azure_resources` rows have `subscription_id` AND `monthly_cost_usd` -> abstain (E6).
   - All spend in owner subs -> abstain (E7).
   - Non-owner spend below threshold -> abstain (E8).
5. **Rule fires on E9 + E13 positive paths.** `scope == "single"` AND `applied_scope_subscription_ids` non-empty AND non-owner spend `>= $50/mo` -> exactly one finding per reservation. Co-fire with `AZ.RESERVATION_UNDERUTILIZED` is intentional (E13).
6. **Principal AND every sub-ID are redacted in BOTH the rendered template AND the evidence dict.** §3.5 has SIX `ctx.redact(...)` call sites (Finding.principal, render arg `principal`, render args for owner/sibling sub lists, evidence values for owner/sibling sub lists). Stage-4 reviewer counts call sites in the diff and rejects if any of the six is missing. **This is the exact failure mode PR #78 BLOCKING #1 caught (symmetry across `principal`, `recommendation`, and `evidence`); rule 4's two-list-of-IDs surface area extends the symmetry.**
7. **No new ARM scope.** §3.7 binds `arm_collector.py:31` as the citation. Confirm the implementation does NOT modify `_ARM_SCOPES`. **Hard rule #1.**
8. **No catalogue YAML change.** `data/catalog/azure/*.yaml` is untouched; the rule references no SKU id.
9. **End-to-end regression test (test #12) uses the real `run_rules` engine**, not a mocked rule callable. Yuki-net pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`. If the implementer drops it to a unit-only call, reject.
10. **Wording is conservative.** §3.6 uses "verify ... then consider ... if not appropriate ... capture ... review"; "re-scope", "widen", "change" do not appear as imperatives in the recommendation_template.
11. **`scripts/generate_docs.py --check` will pass post-implementation.** All of `docs/rules.md`, `examples/demo-report.*`, `examples/demo-triage.*`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`, and the new `.j2` playbook template are committed in the same PR.
12. **Cross-rule isolation invariants** (§2.4):
    - Co-firing with `AZ.RESERVATION_UNDERUTILIZED` is intentional and pinned by test #13.
    - Co-firing with `AZ.COMMITMENT_UNDER_COVERED` (rule 2) is intentional; no exclusion logic added to either rule.
    - Co-firing with `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3) is intentional; no exclusion logic added.
    - No collision with `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1, different model).
    - No collision with `AZ.AHB_ELIGIBLE` (rule 5, future, different field).
13. **Backward-compat invariant for the CSV strict-column loader** (test #15(c)): legacy `azure_reservations.csv` files without the new column must load with `applied_scope_subscription_ids=None`. Pinned by §3.7 citation `csv_collector.py:54-107`.
14. **Cleanup-amendment scope** (§3.14 + §3.15 #4): the rule 2 amendment that consumes `applied_scope_subscription_ids` is correctly OUT of scope for this PR; confirm the follow-up issue is filed (or instructed to be filed at impl time). Steelman: should the amendment ship in this PR to fully realise rule 4's value? My answer is no (one rule, one PR; rule 2's impl is in flight on PR #88 and a schema-consumer change would force a stage-3 amendment) -- Noor stress-tests.

If Noor returns `REQUEST_CHANGES` on any blocking item, the **Reviewer Rejection Lockout** protocol applies (Maya is locked out of revising her own plan; revision routes to a different agent -- likely Yuki or Diego, per PR #78 + PR #85 precedent).

**Verdict format (per `.github/copilot-instructions.md`):**

```
**Stage-4 Adversarial Review -- Noor**

VERDICT: APPROVE
(or VERDICT: REQUEST_CHANGES with numbered findings)
```

This triggers `.github/workflows/squad-approve.yml` and lets the PR merge through the documented async path.

---

## Section 5: Stage-5 plan (Diego primary, Yuki backup)

**Implementer:** Diego (Azure compute / storage / SQL / Cost Mgmt specialist). Diego owns:

- The new `AzureReservation.applied_scope_subscription_ids` field.
- The ARM collector additions (he has the pattern muscle from the existing `_collect_reservations`, the rule-1 implementation on PR #85, and the rule-2 implementation in flight on PR #88).
- The `_scope_ids_to_csv` helper.
- The rule registration.
- The packaged-mirror sync at `src/finops_assess/data/rules/azure.yaml`.
- The new `.j2` playbook template (LF-pinned).
- `docs/plan.md` §6 line-add and `docs/schema.md` field-add.
- `CHANGELOG.md` entry.
- All gates: validate, ruff, mypy, pytest, generate_docs --check.
- File the rule 2 cleanup follow-up issue at impl-PR open time (§3.14 + §3.15 #4).

**Backup:** Yuki (tester / quality / CI matrix owner). If Diego is at capacity from PR #85 follow-ups OR PR #88 stage-4 revisions, Yuki picks up; she will likely lean harder on tests #11 (six-redaction-site count) and #12 (e2e regression net) since those are the cross-rule contract probes. **Note:** Diego is NOT locked out for new work; PR #85's lockout was per-PR and has been released (PR #87 wrap canonicalised). Diego primary.

**Branch:** `squad/59-impl-reservation-scope-mismatch`. Open as draft, link this PR + issue #59. Reference the §11 stage-3 plan PR (this PR) in the implementation PR description.

**Sequencing notes:**

- Rule 4's impl PR can open in parallel with rule 3's impl PR (different fields on the same model; trivial textual conflict on `models.py` resolved by either side).
- Rule 4's impl PR can open in parallel with rule 2's impl PR (PR #88; different rule registrations, no shared model field). The only shared file is `tests/test_engine.py` (the `REQUIRED_RULES` set); a textual conflict on that line is trivial to resolve.
- Rule 4's impl PR should NOT amend rule 2 in the same diff (out of scope per §3.14). The amendment is a follow-up issue.

**Lockout note:** if Noor REJECTs this stage-3 plan, the revision routes to a **different** agent than Maya (per the Reviewer Rejection Lockout pattern, canonicalised in `.squad/decisions.md` from PR #78 + PR #85 lessons). Maya cannot revise her own plan under rejection.

---

## Section 6: Sign-off mechanics

| Stage | Owner | Artefact | Status |
|---|---|---|---|
| 1 | Maya | §1 above | DONE (this PR) |
| 2 | Maya | §2 above | DONE (this PR) |
| 3 | Maya (Opus 4.7) | §3 above | DONE (this PR) |
| 4 | Noor (Opus 4.7) | PR comment marker `**Stage-4 Adversarial Review -- Noor**` + `VERDICT: APPROVE` | PENDING |
| 5 | Diego (Sonnet, Opus 4.7 if §3 calls for it) | Sibling impl PR on `squad/59-impl-reservation-scope-mismatch` | BLOCKED on stage-4 |

This plan PR is **draft** until Noor's verdict; on `APPROVE` it becomes ready, the auto-approve workflow fires, and the plan PR squash-merges. Implementation PR opens after.

---

## Section 7: Stage-3 norms operationalised in this plan

(Maya's running checklist; applies to every stage-3 plan in the #59 epic.)

| # | Norm | Where it shows up in this plan |
|---|------|---|
| 1 | Plan-PR convention `docs/plans/NNN-<slug>.md` | This file: `docs/plans/059-az-reservation-scope-mismatch.md`, LF line endings. |
| 2 | §3.7 producer-path citation table | Yes (§3.7), 16 cells anchored to file:line. |
| 3 | One rule, one PR | Yes. Rule 5 gets its own plan / PR. Rule 2 cleanup-amendment is also its own follow-up issue. |
| 4 | Stage-4 ask: ~14 invariants enumerated explicitly | Yes (§4): **14 invariants** enumerated. |
| 5 | Stage-5 plan: name primary + backup implementer | Yes (§5): Diego primary, Yuki backup. Diego NOT locked out. |
| 6 | Tests include an e2e regression test using real `run_rules` (Yuki-net pattern, ref `tests/test_playbook_cross_run_stability.py`) | Yes (test #12 in §3.8). |
| 7 | Conservative recommendation wording ("verify ... then consider", not "re-scope" / "widen") | Yes (§2.5, §3.6). |
| 8 | Producer-path citations independently re-verified at stage-4 | Noor's job (§4 invariant 1). |
| 9 | `extra="forbid"` on any new pydantic model OR new field | No new model; existing `AzureReservation` keeps `extra="forbid"` (§3.2); new field has no `extra` exposure. |
| 10 | Twice-applied (or more) `ctx.redact()` for any user-identifying field | Yes (§3.5 + §2.6): SIX call sites for redaction (Finding.principal, render arg principal, render args for two sub-ID lists, evidence values for two sub-ID lists). |
| 11 | §1.1 brief MUST disambiguate discriminator strings from identifier values (binding from PR #85 lockout) | Yes (§1.1): explicit side-by-side table for `appliedScopeType` (discriminator) vs `appliedScopes` (identifier list); existing `scope` field's hidden-discriminator semantics flagged in §3.2 docstring; rule normalises defensively. |
