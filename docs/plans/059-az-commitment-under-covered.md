# §11 Stage-3 Plan: `AZ.COMMITMENT_UNDER_COVERED` (#59, child 2 of 5)

> **Author:** Maya (Lead / FinOps PM), model: **Opus 4.7**
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #59 (epic), release `release:v0.5.0`, priority `priority:p1`
> **Branch (this plan):** `squad/59-plan-maya-commitment-under-covered`
> **Branch (implementation):** `squad/59-impl-commitment-under-covered` (Diego, post-Noor)
> **Implementer:** Diego (primary, Azure specialist), Yuki backup if Diego is at capacity
> **Adversarial reviewer:** Noor (stage-4)
> **Sibling plan:** `docs/plans/059-az-savings-plan-eligible-spend.md` (rule 1 of 5, same epic, in stage-4 review)

This plan covers **one** rule from the five-rule epic: `AZ.COMMITMENT_UNDER_COVERED`. Rule 1 (`AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`) is on its own branch (`squad/59-plan-maya-savings-plan-eligible`) under stage-4 review. The remaining three rules (`AZ.COMMITMENT_RENEWAL_REVIEW`, `AZ.RESERVATION_SCOPE_MISMATCH`, `AZ.AHB_ELIGIBLE`) get their own stage-3 plans and PRs. One rule, one PR, confirmed by the epic body.

The plan format mirrors the rule-1 plan and the binding norm canonicalised in `.squad/decisions.md` post-PR-#78: **every claim about a value the rule emits MUST cite the producer code path (file:line) that establishes it.**

**Headline (different from rule 1):** This rule needs **zero schema changes**, it is a derived view over the existing `AzureReservation` and `AzureResource` rows. The R3-style alternative ("add a new normalised cost-row model") is examined in §3 and rejected for V1.

---

## Section 1: Stage-1 Research brief (Maya, ground-truth read)

### 1.1 What "commitment under-covered" actually means

Two operationally distinct sub-cases collapse onto the same observable signal:

1. **Scope is too narrow.** A reservation is `appliedScopeType="Single"` and locked to subscription A. Subscription A is using less than ~80 % of the reserved capacity. Subscription B in the same billing scope is paying on-demand for SKUs the reservation could otherwise cover. The fix is **not** to buy more, it is to widen the reservation's applied scope to "Shared" (or "ManagementGroup") so sub-B's matching workloads fall under the unused capacity.
2. **Sibling consumption could absorb.** Reservation is already `Shared` but sub-B has on-demand spend on a SKU that should be matching. Either the SKU/family/region does not actually match (operator-side investigation), or the reservation's applied scope excludes sub-B (e.g. management-group scope where sub-B sits outside the chosen MG).

Both cases are remediable by **changing the reservation's applied scope**, never by buying more commitment. That distinguishes this rule from `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1, which says "buy a Savings Plan to cover currently-uncovered spend") and from `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3, which says "decide whether to renew at expiry"). Rule 2 is the **mis-allocation** rule.

### 1.2 What the existing data already gives us, and what it does NOT

I read the producer code on `main` SHA `0942872` end-to-end before writing this section. The bullets below are **producer-grounded**, not API-spec-grounded:

- `AzureReservation` (`src/finops_assess/models.py:235-250`): carries `reservation_id` (PK), `reservation_name`, `sku`, `scope`, `utilization_pct` (0-100, nullable), `monthly_cost_usd` (nullable). The `scope` field is a **free-form string** holding the value the ARM collector writes at `arm_collector.py:530`, `props.get("appliedScopeType") or ""`, so observed values are `"Single"`, `"Shared"`, `"ManagementGroup"`, or `""` (empty when the API omitted it). It is **not** the ARM scope ID; that is a different field on the API response (`appliedScopes`, plural list). **The current schema does not carry `appliedScopes`** (the list of applied subscription IDs for Single-scope reservations).
- `AzureResource` (`src/finops_assess/models.py:206-232`): carries `resource_id` (PK), `subscription_id` (free-form string, nullable), `monthly_cost_usd` (nullable, `ge=0`). Aggregating `monthly_cost_usd` group-by `subscription_id` gives a per-sub spend total, the only sub-level cost signal the dataset exposes today.
- **There is NO Cost Management API call in the ARM collector today.** I grep'd `src/finops_assess/collectors/arm_collector.py` for `costManagement`, `costmanagement`, `forecast`, `query`, `Cost Mgmt`, `query`, only false-positive matches on field names like `monthly_cost_usd`. The `_API_VERSIONS` map at `arm_collector.py:35-44` does not include any Cost Management or `query` endpoint. The only billing-style data in the schema is the per-resource `monthly_cost_usd` cell.
- The CSV collector `src/finops_assess/collectors/csv_collector.py:144` reads `azure_reservations.csv` into `AzureReservation` rows; **CSV-mode operators can populate `monthly_cost_usd` on `azure_resources.csv` today** (the column exists in the writer's header at `arm_collector.py:551` and the model field at `models.py:227`), even though the live ARM collector currently emits empty cells (`arm_collector.py:402, 445, 476, 503, 532`). So the rule has data to work on in CSV mode and degrades to "no signal" in ARM-only live mode until a future Cost Management collector lands.

**Stage-3 correction to the consensus / stage-2 framing.** The epic body for #59 says "Cost Mgmt + reservation list" and the per-issue note for rule 2 says "Cost Mgmt + reservation list (existing collectors, no new collector needed)". My read of `main` is that **the Cost Management API is NOT actually called by any existing collector**. The only cost data the engine sees is `azure_resources.monthly_cost_usd`. This plan ships rule 2 against that data and explicitly does **not** add a Cost Management collector (out of scope, separate issue). Stage-4 (Noor) should verify this correction against the same producer paths before signing off; if Noor disagrees with the read, the plan amends rather than silently re-routes (per the §11 ground rule and the precedent in `.squad/agents/lead/history.md` line 31, surface corrections explicitly, do not silently override).

### 1.3 Catalogue SKUs the rule references

- **None.** Reservations and Savings Plans cut across many catalogue SKUs and have no `list_price_usd_month` we could anchor to without redistributing Microsoft's price tables (hard rule #3 / #5). Same posture as `AZ.RESERVATION_UNDERUTILIZED` (rule it most closely resembles), which also references no catalogue id.

### 1.4 Read scopes required

- `Cost Management Reader` (already declared, see `docs/plan.md` §9), used in CSV mode by the operator's own data export; not directly invoked by the rule code.
- `Reader` on the resources covered (already declared, see `docs/plan.md` §9), same.
- ARM collector audience `https://management.azure.com/.default` (`src/finops_assess/collectors/arm_collector.py:31`), **unchanged**.
- **No new scope. No `*.ReadWrite.*` scope. Hard rule #1 upheld.**

---

## Section 2: Stage-2 Rubberduck (Maya, plain-English walkthrough)

### 2.1 What the rule is supposed to say

> "Reservation `{reservation_id}` ({scope_kind}-scope, {utilization_pct}% utilised) has unused capacity, AND sibling subscription `{sibling_sub}` shows ${sibling_on_demand_spend_usd}/month of on-demand resource spend over the same window. Verify the sibling's on-demand SKUs are compatible with this reservation's family / region (Azure auto-applies on a best-fit basis), then consider widening the reservation's applied scope so the sibling's workload absorbs the unused capacity."

That is conservative, names the operator-side check (SKU compatibility) the rule cannot perform from the current schema, and never tells the operator to spend money, the recommended action is **scope-widening, not purchasing**.

### 2.2 What could go wrong (edge cases)

| # | Edge | Behaviour required |
|---|------|---|
| E1 | Dataset has no reservations of any kind (or none of the relevant SKU family) | Rule emits no finding (vacuous loop). |
| E2 | All reservations report `utilization_pct >= 80%` | No reservation passes the utilisation gate; rule emits no finding. (Identical threshold to `AZ.RESERVATION_UNDERUTILIZED`, see overlap discussion in §2.4.) |
| E3 | Sibling sub on-demand spend is below the micro-threshold (`< $50`/month) | Skip that sibling; if no sibling crosses the threshold, no finding for that reservation. |
| E4 | Lookback period is `< 30 days` (insufficient signal) | The current `AzureReservation` schema does NOT carry a lookback-period field; we inherit `RESERVATION_UNDERUTILIZED`'s implicit assumption that reported `utilization_pct` is a 30-day average (the ARM collector at `arm_collector.py:518-523` deliberately picks the `30days`/`30d`/`monthly` aggregate, falling back to `onDemandUtilizationPercentage`). **Rule documents the assumption; if the collector ever emits a shorter aggregate, this rule will inherit that drift along with `RESERVATION_UNDERUTILIZED`.** Issue tracker note in §6. |
| E5 | Reservation expires within 30 days (out of scope, rule 3 territory) | The current `AzureReservation` schema does NOT carry `expiry_date`. **Rule 2 cannot detect this; rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`) will add the field.** Document explicitly in §3.13 as a known V1 limitation that may produce a "consider widening scope" recommendation on a reservation that is about to expire. Operator owns the cross-check. |
| E6 | Sibling sub is in a different billing scope (no actual transferability) | The current dataset has **no billing-scope grouping**. V1 treats every `subscription_id` observed in `azure_resources` as a candidate sibling. Operators with multi-billing-scope tenants are advised in `docs/rules.md` to scope their CSV input per billing account. Cross-billing-scope false positives are a documented V1 limitation. |
| E7 | Reservation `scope` is already `"Shared"` and no consuming sibling sub exists in the dataset | If no sibling crosses the spend threshold, no finding. The rule does not fire vacuously. |
| E8 | Same-finding deduplication (Yuki-net invariant inherited from rule 1) | Dedup on `(reservation_id, sibling_sub)` so the same opportunity is not double-fired across multiple resource rows in the same sub. One `Finding` per `(reservation, sibling)` pair. |
| E9 | Reservation `utilization_pct is None` (no signal) | Skip, abstain rather than guess at zero (mirrors `AZ.RESERVATION_UNDERUTILIZED` at `azure_rules.py:167-168`). |
| E10 | No `azure_resources` row populates `subscription_id` OR `monthly_cost_usd` | Rule abstains across the board (no on-demand signal exists). This is the live-ARM-mode default until a Cost Management collector lands. |
| E11 | Reservation `scope == "Single"` but the schema does not record which sub it is locked to | Conservative behaviour: count **all** subs in the dataset as candidate siblings, including the actual owner sub (over-counting risk on the owner sub itself). Documented as known V1 limitation. Future schema extension (`applied_scope_subscription_ids: list[str]`) is the cleaner fix and is out of scope here, that field belongs to rule 4 (`AZ.RESERVATION_SCOPE_MISMATCH`), which is the closer schema match. **The conservative over-count is preferable to silently dropping a real sibling sub for V1.** |
| E12 | Sibling `subscription_id` aggregates a single resource with `monthly_cost_usd = 0.0` | Treated as below `$50/mo` threshold (E3); skipped. |

### 2.3 False-positive risks

- **Over-counting on the owner sub when reservation is Single-scope and we cannot identify the owner (E11).** The owner sub will look like a "sibling" and contribute to the on-demand spend total. Mitigation: the recommendation wording explicitly asks the operator to verify SKU compatibility; if the "sibling" is actually the owner sub, the operator's verification will catch it as a tautology. The over-count is conservative, it produces a finding the operator dismisses on inspection, not a missed finding.
- **Cross-billing-scope siblings (E6).** Same mitigation: the recommendation asks for verification; the operator catches the cross-scope case. Documented as a `docs/rules.md` caveat.
- **SKU/family/region mismatch.** A reservation for `Standard_D4s_v5` cannot absorb on-demand `Standard_E32_v5`. The rule has **no SKU-compatibility check** today. Mitigation: wording, "verify the sibling's on-demand SKUs are compatible". This is the same posture as `AZ.RESERVATION_UNDERUTILIZED`, which also flags low utilisation without checking SKU coverage. Operator-owned verification is the design.
- **Lookback assumption (E4).** Inherits from `AZ.RESERVATION_UNDERUTILIZED`. If the collector ever changes the aggregate window, both rules drift together, a single fix at the collector layer corrects both. Acceptable coupling.

### 2.4 Cross-rule isolation, overlap with `AZ.RESERVATION_UNDERUTILIZED` and `AZ.COMMITMENT_RENEWAL_REVIEW`

- **Overlap with `AZ.RESERVATION_UNDERUTILIZED`** (`src/finops_assess/rules_impl/azure_rules.py:163-190`): both gate on `utilization_pct < 80%`. **Every rule-2 finding will also trigger `AZ.RESERVATION_UNDERUTILIZED` on the same reservation.** This is intentional and complementary, not duplicative:
  - `RESERVATION_UNDERUTILIZED` says: "this reservation is wasteful, exchange or shrink at next renewal."
  - `COMMITMENT_UNDER_COVERED` says: "this reservation is wasteful AND a sibling sub has on-demand spend, consider widening the applied scope so the sibling absorbs the waste, instead of (or in addition to) shrinking."
  - The two recommendations live on different cost levers (commitment size vs scope) and the operator picks the cheaper remediation. The dual fire is the **signal**: it tells the operator they have two options, not one.
  - Stage-4 reviewer: do not request consolidation. The cross-rule independence is what makes the playbook useful.
- **Overlap with `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3, future)**: rule 3 will fire when a reservation's `expiry_date` is within `N` days. Rule 2 will not detect that case (E5) because the current schema lacks `expiry_date`. When rule 3 lands, the two rules will be **disjoint by gate**: rule 3 gates on time-to-expiry; rule 2 gates on utilisation + sibling spend. They can both fire on the same reservation if it is both under-utilised AND about to expire, that is a meaningful dual signal ("rebalance the scope before deciding whether to renew"). No isolation work required at rule 2's stage; rule 3's stage-3 plan owns the rendezvous test.
- **Overlap with `AZ.RESERVATION_SCOPE_MISMATCH` (rule 4, future)**: rule 4 is the closer cousin. Rule 4 will likely fire when `appliedScopes` (list of subscription IDs for Single-scope reservations) does NOT include subs the operator's tagging convention says it should. Rule 2 fires on the **observed-spend** signal; rule 4 will fire on the **declared-intent** signal (tags, naming, mgmt-group structure). Stage-3 plan for rule 4 will tighten the boundary. For now: rule 2 abstains when the signal is missing (`scope == "Shared"` AND no sibling crosses the threshold), so rule 4's eventual addition cannot create a contradicting finding.

### 2.5 Conservative recommendation wording (drafted)

> "Reservation `{principal}` is `{scope_kind}`-scope and averaged `{utilization_pct}%` utilisation, while sibling subscription `{sibling_sub}` shows `${sibling_on_demand_spend_usd}` of on-demand resource spend over the same window. Verify the sibling's on-demand SKUs are compatible with this reservation's family and region (Azure auto-applies on a best-fit basis), then consider widening the reservation's applied scope so the sibling's workload absorbs the unused capacity."

Verb-conservative ("verify ... then consider"); names the operator-side check; never says "buy" or "purchase"; matches rule-1's voice and the existing `AZ.RESERVATION_UNDERUTILIZED` register ("Exchange or shrink the commitment at next renewal.").

### 2.6 Security implications

- **No new scope.** Cost Management Reader and Reader on resources are already declared; `_ARM_SCOPES` is unchanged at `arm_collector.py:31`.
- **PII redaction posture (special, see §3.7 binding citation).** The rule emits TWO redactable identifiers per finding:
  1. `principal = ctx.redact(reservation.reservation_id)`, the reservation ARM ID. **Not a user identity**, but it MUST flow through `ctx.redact()` because the rule pipeline treats every `principal` as redactable per `engine.py:70-75` and the post-PR-#78 honest-manifest contract.
  2. `evidence["sibling_sub"] = ctx.redact(subscription_id)`, the sibling subscription identifier. **Same posture: not a user identity, but redacted for symmetry with the principal.** The convention matches `AzureReservation` (where the principal is the `reservation_id`, not a user) and matches `AZ.RESERVATION_UNDERUTILIZED`'s posture. See §3.5 for the call sites and §3.7 for the binding citation.
- **No third-party copyrighted material.** All numbers come from the operator's own tenant data. No Microsoft pricing pages bundled.

### 2.7 Alternatives considered (rejected)

- **(R1) Reuse `AzureReservation` and extend it with `applied_scope_subscription_ids: list[str]` so the rule can identify the owner sub of a Single-scope reservation and only treat genuinely-different subs as siblings.** Rejected for THIS PR: that extension belongs to rule 4 (`AZ.RESERVATION_SCOPE_MISMATCH`), which is the natural consumer of `appliedScopes`. Adding it here entangles two rules into one PR, breaks the "one rule, one PR" cadence the epic mandates, and forces stage-3 plans for rules 2 AND 4 to co-evolve. V1 of rule 2 ships with the conservative E11 over-count; V2 sharpens once rule 4 lands the schema addition. The over-count is operator-visible (the recommendation says "verify the sibling's on-demand SKUs are compatible") so the false-positive cost is one operator skim per finding, not a silent bad action.
- **(R2) Add a new `AzureSubscriptionCost` model** with `(subscription_id, period_start, period_end, on_demand_usd, reservation_covered_usd)` so the rule can split on-demand vs reservation-covered spend at sub-level. Rejected for V1: there is no producer for this row today (the ARM collector does not call Cost Management; the CSV collector has no `azure_subscription_costs.csv` reader). Adding a model without a producer is YAGNI; pydantic will silently accept zero rows in every existing dataset and the rule will degrade to "no signal" in identical fashion to V1's `monthly_cost_usd` aggregation. The future Cost Management collector (separate issue, deferred) is the right place to introduce this model, paired with its producer in the same PR. Adding it here decouples the schema from the producer and creates a "model exists but is never populated" failure mode the loader cannot diagnose. **R2 also fails the rule-1 R3 test for "distinct primary key", `(subscription_id, period_start, period_end)` is a composite key over the same join surface as the future `AzureBenefitRecommendation` (rule 1's new model), so co-existence creates ambiguity about which row source the engine should prefer when both are present.**
- **(R3) Reuse `AzureBenefitRecommendation`** (the new model rule 1 is adding) by reading rule 1's recommendation rows and inverting them to detect "spend that the API thinks could be moved under a SP" as a proxy for "uncovered sibling spend". Rejected: that conflates two operationally distinct findings (rule 1 = "buy a SP"; rule 2 = "widen an existing reservation's scope"). The ARM API endpoints differ (`benefitRecommendations` vs `reservations`), the join key differs (`recommendation_id` vs `reservation_id`), and the operator action differs (purchase vs scope-change). If rule 1 has not landed by the time rule 2 implements, rule 2 would be blocked on rule 1's PR, the epic's "one rule, one PR" cadence rejects that coupling.
- **(R4) Implement rule 2 as a derived view from `AZ.RESERVATION_UNDERUTILIZED` findings** (post-process rule 1's output to add the sibling-sub angle). Rejected: the rule engine does not support post-processing of findings; rules consume `RuleContext`, not other rules' outputs. Implementing this would require an engine extension (`finding_postprocessors` registry or similar) that is out of scope. Even if the extension existed, two independent rule firings (with overlapping but distinct evidence dicts) is the design, the playbook reporter renders one ticket per finding and the operator gets two complementary tickets.

---

## Section 3: Stage-3 plan proper (file-level checklist)

### 3.1 Acceptance criteria (small enough for ONE PR)

- [ ] **No new pydantic model.** This is the single biggest delta from rule 1's plan. Implementer DO NOT extend `AzureReservation` or add `AzureSubscriptionCost`; the conservative V1 reads the existing schema only.
- [ ] **No `NormalizedDataset` field added.** The rule consumes `azure_reservations` and `azure_resources`, both already on `NormalizedDataset` (`src/finops_assess/models.py:383-384`).
- [ ] **No CSV collector change.** The CSV collector at `csv_collector.py:144` already reads `azure_reservations.csv`; `azure_resources.csv` is read at `csv_collector.py:143`.
- [ ] **No ARM collector change.** No new endpoint, no new column. `_ARM_SCOPES` (`arm_collector.py:31`) is byte-identical post-PR.
- [ ] YAML rule entry added to `data/rules/azure.yaml` AND packaged mirror at `src/finops_assess/data/rules/azure.yaml` (byte-equal).
- [ ] Rule implementation `commitment_under_covered` registered in `src/finops_assess/rules_impl/azure_rules.py` next to `reservation_underutilized` (line 163 area).
- [ ] New `.j2` playbook template at `src/finops_assess/data/playbooks/azure/AZ.COMMITMENT_UNDER_COVERED.j2`, LF-pinned by the existing `.gitattributes` rule for `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`.
- [ ] `samples/azure_resources.csv` extended with a sibling-sub row that has `subscription_id` AND `monthly_cost_usd` populated (so the new rule fires on the synthetic tenant).
- [ ] `samples/azure_reservations.csv` extended with a Single-scope, 45 %-utilised reservation in the same family as the new sibling row (already present row at line 2 may suffice, see §3.11).
- [ ] Unit tests in `tests/test_az_commitment_under_covered.py` (positive, abstain-on-high-util, abstain-on-no-sibling-spend, abstain-on-missing-cost-data, dedup on (reservation, sibling) pair, redaction on by default, cleartext when off, E11 over-count documented).
- [ ] **End-to-end regression test (real `run_rules` engine, not a mocked rule call).** Pattern reference: `tests/test_playbook_cross_run_stability.py:1-80` (Yuki-net pattern). Test asserts the rule fires once, asserts dedup invariant E8, asserts redaction.
- [ ] `tests/test_engine.py` `REQUIRED_RULES` set (line 23) includes `"AZ.COMMITMENT_UNDER_COVERED"` AND the synthetic tenant fires it.
- [ ] `tests/test_csv_collector.py` round-trip for `azure_reservations.csv` and `azure_resources.csv` already covers the new rule's input shape, no new loader test needed; the rule's E2E test exercises the same path.
- [ ] `docs/plan.md` §6 lists the new rule under Azure rules.
- [ ] `python scripts/generate_docs.py` regenerates `docs/rules.md`, `examples/demo-report.{json,html,csv}`, `examples/demo-triage.{json,csv}`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`; all regenerated bytes committed.
- [ ] `python scripts/generate_docs.py --check` passes locally and in CI.
- [ ] All gates green: `finops-assess validate`, `ruff check`, `ruff format --check`, `mypy src`, `pytest`.
- [ ] No new scope requested in `arm_collector.py` (`_ARM_SCOPES` byte-unchanged at line 31).
- [ ] No catalogue YAML changes in `data/catalog/azure/*.yaml`.

If the implementation cannot meet **all** criteria in one PR, decompose further. The lockable signal is "draft PR is green and < ~400 LoC product code" (this rule is smaller than rule 1 because there is no schema or collector change).

### 3.2 Schema additions, `src/finops_assess/models.py`

**None.** This is the biggest delta from rule 1's plan and the headline of this PR. Confirmed in §1.2, the existing `AzureReservation` (`models.py:235-250`) and `AzureResource` (`models.py:206-232`) carry every field the rule needs (`reservation_id`, `scope`, `utilization_pct`, `subscription_id`, `monthly_cost_usd`). The rule synthesises sub-level on-demand spend from per-resource rows at runtime (see §3.5 aggregation logic). No `extra="forbid"` blast radius, no migration, no new manifest version.

### 3.3 CSV collector, `src/finops_assess/collectors/csv_collector.py`

**No changes.** The collector already reads both `azure_reservations.csv` (line 144) and `azure_resources.csv` (line 143). The rule reads from the resulting `NormalizedDataset` directly.

### 3.4 ARM collector, `src/finops_assess/collectors/arm_collector.py`

**No changes.** `_ARM_SCOPES` (line 31) is unchanged. `_collect_reservations` (lines 244-253) emits the rows the rule consumes. The reservation row builder at lines 525-534 already writes `scope = appliedScopeType`, which is exactly the Single/Shared discriminator the rule reads. No new endpoint, no new column.

**Forward-pointer note for rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`):** that rule will need an `expiry_date` field on `AzureReservation` and a corresponding addition to the reservation row builder (parsing `props.get("expiryDateTime")`). That schema change is owned by rule 3's stage-3 plan, not this one. Stage-4 reviewer: confirm this PR does not pre-emptively touch it.

### 3.5 Rule implementation, `src/finops_assess/rules_impl/azure_rules.py`

```python
# ---------------------------------------------------------------------------
# AZ.COMMITMENT_UNDER_COVERED
# ---------------------------------------------------------------------------
# Same utilisation threshold as AZ.RESERVATION_UNDERUTILIZED -- intentional;
# see plan §2.4 (cross-rule isolation discussion).
_COMMITMENT_UTIL_THRESHOLD = 80.0
_SIBLING_MIN_ON_DEMAND_USD = 50.0


@register("AZ.COMMITMENT_UNDER_COVERED")
def commitment_under_covered(ctx: RuleContext) -> Iterable[Finding]:
    """Flag under-utilised reservations whose unused capacity could absorb
    a sibling subscription's on-demand spend (scope-widening opportunity).

    See plan §2.4 for the intentional overlap with AZ.RESERVATION_UNDERUTILIZED.
    """
    # Aggregate on-demand spend per subscription_id from azure_resources.
    sibling_spend: dict[str, float] = {}
    for resource in ctx.dataset.azure_resources:
        sub = resource.subscription_id
        if sub is None or not sub.strip():
            continue
        cost = resource.monthly_cost_usd
        if cost is None:
            continue
        sibling_spend[sub] = sibling_spend.get(sub, 0.0) + float(cost)

    if not sibling_spend:
        return  # E10: no on-demand signal

    seen: set[tuple[str, str]] = set()  # E8 dedup on (reservation_id, sibling_sub)
    for reservation in ctx.dataset.azure_reservations:
        if reservation.utilization_pct is None:
            continue  # E9
        if reservation.utilization_pct >= _COMMITMENT_UTIL_THRESHOLD:
            continue  # E2

        scope_raw = (reservation.scope or "").strip().lower()
        scope_kind = "Single" if scope_raw == "single" else (
            "Shared" if scope_raw in ("shared", "managementgroup") else "Unknown"
        )

        for sibling_sub, on_demand in sibling_spend.items():
            if on_demand < _SIBLING_MIN_ON_DEMAND_USD:
                continue  # E3
            key = (reservation.reservation_id, sibling_sub)
            if key in seen:
                continue  # E8
            seen.add(key)

            yield Finding(
                rule_id=ctx.rule.id,
                surface="azure",
                severity=ctx.rule.severity,
                principal=ctx.redact(reservation.reservation_id),
                current_sku=reservation.sku,
                estimated_monthly_savings_usd=None,  # not quantifiable from this signal
                recommendation=render(
                    ctx.rule.recommendation_template,
                    principal=ctx.redact(reservation.reservation_id),
                    scope_kind=scope_kind,
                    utilization_pct=round(reservation.utilization_pct, 1),
                    sibling_sub=ctx.redact(sibling_sub),
                    sibling_on_demand_spend_usd=round(on_demand, 2),
                ),
                evidence={
                    "reservation_name": reservation.reservation_name,
                    "sku": reservation.sku,
                    "scope_kind": scope_kind,
                    "utilization_pct": reservation.utilization_pct,
                    "monthly_cost_usd": reservation.monthly_cost_usd,
                    "sibling_sub": ctx.redact(sibling_sub),
                    "sibling_on_demand_spend_usd": round(on_demand, 2),
                },
            )
```

`_round` already exists at `azure_rules.py:18`. `render` is the existing template helper (`engine.py:344-352`). **Both `reservation.reservation_id` references AND both `sibling_sub` references MUST go through `ctx.redact()`**, see §3.7 binding citation. Stage-4 reviewer: count call sites in the diff (4 redact calls expected).

**Note on `evidence["sibling_sub"]` redaction:** unlike `AZ.RESERVATION_UNDERUTILIZED` (which puts raw `scope` and `monthly_cost_usd` into evidence, both non-PII identifiers), this rule's `sibling_sub` IS a redaction surface because it identifies a specific Azure subscription that the operator may not want surfaced cleartext in a downstream ticket. Redacting in evidence matches the redaction in the rendered template; mismatched redaction across `principal`, `recommendation`, and `evidence` is the exact failure mode PR #78 BLOCKING #1 caught. Stage-4: verify symmetry.

### 3.6 YAML rule entry, `data/rules/azure.yaml` (and packaged mirror)

```yaml
- id: AZ.COMMITMENT_UNDER_COVERED
  surface: azure
  severity: medium
  summary: Under-utilised reservation while a sibling subscription pays on-demand for a likely-compatible workload.
  recommendation_template: >
    Reservation {principal} is {scope_kind}-scope and averaged
    {utilization_pct}% utilisation, while sibling subscription
    {sibling_sub} shows ${sibling_on_demand_spend_usd} of on-demand
    resource spend over the same window. Verify the sibling's
    on-demand SKUs are compatible with this reservation's family
    and region (Azure auto-applies on a best-fit basis), then
    consider widening the reservation's applied scope so the
    sibling's workload absorbs the unused capacity.
```

**Severity choice: `medium`.** Same tier as rule 1 and `AZ.LOG_ANALYTICS_OVERINGEST`. Rationale: scope-mis-allocation is a savings opportunity, not idle waste. `AZ.RESERVATION_UNDERUTILIZED` is `high` because it implies a forfeitable commitment; this rule's remediation (widening scope) is operator-controllable on demand, so the urgency is lower.

**Sync the packaged mirror** at `src/finops_assess/data/rules/azure.yaml` in the same commit (catalogue YAML is shipped with the wheel; the mirror under `src/finops_assess/data/` is the importlib-resources copy and must stay byte-equal). Pattern reference: PR #55 commit `f54177a` (Maya, M365 docs-voice mirror sync).

### 3.7 Producer-path citations (BINDING per post-PR-#78 norm)

Every claim this rule makes about a value is anchored to the producer code path that establishes the value. Stage-4 reviewer rejects the plan if any cell below is wrong. **Citations verified against `main` SHA `0942872`.**

| Claim | Producer (file:line) | What the producer does |
|---|---|---|
| `principal` is salted-hashed by default | `src/finops_assess/engine.py:70-75` (`RuleContext.redact`) | `if not self.redact_pii: return principal; digest = hashlib.sha256(f"{self.salt}:{principal}".encode()).hexdigest(); return f"sha256:{digest[:16]}"`. The rule MUST call `ctx.redact(...)` on **four** call sites in §3.5: `Finding.principal`, the `principal` arg to `render(...)`, the `sibling_sub` arg to `render(...)`, and the `sibling_sub` evidence value. |
| `principal` is the reservation **ARM ID**, not a user identity | `src/finops_assess/models.py:235-250` (`AzureReservation` definition; `reservation_id: str = Field(..., min_length=1)`) AND `src/finops_assess/rules_impl/azure_rules.py:175` (`AZ.RESERVATION_UNDERUTILIZED` uses `ctx.redact(reservation.reservation_id)` as the `principal`, same convention) | The new rule mirrors this convention exactly. |
| `sibling_sub` is the Azure subscription identifier | `src/finops_assess/models.py:230` (`AzureResource.subscription_id: str | None = None`) | Free-form string. The rule treats it as redactable for symmetry with `principal`; rationale documented in §2.6. |
| `principal` is **not stable across runs** with default redaction | `src/finops_assess/engine.py:151` (`run_rules`) | `salt_value = salt if salt is not None else secrets.token_hex(16)`. The CLI does not flow a stable salt today. Issue #73 is the engine-level fix. This rule inherits the existing per-surface stability declaration in `examples/playbook.jsonl.manifest.json` (Azure marked `per_run` post-PR-#78). **No new reporter contract introduced.** |
| `azure_reservations.csv` is read by the CSV collector | `src/finops_assess/collectors/csv_collector.py:144` | Existing line; no plan change. |
| `azure_resources.csv` is read by the CSV collector | `src/finops_assess/collectors/csv_collector.py:143` | Existing line; no plan change. The rule reads `subscription_id` and `monthly_cost_usd` from these rows. |
| `AzureReservation.scope` carries the appliedScopeType discriminator (`"Single"` / `"Shared"` / `"ManagementGroup"` / `""`) | `src/finops_assess/collectors/arm_collector.py:530` (`"scope": props.get("appliedScopeType") or ""`) | The rule's `scope_kind` derivation (§3.5) treats this string as the discriminator. CSV-mode operators are advised to use the same vocabulary; the CSV mirror at `samples/azure_reservations.csv:2-3` already does (`shared`, `single` lower-cased). |
| `AzureReservation.utilization_pct` is a 30-day average when emitted by ARM | `src/finops_assess/collectors/arm_collector.py:514-523` | The collector deliberately picks the `30days`/`30d`/`monthly` aggregate, falling back to `onDemandUtilizationPercentage`. The rule inherits this assumption (E4); no separate lookback gate. |
| The ARM collector uses **read-only** scopes | `src/finops_assess/collectors/arm_collector.py:31` (`_ARM_SCOPES = ["https://management.azure.com/.default"]`) | This plan does not modify `_ARM_SCOPES`. **Hard rule #1 upheld.** |
| `AZ.RESERVATION_UNDERUTILIZED` (the overlapping rule, see §2.4) | `src/finops_assess/rules_impl/azure_rules.py:160-190` | Threshold `_RESERVATION_UTIL_THRESHOLD = 80.0` (line 160); abstain-on-`None` at line 167-168. Rule 2 mirrors both literals deliberately. |
| `Finding.evidence` is a free-form dict surfaced verbatim by reporters | `src/finops_assess/models.py` `Finding` definition + `src/finops_assess/reporters/json_reporter.py` | All evidence values in §3.5 are non-PII (numerical / identifiers already redacted). `sibling_sub` in evidence is redacted to match the principal's redaction posture. |
| `tests/test_engine.py` REQUIRED_RULES is the rule-presence smoke test | `tests/test_engine.py:23-47` | Add `"AZ.COMMITMENT_UNDER_COVERED"` to the set. The fixture `run_against_samples` (line 50) drives `run_rules` against the synthetic tenant; the parameterised `test_each_required_rule_fires_at_least_once` (line below the set) asserts the rule fires at least once. |

If any of these citations is wrong at implementation time, the implementer flags it back to Maya and the plan is amended, never silently overridden (§11 ground rule and the precedent in `.squad/agents/lead/history.md` lines 31-33, surface corrections explicitly).

### 3.8 Test plan

| # | Test name | File | Asserts |
|---|---|---|---|
| 1 | `test_commitment_under_covered_fires_on_undercovered_sibling` | `tests/test_az_commitment_under_covered.py` | One Single-scope reservation at 45 % utilisation + one `azure_resource` row with `subscription_id="sub-B"` and `monthly_cost_usd=200.0` produces exactly one finding with `rule_id="AZ.COMMITMENT_UNDER_COVERED"` and `severity="medium"`. |
| 2 | `test_commitment_under_covered_abstains_on_high_utilization` | same | Same dataset but reservation at 95 % utilisation → no finding (E2). |
| 3 | `test_commitment_under_covered_abstains_on_null_utilization` | same | `utilization_pct=None` → no finding (E9). |
| 4 | `test_commitment_under_covered_abstains_on_no_sibling_spend` | same | No `azure_resources` rows → no finding (E10). |
| 5 | `test_commitment_under_covered_abstains_on_micro_sibling_spend` | same | Sibling `monthly_cost_usd=10.0` (< $50) → no finding (E3). |
| 6 | `test_commitment_under_covered_dedups_per_reservation_and_sibling` | same | Two `azure_resources` rows for the same `subscription_id="sub-B"` (each $200) → one finding (E8 dedup), evidence shows aggregated $400. |
| 7 | `test_commitment_under_covered_redacts_principal_and_sibling_by_default` | same | With `redact_pii=True` (default), `finding.principal` starts with `sha256:` AND `finding.evidence["sibling_sub"]` starts with `sha256:`. **Cites `engine.py:70-75` in the test docstring.** |
| 8 | `test_commitment_under_covered_emits_cleartext_with_redaction_off` | same | With `redact_pii=False`, `finding.principal == reservation.reservation_id` AND `finding.evidence["sibling_sub"] == "sub-B"` exactly. |
| 9 | `test_commitment_under_covered_overlaps_reservation_underutilized` | same | Both rules fire on the same reservation; assert `rule_ids = {"AZ.RESERVATION_UNDERUTILIZED", "AZ.COMMITMENT_UNDER_COVERED"}` are both present. **This is the cross-rule isolation invariant from §2.4, operationally complementary, not duplicative.** |
| 10 | `test_commitment_under_covered_e2e_through_run_rules` | same | End-to-end regression: synthetic dataset, real `run_rules(...)` call, asserts exactly one finding emerges. **Pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`** (Yuki-net, real engine, no mocked rule callable). |
| 11 | `test_commitment_under_covered_redacted_principal_unstable_across_runs` | same | Two `run_rules(...)` invocations with `redact_pii=True` (default) and no shared salt produce DIFFERENT redacted principals for the same reservation. **Inherits the PR #78 cross-run-stability test pattern**, this rule's manifest declaration is `per_run` for Azure (already declared post-PR-#78), and this test prevents future drift. |
| 12 | extend `tests/test_engine.py:REQUIRED_RULES` | `tests/test_engine.py` | Add `"AZ.COMMITMENT_UNDER_COVERED"` to the set at line 23. The synthetic tenant must fire it at least once, see `samples/` extension in §3.11. |

**Fixtures:** all synthetic rows constructed in-test (no on-disk fixture files for tests 1-11). The on-disk samples extension (§3.11) is for the `samples/` smoke-fire (test 12) and the demo-report regen.

### 3.9 Doc regen

The implementer runs `python scripts/generate_docs.py` once and commits **all** regenerated artefacts in the same PR:

- `docs/rules.md`, auto-generated from `data/rules/azure.yaml`. Will gain a new entry for `AZ.COMMITMENT_UNDER_COVERED`.
- `examples/demo-report.{json,html,csv}`, will gain a finding row from the extended sample (see §3.11).
- `examples/demo-triage.{json,csv}`, same.
- `examples/playbook.jsonl{,.manifest.json}`, same; the playbook reporter renders any rule with a registered `.j2` template. **The new template** at `src/finops_assess/data/playbooks/azure/AZ.COMMITMENT_UNDER_COVERED.j2` is required (LF-pinned by the existing `.gitattributes` rule for `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`). Template body is a paraphrase of the recommendation; bracketed sections [TITLE]/[DESCRIPTION]/[REMEDIATION_STEPS]/[VERIFICATION_CHECKLIST]/[REFERENCES] mirror `AZ.RESERVATION_UNDERUTILIZED.j2`.
- `examples/focus-aligned.csv{,.manifest.json}`, Azure-only today; will pick up the new finding automatically.

`python scripts/generate_docs.py --check` is the docs-freshness gate (`tests/test_generate_docs.py::test_check_mode_passes_for_committed_artifacts`); it WILL fail without the regen commit.

### 3.10 `data/personas.yaml` impact

**None.** Personas inherit licensing rules (`M365.*` and `GH.COPILOT_*`). Cost-discipline rules like `AZ.*` apply to resources, not user identities. Same posture as every existing `AZ.*` rule and as rule 1's plan.

### 3.11 `samples/` extension

Two minimal edits to make the synthetic tenant fire the new rule:

1. **`samples/azure_resources.csv`**, append one row with `subscription_id` and `monthly_cost_usd` populated (the existing rows leave both empty per `samples/azure_resources.csv:2-3`):

```
/subscriptions/00000001/rg/prod/vm/vm-sibling-undercovered,virtualMachine,Standard_D4s_v5,eastus,55.0,68.0,72.0,1200.0,,,,180.00,,sub-undercovered-001,,
```

   This row carries `subscription_id="sub-undercovered-001"` and `monthly_cost_usd=180.00`, which crosses the $50 threshold (E3) and gives the rule a sibling to fire on. The activity numbers (CPU 55 %, mem 72 %) are deliberately above the IDLE / OVERSIZED gates so this row fires ONLY the new rule.

2. **`samples/azure_reservations.csv`**, the existing row at line 2 (`ri-001`, `shared`, `45.0%` utilisation) already satisfies the utilisation gate. The Single-scope row at line 3 (`ri-002`, `single`, `92.0%`) is above threshold and will not fire. **No change needed**, but the implementer should verify by running the test suite and adjust if the synthetic tenant geometry shifts.

   If the existing `ri-001` row does NOT trigger because the `subscription_id` join falls outside the reservation's billing scope assumption (E11 owner-overcounting case), append a third row with `scope="single"` and `utilization_pct=40.0` so the synthetic tenant has an unambiguous fire condition.

### 3.12 `docs/plan.md` §6 update

Add to the Azure rules block (~line 215, after the rule-1 entry, both rules are released together in v0.5.0):

```
- `AZ.COMMITMENT_UNDER_COVERED`: under-utilised reservation while a sibling subscription pays on-demand for a likely-compatible workload (scope-widening signal).
```

Keep the §6 entry one line; the full rule body is `docs/rules.md` (auto-generated).

### 3.13 Out of scope (and why)

- **Live Cost Management API integration.** The current ARM collector does not call Cost Management; this rule operates on the per-resource `monthly_cost_usd` column that CSV-mode operators populate today. The Cost Management collector is a separate, larger effort (separate issue, deferred). When it lands, this rule will get sharper signal automatically, no rule-code change required.
- **`applied_scope_subscription_ids` schema extension.** Belongs to rule 4 (`AZ.RESERVATION_SCOPE_MISMATCH`). V1 of rule 2 ships with the conservative E11 over-count.
- **`expiry_date` schema extension.** Belongs to rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`). V1 of rule 2 cannot detect E5 (about-to-expire reservations) and the recommendation_template makes no claim about renewal, the operator's verification step covers it.
- **SKU-compatibility check between reservation.sku and sibling-sub on-demand SKUs.** Out of scope; the recommendation explicitly asks the operator to verify. Same posture as `AZ.RESERVATION_UNDERUTILIZED`.
- **Reservation-vs-Savings-Plan A/B suggestion.** Reservations and SPs have different remediation paths; this rule fires only on Reservation rows (the schema does not currently distinguish them, but the rule's gating on `appliedScopeType` is reservation-specific semantics). When the schema gains a `commitment_kind` discriminator, the rule's wording sharpens; for now both row kinds flow through the same code path.
- **The other three rules in #59.** Each gets its own stage-3 plan.

### 3.14 Cross-cutting decisions worth flagging

1. **No new normalised input row type.** Headline delta from rule 1's plan. R1, R2, R3, R4 alternatives all rejected in §2.7 with rationale. The Scribe should canonicalise this finding alongside rule 1's "new model required" decision so future "do we need a new input row?" questions have both poles documented.
2. **No catalogue change.** Reservations are not catalogue SKUs.
3. **No engine change.** The rule is a pure additive registration; `RuleContext` is consumed unchanged.
4. **No new scope.** Cost Management Reader and Reader on resources already requested. **Hard rule #1 upheld via `arm_collector.py:31` citation.**
5. **Intentional cross-rule overlap with `AZ.RESERVATION_UNDERUTILIZED`.** Documented in §2.4 and tested in §3.8 test #9. Stage-4: do not request consolidation.
6. **Two redaction surfaces per finding** (`principal` + `sibling_sub`), both flowing through `ctx.redact()`. Tested at §3.8 test #7 and test #8. PR #78 BLOCKING #1 lessons applied.

---

## Section 4: Stage-4 ask (Noor, adversarial reviewer)

**Reviewer:** Noor (squad:noor), model **Opus 4.7** mandatory (per §11; never downgrade).

**Specific invariants Noor must verify (steelman against the plan, do not just agree):**

1. **Producer-path citations are correct against `main` SHA `0942872`.** Open every cell in §3.7 against the repo at that SHA. Reject if any line number is wrong or any claim is not what the producer actually does. Particular focus: `arm_collector.py:530` (`scope = appliedScopeType`), confirm the rule's `scope_kind` derivation logic in §3.5 matches the actual collector vocabulary.
2. **Stage-3 correction in §1.2 is accurate.** Verify by reading `src/finops_assess/collectors/arm_collector.py` end-to-end on `main` SHA `0942872`, confirm there is **no Cost Management API call**, only the resource / reservation / log-workspace endpoints in `_API_VERSIONS` (`arm_collector.py:35-44`). If Noor finds a Cost Management call I missed, the plan amends to either: (a) read the existing Cost Management rows directly (cleaner V1), or (b) keep the per-resource aggregation and document the deferred work. **Do not silently re-route, surface the disagreement.**
3. **Rule abstains on the negative paths E1 through E12** (§2.2). Walk each edge against the rule body in §3.5; assert the rule abstains via the documented short-circuit. Specific focus: E11 over-counting (Single-scope reservation, owner sub treated as a sibling), confirm this is a documented limitation, not a silent bug. Test #9 in §3.8 covers the cross-rule overlap; tests #2-#5 cover the abstention paths.
4. **Principal AND sibling are redacted in BOTH the rendered template AND the evidence dict.** §3.5 has FOUR `ctx.redact(...)` call sites (counting `Finding.principal`, the `principal` arg to `render`, the `sibling_sub` arg to `render`, and the `sibling_sub` evidence value). Stage-4 reviewer counts call sites in the diff and rejects if any of the four is missing. This is the exact failure mode PR #78 BLOCKING #1 caught, symmetry across `principal`, `recommendation`, and `evidence` is binding.
5. **No new write scope.** §3.7 binds `arm_collector.py:31` as the citation. Confirm the implementation does NOT modify `_ARM_SCOPES`. **Hard rule #1.**
6. **No new pydantic model and no `NormalizedDataset` field added.** §3.2 declares zero schema changes. Confirm the diff does not add fields to `AzureReservation`, `AzureResource`, or `NormalizedDataset`; if it does, reject and route to the rule that owns that field (rule 3 owns `expiry_date`, rule 4 owns `applied_scope_subscription_ids`).
7. **No catalogue YAML change.** `data/catalog/azure/*.yaml` is untouched; the rule references no SKU id.
8. **End-to-end regression test (test #10) uses the real `run_rules` engine, not a mocked rule callable.** Yuki-net pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`. If the implementer drops it to a unit-only call, reject.
9. **Cross-run instability test (test #11) covers the per-run salt assumption.** This is the PR #78 lesson for any rule whose principals carry through the playbook reporter. Reject if absent.
10. **`docs/plan.md` §6 lists the new rule.** Stage-3 plan and YAML must stay in sync per `.github/copilot-instructions.md`.
11. **Wording is conservative.** §3.6 uses "verify ... then consider"; "purchase", "buy", "must" do not appear in the recommendation_template.
12. **`scripts/generate_docs.py --check` will pass post-implementation.** All of `docs/rules.md`, `examples/demo-report.*`, `examples/demo-triage.*`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`, and the new `.j2` playbook template are committed in the same PR.
13. **Cross-rule isolation discussion in §2.4 is sound.** Confirm:
    - Overlap with `AZ.RESERVATION_UNDERUTILIZED` is intentional and complementary (test #9).
    - No fire-condition collision with `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3, future), rule 3 gates on `expiry_date` which rule 2 cannot read.
    - No fire-condition collision with `AZ.RESERVATION_SCOPE_MISMATCH` (rule 4, future), rule 4 will gate on declared-intent (tags, naming, mgmt-group structure); rule 2 gates on observed-spend. They can both fire on the same reservation if both signals trigger; that is meaningful, not duplicative.
14. **Adversarial alternative considered.** Confirm the §2.7 R1/R2/R3/R4 rejection rationale holds. In particular: is R2 (add `AzureSubscriptionCost` model now) actually rejected, or should it ship in this PR to avoid a future migration? Steelman the "ship the model now, populate it later" angle and confirm the YAGNI rejection is correct.
15. **E11 over-counting is acceptable for V1.** Steelman: would the over-count produce findings the operator dismisses as obvious-noise enough to erode trust in the rule? Or is the recommendation-wording's "verify" instruction sufficient mitigation? The plan says yes; Noor stress-tests.

If Noor returns `REQUEST_CHANGES` on any blocking item, the **Reviewer Rejection Lockout** protocol applies (Maya is locked out of revising her own plan; revision routes to a different agent, likely Yuki or Diego, per PR #78 precedent).

**Verdict format (per `.github/copilot-instructions.md`):**

```
**Stage-4 Adversarial Review -- Noor**

VERDICT: APPROVE
(or VERDICT: REQUEST_CHANGES with numbered findings)
```

This triggers `.github/workflows/squad-approve.yml` and lets the PR merge through the documented async path. **Coordinator must apply the `squad:noor` label** before posting the verdict comment so the workflow fires (lesson canonicalised in `.squad/identity/now.md` from PR #78 driving cycle).

---

## Section 5: Acceptance criteria (consolidated for stage-5 lockability)

A draft implementation PR is **mergeable** when ALL of the following hold:

1. All criteria in §3.1 ticked in the PR body checklist.
2. All §3.7 producer-path citations preserved verbatim in the PR description (or linked from this stage-3 plan PR).
3. All §3.8 tests (#1 through #12) green locally and in CI.
4. `python scripts/generate_docs.py --check` green in CI.
5. `finops-assess validate`, `ruff check`, `ruff format --check`, `mypy src`, `pytest` all green in CI on Python 3.11 AND 3.12 (matrix per `.github/workflows/ci.yml`).
6. Diff statistics:
   - Source code added: < ~120 LoC (rule body + 4 redact call sites + thresholds + scope_kind derivation).
   - Tests added: ~250-350 LoC (12 tests, mostly small fixtures).
   - YAML / docs / samples / regenerated artefacts: bytes proportional to the rule's footprint.
   - **Zero new pydantic models. Zero `NormalizedDataset` field additions. Zero `_ARM_SCOPES` byte changes. Zero catalogue YAML touches.**
7. `tests/test_engine.py:REQUIRED_RULES` extended (line 23) AND the synthetic-tenant smoke test fires the new rule at least once (per the parametrised assertion at line ~50-65).
8. Noor's stage-4 verdict comment posted with `VERDICT: APPROVE`. Auto-approve workflow fires. CI green. PR squash-merges async.

---

## Section 6: Out-of-scope (consolidated, with issue routing)

| Item | Why deferred | Owner / next step |
|---|---|---|
| Cost Management API integration in `arm_collector.py` | Larger effort; separate epic. Rule 2 ships against per-resource `monthly_cost_usd` aggregation. | File a v0.6.0 issue if not already filed; route to Diego. |
| `AzureReservation.expiry_date` field | Owned by rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`). | Rule 3 stage-3 plan (Maya). |
| `AzureReservation.applied_scope_subscription_ids` field | Owned by rule 4 (`AZ.RESERVATION_SCOPE_MISMATCH`). | Rule 4 stage-3 plan (Maya). |
| SKU-compatibility check between reservation and sibling on-demand workload | Operator-side per recommendation wording; matches `AZ.RESERVATION_UNDERUTILIZED` posture. | No future issue planned; operator-owned by design. |
| Engine post-processing of findings (R4 in §2.7) | Engine extension; not justified by this rule alone. | Defer until a second use case appears; then file. |
| `AzureSubscriptionCost` model (R2 in §2.7) | YAGNI without a producer; will land paired with the Cost Management collector. | Same v0.6.0 issue as the collector. |
| Per-billing-scope sibling grouping (E6 mitigation) | No billing-scope grouping exists in the schema; documented as a CSV-mode operator caveat in `docs/rules.md`. | Future schema work; track if operator feedback warrants. |

---

## Section 7: Producer-path citation table (single-source-of-truth, BINDING)

Stage-4 reviewer reads ONLY this table to verify citations. Re-stating §3.7 here as a single-source-of-truth artefact so the table is unambiguous when this plan is excerpted into the PR body.

| # | Claim | File | Line(s) | Producer SHA |
|---|---|---|---|---|
| 1 | `RuleContext.redact()` is the sole redaction site | `src/finops_assess/engine.py` | 70-75 | `0942872` |
| 2 | `run_rules` per-run salt default | `src/finops_assess/engine.py` | 151 | `0942872` |
| 3 | `render(template, **values)` is the sole template helper | `src/finops_assess/engine.py` | 344-352 | `0942872` |
| 4 | `AzureReservation` model definition | `src/finops_assess/models.py` | 235-250 | `0942872` |
| 5 | `AzureResource` model definition (incl. `subscription_id`, `monthly_cost_usd`) | `src/finops_assess/models.py` | 206-232 | `0942872` |
| 6 | `NormalizedDataset.azure_reservations` field | `src/finops_assess/models.py` | 384 | `0942872` |
| 7 | `NormalizedDataset.azure_resources` field | `src/finops_assess/models.py` | 383 | `0942872` |
| 8 | `_ARM_SCOPES` (read-only audience) | `src/finops_assess/collectors/arm_collector.py` | 31 | `0942872` |
| 9 | `_collect_reservations` (tenant-level GET) | `src/finops_assess/collectors/arm_collector.py` | 244-253 | `0942872` |
| 10 | Reservation row builder (`scope = appliedScopeType`, `utilization_pct = 30d aggregate`) | `src/finops_assess/collectors/arm_collector.py` | 514-534 | `0942872` |
| 11 | `azure_reservations.csv` writer columns | `src/finops_assess/collectors/arm_collector.py` | 559-569 | `0942872` |
| 12 | `azure_resources.csv` writer columns (incl. `subscription_id`, `monthly_cost_usd`) | `src/finops_assess/collectors/arm_collector.py` | 537-558 | `0942872` |
| 13 | `csv_collector` reads `azure_reservations.csv` | `src/finops_assess/collectors/csv_collector.py` | 144 | `0942872` |
| 14 | `csv_collector` reads `azure_resources.csv` | `src/finops_assess/collectors/csv_collector.py` | 143 | `0942872` |
| 15 | `AZ.RESERVATION_UNDERUTILIZED` (overlapping rule, threshold 80 %) | `src/finops_assess/rules_impl/azure_rules.py` | 160-190 | `0942872` |
| 16 | `_round` helper | `src/finops_assess/rules_impl/azure_rules.py` | 18 | `0942872` |
| 17 | `tests/test_engine.py` REQUIRED_RULES set | `tests/test_engine.py` | 23-47 | `0942872` |
| 18 | Yuki-net pattern reference (real-engine E2E test) | `tests/test_playbook_cross_run_stability.py` | 1-80 | `0942872` |
| 19 | `samples/azure_reservations.csv` carries `scope` as `Single`/`Shared`/lowercase | `samples/azure_reservations.csv` | 2-3 | `0942872` |
| 20 | `samples/azure_resources.csv` schema (current rows leave `subscription_id` empty) | `samples/azure_resources.csv` | 2-3 | `0942872` |

If any cell is wrong, the implementer flags it back to Maya before opening the impl PR (§11 ground rule). Stage-4 may amend the table in-place; corrections must follow the "Stage-3 corrections to the consensus" pattern (`.squad/agents/lead/history.md` lines 31-33).

---

## Section 8: Sign-off mechanics

| Stage | Owner | Artefact | Status |
|---|---|---|---|
| 1 | Maya | §1 above | DONE (this PR) |
| 2 | Maya | §2 above | DONE (this PR) |
| 3 | Maya (Opus 4.7) | §3 above | DONE (this PR) |
| 4 | Noor (Opus 4.7) | PR comment marker `**Stage-4 Adversarial Review -- Noor**` + `VERDICT: APPROVE` | PENDING |
| 5 | Diego (Sonnet, Opus 4.7 if §3 calls for it) | Sibling impl PR on `squad/59-impl-commitment-under-covered` | BLOCKED on stage-4 |

This plan PR is **draft** until Noor's verdict; on `APPROVE` it becomes ready, the auto-approve workflow fires, and the plan PR squash-merges. Implementation PR opens after.

**Lockout note:** if Noor REJECTs this stage-3 plan, the revision routes to a **different** agent than Maya (per the Reviewer Rejection Lockout pattern, canonicalised in `.squad/decisions.md` from PR #78 lessons). Maya cannot revise her own plan under rejection.

**Coordinator label gate (binding from `.squad/identity/now.md` PR #78 lessons):** Coordinator MUST apply the `squad:noor` label to this PR before Noor posts the verdict comment, so `.github/workflows/squad-approve.yml` fires on the verdict. Without the label the workflow correctly skips defensively. The label set for this plan PR is `squad`, `squad:maya` (author), `squad:noor` (stage-4 reviewer), `type:plan`.
