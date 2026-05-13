"""Tests for AZ.COMMITMENT_RENEWAL_REVIEW.

Test plan: ``docs/plans/059-az-commitment-renewal-review.md`` §3.8.
Yuki-net pattern reference: ``tests/test_playbook_cross_run_stability.py:1-80``
(real ``run_rules`` engine, NOT a mocked rule callable). Cross-run regression
caught BLOCKING #1 in PR #78; the same pattern is used here so any future
producer-path regression is visible at unit-test time, not in CI on a real
tenant.

Date determinism: every test that hits the rule body monkeypatches
``finops_assess.rules_impl.azure_rules._today_utc`` to a fixed date so the
edge cases are stable regardless of the wall clock. The ``FINOPS_NOW_OVERRIDE``
env var is the same seam used by ``scripts/generate_docs.py`` and
``tests/test_engine.py`` for the engine smoke test.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from finops_assess.engine import run_rules
from finops_assess.models import (
    AzureReservation,
    AzureResource,
    NormalizedDataset,
    Rule,
)

# A stable "today" anchor shared by every test in this module. All synthetic
# expiry_date values are picked relative to this anchor, then ``_today_utc``
# is monkeypatched to return it.
_FIXED_TODAY = date(2026, 5, 13)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _freeze_today(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin AZ.COMMITMENT_RENEWAL_REVIEW's "today" to a fixed date.

    Patches the ``_today_utc`` helper directly so neither the wall clock nor
    a stray ``FINOPS_NOW_OVERRIDE`` from another test can leak in. Tests that
    need to exercise the env-var seam itself opt out via the
    ``no_freeze_today`` marker.
    """
    if request.node.get_closest_marker("no_freeze_today"):
        return
    monkeypatch.setattr(
        "finops_assess.rules_impl.azure_rules._today_utc",
        lambda: _FIXED_TODAY,
    )


def _renewal_review_rule() -> Rule:
    """Mirror the shipped AZ.COMMITMENT_RENEWAL_REVIEW rule definition."""
    return Rule(
        id="AZ.COMMITMENT_RENEWAL_REVIEW",
        surface="azure",
        severity="medium",
        summary=(
            "Reservation expiring within the near-expiry window with auto-renew not configured."
        ),
        recommendation_template=(
            "Reservation {principal} ({term}) expires on {expiry_date} "
            "(in {days_until_expiry} days) and is not configured to auto-renew. "
            "Verify whether the workload still needs reserved capacity. If yes, "
            "consider renewing or exchanging the reservation before the expiry date. "
            "If no, plan for the workload to fall back to on-demand pricing on "
            "{expiry_date} and capture the projected on-demand cost in your forecast."
        ),
        inactivity_days=60,
    )


def _reservation_underutilized_rule() -> Rule:
    """Mirror the shipped AZ.RESERVATION_UNDERUTILIZED rule for cross-rule co-fire pin."""
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
    expiry_date: str | None,
    auto_renew: bool | None,
    utilization_pct: float | None = 90.0,
    sku: str = "Standard_D4s_v5",
    scope: str = "shared",
) -> AzureReservation:
    """Build an ``AzureReservation`` for the rule under test."""
    return AzureReservation(
        reservation_id=rid,
        reservation_name="RI-test",
        sku=sku,
        scope=scope,
        utilization_pct=utilization_pct,
        monthly_cost_usd=500.0,
        expiry_date=expiry_date,
        auto_renew=auto_renew,
    )


def _run(
    *,
    reservations: list[AzureReservation],
    resources: list[AzureResource] | None = None,
    rules: list[Rule] | None = None,
    redact_pii: bool = False,
    salt: str = "test-salt",
) -> list:
    """Drive ``run_rules`` end-to-end with the synthetic dataset (Yuki-net)."""
    dataset = NormalizedDataset(
        azure_reservations=reservations,
        azure_resources=resources or [],
    )
    findings, _summary = run_rules(
        rules=rules or [_renewal_review_rule()],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=redact_pii,
        salt=salt,
    )
    return findings


def _iso(d: date) -> str:
    return d.isoformat()


# ---------------------------------------------------------------------------
# Tests #1 to #13 (plan §3.8)
# ---------------------------------------------------------------------------


def test_renewal_review_fires_on_near_expiry_no_auto_renew() -> None:
    """E7: 30 days out, auto_renew=False -> exactly one medium finding."""
    expiry = _iso(date(2026, 6, 12))  # _FIXED_TODAY + 30 days
    findings = _run(
        reservations=[_reservation(expiry_date=expiry, auto_renew=False)],
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "AZ.COMMITMENT_RENEWAL_REVIEW"
    assert f.surface == "azure"
    assert f.severity == "medium"
    assert f.evidence["expiry_date"] == expiry
    assert f.evidence["days_until_expiry"] == 30
    assert f.evidence["auto_renew"] is False


def test_renewal_review_abstains_on_missing_expiry_date() -> None:
    """E2: expiry_date=None -> no finding."""
    findings = _run(
        reservations=[_reservation(expiry_date=None, auto_renew=False)],
    )
    assert findings == []


def test_renewal_review_abstains_when_auto_renew_unknown() -> None:
    """E5: auto_renew=None -> no finding."""
    findings = _run(
        reservations=[
            _reservation(expiry_date=_iso(date(2026, 6, 12)), auto_renew=None),
        ],
    )
    assert findings == []


def test_renewal_review_abstains_when_auto_renew_true() -> None:
    """E6: auto_renew=True -> no finding (renewal already configured)."""
    findings = _run(
        reservations=[
            _reservation(expiry_date=_iso(date(2026, 6, 12)), auto_renew=True),
        ],
    )
    assert findings == []


def test_renewal_review_abstains_outside_window() -> None:
    """E3: 90 days out (> 60-day window) -> no finding."""
    findings = _run(
        reservations=[
            _reservation(expiry_date=_iso(date(2026, 8, 11)), auto_renew=False),
        ],
    )
    assert findings == []


def test_renewal_review_abstains_when_already_expired() -> None:
    """E4: expiry 5 days ago -> no finding (forward-looking rule)."""
    findings = _run(
        reservations=[
            _reservation(expiry_date=_iso(date(2026, 5, 8)), auto_renew=False),
        ],
    )
    assert findings == []


def test_renewal_review_fires_on_expiry_today() -> None:
    """E10: expiry_date == today, auto_renew=False -> one finding (boundary)."""
    findings = _run(
        reservations=[
            _reservation(expiry_date=_iso(_FIXED_TODAY), auto_renew=False),
        ],
    )
    assert len(findings) == 1
    assert findings[0].evidence["days_until_expiry"] == 0


def test_renewal_review_abstains_on_malformed_expiry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E11: expiry_date passes pydantic length gate but is not a valid date.

    Pydantic enforces ``min_length=10, max_length=10``; the rule's own parser
    is what catches non-date 10-char strings. A WARN log is emitted and the
    rule abstains rather than crashing the rule run.
    """
    caplog.set_level(logging.WARNING, logger="finops_assess.rules_impl.azure_rules")
    findings = _run(
        reservations=[_reservation(expiry_date="not-a-date", auto_renew=False)],
    )
    assert findings == []
    assert any("malformed expiry_date" in r.message for r in caplog.records)


def test_renewal_review_redacts_principal_by_default() -> None:
    """Default ``redact_pii=True`` salts and hashes the principal.

    Cites ``src/finops_assess/engine.py:70-75`` (RuleContext.redact). With
    redaction on, the emitted ``principal`` is ``sha256:<16-hex>`` (23 chars)
    and the cleartext reservation_id MUST NOT appear in the principal or the
    rendered recommendation.
    """
    rid = "/subscriptions/00000000/providers/Microsoft.Capacity/reservationOrders/ro-r/reservations/ri-r"
    findings = _run(
        reservations=[
            _reservation(rid=rid, expiry_date=_iso(date(2026, 6, 12)), auto_renew=False),
        ],
        redact_pii=True,
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.principal.startswith("sha256:")
    assert len(f.principal) == 23
    assert rid not in f.principal
    # Twice-applied redaction: the rendered recommendation must not contain the cleartext id.
    assert rid not in f.recommendation
    assert f.principal in f.recommendation  # same redacted token both places


def test_renewal_review_emits_cleartext_with_redaction_off() -> None:
    """With ``redact_pii=False``, principal is the raw reservation_id."""
    rid = "/subscriptions/00000000/providers/Microsoft.Capacity/reservationOrders/ro-r/reservations/ri-r"
    findings = _run(
        reservations=[
            _reservation(rid=rid, expiry_date=_iso(date(2026, 6, 12)), auto_renew=False),
        ],
        redact_pii=False,
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.principal == rid
    assert rid in f.recommendation


def test_renewal_review_e2e_through_run_rules() -> None:
    """Yuki-net e2e: build a dataset with both a fires row and an abstains row,
    drive the real ``run_rules`` engine, assert exactly one finding lands.

    Pattern reference: ``tests/test_playbook_cross_run_stability.py:1-80``
    (PR #78 BLOCKING #1 caught a producer regression that pure-callable unit
    tests missed; this test fires through the real engine path so the same
    class of regression cannot slip again).
    """
    fires = _reservation(
        rid="/subscriptions/00000000/.../ri-fires",
        expiry_date=_iso(date(2026, 6, 12)),
        auto_renew=False,
    )
    abstains = _reservation(
        rid="/subscriptions/00000000/.../ri-abstains",
        expiry_date=_iso(date(2026, 8, 30)),  # outside 60-day window
        auto_renew=True,
    )
    findings = _run(reservations=[fires, abstains], redact_pii=False)
    assert len(findings) == 1
    assert findings[0].evidence["expiry_date"] == _iso(date(2026, 6, 12))


def test_renewal_review_one_finding_per_reservation() -> None:
    """E8: two near-expiry, auto_renew=False reservations -> two findings."""
    findings = _run(
        reservations=[
            _reservation(
                rid="/subscriptions/00000000/.../ri-a",
                expiry_date=_iso(date(2026, 6, 12)),
                auto_renew=False,
            ),
            _reservation(
                rid="/subscriptions/00000000/.../ri-b",
                expiry_date=_iso(date(2026, 7, 1)),
                auto_renew=False,
            ),
        ],
        redact_pii=False,
    )
    assert len(findings) == 2
    rids = {f.principal for f in findings}
    assert rids == {
        "/subscriptions/00000000/.../ri-a",
        "/subscriptions/00000000/.../ri-b",
    }


def test_renewal_review_co_fires_with_underutilized() -> None:
    """E12 + plan §2.4: a reservation that is BOTH under-utilised AND near
    expiry must produce two findings (one per rule). Pins the disjoint-by-signal
    isolation claim: rule 3 reads ``expiry_date`` + ``auto_renew``;
    AZ.RESERVATION_UNDERUTILIZED reads ``utilization_pct``. Different fields,
    independent gates, intentional co-fire (operator gets both
    "rebalance scope" and "decide on renewal").
    """
    res = _reservation(
        rid="/subscriptions/00000000/.../ri-co-fire",
        expiry_date=_iso(date(2026, 6, 12)),
        auto_renew=False,
        utilization_pct=40.0,  # < 80% triggers AZ.RESERVATION_UNDERUTILIZED
    )
    findings = _run(
        reservations=[res],
        rules=[_renewal_review_rule(), _reservation_underutilized_rule()],
        redact_pii=False,
    )
    rule_ids = {f.rule_id for f in findings}
    assert rule_ids == {"AZ.COMMITMENT_RENEWAL_REVIEW", "AZ.RESERVATION_UNDERUTILIZED"}
    # Both findings reference the same reservation principal.
    principals = {f.principal for f in findings}
    assert principals == {res.reservation_id}


# ---------------------------------------------------------------------------
# Cross-rule isolation against unrelated rules (sanity)
# ---------------------------------------------------------------------------


def test_renewal_review_does_not_fire_on_empty_dataset() -> None:
    """E1: dataset with no reservations -> vacuous loop, no findings."""
    findings = _run(reservations=[])
    assert findings == []


@pytest.mark.no_freeze_today
def test_renewal_review_today_override_env_is_consulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FINOPS_NOW_OVERRIDE`` controls ``_today_utc()``.

    Pins the env-var seam used by ``scripts/generate_docs.py`` and
    ``tests/test_engine.py`` to keep the demo report and the engine smoke
    test deterministic across rebuilds.
    """
    from finops_assess.rules_impl import azure_rules

    monkeypatch.setenv("FINOPS_NOW_OVERRIDE", "2030-01-15")
    assert azure_rules._today_utc() == date(2030, 1, 15)


@pytest.mark.no_freeze_today
def test_renewal_review_today_override_env_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid ``FINOPS_NOW_OVERRIDE`` value logs WARN and uses the wall clock."""
    from finops_assess.rules_impl import azure_rules

    monkeypatch.setenv("FINOPS_NOW_OVERRIDE", "not-a-date")
    caplog.set_level(logging.WARNING, logger="finops_assess.rules_impl.azure_rules")
    today = azure_rules._today_utc()
    # Wall-clock fallback: returned a date (cannot assert exact value).
    assert isinstance(today, date)
    assert any(
        "FINOPS_NOW_OVERRIDE" in r.message and "invalid" in r.message for r in caplog.records
    )
