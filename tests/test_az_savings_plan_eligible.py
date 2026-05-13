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
