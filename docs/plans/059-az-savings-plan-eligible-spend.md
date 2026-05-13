# §11 Stage-3 Plan — `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (#59, child 1 of 5)

> **Author:** Maya (Lead / FinOps PM) — model: **Opus 4.7**
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #59 (epic) — release `release:v0.5.0`, priority `priority:p1`
> **Branch (this plan):** `squad/59-plan-maya-savings-plan-eligible`
> **Branch (implementation):** `squad/59-impl-savings-plan-eligible` (Diego, post-Noor)
> **Implementer:** Diego (primary, Azure specialist) — Yuki backup if Diego is at capacity
> **Adversarial reviewer:** Noor (stage-4)

This plan covers **one** rule from the five-rule epic: `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`. The other four rules in #59 (`AZ.COMMITMENT_UNDER_COVERED`, `AZ.COMMITMENT_RENEWAL_REVIEW`, `AZ.RESERVATION_SCOPE_MISMATCH`, `AZ.AHB_ELIGIBLE`) get their own stage-3 plans and PRs. One rule, one PR — confirmed by the epic body.

The plan format mirrors PR #72 (Maya, #61 playbook reporter) and is constrained by the post-PR-#78 binding norm in `.squad/decisions.md`: **every claim about a value the rule emits MUST cite the producer code path (file:line) that establishes it**.

---

## Section 1 — Stage-1 Research brief (Maya, ground-truth read)

### 1.1 What the Azure Benefit Recommendations API returns

- **Endpoint:** `GET https://management.azure.com/{scope}/providers/Microsoft.CostManagement/benefitRecommendations?api-version=2022-10-01` (or newer, e.g. `2024-08-01`).
  - Source: <https://learn.microsoft.com/en-us/rest/api/cost-management/benefit-recommendations/list>
  - `{scope}` is `subscriptions/{subId}`, `providers/Microsoft.Billing/billingAccounts/{billingAccountId}`, or `providers/Microsoft.Billing/billingProfiles/{billingProfileId}`.
- **Required scopes:** `Cost Management Reader` (already approved, see `docs/plan.md` §9). No new scope needed. **No write scope.**
- **Top-level shape (per recommendation):**
  - `id` — ARM-style identifier of the recommendation.
  - `properties.scope` — the scope the recommendation applies to (`Single` / `Shared`).
  - `properties.term` — `P1Y` or `P3Y`.
  - `properties.lookBackPeriod` — `Last7Days` / `Last30Days` / `Last60Days`.
  - `properties.commitmentGranularity` — `Hourly`.
  - `properties.armSkuName` — e.g. `Microsoft.Compute/virtualMachines/Standard_D4_v4` (or empty for Compute-savings-plan-wide recs).
  - `properties.recommendationDetails.totalCost` — total spend in the lookback window (USD, mixed coverage).
  - `properties.recommendationDetails.costWithoutBenefit` — on-demand spend in the lookback window (USD).
  - `properties.recommendationDetails.netSavings` — projected savings if commitment purchased (USD, lookback window basis).
  - `properties.recommendationDetails.recommendedQuantity` — recommended hourly commitment (USD/hour).
  - `properties.recommendationDetails.wastage` — projected unused commitment in the same window.
- **Important caveats for this rule:**
  - The API can return `null` recommendations when on-demand spend is too low to model; we abstain.
  - Recommendations include both the **Compute Savings Plan** (broad) and **product-specific** suggestions; a single subscription can have multiple recommendations across `term` and `lookBackPeriod`. We pick a single canonical observation per row (declared in §3.4).
  - The API only suggests Savings Plans where **on-demand spend is currently uncovered**; it already filters out spend covered by RIs/SPs. So a positive recommendation is by definition "you have uncovered spend right now".
  - **Pricing is not redistributed.** We surface the API's own `netSavings` and `recommendedQuantity` numbers; we do not paste Microsoft's Savings Plan price list. Hard rule #3.

### 1.2 What the Azure collector already ingests

- `src/finops_assess/collectors/arm_collector.py:244-253` (`_collect_reservations`) lists existing reservations from `providers/Microsoft.Capacity/reservations`. **Not a substitute** — that endpoint reports realised purchases, not recommended ones.
- `src/finops_assess/collectors/arm_collector.py:559-569` writes the existing `azure_reservations.csv` columns: `reservation_id, reservation_name, sku, scope, utilization_pct, monthly_cost_usd`. **No `costWithoutBenefit`, no `recommendedQuantity`, no `netSavings`** — these fields are not available on the reservation list endpoint.
- `src/finops_assess/pricing.py:153,322` defines `AzureCommitmentObservation` and `AzureCommitmentDataset` for **catalogue / pricing-bench** observations from the Retail Prices API. That is a separate concern (price discovery for the catalogue mirror), not per-tenant findings, and the rule engine never consumes those types.
- **Conclusion:** the existing collector and dataset do **not** cover the Benefit Recommendations surface. A new normalised input row type is required (see §3.2).

### 1.3 Catalogue SKUs the rule references

- **None.** Savings Plans are not modelled as catalogue SKUs in `data/catalog/azure/*.yaml` today, and we do not add one in this PR. They cut across many SKUs and have no `list_price_usd_month` we could anchor to without redistributing Microsoft's price tables (hard rule #3 / #5).
- The rule body references API-derived dollar values verbatim; the catalogue is unaffected.

---

## Section 2 — Stage-2 Rubberduck (Maya, plain-English walkthrough)

### 2.1 What the rule is supposed to say

> "For scope X, your last-N-days uncovered on-demand spend is ${costWithoutBenefit}. Azure's Benefit Recommendations API estimates that an hourly Savings Plan commitment of ${recommendedQuantity}/hour for term ${term} would have saved ${netSavings} over the same window. Verify the workload is steady-state and not an anomaly, then consider purchasing the Savings Plan."

That is conservative and faithful to Microsoft's own data. The rule does **not** tell the operator a number to spend; it surfaces the API's own number.

### 2.2 What could go wrong (edge cases)

| # | Edge | Behaviour required |
|---|------|---|
| E1 | API returns no recommendations for the scope (no SP-eligible spend, all spend already covered, or scope below modelling threshold) | Rule emits no finding (abstain). The collector writes zero rows for that scope. |
| E2 | API returns a recommendation with `netSavings <= 0` or `recommendationDetails == null` | Abstain. Negative or null savings are not actionable signal. |
| E3 | `costWithoutBenefit` exists but is below a small threshold (e.g. `< $50`/lookback-window) | Abstain. Below-threshold uncovered spend produces noise; the API itself sometimes returns micro-recommendations when scoped wide. |
| E4 | `lookBackPeriod` is `Last7Days` (insufficient signal for a 1-3-year commitment) | Abstain. We require `Last30Days` or `Last60Days`. Conservative wording is moot if the window is too short. |
| E5 | Multiple recommendations for the same scope (one per `term × lookBackPeriod` combination) | Collector emits all rows; rule de-duplicates on `(scope, term)` and prefers `Last60Days > Last30Days > Last7Days`. Single finding per `(scope, term)` pair. |
| E6 | Subscription is a Dev/Test offer where on-demand is the explicit policy | Rule does not auto-suppress (the operator still owns the call), but the recommendation wording uses "verify the workload is steady-state" so a Dev/Test operator can document the exception and move on. |
| E7 | Mixed RI + SP coverage (some workloads on RI, residual on-demand recommended for SP) | The API already excludes RI-covered hours from `costWithoutBenefit`; we trust its accounting. Rule wording should not claim "all your spend is uncovered" — it says "the uncovered residual is ..." |
| E8 | Partial-region rollouts (recommendation for a region the operator is sunsetting) | Recommendation includes `armSkuName` and `scope`. We surface both in the evidence so the operator can recognise a region-specific stale signal. Rule does not auto-suppress; abstaining here would over-fit. |

### 2.3 False-positive risks

- **Legacy workloads with intentional on-demand for elasticity** (autoscale clusters, batch). The recommendation looks accurate on the lookback window but commits the operator to baseline that may evaporate when the next workload spike resets. **Mitigation:** "verify the workload is steady-state" wording + surface `lookBackPeriod` in evidence + leave the decision to the operator.
- **Dev/test on-demand by policy** (audit/compliance reasons; some teams run dev workloads on PAYG to avoid year-long commitments). **Mitigation:** wording asks for verification, not action; the existing `AZ.DEV_TEST_SUB_MISMATCH` rule already catches the structural side of this.
- **Recommendation churn** — the Benefit Recommendations API can change its top-pick recommendation between collection runs as workload patterns shift. This is a feature, not a bug, but operators using a ticketing reporter will see the same scope re-recommended with different numbers. **Mitigation:** the rule emits one finding per `(scope, term)` and includes `lookBack_period` in evidence so a downstream dedup key can ignore numerical jitter.

### 2.4 Conservative recommendation wording (drafted)

> "Scope `{principal}` shows uncovered on-demand spend of `${cost_without_benefit_usd}` over `{lookback_period}`. Azure's Benefit Recommendations API projects `${net_savings_usd}` in savings if you purchase a `{term}` Savings Plan with an hourly commit of `${recommended_hourly_commit_usd}`. Verify the workload is steady-state and not the trailing edge of a one-off project, then consider the commitment purchase."

This is verb-conservative ("verify ... then consider"), mirrors the existing `AZ.RESERVATION_UNDERUTILIZED` voice ("Exchange or shrink the commitment at next renewal."), and never tells the operator to spend money without due diligence.

### 2.5 Security implications

- **No new scope.** Cost Management Reader is already requested.
- **No PII surfaced.** The principal is the recommendation's scope (an Azure subscription / billing-account ARN). It MUST flow through `ctx.redact()` per hard rule #4. See producer-path citation in §3.5.
- **No third-party copyrighted material.** All numbers come from the operator's own tenant via the API; the rule body uses our own paraphrase. No Microsoft pricing-page text is bundled.

### 2.6 Alternatives considered (rejected)

- **(R1) Compute eligibility ourselves from `azure_resources.csv` + `azure_reservations.csv` without calling the Benefit Recommendations API.** Rejected: we would re-implement Microsoft's modelling (hourly bucketing, term-vs-lookback math, region/family normalisation) with worse data than they have. The whole reason the API exists is that this calculation is non-trivial.
- **(R2) Add a catalogue entry for "Savings Plan Compute"** so the rule can reference a SKU. Rejected: Savings Plans are not priced per SKU and have no `list_price_usd_month` we can publish without redistributing Microsoft pricing pages (hard rule #3). Catalogue stays out of this PR.
- **(R3) Reuse the `AzureReservation` model** by adding optional `cost_without_benefit_usd`, `recommended_hourly_commit_usd`, `net_savings_usd`, `lookback_period`, `term`. Rejected: `AzureReservation` describes a **realised** purchase, with its own primary key (`reservation_id`); a recommendation has a **distinct** primary key (`recommendation_id`) and a separate join surface. Conflating them produces a model where 80 % of fields are mutually exclusive and pydantic `extra="forbid"` becomes a footgun.

---

## Section 3 — Stage-3 plan proper (file-level checklist)

### 3.1 Acceptance criteria (small enough for ONE PR)

- [ ] New pydantic model `AzureBenefitRecommendation` in `src/finops_assess/models.py` with `extra="forbid"`.
- [ ] `NormalizedDataset.azure_benefit_recommendations: list[AzureBenefitRecommendation]` added (`src/finops_assess/models.py` near line 384).
- [ ] CSV collector reads `azure_benefit_recommendations.csv` (`src/finops_assess/collectors/csv_collector.py`).
- [ ] ARM collector adds `_collect_benefit_recommendations()` and writes `azure_benefit_recommendations.csv` (`src/finops_assess/collectors/arm_collector.py`).
- [ ] YAML rule entry added to `data/rules/azure.yaml` and packaged mirror at `src/finops_assess/data/rules/azure.yaml`.
- [ ] Rule implementation `savings_plan_eligible_spend` registered in `src/finops_assess/rules_impl/azure_rules.py`.
- [ ] `samples/azure_benefit_recommendations.csv` added (1 row that fires, 1 row that abstains).
- [ ] Unit tests in `tests/test_az_savings_plan_eligible.py` (positive, negative, abstain-on-missing-data, redaction-on-by-default).
- [ ] End-to-end regression test (real `run_rules` engine, not a mocked rule call) — pattern reference `tests/test_playbook_cross_run_stability.py`.
- [ ] `tests/test_engine.py` `REQUIRED_RULES` set includes `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`.
- [ ] `tests/test_csv_collector.py` covers loading the new file.
- [ ] `docs/plan.md` §6 lists the new rule under Azure rules.
- [ ] `python scripts/generate_docs.py` regenerates `docs/rules.md`, `examples/demo-report.{json,html,csv}`, `examples/demo-triage.{json,csv}`, and the playbook artefacts; all regenerated bytes committed.
- [ ] `python scripts/generate_docs.py --check` passes locally and in CI.
- [ ] All gates green: `finops-assess validate`, `ruff check`, `ruff format --check`, `mypy src`, `pytest`.
- [ ] No new scope requested in `arm_collector.py` (`_ARM_SCOPES` unchanged).
- [ ] No catalogue YAML changes in `data/catalog/azure/*.yaml`.

If the implementation cannot meet **all** criteria in one PR, decompose further (e.g. split the new pydantic model + collector wiring into a thin foundation PR, then the rule + tests in a follow-up). This is the implementer's call at stage 5; the lockable signal is "draft PR is green and < ~600 LoC product code".

### 3.2 Schema additions — `src/finops_assess/models.py`

New model (placed after `AzureLogWorkspace`, before the `GitHubSeatType` literal):

```python
class AzureBenefitRecommendation(BaseModel):
    """A normalised Azure Benefit Recommendations API observation.

    Each row represents one (scope, term, lookback_period) recommendation
    returned by the Cost Management ``benefitRecommendations`` endpoint.
    Rules consume these to surface uncovered on-demand spend that could
    be moved under a Savings Plan or Reservation commitment.

    The collector emits one row per unique (scope, term, lookback_period);
    the rule de-duplicates to one finding per (scope, term).
    """

    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    scope_kind: Literal["Single", "Shared"] | None = None
    term: Literal["P1Y", "P3Y"]
    lookback_period: Literal["Last7Days", "Last30Days", "Last60Days"]
    arm_sku_name: str | None = None
    cost_without_benefit_usd: float | None = Field(default=None, ge=0)
    recommended_hourly_commit_usd: float | None = Field(default=None, ge=0)
    net_savings_usd: float | None = Field(default=None, ge=0)
    wastage_usd: float | None = Field(default=None, ge=0)
    benefit_kind: Literal["SavingsPlan", "Reservation"] = "SavingsPlan"
```

Add to `NormalizedDataset` (after `azure_log_workspaces`, ~line 385):

```python
azure_benefit_recommendations: list[AzureBenefitRecommendation] = Field(default_factory=list)
```

### 3.3 CSV collector — `src/finops_assess/collectors/csv_collector.py`

Three changes:

1. Import `AzureBenefitRecommendation` (~line 36).
2. Add to the docstring file list (~line 9): `* ``azure_benefit_recommendations.csv`` — :class:`AzureBenefitRecommendation` fields.`
3. Add to the `NormalizedDataset(...)` constructor call (~line 144):
   ```python
   azure_benefit_recommendations=_read_csv(
       input_dir / "azure_benefit_recommendations.csv", AzureBenefitRecommendation
   ),
   ```

The strict-column contract (`extra="forbid"`) applies; the existing `_coerce_row` helper handles BOMs and empty cells uniformly.

### 3.4 ARM collector — `src/finops_assess/collectors/arm_collector.py`

Three changes:

1. Add API version (~line 35-44):
   ```python
   "benefitRecommendations": "2022-10-01",
   ```
2. Add a `_collect_benefit_recommendations(client, sub_id)` helper sibling to `_collect_reservations` (after line 253). Iterates the per-subscription scope; if the operator wants billing-account scope they can layer it later (out of scope for this PR — separate issue).
3. Inside `collect_arm`, after the `_collect_reservations` loop (~line 508), add a benefit-recommendations loop that picks the highest-`lookBackPeriod` recommendation per `(scope, term)` and writes rows. Then write `azure_benefit_recommendations.csv` next to the existing reservations CSV (~line 569) with columns matching the model.

**Canonical observation rule (locked to avoid implementer drift):** if the API returns multiple recommendations for the same `(scope, term)`, the collector keeps the one with the longest `lookBackPeriod` (preference order: `Last60Days > Last30Days > Last7Days`). If two rows tie, keep the one with the higher `netSavings`.

### 3.5 Rule implementation — `src/finops_assess/rules_impl/azure_rules.py`

```python
_SP_MIN_LOOKBACK_PERIODS = {"Last30Days", "Last60Days"}
_SP_MIN_UNCOVERED_USD = 50.0


@register("AZ.SAVINGS_PLAN_ELIGIBLE_SPEND")
def savings_plan_eligible_spend(ctx: RuleContext) -> Iterable[Finding]:
    """Flag scopes with uncovered on-demand spend that the Azure Benefit
    Recommendations API projects could be reduced via a Savings Plan."""
    seen: set[tuple[str, str]] = set()
    for rec in ctx.dataset.azure_benefit_recommendations:
        if rec.lookback_period not in _SP_MIN_LOOKBACK_PERIODS:
            continue  # E4
        if rec.net_savings_usd is None or rec.net_savings_usd <= 0:
            continue  # E2
        if rec.cost_without_benefit_usd is None:
            continue  # E1 / null path
        if rec.cost_without_benefit_usd < _SP_MIN_UNCOVERED_USD:
            continue  # E3
        key = (rec.scope, rec.term)
        if key in seen:
            continue  # E5 dedup (collector already prefers longest lookback)
        seen.add(key)

        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(rec.scope),
            current_sku=None,
            estimated_monthly_savings_usd=_round(rec.net_savings_usd),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(rec.scope),
                cost_without_benefit_usd=round(rec.cost_without_benefit_usd, 2),
                lookback_period=rec.lookback_period,
                net_savings_usd=round(rec.net_savings_usd, 2),
                term=rec.term,
                recommended_hourly_commit_usd=round(
                    rec.recommended_hourly_commit_usd or 0.0, 4
                ),
            ),
            evidence={
                "scope_kind": rec.scope_kind,
                "term": rec.term,
                "lookback_period": rec.lookback_period,
                "arm_sku_name": rec.arm_sku_name,
                "cost_without_benefit_usd": rec.cost_without_benefit_usd,
                "recommended_hourly_commit_usd": rec.recommended_hourly_commit_usd,
                "net_savings_usd": rec.net_savings_usd,
                "wastage_usd": rec.wastage_usd,
                "benefit_kind": rec.benefit_kind,
            },
        )
```

`_round` already exists at line 18. `render` is the existing template helper. **Both invocations of `rec.scope` MUST go through `ctx.redact()`** — see §3.7 binding citation.

### 3.6 YAML rule entry — `data/rules/azure.yaml` (and packaged mirror)

```yaml
- id: AZ.SAVINGS_PLAN_ELIGIBLE_SPEND
  surface: azure
  severity: medium
  summary: Scope has uncovered on-demand spend the Benefit Recommendations API would move under a Savings Plan.
  recommendation_template: >
    Scope {principal} shows uncovered on-demand spend of
    ${cost_without_benefit_usd} over {lookback_period}. Azure's Benefit
    Recommendations API projects ${net_savings_usd} in savings if you
    purchase a {term} Savings Plan with an hourly commit of
    ${recommended_hourly_commit_usd}. Verify the workload is steady-state
    and not the trailing edge of a one-off project, then consider the
    commitment purchase.
```

Severity choice: `medium`. Rationale: it's a savings opportunity, not a hard waste signal — not `high` (idle resources), not `low` (cosmetic). Same tier as `AZ.LOG_ANALYTICS_OVERINGEST`, which is the closest peer.

**Sync the packaged mirror** at `src/finops_assess/data/rules/azure.yaml` in the same commit (catalogue YAML is shipped with the wheel; the mirror under `src/finops_assess/data/` is the importlib-resources copy and must stay byte-equal to `data/rules/azure.yaml`). Pattern reference: `f54177a` (Maya, M365 docs-voice mirror sync).

### 3.7 Producer-path citations (BINDING per post-PR-#78 norm)

Every claim this rule makes about a value is anchored to the producer code path that establishes the value. Stage-4 reviewers reject the plan if any cell below is wrong.

| Claim | Producer (file:line) | What the producer does |
|---|---|---|
| `principal` is salted-hashed by default | `src/finops_assess/engine.py:70-75` (`RuleContext.redact`) | `if redact_pii: return f"sha256:{sha256(salt+':'+principal)[:16]}"`. The rule MUST call `ctx.redact(rec.scope)` (twice in §3.5: once for the `Finding.principal`, once for the rendered template). |
| `principal` is **not stable across runs** with default redaction | `src/finops_assess/engine.py:151` (`run_rules`) | `salt_value = salt if salt is not None else secrets.token_hex(16)`. The CLI does not flow a stable salt today. Therefore any downstream consumer of this finding (playbook reporter, FOCUS-aligned exporter) inherits the existing per-surface stability declaration in `examples/playbook.jsonl.manifest.json` — **no new reporter contract** is introduced by this rule. Issue #73 is the engine-level fix; this plan does not block on it. |
| `principal` is the recommendation **scope** (subscription/billing-account ARN), not a user identifier | `src/finops_assess/models.py:235-250` (`AzureReservation`) — same convention as the realised-reservation row, where `reservation_id` is the principal | The new `AzureBenefitRecommendation.scope` field carries the same shape (an ARM ID); redaction works the same way. |
| `azure_benefit_recommendations.csv` is read by the CSV collector | `src/finops_assess/collectors/csv_collector.py:144` (existing `azure_reservations.csv` line) | This plan adds a sibling line; the strict-column contract from `_coerce_row` (~lines 54-90) applies unchanged. |
| The ARM collector uses **read-only** scopes | `src/finops_assess/collectors/arm_collector.py:31` (`_ARM_SCOPES = ["https://management.azure.com/.default"]`) | This plan does not modify `_ARM_SCOPES`. Cost Management Reader is granted on the existing scope; no new scope is requested. **Hard rule #1 upheld.** |
| The reservation collector pattern this implementation mirrors | `src/finops_assess/collectors/arm_collector.py:244-253` (`_collect_reservations`) | Tenant-level GET, paginated via `client.list_all`, gracefully degrades on exception. The new `_collect_benefit_recommendations` follows the same shape but is per-subscription scoped. |
| The CSV writer pattern | `src/finops_assess/collectors/arm_collector.py:559-569` (existing `azure_reservations.csv` write) | The new `azure_benefit_recommendations.csv` write mirrors columns 1:1 with the model field order. |
| `Finding.evidence` is a free-form dict surfaced verbatim by reporters | `src/finops_assess/models.py:Finding` definition + `src/finops_assess/reporters/json_reporter.py` | All evidence values in §3.5 are non-PII (numerical / API-derived strings). No additional redaction needed for evidence. |

If any of these citations is wrong at implementation time, the implementer flags it back to Maya and the plan is amended — never silently overridden (§11 ground rule).

### 3.8 Test plan

| # | Test name | File | Asserts |
|---|---|---|---|
| 1 | `test_savings_plan_fires_on_eligible_spend` | `tests/test_az_savings_plan_eligible.py` | Synthetic `AzureBenefitRecommendation` with `cost_without_benefit_usd=1000.0`, `net_savings_usd=120.0`, `term="P1Y"`, `lookback_period="Last30Days"` produces exactly one finding with `rule_id="AZ.SAVINGS_PLAN_ELIGIBLE_SPEND"` and `severity="medium"`. |
| 2 | `test_savings_plan_abstains_when_savings_zero` | same | `net_savings_usd=0.0` → no finding. |
| 3 | `test_savings_plan_abstains_on_short_lookback` | same | `lookback_period="Last7Days"` → no finding. |
| 4 | `test_savings_plan_abstains_on_micro_uncovered_spend` | same | `cost_without_benefit_usd=10.0` (< $50 threshold) → no finding. |
| 5 | `test_savings_plan_abstains_on_null_signal` | same | `cost_without_benefit_usd=None` → no finding. |
| 6 | `test_savings_plan_dedups_per_scope_and_term` | same | Two rows for `(scope=X, term="P1Y")` with different `lookback_period` → one finding (collector preference order asserted via fixture). |
| 7 | `test_savings_plan_redacts_principal_by_default` | same | With `redact_pii=True` (default), `finding.principal` starts with `sha256:` and `len(finding.principal) == 23`. **Cites `engine.py:70-75` in the test docstring.** |
| 8 | `test_savings_plan_emits_cleartext_with_redaction_off` | same | With `redact_pii=False`, `finding.principal == rec.scope` exactly. |
| 9 | `test_savings_plan_e2e_through_run_rules` | same | End-to-end regression: builds `NormalizedDataset` with one fires-row + one abstains-row, calls real `run_rules(...)`, asserts exactly one finding emerges with the expected rule_id. **Pattern reference: `tests/test_playbook_cross_run_stability.py:42-60`** — uses real engine, not a mocked rule callable. This is the Yuki-net that caught BLOCKING #1 in PR #78. |
| 10 | extend `tests/test_engine.py:REQUIRED_RULES` | `tests/test_engine.py` | Add `"AZ.SAVINGS_PLAN_ELIGIBLE_SPEND"` to the set so the synthetic-tenant smoke test asserts the rule is registered. The set lives at line 23 today. |
| 11 | extend `tests/test_csv_collector.py` | `tests/test_csv_collector.py` | Assert `azure_benefit_recommendations.csv` round-trips correctly through the strict-column loader. |

**Fixtures:** all synthetic rows constructed in-test (no on-disk fixture files required for tests 1-9). The on-disk `samples/azure_benefit_recommendations.csv` is for `finops-assess run --inputs samples/` and the demo-report regen.

### 3.9 Doc regen

The implementer runs `python scripts/generate_docs.py` once and commits **all** regenerated artefacts in the same PR:

- `docs/rules.md` — auto-generated from `data/rules/azure.yaml`. Will gain a new entry for `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`.
- `examples/demo-report.{json,html,csv}` — will likely gain a finding row if the demo dataset includes a positive recommendation. If the demo dataset is updated to include one, that's a deliberate plan choice (see below).
- `examples/demo-triage.{json,csv}` — same.
- `examples/playbook.jsonl{,.manifest.json}` — same; the playbook reporter renders any rule with a registered `.j2` template. **A new template** `src/finops_assess/data/playbooks/AZ.SAVINGS_PLAN_ELIGIBLE_SPEND.j2` is required (LF-pinned by the existing `.gitattributes` rule `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`). Template body is a paraphrase of the recommendation; no new schema.
- `examples/focus-aligned.csv{,.manifest.json}` — the FOCUS-aligned exporter is Azure-only today and will pick up the new finding automatically; bytes regenerate.

`python scripts/generate_docs.py --check` is the docs-freshness gate (`.github/workflows/docs.yml`); it WILL fail without the regen commit.

### 3.10 `data/personas.yaml` impact

**None.** Personas inherit licensing rules (`M365.*` and `GH.COPILOT_*`). Cost-discipline rules like `AZ.*` apply to resources, not user identities. Same posture as every existing `AZ.*` rule. No `data/personas.yaml` change in this PR.

### 3.11 `samples/azure_benefit_recommendations.csv`

```
recommendation_id,scope,scope_kind,term,lookback_period,arm_sku_name,cost_without_benefit_usd,recommended_hourly_commit_usd,net_savings_usd,wastage_usd,benefit_kind
/providers/Microsoft.CostManagement/benefitRecommendations/rec-001,/subscriptions/00000000-0000-0000-0000-000000000001,Single,P1Y,Last30Days,Microsoft.Compute/virtualMachines/Standard_D4s_v5,1450.00,1.85,180.50,12.40,SavingsPlan
/providers/Microsoft.CostManagement/benefitRecommendations/rec-002,/subscriptions/00000000-0000-0000-0000-000000000002,Single,P1Y,Last7Days,Microsoft.Compute/virtualMachines/Standard_D2s_v5,40.00,0.10,2.10,0.00,SavingsPlan
```

Row 1 fires (E1-E5 all pass). Row 2 abstains (`Last7Days` → E4 + uncovered spend below $50 → E3, both reasons; documents the negative path).

### 3.12 `docs/plan.md` §6 update

Add to the Azure rules block (~line 215, after `AZ.LOG_ANALYTICS_OVERINGEST`):

```
- `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND`: scope with uncovered on-demand spend a Savings Plan would cover (Benefit Recommendations API).
```

Keep the §6 entry one line; the full rule body is `docs/rules.md` (auto-generated).

### 3.13 Out of scope (and why)

- **Live ARM call against a real tenant.** Stage 5 is unit + e2e with synthetic data. Live verification is the operator's job at `finops-assess run --collector arm`; the test plan does not require a live call.
- **Billing-account / billing-profile scope.** The collector iterates per-subscription. Higher-scope recommendations (`Microsoft.Billing/billingAccounts/...`) are a follow-up issue (Maya files at PR-open time if not already filed).
- **Reservation-vs-Savings-Plan A/B suggestion.** The API can return both `Reservation` and `SavingsPlan` benefit kinds; this rule surfaces both via `benefit_kind` in evidence but does not split into two rules. A future `AZ.RESERVATION_ELIGIBLE_SPEND` could carve out `benefit_kind="Reservation"` if operators ask.
- **The other four rules in #59.** Each gets its own stage-3 plan. `AZ.COMMITMENT_RENEWAL_REVIEW` will need an additional `AzureReservation.expiry_date` field; `AZ.AHB_ELIGIBLE` will need `AzureResource.os_type` and `license_type`. Those are larger schema changes and deserve their own discussion.

### 3.14 Cross-cutting decisions worth flagging

1. **New normalised input row type** is required (`AzureBenefitRecommendation`). Confirmed in §1.2 — the existing reservation/cost data does NOT cover this surface. The Scribe should canonicalise this finding so future "do we need a new input row?" questions skip the search.
2. **No catalogue change.** Savings Plans are not catalogue SKUs. Confirmed in §1.3.
3. **No engine change.** The rule is a pure additive registration; `RuleContext` is consumed unchanged.
4. **No new scope.** Cost Management Reader on the existing `https://management.azure.com/.default` audience is sufficient. Hard rule #1 upheld via `arm_collector.py:31` citation.

---

## Section 4 — Stage-4 ask (Noor, adversarial reviewer)

**Reviewer:** Noor (squad:noor), model **Opus 4.7** mandatory (per §11; never downgrade).

**Specific invariants Noor must verify (steelman against the plan, do not just agree):**

1. **Producer-path citations are correct.** Open every cell in §3.7 against the repo at the latest `main` SHA (currently `0942872`). Reject if any line number is wrong or any claim is not what the producer actually does.
2. **Rule does not fire on the negative paths E1-E8.** Walk each edge in §2.2 against the rule body in §3.5; assert the rule abstains via the documented short-circuit. Specifically:
   - `net_savings_usd <= 0` → abstain (E2).
   - `cost_without_benefit_usd < $50` → abstain (E3).
   - `lookback_period == "Last7Days"` → abstain (E4).
   - Two rows for `(scope, term)` → one finding (E5 dedup).
3. **Principal in finding is redacted.** §3.5 calls `ctx.redact(rec.scope)` twice — once for `Finding.principal`, once inside `render(...)`. Both call sites must redact; assert by reading the rule body, then assert by reading test #7.
4. **No new write scope.** §3.7 binds `arm_collector.py:31` as the citation. Confirm the implementation does NOT modify `_ARM_SCOPES`.
5. **No catalogue YAML change.** `data/catalog/azure/*.yaml` is untouched; the rule references no SKU id.
6. **End-to-end regression test (test #9) uses the real `run_rules` engine, not a mocked rule callable.** This is the Yuki-net that caught BLOCKING #1 in PR #78; if the implementer drops it to a unit-only call, reject.
7. **`docs/plan.md` §6 lists the new rule.** Stage-3 plan and YAML must stay in sync per `.github/copilot-instructions.md`.
8. **Wording is conservative.** §3.6 uses "verify ... then consider"; "purchase" / "buy" / "must" do not appear in the recommendation_template.
9. **`scripts/generate_docs.py --check` will pass post-implementation.** All of `docs/rules.md`, `examples/demo-report.*`, `examples/demo-triage.*`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`, and the new `.j2` playbook template are committed in the same PR.
10. **Adversarial alternative considered:** could this rule be implemented as a derived view over `azure_resources.csv` + `azure_reservations.csv` (alternative R1 in §2.6)? Confirm the rejection rationale holds — Microsoft's Benefit Recommendations API does the modelling that we shouldn't reimplement.

If Noor returns `REQUEST_CHANGES` on any blocking item, the **Reviewer Rejection Lockout** protocol applies (Maya is locked out of revising her own plan; revision routes to a different agent — likely Yuki or Diego).

**Verdict format (per `.github/copilot-instructions.md`):**

```
**Stage-4 Adversarial Review — Noor**

VERDICT: APPROVE
(or VERDICT: REQUEST_CHANGES with numbered findings)
```

This triggers `.github/workflows/squad-approve.yml` and lets the PR merge through the documented async path.

---

## Section 5 — Stage-5 plan (Diego primary, Yuki backup)

**Implementer:** Diego (Azure compute / storage / SQL / Cost Mgmt specialist). Diego owns:

- The new `AzureBenefitRecommendation` model.
- The ARM collector additions (he has the pattern muscle from existing `_collect_reservations`).
- The rule registration.
- The packaged-mirror sync at `src/finops_assess/data/rules/azure.yaml`.
- The new `.j2` playbook template (LF-pinned).
- `docs/plan.md` §6 line-add.
- All gates: validate, ruff, mypy, pytest, generate_docs --check.

**Backup:** Yuki (tester / quality / CI matrix owner). If Diego is at capacity from PR #82 follow-ups, Yuki picks up; she will likely lean harder on test #9 (e2e regression net) since that's her recent muscle from PR #78.

**Branch:** `squad/59-impl-savings-plan-eligible`. Open as draft, link this PR + issue #59. Reference the §11 stage-3 plan PR (this PR) in the implementation PR description.

**Lockout note:** if Noor REJECTs this stage-3 plan, the revision routes to a **different** agent than Maya (per the Reviewer Rejection Lockout pattern, canonicalised in `.squad/decisions.md` from PR #78 lessons). Maya cannot revise her own plan under rejection.

---

## Section 6 — Sign-off mechanics

| Stage | Owner | Artefact | Status |
|---|---|---|---|
| 1 | Maya | §1 above | DONE (this PR) |
| 2 | Maya | §2 above | DONE (this PR) |
| 3 | Maya (Opus 4.7) | §3 above | DONE (this PR) |
| 4 | Noor (Opus 4.7) | PR comment marker `**Stage-4 Adversarial Review — Noor**` + `VERDICT: APPROVE` | PENDING |
| 5 | Diego (Sonnet, Opus 4.7 if §3 calls for it) | Sibling impl PR on `squad/59-impl-savings-plan-eligible` | BLOCKED on stage-4 |

This plan PR is **draft** until Noor's verdict; on `APPROVE` it becomes ready, the auto-approve workflow fires, and the plan PR squash-merges. Implementation PR opens after.
