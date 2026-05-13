"""Unit tests for AZ.SAVINGS_PLAN_ELIGIBLE_SPEND rule."""

from __future__ import annotations

from finops_assess.engine import RuleContext, run_rules
from finops_assess.models import (
    AzureBenefitRecommendation,
    NormalizedDataset,
    Rule,
)


def _mock_rule(min_uncovered_usd: float = 50.0) -> Rule:
    """Return a mock rule instance for testing."""
    return Rule(
        id="AZ.SAVINGS_PLAN_ELIGIBLE_SPEND",
        surface="azure",
        severity="medium",
        summary="Test rule",
        recommendation_template=(
            "Scope {principal} shows uncovered on-demand spend of "
            "${cost_without_benefit_usd} over {lookback_period}. Azure's Benefit "
            "Recommendations API projects ${net_savings_usd} in savings if you "
            "verify the workload is steady-state and not the trailing edge of a "
            "one-off project, then consider a {term} Savings Plan commitment with "
            "an hourly commit of ${recommended_hourly_commit_usd}."
        ),
        min_uncovered_usd=min_uncovered_usd,
    )


def _mock_context(
    recommendations: list[AzureBenefitRecommendation],
    redact_pii: bool = False,
    min_uncovered_usd: float = 50.0,
) -> RuleContext:
    """Return a mock RuleContext for testing."""
    return RuleContext(
        rule=_mock_rule(min_uncovered_usd=min_uncovered_usd),
        dataset=NormalizedDataset(azure_benefit_recommendations=recommendations),
        catalog={},
        catalog_list=[],
        personas={},
        persona_assignments={},
        assignments_by_principal={},
        usage_by_principal={},
        redact_pii=redact_pii,
        salt="test-salt",
    )


def test_savings_plan_fires_on_eligible_spend() -> None:
    """Happy path: eligible spend produces one finding."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                scope_kind="Single",
                term="P1Y",
                lookback_period="Last30Days",
                arm_sku_name="Microsoft.Compute/virtualMachines/Standard_D4s_v5",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                wastage_usd=10.0,
                benefit_kind="SavingsPlan",
            )
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 1
    assert findings[0].rule_id == "AZ.SAVINGS_PLAN_ELIGIBLE_SPEND"
    assert findings[0].severity == "medium"
    assert findings[0].estimated_monthly_savings_usd == 120.0


def test_savings_plan_abstains_when_savings_zero() -> None:
    """E2: net_savings_usd == 0.0 → abstain."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=0.0,
                benefit_kind="SavingsPlan",
            )
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 0


def test_savings_plan_abstains_on_short_lookback() -> None:
    """E4: lookback_period == 'Last7Days' → abstain."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last7Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            )
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 0


def test_savings_plan_abstains_on_micro_uncovered_spend() -> None:
    """E3: cost_without_benefit_usd < threshold → abstain."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=10.0,
                recommended_hourly_commit_usd=0.10,
                net_savings_usd=2.0,
                benefit_kind="SavingsPlan",
            )
        ],
        min_uncovered_usd=50.0,
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 0


def test_savings_plan_abstains_on_null_signal() -> None:
    """E1: cost_without_benefit_usd == None → abstain."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=None,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            )
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 0


def test_savings_plan_dedups_per_scope_and_term() -> None:
    """E5: Two rows for (scope=X, term='P1Y') → one finding."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            ),
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r2",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last60Days",
                cost_without_benefit_usd=1200.0,
                recommended_hourly_commit_usd=1.60,
                net_savings_usd=140.0,
                benefit_kind="SavingsPlan",
            ),
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    # Collector preferentially picks Last60Days; rule sees only one after dedup
    assert len(findings) == 1


def test_savings_plan_redacts_principal_by_default() -> None:
    """Redact_pii=True → principal starts with 'sha256:' and len == 23.

    Cites src/finops_assess/engine.py:70-75 (RuleContext.redact).
    """
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            )
        ],
        redact_pii=True,
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 1
    assert findings[0].principal.startswith("sha256:")
    assert len(findings[0].principal) == 23


def test_savings_plan_emits_cleartext_with_redaction_off() -> None:
    """Redact_pii=False → principal == rec.scope exactly."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            )
        ],
        redact_pii=False,
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 1
    assert findings[0].principal == "/subscriptions/00000000-0000-0000-0000-000000000001"


def test_savings_plan_filters_benefit_kind() -> None:
    """NIT #2: benefit_kind != 'SavingsPlan' → abstain."""
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    ctx = _mock_context(
        [
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="Reservation",
            )
        ]
    )
    findings = list(savings_plan_eligible_spend(ctx))
    assert len(findings) == 0


def test_savings_plan_e2e_through_run_rules() -> None:
    """End-to-end regression: real run_rules engine.

    Pattern reference: tests/test_playbook_cross_run_stability.py:42-60 (Yuki-net).
    """
    dataset = NormalizedDataset(
        azure_benefit_recommendations=[
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r1",
                scope="/subscriptions/00000000-0000-0000-0000-000000000001",
                term="P1Y",
                lookback_period="Last30Days",
                cost_without_benefit_usd=1000.0,
                recommended_hourly_commit_usd=1.50,
                net_savings_usd=120.0,
                benefit_kind="SavingsPlan",
            ),
            # This row abstains (Last7Days + micro spend)
            AzureBenefitRecommendation(
                recommendation_id="/providers/Microsoft.CostManagement/benefitRecommendations/r2",
                scope="/subscriptions/00000000-0000-0000-0000-000000000002",
                term="P1Y",
                lookback_period="Last7Days",
                cost_without_benefit_usd=10.0,
                recommended_hourly_commit_usd=0.10,
                net_savings_usd=2.0,
                benefit_kind="SavingsPlan",
            ),
        ]
    )
    rule = _mock_rule()
    findings, _ = run_rules(
        rules=[rule],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=True,
        salt="test-salt-e2e",
    )
    # Exactly one finding (first row fires, second abstains)
    assert len(findings) == 1
    assert findings[0].rule_id == "AZ.SAVINGS_PLAN_ELIGIBLE_SPEND"
    assert findings[0].severity == "medium"
    assert findings[0].principal.startswith("sha256:")


# ---------------------------------------------------------------------------
# Stage-4 lockout regression tests for PR #85 (Noor BLOCKING items).
# These guard against the live ARM collector path that the original synthetic
# fixtures did not exercise. Each test cites the specific BLOCKING item it
# regresses against.
# ---------------------------------------------------------------------------


def _make_api_rec(
    *,
    rec_id: str,
    scope_discriminator: str,
    subscription_id: str | None = None,
    resource_group: str | None = None,
    kind: str = "SavingsPlan",
    term: str = "P1Y",
    lookback: str = "Last30Days",
    arm_sku_name: str = "Compute_Savings_Plan",
    cost_without_benefit: float = 1000.0,
    recommended_quantity: float = 1.5,
    net_savings: float = 120.0,
    wastage: float = 5.0,
) -> dict[str, object]:
    """Build a synthetic Cost Management Benefit Recommendation API row.

    Mirrors the shape documented at
    https://learn.microsoft.com/en-us/rest/api/cost-management/benefit-recommendations/list
    """
    props: dict[str, object] = {
        "scope": scope_discriminator,
        "term": term,
        "lookBackPeriod": lookback,
        "armSkuName": arm_sku_name,
        "recommendationDetails": {
            "costWithoutBenefit": cost_without_benefit,
            "recommendedQuantity": recommended_quantity,
            "netSavings": net_savings,
            "wastage": wastage,
        },
    }
    if subscription_id is not None:
        props["subscriptionId"] = subscription_id
    if resource_group is not None:
        props["resourceGroup"] = resource_group
    return {"id": rec_id, "kind": kind, "properties": props}


def test_m1_collector_writes_per_subscription_arn_not_discriminator() -> None:
    """M1 BLOCKING regression (PR #85, Noor stage-4): the collector helper MUST
    write the per-subscription ARN into ``scope`` and the discriminator into
    ``scope_kind``. Pre-fix, the discriminator string ``"Single"`` was written
    into both fields, collapsing N-subscription tenants to <=4 dedup rows.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_a = "11111111-1111-1111-1111-111111111111"
    sub_b = "22222222-2222-2222-2222-222222222222"
    rec_a = _make_api_rec(
        rec_id=f"/subscriptions/{sub_a}/providers/Microsoft.CostManagement/benefitRecommendations/r1",
        scope_discriminator="Single",
        subscription_id=sub_a,
    )
    rec_b = _make_api_rec(
        rec_id=f"/subscriptions/{sub_b}/providers/Microsoft.CostManagement/benefitRecommendations/r2",
        scope_discriminator="Single",
        subscription_id=sub_b,
    )

    row_a = _normalise_benefit_recommendation(rec_a, sub_a)
    row_b = _normalise_benefit_recommendation(rec_b, sub_b)
    assert row_a is not None and row_b is not None

    assert row_a["scope"] == f"/subscriptions/{sub_a}"
    assert row_b["scope"] == f"/subscriptions/{sub_b}"
    assert row_a["scope_kind"] == "Single"
    assert row_b["scope_kind"] == "Single"
    # Critical: scope MUST NOT carry the discriminator string
    assert row_a["scope"] != "Single"
    assert row_b["scope"] != "Single"
    # Critical: per-subscription scopes are distinct (no dedup collapse)
    assert row_a["scope"] != row_b["scope"]


def test_m1_single_scope_falls_back_to_iteration_sub_id() -> None:
    """M1 BLOCKING regression: when the API omits ``properties.subscriptionId``
    (older payload variant), fall back to the iteration's own subscription
    ARN -- never to the discriminator string.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_id = "33333333-3333-3333-3333-333333333333"
    rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/r3",
        scope_discriminator="Single",
        subscription_id=None,  # API omitted the field
    )
    row = _normalise_benefit_recommendation(rec, sub_id)
    assert row is not None
    assert row["scope"] == f"/subscriptions/{sub_id}"
    assert row["scope_kind"] == "Single"


def test_m1_single_scope_with_resource_group_carries_rg_in_arn() -> None:
    """M1 BLOCKING regression: a Single-scope recommendation that targets a
    resource group emits an ARN that includes the resourceGroups segment.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_id = "44444444-4444-4444-4444-444444444444"
    rec = _make_api_rec(
        rec_id=(
            f"/subscriptions/{sub_id}/resourceGroups/rg-prod/providers/"
            "Microsoft.CostManagement/benefitRecommendations/r4"
        ),
        scope_discriminator="Single",
        subscription_id=sub_id,
        resource_group="rg-prod",
    )
    row = _normalise_benefit_recommendation(rec, sub_id)
    assert row is not None
    assert row["scope"] == f"/subscriptions/{sub_id}/resourceGroups/rg-prod"
    assert row["scope_kind"] == "Single"


def test_m1_shared_scope_derives_arn_from_recommendation_id() -> None:
    """M1 BLOCKING regression: a Shared-scope recommendation derives its ARN
    from the recommendation ``id`` URL path (the parent of the
    ``/providers/Microsoft.CostManagement/...`` segment), not from the
    discriminator string.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    billing_account = "987654"
    rec_id = (
        f"/providers/Microsoft.Billing/billingAccounts/{billing_account}/providers/"
        "Microsoft.CostManagement/benefitRecommendations/r5"
    )
    rec = _make_api_rec(
        rec_id=rec_id,
        scope_discriminator="Shared",
    )
    row = _normalise_benefit_recommendation(rec, "ignored-iteration-sub")
    assert row is not None
    assert row["scope"] == f"/providers/Microsoft.Billing/billingAccounts/{billing_account}"
    assert row["scope_kind"] == "Shared"
    assert row["scope"] != "Shared"


def test_m3_collector_parses_benefit_kind_from_api_discriminator() -> None:
    """M3 BLOCKING regression (PR #85, Noor stage-4): the collector helper
    populates ``benefit_kind`` from the API's top-level ``kind`` discriminator.
    Pre-fix, every row was relabelled ``SavingsPlan``, defeating the rule-side
    NIT #2 filter at azure_rules.py:310.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_id = "55555555-5555-5555-5555-555555555555"
    sp_rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/sp",
        scope_discriminator="Single",
        subscription_id=sub_id,
        kind="SavingsPlan",
    )
    res_rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/res",
        scope_discriminator="Single",
        subscription_id=sub_id,
        kind="Reservation",
    )
    sp_row = _normalise_benefit_recommendation(sp_rec, sub_id)
    res_row = _normalise_benefit_recommendation(res_rec, sub_id)
    assert sp_row is not None and res_row is not None
    assert sp_row["benefit_kind"] == "SavingsPlan"
    assert res_row["benefit_kind"] == "Reservation"


def test_m3_rule_abstains_on_reservation_kind_through_collector_path() -> None:
    """M3 BLOCKING regression: a Reservation-kind row from the collector path
    must reach the rule with ``benefit_kind="Reservation"`` so the rule-side
    NIT #2 filter abstains. Pre-fix, every row was relabelled ``SavingsPlan``
    and the filter was dead code in production.
    """
    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation
    from finops_assess.rules_impl.azure_rules import savings_plan_eligible_spend

    sub_id = "66666666-6666-6666-6666-666666666666"
    res_rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/res",
        scope_discriminator="Single",
        subscription_id=sub_id,
        kind="Reservation",
    )
    row = _normalise_benefit_recommendation(res_rec, sub_id)
    assert row is not None

    # Round-trip the row through the model the same way csv_collector does.
    model_row = AzureBenefitRecommendation(
        recommendation_id=row["recommendation_id"],
        scope=row["scope"],
        scope_kind=row["scope_kind"] or None,  # type: ignore[arg-type]
        term=row["term"],  # type: ignore[arg-type]
        lookback_period=row["lookback_period"],  # type: ignore[arg-type]
        arm_sku_name=row["arm_sku_name"] or None,
        cost_without_benefit_usd=float(row["cost_without_benefit_usd"]),
        recommended_hourly_commit_usd=float(row["recommended_hourly_commit_usd"]),
        net_savings_usd=float(row["net_savings_usd"]),
        wastage_usd=float(row["wastage_usd"]),
        benefit_kind=row["benefit_kind"],  # type: ignore[arg-type]
    )
    ctx = _mock_context([model_row])
    findings = list(savings_plan_eligible_spend(ctx))
    assert findings == []


def test_n4_collector_skips_unknown_term_with_warning(caplog) -> None:  # type: ignore[no-untyped-def]
    """N4 NIT regression: an unknown ``term`` enum value is skipped with a
    warning instead of crashing the collector with a hard pydantic
    ValidationError on the downstream model construction.
    """
    import logging

    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_id = "77777777-7777-7777-7777-777777777777"
    rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/r-future",
        scope_discriminator="Single",
        subscription_id=sub_id,
        term="P5Y",  # Hypothetical future term Microsoft has not yet released.
    )
    with caplog.at_level(logging.WARNING, logger="finops_assess.collectors.arm_collector"):
        row = _normalise_benefit_recommendation(rec, sub_id)
    assert row is None
    assert any("unrecognised term" in rec.message for rec in caplog.records)


def test_n4_collector_skips_unsupported_kind_with_warning(caplog) -> None:  # type: ignore[no-untyped-def]
    """N4 NIT regression: an unsupported ``kind`` (e.g. ``IncludedQuantity``,
    which the model intentionally does not list) is skipped with a warning.
    """
    import logging

    from finops_assess.collectors.arm_collector import _normalise_benefit_recommendation

    sub_id = "88888888-8888-8888-8888-888888888888"
    rec = _make_api_rec(
        rec_id="/providers/Microsoft.CostManagement/benefitRecommendations/r-iq",
        scope_discriminator="Single",
        subscription_id=sub_id,
        kind="IncludedQuantity",
    )
    with caplog.at_level(logging.WARNING, logger="finops_assess.collectors.arm_collector"):
        row = _normalise_benefit_recommendation(rec, sub_id)
    assert row is None
    assert any("unsupported kind" in rec.message for rec in caplog.records)
