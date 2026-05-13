"""Unit tests for AZ.COMMITMENT_UNDER_COVERED rule.

Test plan: docs/plans/059-az-commitment-under-covered.md §3.8.
Pattern reference for the e2e / cross-run regression tests:
``tests/test_playbook_cross_run_stability.py:1-80`` (Yuki-net, real
``run_rules`` engine, no mocked rule callable).
"""

from __future__ import annotations

from finops_assess.engine import RuleContext, run_rules
from finops_assess.models import (
    AzureReservation,
    AzureResource,
    NormalizedDataset,
    Rule,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_rule(rule_id: str = "AZ.COMMITMENT_UNDER_COVERED") -> Rule:
    """Return a mock rule instance mirroring the shipped YAML."""
    return Rule(
        id=rule_id,
        surface="azure",
        severity="medium",
        summary="Test rule",
        recommendation_template=(
            "Reservation {principal} is {scope_kind}-scope and averaged "
            "{utilization_pct}% utilisation, while sibling subscription "
            "{sibling_sub} shows ${sibling_on_demand_spend_usd} of on-demand "
            "resource spend over the same window. Verify the sibling's "
            "on-demand SKUs are compatible with this reservation's family "
            "and region (Azure auto-applies on a best-fit basis), then "
            "consider widening the reservation's applied scope so the "
            "sibling's workload absorbs the unused capacity."
        ),
    )


def _reservation_underutilized_rule() -> Rule:
    """Mirror the shipped AZ.RESERVATION_UNDERUTILIZED rule for cross-rule tests."""
    return Rule(
        id="AZ.RESERVATION_UNDERUTILIZED",
        surface="azure",
        severity="high",
        summary="Under-utilised Azure Reservation / Savings Plan.",
        recommendation_template=(
            "Reservation {principal} averaged {utilization_pct}% utilisation. "
            "Exchange or shrink the commitment at next renewal."
        ),
    )


def _mock_context(
    reservations: list[AzureReservation],
    resources: list[AzureResource],
    redact_pii: bool = False,
) -> RuleContext:
    """Return a mock RuleContext for unit testing the rule callable directly."""
    return RuleContext(
        rule=_mock_rule(),
        dataset=NormalizedDataset(
            azure_reservations=reservations,
            azure_resources=resources,
        ),
        catalog={},
        catalog_list=[],
        personas={},
        persona_assignments={},
        assignments_by_principal={},
        usage_by_principal={},
        redact_pii=redact_pii,
        salt="test-salt",
    )


def _shared_reservation(util: float | None = 45.0) -> AzureReservation:
    """A shared-scope reservation that satisfies the utilisation gate by default."""
    return AzureReservation(
        reservation_id=(
            "/subscriptions/00000000/providers/Microsoft.Capacity"
            "/reservationOrders/ro-001/reservations/ri-001"
        ),
        reservation_name="RI-VM-D4s-EastUS",
        sku="Standard_D4s_v5",
        scope="shared",
        utilization_pct=util,
        monthly_cost_usd=500.0,
    )


def _single_reservation(util: float | None = 40.0) -> AzureReservation:
    """A single-scope reservation that satisfies the utilisation gate by default."""
    return AzureReservation(
        reservation_id=(
            "/subscriptions/owner-sub/providers/Microsoft.Capacity"
            "/reservationOrders/ro-002/reservations/ri-002"
        ),
        reservation_name="RI-SQL-Single",
        sku="GP_Gen5_8",
        scope="single",
        utilization_pct=util,
        monthly_cost_usd=800.0,
    )


def _resource(
    sub: str = "sub-B",
    cost: float | None = 200.0,
    suffix: str = "vm-1",
) -> AzureResource:
    """An Azure resource row used to build sibling on-demand spend."""
    return AzureResource(
        resource_id=f"/subscriptions/{sub}/rg/prod/vm/{suffix}",
        resource_type="virtualMachine",
        sku="Standard_D4s_v5",
        location="eastus",
        avg_cpu_pct=55.0,
        p95_cpu_pct=68.0,
        p95_mem_pct=72.0,
        avg_net_kbps=1200.0,
        monthly_cost_usd=cost,
        subscription_id=sub,
    )


# ---------------------------------------------------------------------------
# Plan §3.8 test 1: positive fire path
# ---------------------------------------------------------------------------


def test_commitment_under_covered_fires_on_undercovered_sibling() -> None:
    """One under-utilised Single-scope reservation + one $200 sibling row -> one finding."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[_resource(sub="sub-B", cost=200.0)],
    )
    findings = list(commitment_under_covered(ctx))
    assert len(findings) == 1
    assert findings[0].rule_id == "AZ.COMMITMENT_UNDER_COVERED"
    assert findings[0].severity == "medium"
    assert findings[0].current_sku == "GP_Gen5_8"
    assert findings[0].estimated_monthly_savings_usd is None
    assert findings[0].evidence["scope_kind"] == "Single"
    assert findings[0].evidence["utilization_pct"] == 45.0
    assert findings[0].evidence["sibling_on_demand_spend_usd"] == 200.0


# ---------------------------------------------------------------------------
# Plan §3.8 test 2: abstain on high utilisation (E2)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_abstains_on_high_utilization() -> None:
    """E2: reservation utilisation >= 80% -> no finding."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=95.0)],
        resources=[_resource(sub="sub-B", cost=200.0)],
    )
    findings = list(commitment_under_covered(ctx))
    assert findings == []


# ---------------------------------------------------------------------------
# Plan §3.8 test 3: abstain on null utilisation (E9)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_abstains_on_null_utilization() -> None:
    """E9: reservation utilisation None -> abstain (do not assume zero)."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=None)],
        resources=[_resource(sub="sub-B", cost=200.0)],
    )
    findings = list(commitment_under_covered(ctx))
    assert findings == []


# ---------------------------------------------------------------------------
# Plan §3.8 test 4: abstain on no sibling spend (E10)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_abstains_on_no_sibling_spend() -> None:
    """E10: zero azure_resources rows -> rule short-circuits, no finding."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[],
    )
    findings = list(commitment_under_covered(ctx))
    assert findings == []


def test_commitment_under_covered_abstains_when_cost_is_none() -> None:
    """E10-adjacent: every resource has monthly_cost_usd=None -> no signal -> no finding."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[_resource(sub="sub-B", cost=None)],
    )
    findings = list(commitment_under_covered(ctx))
    assert findings == []


# ---------------------------------------------------------------------------
# Plan §3.8 test 5: abstain on micro-spend sibling (E3)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_abstains_on_micro_sibling_spend() -> None:
    """E3: sibling on-demand spend < $50/month -> skip the sibling -> no finding."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[_resource(sub="sub-B", cost=10.0)],
    )
    findings = list(commitment_under_covered(ctx))
    assert findings == []


# ---------------------------------------------------------------------------
# Plan §3.8 test 6: dedup invariant on (reservation_id, sibling_sub) (E8)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_dedups_per_reservation_and_sibling() -> None:
    """E8: two resource rows for the same sibling sub -> one finding, $400 aggregated."""
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[
            _resource(sub="sub-B", cost=200.0, suffix="vm-1"),
            _resource(sub="sub-B", cost=200.0, suffix="vm-2"),
        ],
    )
    findings = list(commitment_under_covered(ctx))
    assert len(findings) == 1
    assert findings[0].evidence["sibling_on_demand_spend_usd"] == 400.0


# ---------------------------------------------------------------------------
# Plan §3.8 test 7: redaction on by default (twice-applied)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_redacts_principal_and_sibling_by_default() -> None:
    """Cites engine.py:70-75 (RuleContext.redact). With redact_pii=True (default),
    finding.principal AND finding.evidence['sibling_sub'] both start with 'sha256:'.
    """
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[_resource(sub="sub-B", cost=200.0)],
        redact_pii=True,
    )
    findings = list(commitment_under_covered(ctx))
    assert len(findings) == 1
    assert findings[0].principal.startswith("sha256:")
    assert len(findings[0].principal) == 23
    assert findings[0].evidence["sibling_sub"].startswith("sha256:")
    assert len(findings[0].evidence["sibling_sub"]) == 23


# ---------------------------------------------------------------------------
# Plan §3.8 test 8: cleartext when --no-pii-redaction
# ---------------------------------------------------------------------------


def test_commitment_under_covered_emits_cleartext_with_redaction_off() -> None:
    """With redact_pii=False, principal == reservation.reservation_id exactly,
    AND evidence['sibling_sub'] == 'sub-B' exactly.
    """
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    reservation = _single_reservation(util=45.0)
    ctx = _mock_context(
        reservations=[reservation],
        resources=[_resource(sub="sub-B", cost=200.0)],
        redact_pii=False,
    )
    findings = list(commitment_under_covered(ctx))
    assert len(findings) == 1
    assert findings[0].principal == reservation.reservation_id
    assert findings[0].evidence["sibling_sub"] == "sub-B"


# ---------------------------------------------------------------------------
# Plan §3.8 test 9: intentional dual-fire with AZ.RESERVATION_UNDERUTILIZED (§2.4)
# ---------------------------------------------------------------------------


def test_commitment_under_covered_overlaps_reservation_underutilized() -> None:
    """Plan §2.4: every rule-2 finding intentionally co-fires with rule
    AZ.RESERVATION_UNDERUTILIZED on the same reservation. This is the
    cross-rule isolation invariant -- complementary, not duplicative.
    """
    dataset = NormalizedDataset(
        azure_reservations=[_single_reservation(util=45.0)],
        azure_resources=[_resource(sub="sub-B", cost=200.0)],
    )
    findings, _ = run_rules(
        rules=[_mock_rule(), _reservation_underutilized_rule()],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=False,
        salt="test-salt-overlap",
    )
    rule_ids = {f.rule_id for f in findings}
    assert "AZ.COMMITMENT_UNDER_COVERED" in rule_ids
    assert "AZ.RESERVATION_UNDERUTILIZED" in rule_ids


# ---------------------------------------------------------------------------
# Plan §3.8 test 10: end-to-end regression through real run_rules engine
# ---------------------------------------------------------------------------


def test_commitment_under_covered_e2e_through_run_rules() -> None:
    """End-to-end regression: real run_rules engine, no mocked callable.

    Pattern reference: tests/test_playbook_cross_run_stability.py:1-80 (Yuki-net).
    Two reservations + two siblings; only the under-utilised reservation paired
    with the sibling crossing the $50 threshold should produce a finding.
    """
    dataset = NormalizedDataset(
        azure_reservations=[
            _single_reservation(util=45.0),  # under-utilised, fires
            _shared_reservation(util=92.0),  # above threshold, abstains (E2)
        ],
        azure_resources=[
            _resource(sub="sub-B", cost=200.0),  # crosses $50, fires
            _resource(sub="sub-C", cost=10.0),  # below $50, skipped (E3)
        ],
    )
    findings, _ = run_rules(
        rules=[_mock_rule()],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=True,
        salt="test-salt-e2e",
    )
    matching = [f for f in findings if f.rule_id == "AZ.COMMITMENT_UNDER_COVERED"]
    assert len(matching) == 1
    assert matching[0].severity == "medium"
    assert matching[0].principal.startswith("sha256:")


# ---------------------------------------------------------------------------
# Plan §3.8 test 11: cross-run principal instability with default redaction
# ---------------------------------------------------------------------------


def test_commitment_under_covered_redacted_principal_unstable_across_runs() -> None:
    """Inherits the PR #78 cross-run-stability test pattern. Two run_rules
    invocations with redact_pii=True (default) and no shared salt produce
    DIFFERENT redacted principals for the same reservation. Azure surface
    is declared 'per_run' in the playbook manifest post-PR-#78; this test
    prevents future drift.
    """
    dataset = NormalizedDataset(
        azure_reservations=[_single_reservation(util=45.0)],
        azure_resources=[_resource(sub="sub-B", cost=200.0)],
    )

    def _run() -> str:
        findings, _ = run_rules(
            rules=[_mock_rule()],
            catalog=[],
            personas=[],
            persona_assignments={},
            dataset=dataset,
            redact_pii=True,
            # no salt -> engine draws a per-run secrets.token_hex(16)
        )
        matching = [f for f in findings if f.rule_id == "AZ.COMMITMENT_UNDER_COVERED"]
        assert len(matching) == 1
        return matching[0].principal

    principal_run1 = _run()
    principal_run2 = _run()
    assert principal_run1.startswith("sha256:")
    assert principal_run2.startswith("sha256:")
    assert principal_run1 != principal_run2, (
        "Redacted principals must rotate across runs under default redaction "
        "(per-run salt). If this test passes, the engine started honouring "
        "a tenant-stable salt -- update the playbook manifest contract too."
    )


# ---------------------------------------------------------------------------
# Plan §2.2 E11: over-count on Single-scope reservations is documented, not silent
# ---------------------------------------------------------------------------


def test_commitment_under_covered_overcounts_owner_sub_on_single_scope() -> None:
    """E11: Single-scope reservations may include the owner sub as a "sibling".

    The current schema does not record which sub a Single-scope reservation
    is locked to (``applied_scope_subscription_ids`` is the natural fix and
    is the territory of rule 4, ``AZ.RESERVATION_SCOPE_MISMATCH``). The
    conservative posture documented in plan §2.2 / §2.5 is: count every sub
    in the dataset as a candidate sibling, including the owner sub itself.

    This test asserts the over-count behaviour is preserved (every sibling
    sub crossing the $50 threshold produces a finding, even when one of
    them is the owner of a Single-scope reservation). A future change that
    silently drops the owner sub before rule 4 ships would regress this
    invariant; the matching code comment lives at
    ``src/finops_assess/rules_impl/azure_rules.py`` near the
    ``for sibling_sub, on_demand in sibling_spend.items():`` loop.
    """
    from finops_assess.rules_impl.azure_rules import commitment_under_covered

    # Single-scope reservation whose ARM ID encodes "owner-sub" as the locked sub.
    # Two siblings cross the threshold: "owner-sub" itself (the over-count) and "sub-C".
    ctx = _mock_context(
        reservations=[_single_reservation(util=45.0)],
        resources=[
            _resource(sub="owner-sub", cost=300.0, suffix="vm-owner"),
            _resource(sub="sub-C", cost=200.0, suffix="vm-c"),
        ],
        redact_pii=False,
    )
    findings = list(commitment_under_covered(ctx))
    assert len(findings) == 2, (
        "Conservative E11 posture: owner-sub appears as a 'sibling' alongside "
        "the genuine sibling sub. The over-count is preferable to silently "
        "dropping a real sibling. Sharpens once rule 4 lands "
        "appliedScopeSubscriptionIds (plan §2.2 / §2.5)."
    )
    sibling_subs = {f.evidence["sibling_sub"] for f in findings}
    assert sibling_subs == {"owner-sub", "sub-C"}
