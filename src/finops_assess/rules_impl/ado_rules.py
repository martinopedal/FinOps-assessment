"""Azure DevOps savings rules — see ``docs/plan.md`` §6.

These rules consume the :class:`AdoSeat` and :class:`AdoOrgUsage` rows
emitted by the CSV collector (and, in M6, by the live ADO collector).
Every rule degrades gracefully when a signal is missing: we abstain
rather than fabricate a finding since ``last_activity_days is None``
genuinely can mean "never observed" or "we don't have the API scope".
"""

from __future__ import annotations

from collections.abc import Iterable

from finops_assess.engine import RuleContext, register, render
from finops_assess.models import AdoSeat, Finding


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _seat_price(seat: AdoSeat, ctx: RuleContext) -> float | None:
    """Return the catalog list price for a seat's SKU, if known."""
    if seat.sku_id is None:
        return None
    sku = ctx.catalog.get(seat.sku_id)
    if sku is None:
        return None
    return sku.list_price_usd_month


# ---------------------------------------------------------------------------
# ADO.INACTIVE_BASIC_90D
# ---------------------------------------------------------------------------
# Basic or Basic+Test seats with no work-item, code, or pipeline activity
# in the configured window. Stakeholder seats are excluded because they are
# already free. We require an actual signal (not None) before flagging to
# avoid false positives on newly-onboarded users with no telemetry yet.
_BILLABLE_SEAT_TYPES = {"basic", "basic_plus_test"}


@register("ADO.INACTIVE_BASIC_90D")
def inactive_basic_90d(ctx: RuleContext) -> Iterable[Finding]:
    """Flag billable ADO seats with no activity in the configured window."""
    days = ctx.rule.inactivity_days or 90
    for seat in ctx.dataset.ado_seats:
        if seat.seat_type not in _BILLABLE_SEAT_TYPES:
            continue
        if seat.last_activity_days is None:
            continue
        if seat.last_activity_days < days:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="ado",
            severity=ctx.rule.severity,
            principal=ctx.redact(seat.principal),
            current_sku=seat.sku_id,
            estimated_monthly_savings_usd=_round(_seat_price(seat, ctx)),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(seat.principal),
            ),
            evidence={
                "org": seat.org,
                "seat_type": seat.seat_type,
                "last_activity_days": seat.last_activity_days,
                "window_days": days,
            },
        )


# ---------------------------------------------------------------------------
# ADO.STAKEHOLDER_ELIGIBLE
# ---------------------------------------------------------------------------
# Basic seats whose *only* observed activity is reading boards and commenting.
# These users can be stepped down to the free Stakeholder access level.
# We exclude users who already appear inactive (≥ 90 d) to avoid
# double-reporting with ADO.INACTIVE_BASIC_90D.
_INACTIVE_THRESHOLD = 90


@register("ADO.STAKEHOLDER_ELIGIBLE")
def stakeholder_eligible(ctx: RuleContext) -> Iterable[Finding]:
    """Flag Basic seats that only perform board-read / comment activity."""
    for seat in ctx.dataset.ado_seats:
        if seat.seat_type != "basic":
            continue
        if not seat.only_stakeholder_activity:
            continue
        # Abstain if we have no activity recency signal at all.
        if seat.last_activity_days is None:
            continue
        # Don't double-report with INACTIVE_BASIC_90D.
        if seat.last_activity_days >= _INACTIVE_THRESHOLD:
            continue
        # Stakeholder is free, so the full seat price is the estimated saving.
        yield Finding(
            rule_id=ctx.rule.id,
            surface="ado",
            severity=ctx.rule.severity,
            principal=ctx.redact(seat.principal),
            current_sku=seat.sku_id,
            estimated_monthly_savings_usd=_round(_seat_price(seat, ctx)),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(seat.principal),
            ),
            evidence={
                "org": seat.org,
                "seat_type": seat.seat_type,
                "only_stakeholder_activity": True,
                "last_activity_days": seat.last_activity_days,
            },
        )


# ---------------------------------------------------------------------------
# ADO.PARALLEL_JOBS_OVER_PROVISIONED
# ---------------------------------------------------------------------------
# Purchased Microsoft-hosted parallel jobs whose P95 concurrent usage
# is materially below the purchased count. The threshold is set so that
# one spare job (buffer) is not flagged, but two or more consistently
# idle jobs are.
_MIN_OVERPROVISIONED_JOBS = 2


@register("ADO.PARALLEL_JOBS_OVER_PROVISIONED")
def parallel_jobs_over_provisioned(ctx: RuleContext) -> Iterable[Finding]:
    """Flag ADO orgs whose purchased parallel jobs exceed P95 concurrent usage."""
    for org in ctx.dataset.ado_orgs:
        if org.purchased_parallel_jobs is None or org.p95_concurrent_jobs is None:
            continue
        surplus = org.purchased_parallel_jobs - org.p95_concurrent_jobs
        if surplus < _MIN_OVERPROVISIONED_JOBS:
            continue
        # Estimated saving: cost of surplus jobs at the per-job catalog price.
        job_sku = ctx.catalog.get("ADO.PARALLEL_JOB_HOSTED")
        job_price = job_sku.list_price_usd_month if job_sku else None
        est_savings = _round(surplus * job_price) if job_price is not None else None
        yield Finding(
            rule_id=ctx.rule.id,
            surface="ado",
            severity=ctx.rule.severity,
            principal=ctx.redact(org.org),
            estimated_monthly_savings_usd=est_savings,
            recommendation=render(
                ctx.rule.recommendation_template,
                purchased_parallel_jobs=org.purchased_parallel_jobs,
                p95_concurrent_jobs=org.p95_concurrent_jobs,
            ),
            evidence={
                "purchased_parallel_jobs": org.purchased_parallel_jobs,
                "p95_concurrent_jobs": org.p95_concurrent_jobs,
                "surplus_jobs": surplus,
            },
        )


# ---------------------------------------------------------------------------
# ADO.TEST_PLANS_UNUSED
# ---------------------------------------------------------------------------
# Basic+Test Plans seats with no Test Plans activity in the configured window.
# The saving is the price delta between the Basic+Test and Basic catalog entries.
@register("ADO.TEST_PLANS_UNUSED")
def test_plans_unused(ctx: RuleContext) -> Iterable[Finding]:
    """Flag Basic+Test seats with no Test Plans activity in the window."""
    days = ctx.rule.inactivity_days or 60
    for seat in ctx.dataset.ado_seats:
        if seat.seat_type != "basic_plus_test":
            continue
        if seat.last_test_plan_days is None:
            continue
        if seat.last_test_plan_days < days:
            continue
        # Saving = (Basic+Test price) - (Basic price)
        basic_test_sku = ctx.catalog.get("ADO.BASIC_TEST")
        basic_sku = ctx.catalog.get("ADO.BASIC")
        est_savings: float | None = None
        if (
            basic_test_sku is not None
            and basic_test_sku.list_price_usd_month is not None
            and basic_sku is not None
            and basic_sku.list_price_usd_month is not None
        ):
            est_savings = _round(
                basic_test_sku.list_price_usd_month - basic_sku.list_price_usd_month
            )
        yield Finding(
            rule_id=ctx.rule.id,
            surface="ado",
            severity=ctx.rule.severity,
            principal=ctx.redact(seat.principal),
            current_sku=seat.sku_id,
            recommended_sku="ADO.BASIC",
            estimated_monthly_savings_usd=est_savings,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(seat.principal),
            ),
            evidence={
                "org": seat.org,
                "seat_type": seat.seat_type,
                "last_test_plan_days": seat.last_test_plan_days,
                "window_days": days,
            },
        )
