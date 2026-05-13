# §11 Stage-3 Plan: `AZ.COMMITMENT_RENEWAL_REVIEW` (#59, child 3 of 5)

> **Author:** Maya (Lead / FinOps PM), model: **Opus 4.7**
> **Status:** stage-3 plan, awaiting stage-4 adversarial sign-off (Noor)
> **Issue:** #59 (epic), release `release:v0.5.0`, priority `priority:p1`
> **Branch (this plan):** `squad/59-plan-maya-commitment-renewal-review`
> **Branch (implementation):** `squad/59-impl-commitment-renewal-review` (Diego, post-Noor)
> **Implementer:** Diego (primary, Azure specialist), Yuki backup if Diego is at capacity
> **Adversarial reviewer:** Noor (stage-4)
> **Sibling plans:** `docs/plans/059-az-savings-plan-eligible-spend.md` (rule 1/5, MERGED PR #83, impl in flight on PR #85), `docs/plans/059-az-commitment-under-covered.md` (rule 2/5, MERGED PR #84)
> **Producer-path SHA:** `328986e` (current `main` after PR #84 merge)

This plan covers **one** rule from the five-rule epic: `AZ.COMMITMENT_RENEWAL_REVIEW`. Rules 1 and 2 are already through stage-3 (PR #83 and PR #84 merged). Rules 4 (`AZ.RESERVATION_SCOPE_MISMATCH`) and 5 (`AZ.AHB_ELIGIBLE`) get their own stage-3 plans and PRs. One rule, one PR, confirmed by the epic body.

The plan format mirrors the rule-1 and rule-2 plans and the binding norm canonicalised in `.squad/decisions.md` post-PR-#78: **every claim about a value the rule emits MUST cite the producer code path (file:line) that establishes it.**

**Headlines (different from rules 1 and 2):**

1. This rule introduces a **schema change** on the existing `AzureReservation` model (two new optional fields). Rule 1 added a brand-new model; rule 2 added zero schema. Rule 3 sits in the middle.
2. The "no renewal signal" semantics resolve to a **first-class API field**, not a derived heuristic. The Microsoft.Capacity reservations LIST endpoint exposes `properties.renew` (boolean) and `properties.userFriendlyRenewState`. See §1.1 and §2.7.
3. **Two stage-3 corrections** vs the framing carried in the epic body / `.squad/identity/now.md` / the Lead handoff brief. Both are surfaced explicitly in §1.4 so they can be inspected and rejected if Noor disagrees, never silently overridden (§11 ground rule).

---

## Section 1: Stage-1 Research brief (Maya, ground-truth read)

### 1.1 What the Microsoft.Capacity reservations LIST endpoint actually returns

I read the Microsoft Learn reference for the `reservation list-all` operation directly (URL below) before writing this section. The ARM collector already calls this exact endpoint at the api-version this rule needs.

- **Endpoint:** `GET https://management.azure.com/providers/Microsoft.Capacity/reservations?api-version=2022-11-01`
- **Source:** <https://learn.microsoft.com/en-us/rest/api/reserved-vm-instances/reservation/list-all>
- **Required scope:** `Reservation Reader` (or `Reader` on the reservation order). Already implicit in the existing ARM collector posture; **no new scope, no new audience, hard rule #1 upheld** (`src/finops_assess/collectors/arm_collector.py:31`).
- **Per-reservation `properties` shape (2022-11-01), fields rule 3 cares about:**
  - `expiryDate` -- ISO 8601 date string `YYYY-MM-DD` (e.g. `"2023-07-21"`).
  - `expiryDateTime` -- ISO 8601 datetime (e.g. `"2023-07-21T22:46:32.7632798Z"`). **Date-only is the right granularity for a "near expiry" gate**; datetime adds noise.
  - `renew` -- **boolean**. `true` if the operator has configured the reservation to auto-renew at expiry; `false` otherwise. **This is the canonical "renewal signal" field; it does not need to be inferred.**
  - `renewSource` -- ARM ID of the predecessor reservation, populated when this reservation was itself created as a renewal. Not consumed by rule 3 directly; a future rule could use it to detect "lapsed renewal chains".
  - `userFriendlyRenewState` -- string mirror of `renew`, e.g. `"Off"` / `"On"`. Not consumed by rule 3 (we use the boolean directly).
  - `term` -- `"P1Y"` or `"P3Y"`. Surfaced in evidence so the operator can size the renewal decision.
  - `displayProvisioningState` -- e.g. `"Succeeded"`, `"Cancelled"`, `"Failed"`, `"Expired"`. The collector should write only `"Succeeded"` rows into the CSV (cancelled / failed / already-expired reservations are not actionable as "renewal review"); see §3.4.
  - `purchaseDate` -- not consumed by rule 3.
- **List-result `summary` shape:** the response also contains an aggregate `summary.expiringCount`. Tempting to use as a tenant-wide signal, but it is a count of all reservations expiring within an unspecified Azure-internal window and conflates terms / scopes / renewal-state. Rule 3 ignores `summary` and computes its own gate from per-row `expiryDate` + `renew`. (Rejected as a signal source in §2.7.)

### 1.2 What the existing schema and collector already give us

I read the producer code on `main` SHA `328986e` end-to-end before writing this section. The bullets below are **producer-grounded**, not API-spec-grounded:

- `AzureReservation` (`src/finops_assess/models.py:235-250`): carries `reservation_id` (PK), `reservation_name`, `sku`, `scope`, `utilization_pct` (0-100, nullable), `monthly_cost_usd` (nullable). **No `expiry_date`. No `auto_renew` / `renew`.** Both fields are absent from the schema today; rule 3 must add them.
- The ARM collector already calls the right endpoint at the right api-version. `_API_VERSIONS["reservations"] = "2022-11-01"` at `src/finops_assess/collectors/arm_collector.py:40`, and `_collect_reservations` issues `GET .../providers/Microsoft.Capacity/reservations?api-version=2022-11-01` at `arm_collector.py:244-253`. The response body `props` is already in scope at the row builder (`arm_collector.py:511-534`); we only need to read two more keys (`props.get("expiryDate")` and `props.get("renew")`) and write two more CSV columns.
- The CSV collector reads `azure_reservations.csv` into `AzureReservation` rows at `src/finops_assess/collectors/csv_collector.py:144`. Adding two columns to the strict-column header is a backward-compatible change for fresh CSVs; the loader's strict-column gate accepts rows with **fewer** cells than the header (defaulting missing columns to `None`) per the docstring at `csv_collector.py:54-62`. **Operators with pre-existing `azure_reservations.csv` files will get `expiry_date is None` and `auto_renew is None` for legacy rows; rule 3 abstains on those (E2 / E5 in §2.2). This is the desired degrade-gracefully posture.**
- `pricing.py:249-254` already declares an `expiry_date: str | None = Field(default=None, min_length=10, max_length=10)` shape on a different commitment-observation model. **Reuse the same field type and constraints on `AzureReservation` for visual consistency** (§3.2). Same module also documents the ISO 8601 YYYY-MM-DD convention at `pricing.py:178-180`; this plan inherits that convention verbatim.

### 1.3 Catalogue SKUs the rule references

- **None.** Reservations cut across many catalogue SKUs and have no `list_price_usd_month` we can publish without redistributing Microsoft pricing pages (hard rule #3 / #5). Same posture as `AZ.RESERVATION_UNDERUTILIZED` (`azure_rules.py:163-190`) and `AZ.COMMITMENT_UNDER_COVERED` (rule 2). No `data/catalog/azure/*.yaml` change in this PR.

### 1.4 Stage-3 corrections vs prior framings

Two corrections to assertions carried into this stage. Surfacing them rather than silently picking one (§11 ground rule); Noor adjudicates.

#### Correction A: there IS a first-class auto-renew field on the API

The Lead handoff brief said: "no first-class 'auto-renew' field on Microsoft.Capacity reservations as of the 2024 API (I believe; verify against Microsoft Learn)". My read of the api-version 2022-11-01 spec (cited in §1.1) shows `properties.renew` (boolean) and `properties.userFriendlyRenewState` (string) are both present and have been since at least the 2022-03-01 GA. The api-version the collector already uses (`2022-11-01`, see `arm_collector.py:40`) returns these fields. **The "no first-class auto-renew field" assumption is wrong**; we can read the operator's actual renewal intent without inventing a heuristic.

This collapses the three "no renewal signal" options the brief listed:

- **(O1) Boolean field, default `null` in CSV mode.** -- ACCEPTED. Maps 1:1 to `properties.renew`. CSV mode operators leave the column blank if they do not have the data; rule abstains.
- **(O2) Derived signal: no younger reservation in same SKU + scope overlapping.** -- REJECTED. Two failure modes: (i) operators who buy renewals 60-90 days early would be over-counted as "no renewal" until the new purchase appears in the dataset; (ii) operators who buy a renewal with a different SKU (e.g. `Standard_D4s_v3` -> `Standard_D4ds_v5`) would never trigger the heuristic correctly. The API field has neither failure mode.
- **(O3) Operator marks via tag / config.** -- REJECTED. Reinventing a flag the API already exposes is YAGNI and creates a second source of truth that can drift from the live tenant.

**Schema impact:** the consequence of accepting O1 is that rule 3 introduces **two** new fields on `AzureReservation`, not one (`expiry_date` AND `auto_renew`). This is more than the `.squad/identity/now.md` line "Rule 3 needs `AzureReservation.expiry_date` field (small schema change)" anticipated. The increment is one additional optional boolean column in the strict-column CSV header, which is still a small change but worth surfacing explicitly.

#### Correction B: cross-rule isolation framing

The Lead handoff brief said: "rule 2's E5 excludes near-expiry reservations". I read rule 2's plan (`docs/plans/059-az-commitment-under-covered.md` §2.2 row E5, on `main` at `328986e`):

> "E5 | Reservation expires within 30 days (out of scope, rule 3 territory) | The current `AzureReservation` schema does NOT carry `expiry_date`. Rule 2 cannot detect this; rule 3 (`AZ.COMMITMENT_RENEWAL_REVIEW`) will add the field."

Rule 2's E5 documents an **inability to detect** (the schema field is absent), **not a filter-out gate**. When rule 3 lands and the schema gains `expiry_date`, rule 2's filter logic does **not** change; rule 2 keeps its existing gate (`utilization_pct < 80%` AND sibling on-demand spend). The two rules can therefore co-fire on the same reservation that is both under-utilised AND near expiry; rule 2's plan §2.4 explicitly endorses this:

> "they can both fire on the same reservation if it is both under-utilised AND about to expire, that is a meaningful dual signal (rebalance the scope before deciding whether to renew)"

So the cross-rule isolation between rule 2 and rule 3 is **disjoint by signal** (different fields drive each gate), not disjoint by time-window. This plan does not propose to retrofit a near-expiry exclusion into rule 2. If Noor wants tighter isolation, the discussion belongs on a separate amendment to PR #84 (now merged), not on this PR.

---

## Section 2: Stage-2 Rubberduck (Maya, plain-English walkthrough)

### 2.1 What the rule is supposed to say

> "Reservation `{principal}` ({term}) expires on `{expiry_date}` (in `{days_until_expiry}` days) and is not configured to auto-renew. Verify whether the workload still needs reserved capacity. If yes, consider renewing or exchanging the reservation before the expiry date. If no, plan for the workload to fall back to on-demand pricing on `{expiry_date}` and capture the projected on-demand cost in your forecast."

That is verb-conservative ("verify ... if yes ... consider ... if no ... plan"); names the operator-side check (workload still needed?); never tells the operator a single answer; and surfaces the expiry date verbatim so the operator can plug it into a calendar.

### 2.2 What could go wrong (edge cases)

| # | Edge | Behaviour required |
|---|------|---|
| E1 | Dataset has no reservations of any kind | Rule emits no finding (vacuous loop). |
| E2 | Reservation row has `expiry_date is None` (CSV-mode operator left it blank, or live ARM collector exception) | Abstain on that row. Same posture as `AZ.RESERVATION_UNDERUTILIZED` abstaining on `utilization_pct is None` (`azure_rules.py:167-168`). |
| E3 | Reservation `expiry_date` is more than the near-expiry window (60 days) in the future | Abstain. Not yet actionable as a renewal review. |
| E4 | Reservation `expiry_date` is in the past (already expired) | Abstain. Already-expired reservations are not actionable as "renewal review"; the operator has already discovered them by other means (Cost Mgmt, billing alerts). Rule 3 is forward-looking, not historical. |
| E5 | Reservation row has `auto_renew is None` (CSV-mode operator left it blank, or live ARM collector exception) | Abstain on that row. Without the renewal signal we cannot make the rule's claim "is not configured to auto-renew". |
| E6 | Reservation `auto_renew is True` | Abstain. Renewal already configured -- nothing to surface. |
| E7 | Reservation `auto_renew is False` AND `0 <= days_until_expiry <= 60` | **FIRE.** One finding per reservation. |
| E8 | Multiple reservations in the dataset all near expiry | One finding per reservation. No dedup -- each commitment is its own decision. |
| E9 | Reservation `displayProvisioningState != "Succeeded"` (cancelled, failed, expired, pending) | Filter at the **collector**, not the rule. The collector writes only `Succeeded` reservations into `azure_reservations.csv`. Rule 3 inherits this gate transparently. CSV-mode operators are responsible for their own filtering; the rule abstains on `expiry_date is None` for any malformed input (E2), so the worst case is a silent abstain rather than a bad finding. **Implementer note (§3.4): the ARM collector currently does NOT filter `_collect_reservations` by `displayProvisioningState`. Add the filter in this PR.** |
| E10 | Reservation expires today (`days_until_expiry == 0`) | Fire. Borderline case -- the rule is "near expiry", and 0 days qualifies. The operator's verification step covers the edge ("if no, plan for on-demand fallback on `{expiry_date}`"). |
| E11 | Reservation `expiry_date` string is malformed (not ISO 8601 YYYY-MM-DD) | Pydantic's `min_length=10, max_length=10` constraint on the field rejects rows whose string is the wrong length. Anything that parses as length 10 but is not a valid date is caught at rule-evaluation time when `date.fromisoformat()` raises `ValueError`; the rule logs at WARN and abstains for that row. **Do not crash the rule run on a single malformed cell.** |
| E12 | Reservation expires within the window AND `auto_renew is False` AND `utilization_pct < 80%` | Both rule 2 (`AZ.COMMITMENT_UNDER_COVERED`, if sibling spend signal also crosses) and rule 3 will fire on the same reservation. Intentional and complementary, see §2.4. |
| E13 | Same reservation observed in two collector runs producing two CSV rows with the same `reservation_id` | Out of scope for the rule (that is a collector / dataset-builder bug). The strict-column loader would accept both rows; the rule would emit two findings. The dataset-shape contract owns deduplication, not the rule. |

### 2.3 False-positive risks

- **Operator buys renewal early but the dataset is from before the purchase.** The rule will fire ("not configured to auto-renew") even though a successor reservation now exists. Mitigation: the recommendation wording asks the operator to verify, not act; a single skim catches the case. The wording deliberately does not say "your reservation is lapsing"; it says "verify whether the workload still needs reserved capacity".
- **Reservation in a `Cancelled` provisioning state still has `expiry_date` populated.** Mitigation: collector filters by `displayProvisioningState == "Succeeded"` (E9). CSV-mode operators are responsible for their own filtering; legacy CSVs without the filter would produce an extra finding the operator dismisses.
- **`expiryDate` reflects the original purchase term, not a renewed extension.** When a reservation is renewed, the API issues a new reservation row (with `renewSource` pointing to the old one); the old row's `expiryDate` is still its original date. Mitigation: filter on `displayProvisioningState`, which transitions to `Expired` after expiry. The rule will abstain on already-expired rows (E4) and only fire on the new active reservation if its `renew` flag is `false`.
- **Aggressive 60-day window catches reservations the operator has already booked into the FY-end renewal cycle.** Mitigation: the wording's "if yes, consider renewing or exchanging ... before the expiry date" is exactly what the operator is already doing; the finding becomes a "yes, on it" tick rather than a false alarm. The rule's job is to surface, not to assume.

### 2.4 Cross-rule isolation

| Rule | Gate | Co-fire with rule 3? | Boundary |
|------|------|----------------------|----------|
| `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1, MERGED PR #83 plan, impl PR #85 in flight) | `AzureBenefitRecommendation.cost_without_benefit_usd >= $50` AND `net_savings_usd > 0` AND `lookback_period in {Last30Days, Last60Days}` | Independent. Different model (`AzureBenefitRecommendation` vs `AzureReservation`), different join surface. No co-fire interaction. | **Disjoint by model.** |
| `AZ.COMMITMENT_UNDER_COVERED` (rule 2, MERGED PR #84) | `utilization_pct < 80%` AND sibling on-demand spend `>= $50/mo` | Yes -- a reservation can be both under-utilised + near expiry. Both findings emit; the operator gets two complementary recommendations ("rebalance scope" + "decide on renewal"). Rule 2's plan §2.4 explicitly endorses this. | **Disjoint by signal.** Rule 2 reads `utilization_pct` + sibling spend; rule 3 reads `expiry_date` + `auto_renew`. Different fields drive each gate. See Correction B (§1.4). |
| `AZ.RESERVATION_UNDERUTILIZED` (existing, `azure_rules.py:163-190`) | `utilization_pct < 80%` | Yes -- same logic as rule 2 above, also complementary. | **Disjoint by signal.** Different field. |
| `AZ.RESERVATION_SCOPE_MISMATCH` (rule 4, FUTURE) | Will likely gate on `applied_scope_subscription_ids` (declared scope) vs operator tag/intent | Yes -- a reservation can be scope-mismatched + near expiry. Both findings emit; rule 4's stage-3 plan owns the rendezvous test. | **Disjoint by signal** (planned). Rule 4 will read a field rule 3 does not touch. No coupling at rule 3's stage. |

**Stage-4 reviewer:** do not request consolidation across these rules. The cross-rule independence -- "same reservation, multiple complementary findings" -- is what makes the playbook useful. Rule 3's specific contribution is the renewal-decision lever; it does not subsume the others.

### 2.5 Conservative recommendation wording (drafted)

> "Reservation `{principal}` ({term}) expires on `{expiry_date}` (in `{days_until_expiry}` days) and is not configured to auto-renew. Verify whether the workload still needs reserved capacity. If yes, consider renewing or exchanging the reservation before the expiry date. If no, plan for the workload to fall back to on-demand pricing on `{expiry_date}` and capture the projected on-demand cost in your forecast."

Verb-conservative ("verify ... if yes ... consider ... if no ... plan"); names two operator-side checks; never says "renew" / "drop" / "buy" as imperatives. Matches rule 1 and rule 2 voice; matches the existing `AZ.RESERVATION_UNDERUTILIZED` register ("Exchange or shrink the commitment at next renewal.").

### 2.6 Security implications

- **No new scope.** `Reservation Reader` (or `Reader` on the reservation order) is implicit in the existing ARM collector audience; `_ARM_SCOPES` at `arm_collector.py:31` is unchanged.
- **PII redaction posture.** The rule emits ONE redactable identifier per finding: `principal = ctx.redact(reservation.reservation_id)`. **Two call sites required** (the binding norm from the post-PR-#78 honest-manifest contract): once for `Finding.principal`, once for the rendered template's `{principal}` variable. Both must redact. See §3.5 for the call sites and §3.7 for the binding citation.
- **No third-party copyrighted material.** All numbers come from the operator's own tenant data (`expiry_date`, `auto_renew`, `term` are operator-owned). The Microsoft Learn URL is linked, never copied.

### 2.7 Alternatives considered (rejected)

- **(R1) Use `summary.expiringCount` from the LIST response as a tenant-wide signal.** Rejected: the field conflates terms, scopes, and renewal-state into a single integer; the rule would either over-fire (count includes `auto_renew=True` rows) or under-explain (no per-reservation evidence). Per-row evaluation is the only way to attach `principal` to the finding.
- **(R2) Define the near-expiry window as a sliding scale (e.g. info @ 90d / medium @ 60d / high @ 30d).** Rejected for V1: severity laddering is a separate design concern (no other Azure rule does it today), and the YAML schema (`Rule.severity` is a single value, see `models.py:50`) does not support multi-tier severity per rule. Pin **medium @ 60d** for V1; a follow-up issue can re-open laddering after operator feedback. **The 60-day choice mirrors the epic body's framing ("expiring < 60 days") and `pricing.py:179-180`'s example threshold.**
- **(R3) Derive "no renewal signal" from "no younger reservation in same SKU + scope overlapping the expiring one".** Rejected (see Correction A in §1.4 for the full rationale). The API's `properties.renew` boolean is the right source of truth; deriving it from inventory cross-references introduces two failure modes (early-renewal over-count, SKU-changed-renewal under-detect) the API field does not have.
- **(R4) Mark "renewal needed" via an operator-supplied tag / config file.** Rejected (see Correction A). Reinventing an API field as a tag creates a second source of truth.
- **(R5) Add a separate `AzureReservationLifecycle` model rather than extend `AzureReservation`.** Rejected: `expiry_date` and `auto_renew` belong to the reservation itself; they are not observation-time-varying like utilisation. Splitting them off would force every rule that touches both lifecycle and utilisation (e.g. a future combined "should we renew this under-utilised reservation?" rule) to do a model join. The current `AzureReservation` already mixes identity (`reservation_id`, `sku`, `scope`) with utilisation (`utilization_pct`); adding lifecycle fields is the same level of cohesion.
- **(R6) Compute `days_until_expiry` in the collector and write it to the CSV instead of `expiry_date`.** Rejected: a precomputed `days_until_expiry` is stale by the time the rule runs. CSV mode operators who generated the file 7 days ago would see `days_until_expiry=60` evaluated as if the dataset were fresh. Storing the absolute `expiry_date` and computing the delta at rule-eval time keeps the gate honest. Same posture as `pricing.py:178-180`.
- **(R7) Inject a `now_fn` callable into the rule for testability.** Considered, not yet decided. The rule body uses `datetime.now(UTC).date()` for the "today" anchor. Tests will either monkeypatch the import, use `freezegun`, or pass a fixture-supplied `expiry_date` chosen relative to `date.today()` so the test is robust to any clock. **Implementer's call** at stage 5; the plan does not lock the test seam shape, only that the rule body must compute "today" via a single call so the seam exists.

---

## Section 3: Stage-3 plan proper (file-level checklist)

### 3.1 Acceptance criteria (small enough for ONE PR)

- [ ] **Schema:** `AzureReservation` (`src/finops_assess/models.py:235-250`) gains two optional fields:
  - [ ] `expiry_date: str | None = Field(default=None, min_length=10, max_length=10)` -- ISO 8601 YYYY-MM-DD.
  - [ ] `auto_renew: bool | None = Field(default=None)` -- `None` means signal absent (CSV-mode operator left blank).
- [ ] **CSV collector:** `src/finops_assess/collectors/csv_collector.py` reads the new columns transparently (no code change needed -- the strict-column loader at `csv_collector.py:54-90` already handles new optional columns by defaulting to `None`).
- [ ] **ARM collector:** `src/finops_assess/collectors/arm_collector.py`:
  - [ ] `_collect_reservations` (`arm_collector.py:244-253`) is unchanged (api-version `2022-11-01` already returns `expiryDate` + `renew`).
  - [ ] Reservation row builder (`arm_collector.py:511-534`) reads `props.get("expiryDate")` and `props.get("renew")` into the new CSV columns.
  - [ ] Reservation row builder filters by `displayProvisioningState == "Succeeded"` (E9) -- skip cancelled / failed / expired rows.
  - [ ] CSV header (`arm_collector.py:559-569`) gains two columns at the end: `expiry_date`, `auto_renew`.
- [ ] **YAML rule entry:** added to `data/rules/azure.yaml` AND the packaged mirror at `src/finops_assess/data/rules/azure.yaml` (byte-equal). Includes `inactivity_days: 60` (reusing the existing `Rule.inactivity_days` field as the near-expiry window threshold; rule body reads `ctx.rule.inactivity_days or 60`).
- [ ] **Rule implementation:** `commitment_renewal_review` registered in `src/finops_assess/rules_impl/azure_rules.py`.
- [ ] **Sample data:** `samples/azure_reservations.csv` gains `expiry_date` + `auto_renew` columns; one row that fires (near expiry, `auto_renew=False`) + one row that abstains (`auto_renew=True` or `expiry_date` far future).
- [ ] **Playbook template:** `src/finops_assess/data/playbooks/azure/AZ.COMMITMENT_RENEWAL_REVIEW.j2` (LF-pinned by `.gitattributes` rule `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`).
- [ ] **Unit tests:** `tests/test_az_commitment_renewal_review.py` covering E1-E12 (all positive + abstain paths + redaction polarities).
- [ ] **End-to-end regression test (real `run_rules` engine, NOT a mocked rule callable):** Yuki-net pattern reference `tests/test_playbook_cross_run_stability.py:1-80`.
- [ ] **`tests/test_engine.py` `REQUIRED_RULES` set** (line 23) includes `AZ.COMMITMENT_RENEWAL_REVIEW`.
- [ ] **`tests/test_csv_collector.py`** covers loading the new columns (with and without them present, to assert backward compatibility).
- [ ] **`docs/plan.md` §6** lists the new rule under Azure rules.
- [ ] **`docs/schema.md`** gains a note for the two new `AzureReservation` fields (the schema doc tracks every field on the normalised models).
- [ ] **`docs/rules.md`** is regenerated by `python scripts/generate_docs.py`.
- [ ] **Demo / playbook artefacts** regenerated: `examples/demo-report.{json,html,csv}`, `examples/demo-triage.{json,csv}`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`.
- [ ] **`python scripts/generate_docs.py --check`** passes locally and in CI.
- [ ] **All gates green:** `finops-assess validate`, `ruff check`, `ruff format --check`, `mypy src`, `pytest`.
- [ ] **CHANGELOG.md** updated under the v0.5.0 / unreleased section noting the new rule + the two-field schema addition (the impl PR ships this; the plan PR does not).
- [ ] **No new ARM scope** in `arm_collector.py` (`_ARM_SCOPES` unchanged).
- [ ] **No catalogue YAML changes** in `data/catalog/azure/*.yaml`.
- [ ] **No engine changes** in `src/finops_assess/engine.py`.

If the implementation cannot meet **all** criteria in one PR, decompose further (e.g. split the schema + collector wiring into a thin foundation PR, then the rule + tests in a follow-up). This is the implementer's call at stage 5; the lockable signal is "draft PR is green and < ~600 LoC product code".

### 3.2 Schema additions, `src/finops_assess/models.py`

Edit `AzureReservation` (currently lines 235-250) to add two fields after `monthly_cost_usd`:

```python
class AzureReservation(BaseModel):
    """A normalised Azure Reservation / Savings Plan snapshot.

    ``utilization_pct`` is the average utilization over the trailing 30 days
    (0-100). Rules abstain when the signal is absent rather than assuming
    zero utilization.

    ``expiry_date`` is the commitment expiration date (ISO 8601 YYYY-MM-DD).
    ``auto_renew`` is the operator's renewal-intent flag; ``None`` means the
    signal is absent (CSV-mode operators may leave it blank). Both fields
    drive ``AZ.COMMITMENT_RENEWAL_REVIEW``; rules abstain on ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    reservation_id: str = Field(..., min_length=1)
    reservation_name: str | None = None
    sku: str | None = None
    scope: str | None = None
    utilization_pct: float | None = Field(default=None, ge=0, le=100)
    monthly_cost_usd: float | None = Field(default=None, ge=0)
    expiry_date: str | None = Field(default=None, min_length=10, max_length=10)
    auto_renew: bool | None = None
```

`extra="forbid"` is preserved (hard rule + binding norm #9). The `min_length=10, max_length=10` constraint on `expiry_date` mirrors `pricing.py:249-254`. The `auto_renew` field has no `Field(...)` wrapper because it has no constraints beyond the boolean type.

`NormalizedDataset.azure_reservations` (`models.py:384`) is **unchanged** -- the same list field carries the extended row.

### 3.3 CSV collector, `src/finops_assess/collectors/csv_collector.py`

**No code change required.** The strict-column loader at `csv_collector.py:54-90` already handles new optional fields:

- Rows with **fewer** cells than the header default missing keys to `None` (docstring at `csv_collector.py:57-62`).
- The model field defaults (`Field(default=None, ...)`) provide the missing values.

The docstring at `csv_collector.py:9` (`* ``azure_reservations.csv`` -- :class:`AzureReservation` fields.`) is already accurate -- it points at the model, which now declares the new fields. **No docstring update needed.**

This is a property of the strict-column contract worth highlighting for Noor: backward compatibility for legacy CSVs is automatic.

### 3.4 ARM collector, `src/finops_assess/collectors/arm_collector.py`

Three localised changes:

1. **Filter by `displayProvisioningState`** in the reservation loop. Edit the loop body at `arm_collector.py:509-534`:

   ```python
   for res in _collect_reservations(client):
       props = res.get("properties") or {}
       if (props.get("displayProvisioningState") or "").lower() != "succeeded":
           continue  # skip cancelled / failed / expired rows
       rid = res.get("id") or ""
       sku_info = res.get("sku") or {}
       util = None
       util_data = props.get("utilization") or {}
       # ... existing utilisation extraction unchanged ...

       reservation_rows.append(
           {
               "reservation_id": rid,
               "reservation_name": props.get("displayName") or "",
               "sku": sku_info.get("name") or "",
               "scope": props.get("appliedScopeType") or "",
               "utilization_pct": "" if util is None else str(round(float(util), 2)),
               "monthly_cost_usd": "",
               "expiry_date": props.get("expiryDate") or "",
               "auto_renew": _renew_to_str(props.get("renew")),
           }
       )
   ```

2. **Add a tiny helper** for the boolean-to-CSV-cell conversion (private to `arm_collector.py`):

   ```python
   def _renew_to_str(value: object) -> str:
       """Render the API's renew flag as a CSV cell.

       ``True`` / ``False`` map to lowercase strings the strict-column
       loader's ``_BOOL_TRUE`` / ``_BOOL_FALSE`` sets recognise. ``None``
       and any other value map to the empty string (signal absent).
       """
       if value is True:
           return "true"
       if value is False:
           return "false"
       return ""
   ```

   Recognised by `csv_collector.py:48-49` (`_BOOL_TRUE = {"true", "1", "yes", "y", "t"}`, `_BOOL_FALSE = {"false", "0", "no", "n", "f", ""}`). Note that `""` is in `_BOOL_FALSE` -- the implementer must verify what that maps to in `_coerce_row` so the "signal absent" case correctly resolves to `None`, not `False`. See §3.7 producer-path citation.

3. **Extend the CSV header** at `arm_collector.py:561-568` (the `_write_csv` call for `azure_reservations.csv`) to add two columns at the end:

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
           "expiry_date",
           "auto_renew",
       ],
       reservation_rows,
   )
   ```

**No new `_API_VERSIONS` entry, no new `_ARM_SCOPES` entry.** The api-version `2022-11-01` (`arm_collector.py:40`) already returns the fields we need (verified against Microsoft Learn in §1.1).

### 3.5 Rule implementation, `src/finops_assess/rules_impl/azure_rules.py`

Add at the end of the file (after `AZ.DEV_TEST_SUB_MISMATCH` at line 291):

```python
# ---------------------------------------------------------------------------
# AZ.COMMITMENT_RENEWAL_REVIEW
# ---------------------------------------------------------------------------
import logging
from datetime import UTC, date, datetime

_RENEWAL_REVIEW_DEFAULT_WINDOW_DAYS = 60
_logger = logging.getLogger(__name__)


def _today_utc() -> date:
    """Single seam for "today" so tests can monkeypatch it cleanly."""
    return datetime.now(UTC).date()


def _parse_expiry(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        _logger.warning("AZ.COMMITMENT_RENEWAL_REVIEW: malformed expiry_date %r; abstaining", value)
        return None


@register("AZ.COMMITMENT_RENEWAL_REVIEW")
def commitment_renewal_review(ctx: RuleContext) -> Iterable[Finding]:
    """Flag reservations expiring within the near-expiry window with auto-renew off."""
    window_days = ctx.rule.inactivity_days or _RENEWAL_REVIEW_DEFAULT_WINDOW_DAYS
    today = _today_utc()
    for reservation in ctx.dataset.azure_reservations:
        if reservation.expiry_date is None:
            continue  # E2
        if reservation.auto_renew is None:
            continue  # E5
        if reservation.auto_renew is True:
            continue  # E6
        expiry = _parse_expiry(reservation.expiry_date)
        if expiry is None:
            continue  # E11
        days_until_expiry = (expiry - today).days
        if days_until_expiry < 0:
            continue  # E4 (already expired)
        if days_until_expiry > window_days:
            continue  # E3 (not yet near expiry)

        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(reservation.reservation_id),
            current_sku=reservation.sku,
            estimated_monthly_savings_usd=None,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(reservation.reservation_id),
                expiry_date=reservation.expiry_date,
                days_until_expiry=days_until_expiry,
                term=reservation.sku or "?",
            ),
            evidence={
                "reservation_name": reservation.reservation_name,
                "sku": reservation.sku,
                "scope": reservation.scope,
                "expiry_date": reservation.expiry_date,
                "days_until_expiry": days_until_expiry,
                "auto_renew": reservation.auto_renew,
                "utilization_pct": reservation.utilization_pct,
                "monthly_cost_usd": reservation.monthly_cost_usd,
            },
        )
```

**Both invocations of `reservation.reservation_id` MUST go through `ctx.redact()`** -- once for `Finding.principal`, once for the rendered template. See §3.7 binding citation. Same posture as `AZ.RESERVATION_UNDERUTILIZED` at `azure_rules.py:175,180`.

`estimated_monthly_savings_usd=None` because the rule does not predict a saving (renewal vs lapse is a workload decision; the savings depend on operator choice). Same posture as `AZ.RESERVATION_UNDERUTILIZED` (`azure_rules.py:177`) which also returns `None` here.

The `term` argument to `render()` is named optimistically -- the existing schema does not carry the API's `properties.term` ("P1Y" / "P3Y") field. Rather than expand the schema for cosmetic wording, V1 substitutes `reservation.sku` (or `"?"`); the operator can read the actual term from Azure portal. **A future schema extension could add `term: Literal["P1Y", "P3Y"] | None`; out of scope for V1.** Stage-4 reviewer: confirm this trade-off is acceptable, or amend the plan.

`logging` import goes at the top of the module per ruff `I` rule; the `from datetime import UTC, date, datetime` import stays grouped with the other stdlib imports. The `_today_utc` and `_parse_expiry` helpers are private (underscore-prefixed) per the repo convention.

### 3.6 YAML rule entry, `data/rules/azure.yaml` (and packaged mirror)

Append to `data/rules/azure.yaml`:

```yaml
- id: AZ.COMMITMENT_RENEWAL_REVIEW
  surface: azure
  severity: medium
  summary: Reservation expiring within the near-expiry window with auto-renew off.
  recommendation_template: >
    Reservation {principal} ({term}) expires on {expiry_date}
    (in {days_until_expiry} days) and is not configured to auto-renew.
    Verify whether the workload still needs reserved capacity. If yes,
    consider renewing or exchanging the reservation before the expiry date.
    If no, plan for the workload to fall back to on-demand pricing on
    {expiry_date} and capture the projected on-demand cost in your forecast.
  inactivity_days: 60
```

`inactivity_days: 60` is reused as the near-expiry window threshold (the existing `Rule.inactivity_days` field already carries the "N-day window" idiom for `AZ.IDLE_VM_14D`, `AZ.RESERVATION_UNDERUTILIZED`, etc.). No new YAML schema field needed. Rule body reads `ctx.rule.inactivity_days or 60` as the default fallback.

Severity choice: `medium`. Rationale: it is a forward-looking decision lever, not an active waste signal. Same tier as `AZ.LOG_ANALYTICS_OVERINGEST` and `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1). Not `high` (no immediate cost burn), not `low` (decision is genuinely material).

**Sync the packaged mirror** at `src/finops_assess/data/rules/azure.yaml` in the same commit (catalogue YAML is shipped with the wheel; the mirror must stay byte-equal). Pattern reference: rule 1 plan §3.6.

### 3.7 Producer-path citations (BINDING per post-PR-#78 norm)

Every claim this rule makes about a value is anchored to the producer code path that establishes the value, on `main` SHA `328986e`. Stage-4 reviewers reject the plan if any cell below is wrong.

| Claim | Producer (file:line) | What the producer does |
|---|---|---|
| `principal` is salted-hashed by default | `src/finops_assess/engine.py:70-75` (`RuleContext.redact`) | `if redact_pii: return f"sha256:{sha256(salt+':'+principal)[:16]}"`. The rule MUST call `ctx.redact(reservation.reservation_id)` **twice** in §3.5 (once for `Finding.principal`, once inside `render(...)`). |
| `principal` is **not stable across runs** with default redaction | `src/finops_assess/engine.py:151` (`run_rules`) | `salt_value = salt if salt is not None else secrets.token_hex(16)`. The CLI does not flow a stable salt today. Per-run salt instability is the existing Azure-surface posture; no new reporter contract is introduced by this rule. Issue #73 is the engine-level fix; this plan does not block on it. |
| `principal` is the **reservation ARM ID**, not a user identifier | `src/finops_assess/models.py:245` (`reservation_id: str`) and `azure_rules.py:175` (`AZ.RESERVATION_UNDERUTILIZED` precedent) | Same convention: reservation ID is treated as a redactable principal even though it is not user-PII, because the rule pipeline treats every `principal` as redactable. |
| `expiry_date` is ISO 8601 YYYY-MM-DD | This plan adds `expiry_date: str = Field(min_length=10, max_length=10)` mirroring `src/finops_assess/pricing.py:249-254` | The 10-character bound rejects datetime strings. Date format is enforced at rule-eval time by `date.fromisoformat()` (§3.5); malformed strings log WARN and abstain (E11). |
| `auto_renew` is a tri-state boolean (`True` / `False` / `None`) | This plan adds `auto_renew: bool | None = None` on `AzureReservation` | `None` semantics are "signal absent" -- abstain. Same posture as `utilization_pct is None` at `azure_rules.py:167-168`. |
| The ARM collector's reservation list endpoint already returns `expiryDate` and `renew` at api-version `2022-11-01` | `src/finops_assess/collectors/arm_collector.py:40` (`"reservations": "2022-11-01"`) and `arm_collector.py:244-253` (`_collect_reservations`) | The endpoint URL is already correct; the row builder at `arm_collector.py:511-534` only needs to read two more `props.get(...)` keys. No new API call, no new scope. |
| The ARM collector uses **read-only** scopes | `src/finops_assess/collectors/arm_collector.py:31` (`_ARM_SCOPES = ["https://management.azure.com/.default"]`) | This plan does not modify `_ARM_SCOPES`. Hard rule #1 upheld. |
| Reservation row builder pattern this implementation extends | `src/finops_assess/collectors/arm_collector.py:509-534` | Existing loop reads `props.get("appliedScopeType")` (line 530); this plan adds `props.get("expiryDate")` and `props.get("renew")` to the same dict, plus a `displayProvisioningState` filter at the top of the loop body (E9). |
| CSV header for `azure_reservations.csv` | `src/finops_assess/collectors/arm_collector.py:561-568` | This plan adds two columns at the end: `expiry_date`, `auto_renew`. Order matters because `_write_csv` writes a header row in the order given. |
| CSV strict-column loader is backward-compatible for new optional fields | `src/finops_assess/collectors/csv_collector.py:54-90` (`_coerce_row`), specifically the docstring at lines 56-62 | Rows with fewer cells than the header default missing keys to `None`. Legacy `azure_reservations.csv` files (no `expiry_date` / `auto_renew` columns) load unchanged; the rule abstains on those rows (E2 / E5). |
| `_BOOL_FALSE` includes the empty string | `src/finops_assess/collectors/csv_collector.py:49` (`_BOOL_FALSE = {"false", "0", "no", "n", "f", ""}`) | **Implementer caveat:** the empty-string-as-False default could conflict with the desired "signal absent -> None" semantics. The implementer MUST verify in test #5 that the loader maps an empty cell to `None` (via the missing-key default path), NOT to `False` (via the boolean coercion path). The strict-column loader's missing-key handling at `csv_collector.py:78-90` resolves this; absent cells never reach `_BOOL_FALSE`. |
| Rule abstain pattern when signal is absent | `src/finops_assess/rules_impl/azure_rules.py:167-168` (`AZ.RESERVATION_UNDERUTILIZED`) | Precedent: `if reservation.utilization_pct is None: continue`. Rule 3's body at §3.5 mirrors this for both `expiry_date is None` and `auto_renew is None`. |
| `Rule.inactivity_days` field carries the N-day-window idiom | `src/finops_assess/models.py:Rule` definition + existing usages in `azure_rules.py:24` (`AZ.IDLE_VM_14D`) | Same field reused for "near expiry window". No new YAML schema field. |
| `Finding.evidence` is a free-form dict surfaced verbatim by reporters | `src/finops_assess/models.py:Finding` definition + `src/finops_assess/reporters/json_reporter.py` | All evidence values in §3.5 are non-PII (numerical / API-derived strings / booleans). No additional redaction needed for evidence. |
| Yuki-net pattern (real `run_rules` engine, NOT mocked rule callable) | `tests/test_playbook_cross_run_stability.py:1-80` | Test #10 in §3.8 mirrors this pattern. Caught BLOCKING #1 in PR #78. |

If any of these citations is wrong at implementation time, the implementer flags it back to Maya and the plan is amended -- never silently overridden (§11 ground rule).

### 3.8 Test plan

| # | Test name | File | Asserts |
|---|---|---|---|
| 1 | `test_renewal_review_fires_on_near_expiry_no_auto_renew` | `tests/test_az_commitment_renewal_review.py` | Reservation with `expiry_date = today + 30 days`, `auto_renew=False` -> exactly one finding with `rule_id="AZ.COMMITMENT_RENEWAL_REVIEW"` and `severity="medium"`. |
| 2 | `test_renewal_review_abstains_on_missing_expiry_date` | same | `expiry_date=None` -> no finding (E2). |
| 3 | `test_renewal_review_abstains_when_auto_renew_unknown` | same | `auto_renew=None` -> no finding (E5). |
| 4 | `test_renewal_review_abstains_when_auto_renew_true` | same | `auto_renew=True` -> no finding (E6). |
| 5 | `test_renewal_review_abstains_outside_window` | same | `expiry_date = today + 90 days`, `auto_renew=False` -> no finding (E3). |
| 6 | `test_renewal_review_abstains_when_already_expired` | same | `expiry_date = today - 5 days`, `auto_renew=False` -> no finding (E4). |
| 7 | `test_renewal_review_fires_on_expiry_today` | same | `expiry_date = today`, `auto_renew=False` -> one finding (E10 boundary). |
| 8 | `test_renewal_review_abstains_on_malformed_expiry` | same | `expiry_date="not-a-date"` (length 10 to pass pydantic) -> no finding + WARN log captured (E11). |
| 9 | `test_renewal_review_redacts_principal_by_default` | same | With `redact_pii=True` (default), `finding.principal.startswith("sha256:")` and `len(finding.principal) == 23`. **Cites `engine.py:70-75` in the test docstring.** |
| 10 | `test_renewal_review_emits_cleartext_with_redaction_off` | same | With `redact_pii=False`, `finding.principal == reservation.reservation_id` exactly. |
| 11 | `test_renewal_review_e2e_through_run_rules` | same | End-to-end regression: build `NormalizedDataset` with one fires-row + one abstains-row, call real `run_rules(...)`, assert exactly one finding. **Pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`** -- uses real engine, not a mocked rule callable. Yuki-net invariant from PR #78. |
| 12 | `test_renewal_review_one_finding_per_reservation` | same | Two reservations, both near expiry with auto_renew=False -> two findings (E8 -- no dedup; each commitment is its own decision). |
| 13 | `test_renewal_review_co_fires_with_underutilized` | same | One reservation: `utilization_pct=40`, `expiry_date = today + 30`, `auto_renew=False` -> two findings (one `AZ.RESERVATION_UNDERUTILIZED`, one `AZ.COMMITMENT_RENEWAL_REVIEW`). Pins the §2.4 disjoint-by-signal claim. |
| 14 | extend `tests/test_engine.py:REQUIRED_RULES` | `tests/test_engine.py:23-47` | Add `"AZ.COMMITMENT_RENEWAL_REVIEW"` to the set so the synthetic-tenant smoke test asserts the rule is registered. |
| 15 | extend `tests/test_csv_collector.py` | `tests/test_csv_collector.py` | (a) Round-trip a `azure_reservations.csv` with the new columns. (b) Round-trip a legacy `azure_reservations.csv` WITHOUT the new columns; assert both rows load with `expiry_date is None` and `auto_renew is None`. Backward-compat invariant. |

**Date determinism for tests 1, 5, 6, 7:** the implementer chooses one of (a) `freezegun`, (b) monkeypatch `_today_utc` in `azure_rules`, or (c) compute `expiry_date` relative to `date.today()` in the test fixture. Option (c) needs no new dependency; option (b) is cleanest. The implementer picks at stage 5; the plan does not lock the seam.

**Fixtures:** all synthetic rows constructed in-test (no on-disk fixture files required for tests 1-13). The on-disk `samples/azure_reservations.csv` is for `finops-assess run --inputs samples/` and the demo-report regen.

### 3.9 Doc regen

The implementer runs `python scripts/generate_docs.py` once and commits **all** regenerated artefacts in the same PR:

- `docs/rules.md` -- auto-generated from `data/rules/azure.yaml`. Will gain a new entry for `AZ.COMMITMENT_RENEWAL_REVIEW`.
- `examples/demo-report.{json,html,csv}` -- will gain a finding row if the demo dataset includes a near-expiry reservation. The implementer updates `samples/azure_reservations.csv` to include one fires-row + one abstains-row (§3.11 below).
- `examples/demo-triage.{json,csv}` -- same.
- `examples/playbook.jsonl{,.manifest.json}` -- same; the playbook reporter renders any rule with a registered `.j2` template. **A new template** `src/finops_assess/data/playbooks/azure/AZ.COMMITMENT_RENEWAL_REVIEW.j2` is required (LF-pinned by `.gitattributes` rule `src/finops_assess/data/playbooks/**/*.j2 text eol=lf`). Template body is a paraphrase of the recommendation; no new schema.
- `examples/focus-aligned.csv{,.manifest.json}` -- the FOCUS-aligned exporter is Azure-only today and will pick up the new finding automatically; bytes regenerate.

`python scripts/generate_docs.py --check` is the docs-freshness gate (`.github/workflows/docs.yml`); it WILL fail without the regen commit.

### 3.10 `data/personas.yaml` impact

**None.** Personas inherit licensing rules (`M365.*` and `GH.COPILOT_*`). Cost-discipline rules like `AZ.*` apply to resources, not user identities. Same posture as every existing `AZ.*` rule. No `data/personas.yaml` change in this PR.

### 3.11 `samples/azure_reservations.csv`

Add `expiry_date` + `auto_renew` columns. The implementer chooses two relative-to-today dates that the demo-report regen can stably produce; one suggestion (90 days into the future for the abstain row, 30 days for the fire row, computed at sample-author time and frozen in the CSV):

```
reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd,expiry_date,auto_renew
/providers/Microsoft.Capacity/reservationOrders/order-001/reservations/res-001,VM_RI_demo_lapsing,Standard_D4s_v3,Single,72.0,1450.00,2026-07-12,false
/providers/Microsoft.Capacity/reservationOrders/order-002/reservations/res-002,VM_RI_demo_renewing,Standard_D2s_v3,Shared,85.0,720.00,2026-08-30,true
```

Row 1 fires (`auto_renew=false`, expiry within 60d of the demo regen anchor). Row 2 abstains (`auto_renew=true`).

**Caveat for demo-report determinism:** the demo regen is dependent on `date.today()` at rebuild time. Either (a) the implementer freezes `_today_utc()` in the regen script via an env var, OR (b) the sample dates are picked far enough in the future that the demo runs deterministically for ~6 months. Implementer's call; the plan does not lock it. **Stage-4 reviewer should flag this as a stability concern if the implementer ships option (b) without an explicit refresh-cadence note in `CHANGELOG.md`.**

### 3.12 `docs/plan.md` §6 update

Add to the Azure rules block (after `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` once that lands from PR #85, OR alphabetically near `AZ.RESERVATION_UNDERUTILIZED`):

```
- `AZ.COMMITMENT_RENEWAL_REVIEW`: reservation expiring within 60 days with auto-renew not configured.
```

Keep the §6 entry one line; the full rule body is `docs/rules.md` (auto-generated).

### 3.13 `docs/schema.md` update

Add a note for the two new `AzureReservation` fields. The schema doc tracks every field on the normalised models; this is required by `.github/copilot-instructions.md` ("Documentation updates" section: "schemas" is enumerated).

### 3.14 Out of scope (and why)

- **Live ARM call against a real tenant.** Stage 5 is unit + e2e with synthetic data. Live verification is the operator's job at `finops-assess run --collector arm`; the test plan does not require a live call.
- **`term: Literal["P1Y", "P3Y"] | None` field on `AzureReservation`.** The recommendation_template uses `{term}` which V1 substitutes from `reservation.sku or "?"`. Adding a real `term` field is out of scope for this PR; surface as a follow-up issue if operators ask. Stage-4 reviewer should confirm this trade-off is acceptable.
- **`renew_source: str | None` field** for "lapsed renewal chain" detection. Not consumed by rule 3 directly. A future rule could use it; out of scope here.
- **Severity laddering** (info @ 90d / medium @ 60d / high @ 30d). Out of scope for V1; pin medium @ 60d. Re-open after operator feedback (R2 in §2.7).
- **Engine "now" injection seam.** The rule body has `_today_utc()` as a single-call seam, sufficient for monkeypatch-based tests. A first-class engine-level "now" is a separate refactor and is not justified by this rule alone.
- **Rules 4 (`AZ.RESERVATION_SCOPE_MISMATCH`) and 5 (`AZ.AHB_ELIGIBLE`).** Each gets its own stage-3 plan. Rule 5 will need `AzureResource.os_type` + `license_type` (larger schema change).

### 3.15 Cross-cutting decisions worth flagging

1. **Schema change is two new optional fields on an existing model**, not a new model. Confirmed in §1.2 + §1.4 Correction A. The Scribe should canonicalise this so the next "do we add a model or extend one?" question can short-circuit.
2. **The "no renewal signal" question resolves to a first-class API field**, not a heuristic. Confirmed in §1.4 Correction A.
3. **Cross-rule isolation is disjoint by signal** (different fields drive each gate), not disjoint by gate (no exclusion logic between rules). Confirmed in §1.4 Correction B and §2.4. Co-firing is desirable.
4. **No new ARM scope, no new collector method, no new endpoint.** Confirmed in §1.1 + §3.4. The api-version `2022-11-01` already returns the fields we need; we just read two more keys from the existing response. Hard rule #1 upheld via `arm_collector.py:31` citation.
5. **No catalogue change.** Reservations are not catalogue SKUs (R5 in §2.7).
6. **No engine change.** The rule is a pure additive registration; `RuleContext` is consumed unchanged.

---

## Section 4: Stage-4 ask (Noor, adversarial reviewer)

**Reviewer:** Noor (squad:noor), model **Opus 4.7** mandatory (per §11; never downgrade).

**Specific invariants Noor must verify (steelman against the plan, do not just agree):**

1. **Producer-path citations are correct.** Open every cell in §3.7 against the repo at `main` SHA `328986e`. Reject if any line number is wrong or any claim is not what the producer actually does. (This is the third consecutive stage-3 plan from Maya where this norm applies; the bar is "all cells correct or reject".)
2. **Stage-3 corrections (§1.4) are accurate.** Independently verify against Microsoft Learn that `properties.renew` (boolean) is exposed by api-version `2022-11-01`. Independently verify that rule 2's E5 (in `docs/plans/059-az-commitment-under-covered.md`) does NOT actually exclude near-expiry reservations from rule 2's gate.
3. **Rule abstains on E1-E11 negative paths.** Walk each edge in §2.2 against the rule body in §3.5; assert the rule short-circuits via the documented gate. Specifically:
   - `expiry_date is None` -> abstain (E2).
   - `auto_renew is None` -> abstain (E5).
   - `auto_renew is True` -> abstain (E6).
   - `expiry_date in the past` -> abstain (E4).
   - `expiry_date > today + window_days` -> abstain (E3).
   - Malformed `expiry_date` -> WARN log + abstain (E11).
4. **Rule fires on E7 + E10 positive paths.** `auto_renew=False` AND `0 <= days_until_expiry <= 60` -> exactly one finding per reservation.
5. **Principal in finding is redacted.** §3.5 calls `ctx.redact(reservation.reservation_id)` twice -- once for `Finding.principal`, once inside `render(...)`. Both call sites must redact; assert by reading the rule body, then assert by reading test #9.
6. **No new ARM scope.** §3.7 binds `arm_collector.py:31` as the citation. Confirm the implementation does NOT modify `_ARM_SCOPES`. **Hard rule #1.**
7. **No catalogue YAML change.** `data/catalog/azure/*.yaml` is untouched; the rule references no SKU id.
8. **End-to-end regression test (test #11) uses the real `run_rules` engine**, not a mocked rule callable. Yuki-net pattern reference: `tests/test_playbook_cross_run_stability.py:1-80`. If the implementer drops it to a unit-only call, reject.
9. **Wording is conservative.** §3.6 uses "verify ... if yes ... consider ... if no ... plan"; "renew", "drop", "buy" do not appear as imperatives in the recommendation_template.
10. **`scripts/generate_docs.py --check` will pass post-implementation.** All of `docs/rules.md`, `examples/demo-report.*`, `examples/demo-triage.*`, `examples/playbook.jsonl{,.manifest.json}`, `examples/focus-aligned.csv{,.manifest.json}`, and the new `.j2` playbook template are committed in the same PR.
11. **Cross-rule isolation invariants** (§2.4):
    - Co-firing with `AZ.RESERVATION_UNDERUTILIZED` is intentional and pinned by test #13.
    - Co-firing with `AZ.COMMITMENT_UNDER_COVERED` (rule 2) is intentional; no exclusion logic added to either rule.
    - No collision with `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1, different model).
    - No collision with `AZ.RESERVATION_SCOPE_MISMATCH` (rule 4, future, different field).
12. **Adversarial alternative considered:** is R3 (derived no-renewal heuristic) actually rejected, or should the rule ship without `auto_renew` as a schema field and infer it from inventory cross-references? Steelman R3 and confirm the API-field rejection rationale (§1.4 Correction A) holds.
13. **Backward-compat invariant for the CSV strict-column loader** (test #15(b)): legacy `azure_reservations.csv` files without the new columns must load with `expiry_date=None` and `auto_renew=None`. Pinned by §3.7 citation `csv_collector.py:54-90`.
14. **Demo-report determinism risk** (§3.11 caveat): if the implementer ships option (b) (sample dates picked into the future), confirm a refresh-cadence note appears in `CHANGELOG.md`.

If Noor returns `REQUEST_CHANGES` on any blocking item, the **Reviewer Rejection Lockout** protocol applies (Maya is locked out of revising her own plan; revision routes to a different agent -- likely Yuki or Diego).

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

- The two new `AzureReservation` fields.
- The ARM collector additions (he has the pattern muscle from existing `_collect_reservations` + the rule-1 implementation in flight on PR #85).
- The `displayProvisioningState` filter.
- The rule registration.
- The packaged-mirror sync at `src/finops_assess/data/rules/azure.yaml`.
- The new `.j2` playbook template (LF-pinned).
- `docs/plan.md` §6 line-add and `docs/schema.md` field-add.
- `CHANGELOG.md` entry.
- All gates: validate, ruff, mypy, pytest, generate_docs --check.

**Backup:** Yuki (tester / quality / CI matrix owner). If Diego is at capacity from PR #85 follow-ups, Yuki picks up; she will likely lean harder on tests #11 (e2e regression net) and #13 (co-fire pin) since those are the cross-rule contract probes.

**Branch:** `squad/59-impl-commitment-renewal-review`. Open as draft, link this PR + issue #59. Reference the §11 stage-3 plan PR (this PR) in the implementation PR description.

**Sequencing note:** rule 3's impl PR can open in parallel with rule 1's impl PR (PR #85) since they touch different models (`AzureBenefitRecommendation` vs `AzureReservation`) and different rule registrations. The only shared file is `tests/test_engine.py` (the `REQUIRED_RULES` set); a textual conflict on that line is trivial to resolve.

**Lockout note:** if Noor REJECTs this stage-3 plan, the revision routes to a **different** agent than Maya (per the Reviewer Rejection Lockout pattern, canonicalised in `.squad/decisions.md` from PR #78 lessons). Maya cannot revise her own plan under rejection.

---

## Section 6: Sign-off mechanics

| Stage | Owner | Artefact | Status |
|---|---|---|---|
| 1 | Maya | §1 above | DONE (this PR) |
| 2 | Maya | §2 above | DONE (this PR) |
| 3 | Maya (Opus 4.7) | §3 above | DONE (this PR) |
| 4 | Noor (Opus 4.7) | PR comment marker `**Stage-4 Adversarial Review -- Noor**` + `VERDICT: APPROVE` | PENDING |
| 5 | Diego (Sonnet, Opus 4.7 if §3 calls for it) | Sibling impl PR on `squad/59-impl-commitment-renewal-review` | BLOCKED on stage-4 |

This plan PR is **draft** until Noor's verdict; on `APPROVE` it becomes ready, the auto-approve workflow fires, and the plan PR squash-merges. Implementation PR opens after.

---

## Section 7: Stage-3 norms operationalised in this plan

(Maya's running checklist; applies to every stage-3 plan in the #59 epic.)

| # | Norm | Where it shows up in this plan |
|---|------|---|
| 1 | Plan-PR convention `docs/plans/NNN-<slug>.md` | This file: `docs/plans/059-az-commitment-renewal-review.md`, LF line endings. |
| 2 | §3.7 producer-path citation table | Yes (§3.7), 14 cells anchored to file:line. |
| 3 | One rule, one PR | Yes. Rule 4 + rule 5 get their own plans / PRs. |
| 4 | Stage-4 ask: ~10 invariants enumerated explicitly | Yes (§4): **14 invariants** enumerated. |
| 5 | Stage-5 plan: name primary + backup implementer | Yes (§5): Diego primary, Yuki backup. |
| 6 | Tests include an e2e regression test using real `run_rules` (Yuki-net pattern, ref `tests/test_playbook_cross_run_stability.py`) | Yes (test #11 in §3.8). |
| 7 | Conservative recommendation wording ("verify and then consider", not "renew" / "drop") | Yes (§2.5, §3.6). |
| 8 | Producer-path citations independently re-verified at stage-4 | Noor's job (§4 invariant 1). |
| 9 | `extra="forbid"` on any new pydantic model | No new model in this PR; existing `AzureReservation` keeps `extra="forbid"` (§3.2). |
| 10 | Twice-applied `ctx.redact()` for any user-identifying field | Yes (§3.5): two call sites for `reservation_id` (Finding.principal + render arg). |
