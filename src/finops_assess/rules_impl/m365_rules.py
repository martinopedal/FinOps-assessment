"""M365 / Entra savings rules — see ``docs/plan.md`` §6."""

from __future__ import annotations

from collections.abc import Iterable

from finops_assess.engine import (
    RuleContext,
    cheapest_covering_sku,
    effective_features,
    register,
    render,
    transitive_includes,
)
from finops_assess.models import Finding


def _user_lookup(ctx: RuleContext) -> dict[str, object]:
    return {u.principal: u for u in ctx.dataset.users}


def _savings(price: float | None) -> float | None:
    return None if price is None else round(price, 2)


def _delta(current: float | None, recommended: float | None) -> float | None:
    if current is None or recommended is None:
        return None
    return round(max(0.0, current - recommended), 2)


# ---------------------------------------------------------------------------
# M365.UNUSED_LICENSE_30D
# ---------------------------------------------------------------------------

# Each catalog feature tag maps to one or more usage signals. A signal value
# of ``None`` means "never observed"; an integer is days since last activity.
_FEATURE_TO_SIGNALS: dict[str, tuple[str, ...]] = {
    "mailbox.50gb": ("exchange",),
    "mailbox.100gb": ("exchange",),
    "mailbox.2gb": ("exchange",),
    "office.desktop": ("office",),
    "office.web": ("office",),
    "teams.full": ("teams",),
    "teams.basic": ("teams",),
    "sharepoint.full": ("sharepoint",),
    "sharepoint.read": ("sharepoint",),
    "intune.mdm": ("intune",),
    "intune.mam": ("intune",),
    "entra.p1": ("entra",),
    "entra.p2": ("entra_p2",),
    "defender.o365.p1": ("defender_o365",),
    "defender.o365.p2": ("defender_o365",),
    "purview.dlp": ("purview_dlp",),
    "purview.records": ("purview",),
    "powerbi.pro": ("powerbi",),
    "copilot.m365": ("copilot",),
}


def _sku_signals(sku_id: str, ctx: RuleContext) -> set[str]:
    signals: set[str] = set()
    for feat in effective_features(sku_id, ctx.catalog):
        signals.update(_FEATURE_TO_SIGNALS.get(feat, ()))
    return signals


@register("M365.UNUSED_LICENSE_30D")
def unused_license_30d(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 30
    users = _user_lookup(ctx)
    for assignment in ctx.dataset.assignments:
        sku = ctx.catalog.get(assignment.sku_id)
        if sku is None or sku.cloud != "m365":
            continue
        if sku.list_price_usd_month is None and sku.family == "m365_addon":
            # Add-on without price still warrants flagging; keep going.
            pass
        signals = _sku_signals(assignment.sku_id, ctx)
        if not signals:
            continue
        usage = ctx.usage_by_principal.get(assignment.principal, {})
        # Active if ANY relevant signal has activity within the window.
        is_active = False
        for sig in signals:
            last = usage.get(sig)
            if last is not None and last <= days:
                is_active = True
                break
        if is_active:
            continue
        # Skip system principals / shared mailboxes — they have dedicated rules.
        user = users.get(assignment.principal)
        if user is None:
            continue
        if getattr(user, "user_type", "member") in {"shared_mailbox", "service"}:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="m365",
            severity=ctx.rule.severity,
            principal=ctx.redact(assignment.principal),
            current_sku=assignment.sku_id,
            estimated_monthly_savings_usd=_savings(sku.list_price_usd_month),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(assignment.principal),
                current_sku=assignment.sku_id,
            ),
            evidence={
                "inactivity_window_days": days,
                "checked_signals": sorted(signals),
                "last_activity_days": {s: usage.get(s) for s in sorted(signals)},
            },
        )


# ---------------------------------------------------------------------------
# M365.OVER_LICENSED_VS_PERSONA
# ---------------------------------------------------------------------------


@register("M365.OVER_LICENSED_VS_PERSONA")
def over_licensed_vs_persona(ctx: RuleContext) -> Iterable[Finding]:
    for assignment in ctx.dataset.assignments:
        sku = ctx.catalog.get(assignment.sku_id)
        if sku is None or sku.cloud != "m365" or sku.list_price_usd_month is None:
            continue
        if sku.family in {"m365_addon", "voice", "windows", "windows_365"}:
            continue
        persona_assn = ctx.persona_assignments.get(assignment.principal)
        if persona_assn is None:
            continue
        persona = ctx.personas.get(persona_assn.persona_id)
        if persona is None or not persona.required_features:
            continue
        required = set(persona.required_features)
        current_features = effective_features(assignment.sku_id, ctx.catalog)
        if not required.issubset(current_features):
            continue  # Current SKU doesn't even cover the persona; not over-licensed.
        cheaper = cheapest_covering_sku(required, ctx.catalog_list, ctx.catalog, cloud="m365")
        if cheaper is None or cheaper.id == assignment.sku_id:
            continue
        if (
            cheaper.list_price_usd_month is None
            or cheaper.list_price_usd_month >= sku.list_price_usd_month
        ):
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="m365",
            severity=ctx.rule.severity,
            principal=ctx.redact(assignment.principal),
            current_sku=assignment.sku_id,
            recommended_sku=cheaper.id,
            estimated_monthly_savings_usd=_delta(
                sku.list_price_usd_month, cheaper.list_price_usd_month
            ),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(assignment.principal),
                persona=persona.id,
                current_sku=assignment.sku_id,
                recommended_sku=cheaper.id,
            ),
            confidence=persona_assn.confidence,
            evidence={
                "persona": persona.id,
                "persona_required_features": sorted(required),
                "current_features": sorted(current_features),
            },
        )


# ---------------------------------------------------------------------------
# M365.DUPLICATE_BUNDLE
# ---------------------------------------------------------------------------


@register("M365.DUPLICATE_BUNDLE")
def duplicate_bundle(ctx: RuleContext) -> Iterable[Finding]:
    for principal, sku_ids in ctx.assignments_by_principal.items():
        m365_skus = [s for s in sku_ids if (e := ctx.catalog.get(s)) and e.cloud == "m365"]
        if len(m365_skus) < 2:
            continue
        for outer in m365_skus:
            included = transitive_includes(outer, ctx.catalog)
            for other in m365_skus:
                if other == outer:
                    continue
                if other in included:
                    duplicate = ctx.catalog[other]
                    yield Finding(
                        rule_id=ctx.rule.id,
                        surface="m365",
                        severity=ctx.rule.severity,
                        principal=ctx.redact(principal),
                        current_sku=outer,
                        estimated_monthly_savings_usd=_savings(duplicate.list_price_usd_month),
                        recommendation=render(
                            ctx.rule.recommendation_template,
                            principal=ctx.redact(principal),
                            current_sku=outer,
                            duplicate_sku=other,
                        ),
                        evidence={
                            "bundle": outer,
                            "duplicate_sku": other,
                            "all_assignments": sorted(sku_ids),
                        },
                    )


# ---------------------------------------------------------------------------
# M365.DISABLED_USER_LICENSED
# ---------------------------------------------------------------------------


@register("M365.DISABLED_USER_LICENSED")
def disabled_user_licensed(ctx: RuleContext) -> Iterable[Finding]:
    users_by_id = {u.principal: u for u in ctx.dataset.users}
    for principal, sku_ids in ctx.assignments_by_principal.items():
        user = users_by_id.get(principal)
        if user is None or user.account_enabled:
            continue
        for sku_id in sku_ids:
            sku = ctx.catalog.get(sku_id)
            if sku is None or sku.cloud != "m365":
                continue
            yield Finding(
                rule_id=ctx.rule.id,
                surface="m365",
                severity=ctx.rule.severity,
                principal=ctx.redact(principal),
                current_sku=sku_id,
                estimated_monthly_savings_usd=_savings(sku.list_price_usd_month),
                recommendation=render(
                    ctx.rule.recommendation_template,
                    principal=ctx.redact(principal),
                    current_sku=sku_id,
                ),
                evidence={"account_enabled": False},
            )


# ---------------------------------------------------------------------------
# M365.SHARED_MAILBOX_LICENSED
# ---------------------------------------------------------------------------


@register("M365.SHARED_MAILBOX_LICENSED")
def shared_mailbox_licensed(ctx: RuleContext) -> Iterable[Finding]:
    users_by_id = {u.principal: u for u in ctx.dataset.users}
    for principal, sku_ids in ctx.assignments_by_principal.items():
        user = users_by_id.get(principal)
        if user is None or user.user_type != "shared_mailbox":
            continue
        size = user.mailbox_size_gb if user.mailbox_size_gb is not None else 0.0
        if size >= 50.0:
            continue  # Above 50 GB legitimately needs a paid license.
        for sku_id in sku_ids:
            sku = ctx.catalog.get(sku_id)
            if sku is None or sku.cloud != "m365":
                continue
            if not any(f.startswith("mailbox.") for f in effective_features(sku_id, ctx.catalog)):
                continue
            yield Finding(
                rule_id=ctx.rule.id,
                surface="m365",
                severity=ctx.rule.severity,
                principal=ctx.redact(principal),
                current_sku=sku_id,
                estimated_monthly_savings_usd=_savings(sku.list_price_usd_month),
                recommendation=render(
                    ctx.rule.recommendation_template,
                    principal=ctx.redact(principal),
                    current_sku=sku_id,
                    mailbox_size_gb=round(size, 1),
                ),
                evidence={"mailbox_size_gb": size, "user_type": "shared_mailbox"},
            )


# ---------------------------------------------------------------------------
# M365.GUEST_PREMIUM_LICENSED
# ---------------------------------------------------------------------------


@register("M365.GUEST_PREMIUM_LICENSED")
def guest_premium_licensed(ctx: RuleContext) -> Iterable[Finding]:
    users_by_id = {u.principal: u for u in ctx.dataset.users}
    for principal, sku_ids in ctx.assignments_by_principal.items():
        user = users_by_id.get(principal)
        if user is None or user.user_type != "guest":
            continue
        for sku_id in sku_ids:
            sku = ctx.catalog.get(sku_id)
            if sku is None or sku.cloud != "m365":
                continue
            yield Finding(
                rule_id=ctx.rule.id,
                surface="m365",
                severity=ctx.rule.severity,
                principal=ctx.redact(principal),
                current_sku=sku_id,
                estimated_monthly_savings_usd=_savings(sku.list_price_usd_month),
                recommendation=render(
                    ctx.rule.recommendation_template,
                    principal=ctx.redact(principal),
                    current_sku=sku_id,
                ),
                evidence={"user_type": "guest"},
            )


# ---------------------------------------------------------------------------
# M365.COPILOT_INACTIVE_60D
# ---------------------------------------------------------------------------


@register("M365.COPILOT_INACTIVE_60D")
def copilot_inactive_60d(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 60
    for assignment in ctx.dataset.assignments:
        if assignment.sku_id != "M365_COPILOT":
            continue
        sku = ctx.catalog.get(assignment.sku_id)
        if sku is None:
            continue
        usage = ctx.usage_by_principal.get(assignment.principal, {})
        last = usage.get("copilot")
        if last is not None and last <= days:
            continue
        yield Finding(
            rule_id=ctx.rule.id,
            surface="m365",
            severity=ctx.rule.severity,
            principal=ctx.redact(assignment.principal),
            current_sku=assignment.sku_id,
            estimated_monthly_savings_usd=_savings(sku.list_price_usd_month),
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(assignment.principal),
            ),
            evidence={"copilot_last_activity_days": last, "window_days": days},
        )


# ---------------------------------------------------------------------------
# M365.E5_FEATURES_UNUSED
# ---------------------------------------------------------------------------

_E5_SIGNALS = ("defender_o365", "purview_dlp", "entra_p2")
_E5_SKUS = {"SPE_E5", "ENTERPRISEPREMIUM"}
# Recommended step-down per current SKU.
_E5_STEPDOWN = {
    "SPE_E5": "SPE_E3",
    "ENTERPRISEPREMIUM": "ENTERPRISEPACK",
}


@register("M365.E5_FEATURES_UNUSED")
def e5_features_unused(ctx: RuleContext) -> Iterable[Finding]:
    days = ctx.rule.inactivity_days or 90
    for assignment in ctx.dataset.assignments:
        if assignment.sku_id not in _E5_SKUS:
            continue
        sku = ctx.catalog.get(assignment.sku_id)
        if sku is None:
            continue
        usage = ctx.usage_by_principal.get(assignment.principal, {})
        any_active = any(
            (last := usage.get(sig)) is not None and last <= days for sig in _E5_SIGNALS
        )
        if any_active:
            continue
        recommended = _E5_STEPDOWN.get(assignment.sku_id)
        recommended_sku = ctx.catalog.get(recommended) if recommended else None
        savings = _delta(
            sku.list_price_usd_month,
            recommended_sku.list_price_usd_month if recommended_sku else None,
        )
        yield Finding(
            rule_id=ctx.rule.id,
            surface="m365",
            severity=ctx.rule.severity,
            principal=ctx.redact(assignment.principal),
            current_sku=assignment.sku_id,
            recommended_sku=recommended,
            estimated_monthly_savings_usd=savings,
            recommendation=render(
                ctx.rule.recommendation_template,
                principal=ctx.redact(assignment.principal),
            ),
            evidence={
                "checked_signals": list(_E5_SIGNALS),
                "last_activity_days": {sig: usage.get(sig) for sig in _E5_SIGNALS},
                "window_days": days,
            },
        )
