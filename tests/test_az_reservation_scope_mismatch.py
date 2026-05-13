"""Tests for AZ.RESERVATION_SCOPE_MISMATCH.

Test plan: ``docs/plans/059-az-reservation-scope-mismatch.md`` §3.8.
Pattern reference: ``tests/test_az_commitment_renewal_review.py`` (Yuki-net
pattern — real ``run_rules`` engine, NOT a mocked rule callable).

This rule does NOT depend on the wall clock so no ``_today_utc``
monkeypatching is needed. The rule pre-aggregates spend per subscription
from ``azure_resources`` and compares with the reservation's
``applied_scope_subscription_ids`` to identify scope mismatches.
"""

from __future__ import annotations

import logging

import pytest

from finops_assess.engine import run_rules
from finops_assess.models import (
    AzureReservation,
    AzureResource,
    Finding,
    NormalizedDataset,
    Rule,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _scope_mismatch_rule(*, threshold: float = 50.0) -> Rule:
    """Mirror the shipped AZ.RESERVATION_SCOPE_MISMATCH rule definition."""
    return Rule(
        id="AZ.RESERVATION_SCOPE_MISMATCH",
        surface="azure",
        severity="medium",
        summary=(
            "Single-scope reservation while sibling subscriptions carry significant "
            "on-demand spend for likely-compatible workloads."
        ),
        recommendation_template=(
            "Reservation {principal} is scoped to {owner_subs} while subscriptions "
            "{sibling_subs} carry ${non_owner_usd}/mo of on-demand spend on "
            "potentially compatible workloads. Consider widening the reservation's "
            "applied scope (Single → Shared or Management Group) so the sibling "
            "workloads can absorb unused reserved capacity, or verify the narrow "
            "scope is intentional (e.g., chargeback isolation)."
        ),
        min_uncovered_usd=threshold,
    )


def _reservation_underutilized_rule() -> Rule:
    """Mirror AZ.RESERVATION_UNDERUTILIZED for cross-rule co-fire pin."""
    return Rule(
        id="AZ.RESERVATION_UNDERUTILIZED",
        surface="azure",
        severity="high",
        summary="Reservation / Savings Plan utilization below 80% for 30 days.",
        recommendation_template=(
            "Reservation {principal} averaged {utilization_pct}% utilization "
            "over 30 days. Exchange or shrink the commitment at next renewal."
        ),
        inactivity_days=30,
    )


def _reservation(
    *,
    rid: str = "/subscriptions/00000000/providers/Microsoft.Capacity/reservationOrders/ro-x/reservations/ri-x",
    scope: str = "single",
    scope_ids: list[str] | None = None,
    utilization_pct: float | None = 90.0,
    monthly_cost_usd: float | None = 800.0,
    sku: str = "Standard_D4s_v5",
) -> AzureReservation:
    """Build an ``AzureReservation`` for the rule under test."""
    return AzureReservation(
        reservation_id=rid,
        reservation_name="RI-test",
        sku=sku,
        scope=scope,
        utilization_pct=utilization_pct,
        monthly_cost_usd=monthly_cost_usd,
        applied_scope_subscription_ids=scope_ids,
    )


def _resource(
    *,
    subscription_id: str = "sub-owner",
    monthly_cost_usd: float = 200.0,
    resource_id: str | None = None,
) -> AzureResource:
    """Build an ``AzureResource`` with spend in a given subscription."""
    return AzureResource(
        resource_id=resource_id or f"/subscriptions/{subscription_id}/rg/test/vm/vm-1",
        resource_type="virtualMachine",
        sku="Standard_D4s_v5",
        location="eastus",
        monthly_cost_usd=monthly_cost_usd,
        subscription_id=subscription_id,
    )


def _run(
    *,
    reservations: list[AzureReservation],
    resources: list[AzureResource] | None = None,
    rules: list[Rule] | None = None,
    redact_pii: bool = False,
    salt: str = "test-salt",
) -> list[Finding]:
    """Drive ``run_rules`` end-to-end with the synthetic dataset (Yuki-net)."""
    dataset = NormalizedDataset(
        azure_reservations=reservations,
        azure_resources=resources or [],
    )
    findings, _summary = run_rules(
        rules=rules or [_scope_mismatch_rule()],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=redact_pii,
        salt=salt,
    )
    return findings


# ---------------------------------------------------------------------------
# Test #1: Happy path — single-scope RI with sibling spend > threshold
# ---------------------------------------------------------------------------


def test_fires_on_single_scope_with_sibling_spend() -> None:
    """Single-scope RI owner=sub-owner, sibling=sub-sibling with $200 spend."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=300.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=200.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-sib",
            ),
        ],
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "AZ.RESERVATION_SCOPE_MISMATCH"
    assert f.surface == "azure"
    assert f.severity == "medium"
    assert f.estimated_monthly_savings_usd == 200.0
    assert f.evidence["non_owner_monthly_usd"] == 200.0
    assert len(f.evidence["sibling_subscription_ids"]) == 1


# ---------------------------------------------------------------------------
# Test #2: Abstain — scope=None (E2)
# ---------------------------------------------------------------------------


def test_abstains_on_missing_scope() -> None:
    """scope=None → rule cannot classify, abstains."""
    findings = _run(
        reservations=[
            _reservation(scope=None, scope_ids=["/subscriptions/sub-owner"]),  # type: ignore[arg-type]
        ],
        resources=[
            _resource(subscription_id="sub-sibling", monthly_cost_usd=200.0),
        ],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #3: Abstain — scope=shared (E3)
# ---------------------------------------------------------------------------


def test_abstains_on_shared_scope() -> None:
    """Shared-scope reservations are not single → abstain."""
    findings = _run(
        reservations=[
            _reservation(scope="shared", scope_ids=None),
        ],
        resources=[
            _resource(subscription_id="sub-sibling", monthly_cost_usd=200.0),
        ],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #4: Abstain — applied_scope_subscription_ids=None (E4)
# ---------------------------------------------------------------------------


def test_abstains_on_scope_ids_none() -> None:
    """scope=single but no scope IDs provided → signal absent, abstain."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=None),
        ],
        resources=[
            _resource(subscription_id="sub-sibling", monthly_cost_usd=200.0),
        ],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #5: Abstain — applied_scope_subscription_ids=[] (E5) + WARN
# ---------------------------------------------------------------------------


def test_abstains_on_empty_scope_ids_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """scope=single + empty list → contradictory, abstain + WARN log."""
    with caplog.at_level(logging.WARNING):
        findings = _run(
            reservations=[
                _reservation(scope="single", scope_ids=[]),
            ],
            resources=[
                _resource(subscription_id="sub-sibling", monthly_cost_usd=200.0),
            ],
        )
    assert findings == []
    assert "empty" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Test #6: Abstain — no azure_resources at all (E6)
# ---------------------------------------------------------------------------


def test_abstains_on_no_resources() -> None:
    """No spend data at all → nothing to compare, abstain."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #7: Abstain — all spend in owner sub (E7)
# ---------------------------------------------------------------------------


def test_abstains_when_all_spend_in_owner_sub() -> None:
    """All resource spend in the owner subscription → no mismatch."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=500.0),
        ],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #8: Abstain — sibling spend below threshold (E8)
# ---------------------------------------------------------------------------


def test_abstains_when_sibling_spend_below_threshold() -> None:
    """Sibling spend of $30 < $50 threshold → too small to matter."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=500.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=30.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-cheap",
            ),
        ],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #9: Multiple siblings aggregate
# ---------------------------------------------------------------------------


def test_multiple_siblings_aggregate_spend() -> None:
    """Two siblings each at $40 → $80 total > $50 threshold → fires."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=500.0),
            _resource(
                subscription_id="sub-sib-1",
                monthly_cost_usd=40.0,
                resource_id="/subscriptions/sub-sib-1/rg/test/vm/vm-1",
            ),
            _resource(
                subscription_id="sub-sib-2",
                monthly_cost_usd=40.0,
                resource_id="/subscriptions/sub-sib-2/rg/test/vm/vm-2",
            ),
        ],
    )
    assert len(findings) == 1
    assert findings[0].estimated_monthly_savings_usd == 80.0
    assert len(findings[0].evidence["sibling_subscription_ids"]) == 2


# ---------------------------------------------------------------------------
# Test #10: Case-insensitive scope match ("Single" vs "single")
# ---------------------------------------------------------------------------


def test_scope_case_insensitive() -> None:
    """ARM API may return 'Single' with a capital S; rule normalises."""
    findings = _run(
        reservations=[
            _reservation(scope="Single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=300.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=200.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-s",
            ),
        ],
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# Test #11: Custom threshold via min_uncovered_usd
# ---------------------------------------------------------------------------


def test_custom_threshold() -> None:
    """Rule YAML can set a higher threshold; sibling spend below it → abstain."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=500.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=80.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-t",
            ),
        ],
        rules=[_scope_mismatch_rule(threshold=100.0)],
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Test #12: Yuki-net integration — real run_rules end-to-end
# ---------------------------------------------------------------------------


def test_yuki_net_integration() -> None:
    """Full ``run_rules`` with shipped rule definitions (Yuki-net pattern).

    Uses the real rule loader to confirm the YAML entry wires correctly
    to the Python implementation.
    """
    from finops_assess.rules import load_rules

    all_rules = load_rules()
    scope_rule = [r for r in all_rules if r.id == "AZ.RESERVATION_SCOPE_MISMATCH"]
    assert len(scope_rule) == 1, "AZ.RESERVATION_SCOPE_MISMATCH must exist in shipped YAML"

    dataset = NormalizedDataset(
        azure_reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        azure_resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=300.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=200.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-yn",
            ),
        ],
    )
    findings, _summary = run_rules(
        rules=scope_rule,
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=False,
        salt="yuki-net",
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "AZ.RESERVATION_SCOPE_MISMATCH"


# ---------------------------------------------------------------------------
# Test #13: Co-fire with AZ.RESERVATION_UNDERUTILIZED
# ---------------------------------------------------------------------------


def test_co_fire_with_underutilized() -> None:
    """One reservation can produce both scope-mismatch AND underutilised findings."""
    findings = _run(
        reservations=[
            _reservation(
                scope="single",
                scope_ids=["/subscriptions/sub-owner"],
                utilization_pct=40.0,  # below 80% → underutilised
            ),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=300.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=200.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-cf",
            ),
        ],
        rules=[_scope_mismatch_rule(), _reservation_underutilized_rule()],
    )
    rule_ids = {f.rule_id for f in findings}
    assert "AZ.RESERVATION_SCOPE_MISMATCH" in rule_ids
    assert "AZ.RESERVATION_UNDERUTILIZED" in rule_ids


# ---------------------------------------------------------------------------
# Test #14: PII redaction hashes subscription IDs
# ---------------------------------------------------------------------------


def test_pii_redaction_hashes_sub_ids() -> None:
    """With redact_pii=True, owner and sibling sub IDs must be hashed."""
    findings = _run(
        reservations=[
            _reservation(scope="single", scope_ids=["/subscriptions/sub-owner"]),
        ],
        resources=[
            _resource(subscription_id="sub-owner", monthly_cost_usd=300.0),
            _resource(
                subscription_id="sub-sibling",
                monthly_cost_usd=200.0,
                resource_id="/subscriptions/sub-sibling/rg/test/vm/vm-pii",
            ),
        ],
        redact_pii=True,
        salt="test-pii-salt",
    )
    assert len(findings) == 1
    f = findings[0]
    # The principal and evidence sub IDs should NOT contain the raw values
    assert "/subscriptions/sub-owner" not in f.principal
    assert "/subscriptions/sub-sibling" not in f.principal
    for sid in f.evidence["owner_subscription_ids"]:
        assert "/subscriptions/sub-owner" not in sid
    for sid in f.evidence["sibling_subscription_ids"]:
        assert "/subscriptions/sub-sibling" not in sid
