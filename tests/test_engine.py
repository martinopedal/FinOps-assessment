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
    "AZ.RESERVATION_UNDERUTILIZED",
    "AZ.LOG_ANALYTICS_OVERINGEST",
    "AZ.DEV_TEST_SUB_MISMATCH",
    "AZ.SAVINGS_PLAN_ELIGIBLE_SPEND",
    "AZ.COMMITMENT_UNDER_COVERED",
    "AZ.COMMITMENT_RENEWAL_REVIEW",
    "AZ.RESERVATION_SCOPE_MISMATCH",
    "AZ.AHB_ELIGIBLE",
    "GH.INACTIVE_SEAT_90D",
    "GH.COPILOT_INACTIVE_30D",
    "GH.GHAS_OVER_PROVISIONED",
    "GH.RUNNER_TIER_MISMATCH",
    "ADO.INACTIVE_BASIC_90D",
    "ADO.STAKEHOLDER_ELIGIBLE",
    "ADO.PARALLEL_JOBS_OVER_PROVISIONED",
    "ADO.TEST_PLANS_UNUSED",
}

# Anchor "today" so AZ.COMMITMENT_RENEWAL_REVIEW fires deterministically
# against the dates pinned in samples/azure_reservations.csv. The override
# env var is read by `finops_assess.rules_impl.azure_rules._today_utc`.
# Production runs leave it unset and use the real wall clock.
SAMPLES_TODAY_OVERRIDE = "2026-05-13"


@pytest.fixture(scope="module")
def run_against_samples() -> tuple[dict[str, int], list[object]]:
    dataset = collect_from_directory(SAMPLES)
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    persona_assignments = assign_personas(dataset, personas)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FINOPS_NOW_OVERRIDE", SAMPLES_TODAY_OVERRIDE)
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


def test_registered_rule_ids_works_before_run_rules_is_called() -> None:
    """Regression: previously registered_rule_ids() returned an empty set
    when called before run_rules(), because the rules_impl modules were
    only imported as a side effect of run_rules(). The helper now triggers
    the import itself so callers (and unit tests) get a consistent view.
    """
    # This test relies on subprocess-isolation-like guarantees being absent;
    # importing the engine alone in a fresh interpreter must yield the full
    # set. We can't easily unimport modules, but we can at least assert the
    # set is non-empty and contains a known impl id.
    from finops_assess.engine import registered_rule_ids as rri

    impls = rri()
    assert "M365.UNUSED_LICENSE_30D" in impls
    assert "AZ.IDLE_VM_14D" in impls


def test_features_for_surface_filters_cross_cloud_requirements() -> None:
    """The OVER_LICENSED rule must compare M365 SKUs against the M365-only
    subset of the persona's required features; otherwise personas like
    `developer` (which requires `github.enterprise`) never get a finding.
    """
    from finops_assess.engine import features_for_surface

    developer_required = {"mailbox.50gb", "office.web", "teams.full", "github.enterprise"}
    m365_only = features_for_surface(developer_required, "m365")
    assert m365_only == {"mailbox.50gb", "office.web", "teams.full"}
    github_only = features_for_surface(developer_required, "github")
    assert github_only == {"github.enterprise"}


def test_salt_mode_per_run_by_default() -> None:
    """When no salt is provided, summary reports salt_mode='per_run'."""
    from finops_assess.models import LicenseAssignment, NormalizedDataset, UserRecord

    dummy_rule = load_rules()[0]  # Any rule will do

    _findings, summary = run_rules(
        rules=[dummy_rule],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=NormalizedDataset(
            users=[UserRecord(principal="u1@example.com", display_name="U1")],
            assignments=[
                LicenseAssignment(
                    principal="u1@example.com", sku_id="M365-F3", assigned_date="2024-01-01"
                )
            ],
            usage=[],
            azure_resources=[],
        ),
        redact_pii=True,
        salt=None,
    )
    assert summary["salt_mode"] == "per_run"


def test_salt_mode_tenant_stable_when_salt_provided() -> None:
    """When a salt is explicitly provided, summary reports salt_mode='tenant_stable'."""
    from finops_assess.models import LicenseAssignment, NormalizedDataset, UserRecord

    dummy_rule = load_rules()[0]  # Any rule will do

    _findings, summary = run_rules(
        rules=[dummy_rule],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=NormalizedDataset(
            users=[UserRecord(principal="u1@example.com", display_name="U1")],
            assignments=[
                LicenseAssignment(
                    principal="u1@example.com", sku_id="M365-F3", assigned_date="2024-01-01"
                )
            ],
            usage=[],
            azure_resources=[],
        ),
        redact_pii=True,
        salt="my-fixed-salt",
    )
    assert summary["salt_mode"] == "tenant_stable"
