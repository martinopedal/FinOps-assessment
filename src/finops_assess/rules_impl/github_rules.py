"""GitHub savings rules — see ``docs/plan.md`` §6.

These rules consume the :class:`GitHubSeat` and :class:`GitHubOrg` rows
emitted by the CSV collector (and, in M6, by the live GitHub collector).
Every rule degrades gracefully when a signal is missing: we abstain
rather than fabricate a finding, since `last_activity_days is None`
genuinely can mean "never observed" or "we don't have the API scope".
"""

from __future__ import annotations

from collections.abc import Iterable

from finops_assess.engine import RuleContext, register, render
from finops_assess.models import Finding, GitHubSeat


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _seat_price(seat: GitHubSeat, ctx: RuleContext) -> float | None:
    """Return the catalog list price for a seat's SKU, if known."""
    if seat.sku_id is None:
        return None
    sku = ctx.catalog.get(seat.sku_id)
    if sku is None:
        return None
    return sku.list_price_usd_month


# ---------------------------------------------------------------------------
# GH.INACTIVE_SEAT_90D
# ---------------------------------------------------------------------------
# Enterprise / Team seats with no contributions, reviews, or sign-ins in
# the configured window. Copilot and GHAS-committer seats are scored by
# their own dedicated rules below.
_INTERACTIVE_SEAT_TYPES = {"enterprise", "team"}


@register("GH.INACTIVE_SEAT_90D")
def inactive_seat_90d(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 90
    for seat in ctx.dataset.github_seats:
        if seat.seat_type not in _INTERACTIVE_SEAT_TYPES:
            continue
        # Without any activity signal we cannot prove the threshold, so
        # abstain rather than emit a false positive on a freshly-onboarded
        # user we have no telemetry for yet.
        if seat.last_activity_days is None:
            continue
        if seat.last_activity_days < days:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="github",
            severity=ctx.rule.severity,
            principal=ctx.redact(seat.principal),
            current_sku=seat.sku_id,
            estimated_monthly_savings_usd=_round(_seat_price(seat, ctx)),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(seat.principal),
                current_sku=seat.sku_id or "GitHub",
            ),
            evidence={
                "org": seat.org,
                "seat_type": seat.seat_type,
                "last_activity_days": seat.last_activity_days,
                "window_days": days,
            },
        )


# ---------------------------------------------------------------------------
# GH.COPILOT_INACTIVE_30D
# ---------------------------------------------------------------------------
_COPILOT_SEAT_TYPES = {"copilot_business", "copilot_enterprise"}


@register("GH.COPILOT_INACTIVE_30D")
def copilot_inactive_30d(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 30
    for seat in ctx.dataset.github_seats:
        if seat.seat_type not in _COPILOT_SEAT_TYPES:
            continue
        # The primary signal is "zero suggestions accepted in N days".
        # If we don't have that count we abstain — the underlying seat
        # still being assigned is not by itself proof of waste.
        if seat.copilot_acceptances_30d is None:
            continue
        if seat.copilot_acceptances_30d > 0:
            continue
        # If the operator also gave us a recency signal, require it to
        # corroborate (i.e. don't fire on someone who accepted nothing
        # because they only just got the seat).
        if seat.last_activity_days is not None and seat.last_activity_days < days:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="github",
            severity=ctx.rule.severity,
            principal=ctx.redact(seat.principal),
            current_sku=seat.sku_id,
            estimated_monthly_savings_usd=_round(_seat_price(seat, ctx)),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(seat.principal),
                current_sku=seat.sku_id or "GitHub Copilot",
            ),
            evidence={
                "org": seat.org,
                "seat_type": seat.seat_type,
                "copilot_acceptances_30d": seat.copilot_acceptances_30d,
                "last_activity_days": seat.last_activity_days,
                "window_days": days,
            },
        )


# ---------------------------------------------------------------------------
# GH.GHAS_OVER_PROVISIONED
# ---------------------------------------------------------------------------
@register("GH.GHAS_OVER_PROVISIONED")
def ghas_over_provisioned(ctx: RuleContext) -> Iterable[Finding]:
    for org in ctx.dataset.github_orgs:
        if (
            org.ghas_repo_count is None
            or org.actively_scanned_repos is None
            or org.active_committers is None
        ):
            continue
        if org.ghas_repo_count <= org.actively_scanned_repos:
            continue
        # GHAS is priced per active committer, not per repo. We can flag
        # the gap (repos with GHAS enabled but no scanning signal) but
        # we deliberately leave estimated savings as None because the
        # committer-to-repo mapping is not in the normalised snapshot.
        yield Finding(
            rule_id=ctx.rule.id,
            surface="github",
            severity=ctx.rule.severity,
            principal=ctx.redact(org.org),
            current_sku="GH.GHAS",
            estimated_monthly_savings_usd=None,
            recommendation=render(
                ctx.rule.recommendation_template,
                ghas_repo_count=org.ghas_repo_count,
                active_committers=org.active_committers,
                actively_scanned=org.actively_scanned_repos,
            ),
            evidence={
                "ghas_repo_count": org.ghas_repo_count,
                "actively_scanned_repos": org.actively_scanned_repos,
                "active_committers": org.active_committers,
            },
        )


# ---------------------------------------------------------------------------
# GH.RUNNER_TIER_MISMATCH
# ---------------------------------------------------------------------------
# A material mismatch is "consumed minutes differ from the included
# quota by ≥25 %" in either direction. Below threshold means there is a
# cheaper tier to consider; above means a bundle upgrade likely beats
# overage pricing. We don't compute the dollar delta because runner-
# minute pricing varies by OS/arch and isn't in the catalog.
_RUNNER_MISMATCH_THRESHOLD_PCT = 25.0


def _runner_recommendation(used: int, included: int, tier: str | None) -> str:
    pct = (used - included) / included * 100.0 if included > 0 else 0.0
    tier_label = tier or "current"
    if pct >= _RUNNER_MISMATCH_THRESHOLD_PCT:
        return (
            f"Consumption is {pct:.0f}% above the {tier_label} tier's included "
            "quota; verify whether moving to a higher-tier bundle beats "
            "per-minute overage pricing."
        )
    return (
        f"Consumption is {abs(pct):.0f}% below the {tier_label} tier's "
        "included quota; verify whether a lower-tier bundle would still "
        "cover peak months."
    )


@register("GH.RUNNER_TIER_MISMATCH")
def runner_tier_mismatch(ctx: RuleContext) -> Iterable[Finding]:
    for org in ctx.dataset.github_orgs:
        if org.runner_minutes_used is None or org.runner_minutes_included is None:
            continue
        if org.runner_minutes_included <= 0:
            continue
        delta_minutes = abs(org.runner_minutes_used - org.runner_minutes_included)
        delta_pct = delta_minutes / org.runner_minutes_included * 100.0
        if delta_pct < _RUNNER_MISMATCH_THRESHOLD_PCT:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="github",
            severity=ctx.rule.severity,
            principal=ctx.redact(org.org),
            current_sku=org.runner_tier,
            estimated_monthly_savings_usd=None,
            recommendation=render(
                ctx.rule.recommendation_template,
                used_minutes=org.runner_minutes_used,
                included_minutes=org.runner_minutes_included,
                tier_action_recommendation=_runner_recommendation(
                    org.runner_minutes_used,
                    org.runner_minutes_included,
                    org.runner_tier,
                ),
            ),
            evidence={
                "runner_tier": org.runner_tier,
                "runner_minutes_used": org.runner_minutes_used,
                "runner_minutes_included": org.runner_minutes_included,
                "delta_pct": round(delta_pct, 1),
            },
        )
