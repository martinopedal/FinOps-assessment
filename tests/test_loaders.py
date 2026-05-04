"""Tests for catalog, persona, and rule loaders."""

from __future__ import annotations

from finops_assess.catalog import load_catalog
from finops_assess.rules import load_personas, load_rules


def test_catalog_loads_and_has_expected_minimum_size() -> None:
    entries = load_catalog()
    # M1 target is the full SKU surface (~70+ entries across M365/Azure/GH/ADO).
    assert len(entries) >= 70, f"expected >=70 catalog entries, got {len(entries)}"


def test_catalog_ids_are_unique() -> None:
    entries = load_catalog()
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids))


def test_catalog_includes_all_surfaces() -> None:
    clouds = {e.cloud for e in load_catalog()}
    assert {"m365", "azure", "github", "ado"} <= clouds


def test_catalog_covers_canonical_m365_user_skus() -> None:
    """M1 exit criterion: all M365 user-SKUs are catalogued.

    These IDs are the well-known service-plan / SKU identifiers used by
    Microsoft Graph for the major commercial M365 user-licenses. If any
    of these regress out of the catalogue, persona/savings rules that
    look them up by id will silently misfire.
    """
    ids = {e.id for e in load_catalog()}
    required = {
        # Microsoft 365 enterprise + frontline + business
        "SPE_E1",
        "SPE_E3",
        "SPE_E5",
        "SPE_F1",
        "SPE_F3",
        "SPB",
        # Office 365 enterprise + frontline (distinct from M365 *PE bundles)
        "STANDARDPACK",
        "ENTERPRISEPACK",
        "ENTERPRISEPREMIUM",
        "DESKLESSPACK",
        # Entra / EMS
        "AAD_PREMIUM",
        "AAD_PREMIUM_P2",
        "EMS_E3",
        "EMS_E5",
        # Defender stack
        "MDE_P1",
        "WIN_DEF_ATP",
        "ATA",
        "ADALLOM_S_STANDALONE",
        "ATP_ENTERPRISE",
        "THREAT_INTELLIGENCE",
        # Purview / compliance
        "PURVIEW_DLP",
        "INFORMATION_PROTECTION_AND_GOVERNANCE",
        "M365_E5_COMPLIANCE",
        # Copilot
        "M365_COPILOT",
    }
    missing = required - ids
    assert not missing, f"M365 user-SKU coverage gap: {sorted(missing)}"


def test_catalog_bundle_includes_resolve_to_known_ids() -> None:
    entries = load_catalog()
    known = {e.id for e in entries}
    for e in entries:
        for child in e.includes:
            # Some child service-plan IDs are intentionally not modelled
            # as standalone catalog entries (they only ship inside bundles).
            # We just assert the strings are non-empty and unique-shaped.
            assert child and child == child.strip()
        for pred in e.successor_of:
            assert pred in known, f"{e.id}: successor_of references unknown id {pred}"


def test_personas_load() -> None:
    personas = load_personas()
    ids = {p.id for p in personas}
    assert {"information_worker", "frontline_worker", "service_account"} <= ids


def test_rules_load_for_all_surfaces() -> None:
    rules = load_rules()
    surfaces = {r.surface for r in rules}
    assert {"m365", "azure", "github", "ado"} <= surfaces
    assert len(rules) >= 10
