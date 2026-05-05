"""Azure savings rules — see ``docs/plan.md`` §6.

These rules consume :class:`AzureResource` rows that the CSV collector
normalises (and that the M5 ARM collector will produce). Cost figures use
``monthly_cost_usd`` from the snapshot when present and degrade gracefully
to ``None`` otherwise (no estimates are fabricated).
"""

from __future__ import annotations

from collections.abc import Iterable

from finops_assess.engine import RuleContext, register, render
from finops_assess.models import Finding


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
        if resource.days_inactive is not None and resource.days_inactive < days:
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
                last_attached_at=f"{resource.days_inactive or '?'} days ago",
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
