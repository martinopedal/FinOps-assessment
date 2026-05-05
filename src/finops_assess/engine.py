"""Rule engine — runs registered rule implementations over a normalised dataset.

Each rule is implemented as a callable that takes a :class:`RuleContext` and
yields :class:`Finding` objects. Rules are registered by ID via
``@register("M365.UNUSED_LICENSE_30D")`` so the YAML rule definition
(``data/rules/m365.yaml``) and the Python implementation stay in lockstep.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from finops_assess.models import (
    CatalogEntry,
    Finding,
    NormalizedDataset,
    Persona,
    PersonaAssignment,
    Rule,
)

logger = logging.getLogger(__name__)


@dataclass
class RuleContext:
    """Inputs passed to every rule implementation.

    Attributes
    ----------
    catalog:
        Indexed by SKU id.
    catalog_list:
        Original list (preserves declaration order).
    personas:
        Indexed by persona id.
    persona_assignments:
        Indexed by principal.
    dataset:
        The normalised collector output.
    rule:
        The :class:`Rule` definition (severity / template / inactivity_days).
    redact_pii:
        When ``True``, every emitted ``principal`` is salted-hashed.
    salt:
        Per-run salt; never logged; only ``redact()`` reads it.
    assignments_by_principal:
        Pre-built index of ``LicenseAssignment`` by principal.
    usage_by_principal:
        Pre-built index of ``UsageSignal`` by principal.
    """

    catalog: dict[str, CatalogEntry]
    catalog_list: list[CatalogEntry]
    personas: dict[str, Persona]
    persona_assignments: dict[str, PersonaAssignment]
    dataset: NormalizedDataset
    rule: Rule
    redact_pii: bool
    salt: str
    assignments_by_principal: dict[str, list[str]] = field(default_factory=dict)
    usage_by_principal: dict[str, dict[str, int | None]] = field(default_factory=dict)

    def redact(self, principal: str) -> str:
        """Return either the raw principal or a salted SHA-256 of it."""
        if not self.redact_pii:
            return principal
        digest = hashlib.sha256(f"{self.salt}:{principal}".encode()).hexdigest()
        return f"sha256:{digest[:16]}"


RuleImpl = Callable[[RuleContext], Iterable[Finding]]
_REGISTRY: dict[str, RuleImpl] = {}


def register(rule_id: str) -> Callable[[RuleImpl], RuleImpl]:
    """Register a rule implementation under its YAML rule id."""

    def decorator(fn: RuleImpl) -> RuleImpl:
        if rule_id in _REGISTRY:
            raise ValueError(f"duplicate rule registration: {rule_id}")
        _REGISTRY[rule_id] = fn
        return fn

    return decorator


def registered_rule_ids() -> set[str]:
    return set(_REGISTRY)


def _build_indexes(
    dataset: NormalizedDataset,
) -> tuple[dict[str, list[str]], dict[str, dict[str, int | None]]]:
    assignments: dict[str, list[str]] = defaultdict(list)
    for a in dataset.assignments:
        assignments[a.principal].append(a.sku_id)
    usage: dict[str, dict[str, int | None]] = defaultdict(dict)
    for u in dataset.usage:
        usage[u.principal][u.signal] = u.last_activity_days
    return dict(assignments), dict(usage)


def run_rules(
    *,
    rules: list[Rule],
    catalog: list[CatalogEntry],
    personas: list[Persona],
    persona_assignments: dict[str, PersonaAssignment],
    dataset: NormalizedDataset,
    redact_pii: bool = True,
    salt: str | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Run every enabled rule that has a registered implementation.

    Returns ``(findings, summary)``. The summary contains per-rule counts
    plus the redaction salt iff redaction was disabled (so the operator can
    re-correlate later if they choose).
    """
    # Import the rule-impl modules so their @register decorators fire.
    # Local import to avoid a circular dependency at module load time.
    from finops_assess import rules_impl  # noqa: F401  (registers rules)

    catalog_by_id = {c.id: c for c in catalog}
    personas_by_id = {p.id: p for p in personas}
    assignments_idx, usage_idx = _build_indexes(dataset)
    salt_value = salt if salt is not None else secrets.token_hex(16)

    findings: list[Finding] = []
    counts: dict[str, int] = {}
    skipped: list[str] = []

    for rule in rules:
        if not rule.enabled:
            continue
        impl = _REGISTRY.get(rule.id)
        if impl is None:
            skipped.append(rule.id)
            continue
        ctx = RuleContext(
            catalog=catalog_by_id,
            catalog_list=catalog,
            personas=personas_by_id,
            persona_assignments=persona_assignments,
            dataset=dataset,
            rule=rule,
            redact_pii=redact_pii,
            salt=salt_value,
            assignments_by_principal=assignments_idx,
            usage_by_principal=usage_idx,
        )
        produced = list(impl(ctx))
        counts[rule.id] = len(produced)
        findings.extend(produced)

    summary: dict[str, Any] = {
        "rule_counts": counts,
        "rules_skipped_no_impl": sorted(skipped),
        "total_findings": len(findings),
        "principals_evaluated": len(dataset.users),
        "assignments_evaluated": len(dataset.assignments),
        "azure_resources_evaluated": len(dataset.azure_resources),
    }
    if not redact_pii:
        summary["pii_redaction"] = "disabled"
    return findings, summary


# ---------------------------------------------------------------------------
# Helpers shared by rule implementations
# ---------------------------------------------------------------------------


# Feature implication map: holding the key-feature also satisfies every
# value-feature. Captures the small hierarchy that exists in the curated
# taxonomy (mailbox sizes, office surface, teams tier) so that the
# "covers persona's required features" check is robust.
_FEATURE_IMPLIES: dict[str, frozenset[str]] = {
    "mailbox.100gb": frozenset({"mailbox.100gb", "mailbox.50gb", "mailbox.2gb"}),
    "mailbox.50gb": frozenset({"mailbox.50gb", "mailbox.2gb"}),
    "mailbox.2gb": frozenset({"mailbox.2gb"}),
    "office.desktop": frozenset({"office.desktop", "office.web"}),
    "office.web": frozenset({"office.web"}),
    "teams.full": frozenset({"teams.full", "teams.basic"}),
    "teams.basic": frozenset({"teams.basic"}),
    "sharepoint.advanced": frozenset({"sharepoint.advanced", "sharepoint.full", "sharepoint.read"}),
    "sharepoint.full": frozenset({"sharepoint.full", "sharepoint.read"}),
    "sharepoint.read": frozenset({"sharepoint.read"}),
    "intune.mdm": frozenset({"intune.mdm", "intune.mam"}),
    "intune.mam": frozenset({"intune.mam"}),
    "entra.p2": frozenset({"entra.p2", "entra.p1"}),
    "entra.p1": frozenset({"entra.p1"}),
    "entra.p1.frontline": frozenset({"entra.p1.frontline"}),
    "defender.o365.p2": frozenset({"defender.o365.p2", "defender.o365.p1"}),
    "defender.o365.p1": frozenset({"defender.o365.p1"}),
}


def _expand(features: set[str]) -> set[str]:
    """Expand a feature set with everything it implies."""
    out: set[str] = set()
    for f in features:
        out.update(_FEATURE_IMPLIES.get(f, frozenset({f})))
    return out


def effective_features(sku_id: str, catalog: dict[str, CatalogEntry]) -> set[str]:
    """Return all feature tags a SKU exposes, transitively walking ``includes``.

    The returned set is *expanded* via the feature-implication map so that
    higher-tier features (e.g. ``mailbox.100gb``) are treated as covering
    lower-tier ones (``mailbox.50gb``, ``mailbox.2gb``).
    """
    seen_skus: set[str] = set()
    features: set[str] = set()

    def walk(sid: str) -> None:
        if sid in seen_skus:
            return
        seen_skus.add(sid)
        entry = catalog.get(sid)
        if entry is None:
            return
        features.update(entry.features)
        for child in entry.includes:
            walk(child)

    walk(sku_id)
    return _expand(features)


def transitive_includes(sku_id: str, catalog: dict[str, CatalogEntry]) -> set[str]:
    """Return every child SKU id reachable via ``includes`` (excluding ``sku_id``)."""
    out: set[str] = set()
    stack = [sku_id]
    while stack:
        cur = stack.pop()
        entry = catalog.get(cur)
        if entry is None:
            continue
        for child in entry.includes:
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def cheapest_covering_sku(
    required: set[str],
    catalog_list: list[CatalogEntry],
    catalog: dict[str, CatalogEntry],
    cloud: str = "m365",
) -> CatalogEntry | None:
    """Return the cheapest SKU on ``cloud`` whose effective features ⊇ ``required``.

    SKUs without a known list price are ignored for ranking. Returns ``None``
    if nothing covers the requirement at a known price.
    """
    candidates: list[tuple[float, CatalogEntry]] = []
    for entry in catalog_list:
        if entry.cloud != cloud or entry.list_price_usd_month is None:
            continue
        if required.issubset(effective_features(entry.id, catalog)):
            candidates.append((entry.list_price_usd_month, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def render(template: str, **values: Any) -> str:
    """Format a recommendation template, leaving unknown placeholders intact."""
    cleaned = " ".join(template.split())

    class _SafeDict(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return cleaned.format_map(_SafeDict(**values))
