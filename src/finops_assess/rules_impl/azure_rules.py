"""Azure savings rules — see ``docs/plan.md`` §6.

These rules consume :class:`AzureResource`, :class:`AzureReservation`, and
:class:`AzureLogWorkspace` rows that the CSV collector normalises (and that
the M5 ARM collector will produce). Cost figures use ``monthly_cost_usd``
from the snapshot when present and degrade gracefully to ``None`` otherwise
(no estimates are fabricated).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from datetime import UTC, date, datetime

from finops_assess.engine import RuleContext, register, render
from finops_assess.models import Finding

logger = logging.getLogger(__name__)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


@register("AZ.IDLE_VM_14D")
def idle_vm_14d(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 14
    for resource in ctx.dataset.azure_resources:
        if resource.resource_type != "virtualMachine":
            continue
        if resource.avg_cpu_pct is None or resource.avg_net_kbps is None:
            continue
        if resource.avg_cpu_pct >= 5.0 or resource.avg_net_kbps >= 100.0:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(resource.resource_id),
            current_sku=resource.sku,
            estimated_monthly_savings_usd=_round(resource.monthly_cost_usd),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(resource.resource_id),
                avg_cpu_pct=round(resource.avg_cpu_pct, 1),
                avg_net_kbps=round(resource.avg_net_kbps, 1),
            ),
            evidence={
                "avg_cpu_pct": resource.avg_cpu_pct,
                "avg_net_kbps": resource.avg_net_kbps,
                "window_days": days,
                "location": resource.location,
            },
        )


@register("AZ.UNATTACHED_DISK")
def unattached_disk(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 7
    for resource in ctx.dataset.azure_resources:
        if resource.resource_type != "managedDisk":
            continue
        if resource.attached is None or resource.attached:
            continue
        # The rule is "not attached for ≥ N days"; with no telemetry we
        # cannot prove the threshold, so we abstain rather than emit a
        # false positive (`last_attached_at` would render as `? days ago`).
        if resource.days_inactive is None:
            continue
        if resource.days_inactive < days:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(resource.resource_id),
            current_sku=resource.sku,
            estimated_monthly_savings_usd=_round(resource.monthly_cost_usd),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(resource.resource_id),
                disk_size_gb="?",
                disk_sku=resource.sku or "?",
                last_attached_at=f"{resource.days_inactive} days ago",
            ),
            evidence={
                "attached": False,
                "days_inactive": resource.days_inactive,
                "location": resource.location,
            },
        )


@register("AZ.PUBLIC_IP_UNATTACHED")
def public_ip_unattached(ctx: RuleContext) -> Iterable[Finding]:
    for resource in ctx.dataset.azure_resources:
        if resource.resource_type != "publicIp":
            continue
        if resource.associated is None or resource.associated:
            continue
        # The rule's pricing assumption (~$3.65/mo idle charge) is
        # specifically for **Standard** public IPs; Basic public IPs are
        # priced and lifecycle differently and Microsoft is retiring the
        # SKU on its own schedule. Skip anything that isn't explicitly
        # tagged Standard so the recommendation is sound.
        if (resource.sku or "").lower() != "standard":
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(resource.resource_id),
            current_sku=resource.sku,
            estimated_monthly_savings_usd=_round(resource.monthly_cost_usd),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(resource.resource_id),
            ),
            evidence={"associated": False, "location": resource.location},
        )


@register("AZ.OVERSIZED_VM")
def oversized_vm(ctx: RuleContext) -> Iterable[Finding]:
    for resource in ctx.dataset.azure_resources:
        if resource.resource_type != "virtualMachine":
            continue
        if resource.p95_cpu_pct is None or resource.p95_mem_pct is None:
            continue
        if resource.p95_cpu_pct >= 40.0 or resource.p95_mem_pct >= 40.0:
            continue
        # The IDLE_VM rule already covers genuinely-idle VMs; oversized is
        # for VMs that are *used* but consistently below 40% headroom.
        if resource.avg_cpu_pct is not None and resource.avg_cpu_pct < 5.0:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(resource.resource_id),
            current_sku=resource.sku,
            recommended_sku=resource.recommended_sku,
            estimated_monthly_savings_usd=None,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(resource.resource_id),
                current_sku=resource.sku or "?",
                recommended_sku=resource.recommended_sku or "<smaller SKU in same family>",
                p95_cpu_pct=round(resource.p95_cpu_pct, 1),
                p95_mem_pct=round(resource.p95_mem_pct, 1),
            ),
            evidence={
                "p95_cpu_pct": resource.p95_cpu_pct,
                "p95_mem_pct": resource.p95_mem_pct,
                "location": resource.location,
            },
        )


# ---------------------------------------------------------------------------
# AZ.RESERVATION_UNDERUTILIZED
# ---------------------------------------------------------------------------
_RESERVATION_UTIL_THRESHOLD = 80.0


@register("AZ.RESERVATION_UNDERUTILIZED")
def reservation_underutilized(ctx: RuleContext) -> Iterable[Finding]:
    """Flag Reservations / Savings Plans with < 80 % average utilization."""
    for reservation in ctx.dataset.azure_reservations:
        if reservation.utilization_pct is None:
            continue
        if reservation.utilization_pct >= _RESERVATION_UTIL_THRESHOLD:
            continue
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
                utilization_pct=round(reservation.utilization_pct, 1),
            ),
            evidence={
                "reservation_name": reservation.reservation_name,
                "sku": reservation.sku,
                "scope": reservation.scope,
                "utilization_pct": reservation.utilization_pct,
                "monthly_cost_usd": reservation.monthly_cost_usd,
            },
        )


# ---------------------------------------------------------------------------
# AZ.LOG_ANALYTICS_OVERINGEST
# ---------------------------------------------------------------------------
@register("AZ.LOG_ANALYTICS_OVERINGEST")
def log_analytics_overingest(ctx: RuleContext) -> Iterable[Finding]:
    """Flag Log Analytics workspaces that would save by moving commitment tiers."""
    for workspace in ctx.dataset.azure_log_workspaces:
        if workspace.recommended_tier is None:
            continue
        if workspace.daily_gb is None:
            continue
        # Estimate monthly saving from the pre-computed percentage when available.
        est_savings: float | None = None
        if workspace.est_savings_pct is not None and workspace.monthly_cost_usd is not None:
            est_savings = _round(workspace.monthly_cost_usd * workspace.est_savings_pct / 100.0)
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(workspace.workspace_id),
            estimated_monthly_savings_usd=est_savings,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(workspace.workspace_id),
                daily_gb=round(workspace.daily_gb, 1),
                recommended_tier=workspace.recommended_tier,
                est_savings_pct=round(workspace.est_savings_pct, 1)
                if workspace.est_savings_pct is not None
                else "?",
            ),
            evidence={
                "workspace_name": workspace.workspace_name,
                "daily_gb": workspace.daily_gb,
                "commitment_tier_gb": workspace.commitment_tier_gb,
                "recommended_tier": workspace.recommended_tier,
                "est_savings_pct": workspace.est_savings_pct,
            },
        )


# ---------------------------------------------------------------------------
# AZ.DEV_TEST_SUB_MISMATCH
# ---------------------------------------------------------------------------
# Detects mismatches between the env tag on a resource and the subscription
# offer type. Two cases:
#   1. env=prod resource in a Dev/Test subscription (financial risk: prod
#      workloads lose their SLA and may violate EA Dev/Test eligibility).
#   2. env=dev/test resource in a non-Dev/Test subscription (cost risk:
#      paying production prices for non-production workloads).
def _is_devtest_offer(offer: str) -> bool:
    """Return True when the subscription offer is a Dev/Test variant."""
    lower = offer.lower().replace("-", "").replace("_", "").replace(" ", "").replace("/", "")
    return "devtest" in lower or lower in {"dev", "test"}


def _is_prod_env(env_tag: str) -> bool:
    return env_tag.lower().startswith("prod")


def _is_devtest_env(env_tag: str) -> bool:
    lower = env_tag.lower()
    return lower.startswith("dev") or lower.startswith("test") or lower == "nonprod"


@register("AZ.DEV_TEST_SUB_MISMATCH")
def dev_test_sub_mismatch(ctx: RuleContext) -> Iterable[Finding]:
    """Flag resources whose env tag and subscription offer type disagree."""
    for resource in ctx.dataset.azure_resources:
        if resource.env_tag is None or resource.subscription_offer is None:
            continue
        env = resource.env_tag
        offer = resource.subscription_offer
        is_devtest_sub = _is_devtest_offer(offer)
        is_mismatch = (_is_prod_env(env) and is_devtest_sub) or (
            _is_devtest_env(env) and not is_devtest_sub
        )
        if not is_mismatch:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="azure",
            severity=ctx.rule.severity,
            principal=ctx.redact(resource.resource_id),
            current_sku=resource.sku,
            estimated_monthly_savings_usd=None,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(resource.resource_id),
                env_tag=env,
                subscription_id=resource.subscription_id or "?",
                subscription_offer=offer,
            ),
            evidence={
                "env_tag": env,
                "subscription_id": resource.subscription_id,
                "subscription_offer": offer,
                "location": resource.location,
            },
        )


# ---------------------------------------------------------------------------
# AZ.COMMITMENT_UNDER_COVERED
# ---------------------------------------------------------------------------
# Same utilisation threshold as AZ.RESERVATION_UNDERUTILIZED -- intentional;
# see docs/plans/059-az-commitment-under-covered.md §2.4 (cross-rule isolation discussion).
_COMMITMENT_UTIL_THRESHOLD = 80.0
_SIBLING_MIN_ON_DEMAND_USD = 50.0


@register("AZ.COMMITMENT_UNDER_COVERED")
def commitment_under_covered(ctx: RuleContext) -> Iterable[Finding]:
    """Flag under-utilised reservations whose unused capacity could absorb
    a sibling subscription's on-demand spend (scope-widening opportunity).

    See docs/plans/059-az-commitment-under-covered.md §2.4 for the intentional
    overlap with AZ.RESERVATION_UNDERUTILIZED.
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
        scope_kind = (
            "Single"
            if scope_raw == "single"
            else ("Shared" if scope_raw in ("shared", "managementgroup") else "Unknown")
        )

        for sibling_sub, on_demand in sibling_spend.items():
            # E11: Single-scope reservations may include the owner sub as a "sibling"
            # -- conservative over-count documented in plan §2.2 / §2.5;
            # sharpens once rule 4 lands appliedScopeSubscriptionIds.
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


# ---------------------------------------------------------------------------
# AZ.SAVINGS_PLAN_ELIGIBLE_SPEND
# ---------------------------------------------------------------------------
_SP_MIN_LOOKBACK_PERIODS = {"Last30Days", "Last60Days"}


@register("AZ.SAVINGS_PLAN_ELIGIBLE_SPEND")
def savings_plan_eligible_spend(ctx: RuleContext) -> Iterable[Finding]:
    """Flag scopes with uncovered on-demand spend that the Azure Benefit
    Recommendations API projects could be reduced via a Savings Plan.
    """
    min_uncovered = ctx.rule.min_uncovered_usd or 50.0
    # N2 (Noor stage-4 PR #85, RESOLVED PASS): cross-rule isolation vs
    # AZ.RESERVATION_UNDERUTILIZED is safe by construction -- the two rules
    # consume disjoint dataset slices (azure_reservations vs azure_benefit_recommendations).
    seen: set[tuple[str, str]] = set()

    for rec in ctx.dataset.azure_benefit_recommendations:
        # NIT #2: Filter to SavingsPlan only
        if rec.benefit_kind != "SavingsPlan":
            continue

        # E4: Abstain on short lookback
        if rec.lookback_period not in _SP_MIN_LOOKBACK_PERIODS:
            continue

        # E2: Abstain on zero or negative savings
        if rec.net_savings_usd is None or rec.net_savings_usd <= 0:
            continue

        # E1 / null path: Abstain on missing cost data
        if rec.cost_without_benefit_usd is None:
            continue

        # E3: Abstain on micro uncovered spend (tunable threshold)
        if rec.cost_without_benefit_usd < min_uncovered:
            continue

        # E5: Dedup per (scope, term)
        key = (rec.scope, rec.term)
        if key in seen:
            continue
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
                recommended_hourly_commit_usd=round(rec.recommended_hourly_commit_usd or 0.0, 4),
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


# ---------------------------------------------------------------------------
# AZ.COMMITMENT_RENEWAL_REVIEW
# ---------------------------------------------------------------------------
# Surfaces reservations expiring within the near-expiry window whose operator
# has NOT configured auto-renew. The rule is forward-looking: already-expired
# reservations and reservations with auto_renew=True are abstained on. The
# decision (renew, exchange, or let lapse) belongs to the operator and depends
# on whether the workload still needs reserved capacity.
#
# See docs/plans/059-az-commitment-renewal-review.md (Maya, stage-3 plan).
# Cross-rule isolation: disjoint by signal from AZ.RESERVATION_UNDERUTILIZED
# (different fields drive each gate); co-firing on the same reservation is
# intentional and complementary (rebalance scope + decide on renewal).
_RENEWAL_REVIEW_DEFAULT_WINDOW_DAYS = 60
# Env var the demo-regen script and tests set to anchor "today" to a fixed
# date so the example reports and the REQUIRED_RULES smoke test stay
# deterministic without forcing operators to refresh ``samples/`` quarterly.
# Production runs leave this unset and use the real wall clock.
_TODAY_OVERRIDE_ENV = "FINOPS_NOW_OVERRIDE"


def _today_utc() -> date:
    """Return today's date in UTC, honoring ``FINOPS_NOW_OVERRIDE`` if set.

    Single call site so tests can either monkeypatch this helper or set
    ``FINOPS_NOW_OVERRIDE=YYYY-MM-DD`` to anchor evaluation to a fixed day.
    Invalid override values fall back to the wall clock with a warning.
    """
    override = os.environ.get(_TODAY_OVERRIDE_ENV)
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            logger.warning(
                "AZ.COMMITMENT_RENEWAL_REVIEW: invalid %s=%r; using wall clock",
                _TODAY_OVERRIDE_ENV,
                override,
            )
    return datetime.now(UTC).date()


def _parse_expiry(value: str) -> date | None:
    """Parse an ISO 8601 YYYY-MM-DD expiry date; log WARN and return ``None`` on bad input.

    Pydantic's ``min_length=10, max_length=10`` constraint rejects strings of
    the wrong length at load time. Anything that passes that gate but is not
    a valid date (e.g. ``"not-a-date"``) is caught here so the rule abstains
    on the row rather than crashing the whole rule run.
    """
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning("AZ.COMMITMENT_RENEWAL_REVIEW: malformed expiry_date %r; abstaining", value)
        return None


@register("AZ.COMMITMENT_RENEWAL_REVIEW")
def commitment_renewal_review(ctx: RuleContext) -> Iterable[Finding]:
    """Flag reservations expiring within the near-expiry window with auto-renew off."""
    window_days = ctx.rule.inactivity_days or _RENEWAL_REVIEW_DEFAULT_WINDOW_DAYS
    today = _today_utc()
    for reservation in ctx.dataset.azure_reservations:
        if reservation.expiry_date is None:
            continue  # E2: signal absent
        if reservation.auto_renew is None:
            continue  # E5: signal absent
        if reservation.auto_renew is True:
            continue  # E6: renewal already configured
        expiry = _parse_expiry(reservation.expiry_date)
        if expiry is None:
            continue  # E11: malformed date
        days_until_expiry = (expiry - today).days
        if days_until_expiry < 0:
            continue  # E4: already expired
        if days_until_expiry > window_days:
            continue  # E3: not yet near expiry

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
