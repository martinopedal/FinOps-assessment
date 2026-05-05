"""Tests for the rule engine — one assertion per rule, against the synthetic ./samples tenant."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from finops_assess.catalog import load_catalog
from finops_assess.collectors import collect_from_directory
from finops_assess.engine import (
    cheapest_covering_sku,
    effective_features,
    registered_rule_ids,
    run_rules,
)
from finops_assess.persona import assign_personas
from finops_assess.rules import load_personas, load_rules

SAMPLES = Path(__file__).resolve().parents[1] / "samples"

REQUIRED_RULES = {
    "M365.UNUSED_LICENSE_30D",
    "M365.OVER_LICENSED_VS_PERSONA",
    "M365.DUPLICATE_BUNDLE",
    "M365.DISABLED_USER_LICENSED",
    "M365.SHARED_MAILBOX_LICENSED",
    "M365.GUEST_PREMIUM_LICENSED",
    "M365.COPILOT_INACTIVE_60D",
    "M365.E5_FEATURES_UNUSED",
    "AZ.IDLE_VM_14D",
    "AZ.UNATTACHED_DISK",
    "AZ.PUBLIC_IP_UNATTACHED",
    "AZ.OVERSIZED_VM",
}


@pytest.fixture(scope="module")
def run_against_samples() -> tuple[dict[str, int], list[object]]:
    dataset = collect_from_directory(SAMPLES)
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    persona_assignments = assign_personas(dataset, personas)
    findings, _summary = run_rules(
        rules=rules,
        catalog=catalog,
        personas=personas,
        persona_assignments=persona_assignments,
        dataset=dataset,
        redact_pii=False,
        salt="test",
    )
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[f.rule_id] += 1
    return dict(counts), list(findings)


def test_m2_milestone_at_least_ten_rules_fire(
    run_against_samples: tuple[dict[str, int], list[object]],
) -> None:
    """M2 exit criterion (`docs/plan.md` §2): ≥10 working rules across M365 + Azure."""
    counts, _ = run_against_samples
    fired = {rid for rid, n in counts.items() if n > 0}
    assert len(fired) >= 10, f"expected ≥10 firing rules, got {len(fired)}: {sorted(fired)}"


@pytest.mark.parametrize("rule_id", sorted(REQUIRED_RULES))
def test_each_required_rule_fires_at_least_once(
    rule_id: str, run_against_samples: tuple[dict[str, int], list[object]]
) -> None:
    counts, _ = run_against_samples
    assert counts.get(rule_id, 0) > 0, f"{rule_id} produced no findings against ./samples"


def test_every_required_rule_has_a_registered_impl() -> None:
    impls = registered_rule_ids()
    missing = REQUIRED_RULES - impls
    assert not missing, f"rule(s) declared in YAML but not implemented: {sorted(missing)}"


def test_pii_redaction_hashes_principals() -> None:
    dataset = collect_from_directory(SAMPLES)
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    persona_assignments = assign_personas(dataset, personas)
    findings, _ = run_rules(
        rules=rules,
        catalog=catalog,
        personas=personas,
        persona_assignments=persona_assignments,
        dataset=dataset,
        redact_pii=True,
        salt="test-salt",
    )
    # No raw UPNs (which all contain '@') should appear in redacted output.
    for f in findings:
        if f.surface != "azure":
            assert "@" not in f.principal, f"raw UPN leaked: {f.principal} ({f.rule_id})"
            assert f.principal.startswith("sha256:")


def test_effective_features_walks_includes() -> None:
    catalog = {e.id: e for e in load_catalog()}
    e3 = effective_features("SPE_E3", catalog)
    # mailbox.100gb is direct on E3 and should imply mailbox.50gb / 2gb.
    assert "mailbox.100gb" in e3
    assert "mailbox.50gb" in e3
    assert "mailbox.2gb" in e3
    # office.desktop implies office.web.
    assert "office.web" in e3


def test_cheapest_covering_sku_for_frontline_worker_picks_f3() -> None:
    catalog_list = load_catalog()
    catalog = {e.id: e for e in catalog_list}
    required = {"mailbox.2gb", "office.web", "teams.basic", "intune.mam"}
    chosen = cheapest_covering_sku(required, catalog_list, catalog, cloud="m365")
    assert chosen is not None
    # Among priced SKUs covering the frontline persona, F3 ($8) should win.
    assert chosen.id == "SPE_F3"
