"""Tests for AZ.AHB_ELIGIBLE.

Test plan: ``docs/plans/059-az-ahb-eligible.md`` §3.8.
Uses the Yuki-net end-to-end pattern (real ``run_rules`` engine, not a mocked
rule callable) consistent with the existing Azure rule test suites.
"""

from __future__ import annotations

import pytest

from finops_assess.engine import run_rules
from finops_assess.models import (
    AzureResource,
    Finding,
    NormalizedDataset,
    Rule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ahb_rule() -> Rule:
    """Mirror the shipped AZ.AHB_ELIGIBLE rule definition."""
    return Rule(
        id="AZ.AHB_ELIGIBLE",
        surface="azure",
        severity="info",
        summary=("Windows VM running pay-as-you-go without Azure Hybrid Benefit applied."),
        recommendation_template=(
            "VM {principal} ({sku}, {location}) has os_type=Windows but "
            "license_type={license_type}. Consider enabling Azure Hybrid Benefit "
            "(Windows_Server) to reduce the Windows Server licence cost component."
        ),
    )


def _vm(
    *,
    rid: str = "/subscriptions/00000000/rg/test/vm/vm-test",
    sku: str = "Standard_D4s_v5",
    location: str = "eastus",
    os_type: str | None = "Windows",
    license_type: str | None = None,
    resource_type: str = "virtualMachine",
) -> AzureResource:
    """Build a minimal ``AzureResource`` for the rule under test."""
    return AzureResource(
        resource_id=rid,
        resource_type=resource_type,
        sku=sku,
        location=location,
        os_type=os_type,  # type: ignore[arg-type]
        license_type=license_type,
    )


def _run(
    *,
    resources: list[AzureResource],
    rules: list[Rule] | None = None,
    redact_pii: bool = False,
    salt: str = "test-salt",
) -> list[Finding]:
    """Drive ``run_rules`` end-to-end with the synthetic dataset."""
    dataset = NormalizedDataset(azure_resources=resources)
    findings, _summary = run_rules(
        rules=rules or [_ahb_rule()],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=dataset,
        redact_pii=redact_pii,
        salt=salt,
    )
    return findings


# ---------------------------------------------------------------------------
# E1: Windows VM, no license_type -> fires
# ---------------------------------------------------------------------------


def test_fires_windows_payg_none() -> None:
    """E1: Windows VM with license_type=None -> one info finding."""
    findings = _run(resources=[_vm(os_type="Windows", license_type=None)])
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "AZ.AHB_ELIGIBLE"
    assert f.surface == "azure"
    assert f.severity == "info"
    assert f.evidence["os_type"] == "Windows"
    assert f.evidence["license_type"] is None
    assert f.confidence == "high"


# ---------------------------------------------------------------------------
# E2: Windows VM, license_type="" (empty string from CSV) -> fires
# ---------------------------------------------------------------------------


def test_fires_windows_payg_empty_string() -> None:
    """E2: Windows VM with license_type='' -> fires (empty is not AHB)."""
    findings = _run(resources=[_vm(os_type="Windows", license_type="")])
    assert len(findings) == 1
    assert findings[0].evidence["license_type"] == ""


# ---------------------------------------------------------------------------
# E3: Windows VM, license_type="PAYG" (unexpected string) -> fires
# ---------------------------------------------------------------------------


def test_fires_windows_payg_unknown_string() -> None:
    """E3: Windows VM with license_type='PAYG' -> fires (not in allow-set)."""
    findings = _run(resources=[_vm(os_type="Windows", license_type="PAYG")])
    assert len(findings) == 1
    assert findings[0].evidence["license_type"] == "PAYG"


# ---------------------------------------------------------------------------
# E4: Linux VM -> abstains
# ---------------------------------------------------------------------------


def test_abstains_linux() -> None:
    """E4: Linux VM -> no finding (AHB is Windows-only)."""
    findings = _run(resources=[_vm(os_type="Linux")])
    assert findings == []


# ---------------------------------------------------------------------------
# E5: Windows VM with Windows_Server -> abstains
# ---------------------------------------------------------------------------


def test_abstains_windows_server_ahb() -> None:
    """E5: Windows VM with license_type='Windows_Server' -> no finding."""
    findings = _run(resources=[_vm(os_type="Windows", license_type="Windows_Server")])
    assert findings == []


# ---------------------------------------------------------------------------
# E6: Windows VM with Windows_Client -> abstains
# ---------------------------------------------------------------------------


def test_abstains_windows_client_ahb() -> None:
    """E6: Windows VM with license_type='Windows_Client' -> no finding."""
    findings = _run(resources=[_vm(os_type="Windows", license_type="Windows_Client")])
    assert findings == []


# ---------------------------------------------------------------------------
# E7: os_type=None -> abstains (unknown OS, can't assert Windows)
# ---------------------------------------------------------------------------


def test_abstains_os_type_none() -> None:
    """E7: os_type=None -> no finding."""
    findings = _run(resources=[_vm(os_type=None)])
    assert findings == []


# ---------------------------------------------------------------------------
# E8: Non-VM resource -> abstains
# ---------------------------------------------------------------------------


def test_abstains_non_vm_resource() -> None:
    """E8: managedDisk resource -> no finding."""
    findings = _run(resources=[_vm(resource_type="managedDisk", os_type="Windows")])
    assert findings == []


# ---------------------------------------------------------------------------
# E9: Multiple VMs, mixed -> correct fire/abstain per-VM
# ---------------------------------------------------------------------------


def test_mixed_fleet() -> None:
    """E9: 3 Windows VMs (1 PAYG, 1 AHB, 1 Client) + 1 Linux -> 1 finding."""
    resources = [
        _vm(rid="/subscriptions/00000000/rg/t/vm/win-payg", license_type=None),
        _vm(rid="/subscriptions/00000000/rg/t/vm/win-ahb", license_type="Windows_Server"),
        _vm(rid="/subscriptions/00000000/rg/t/vm/win-client", license_type="Windows_Client"),
        _vm(rid="/subscriptions/00000000/rg/t/vm/linux", os_type="Linux"),
    ]
    findings = _run(resources=resources)
    assert len(findings) == 1
    assert "/vm/win-payg" in findings[0].principal


# ---------------------------------------------------------------------------
# E10: PII redaction
# ---------------------------------------------------------------------------


def test_pii_redaction() -> None:
    """E10: redact_pii=True -> principal and evidence.resource_id are hashed."""
    findings = _run(
        resources=[_vm(os_type="Windows", license_type=None)],
        redact_pii=True,
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.principal.startswith("sha256:")
    assert f.evidence["resource_id"].startswith("sha256:")


# ---------------------------------------------------------------------------
# E11: Evidence shape includes all expected keys
# ---------------------------------------------------------------------------


def test_evidence_shape() -> None:
    """E11: Evidence dict contains the 5 expected keys."""
    findings = _run(resources=[_vm(os_type="Windows", license_type=None)])
    assert len(findings) == 1
    evidence = findings[0].evidence
    expected_keys = {"resource_id", "os_type", "license_type", "sku", "location"}
    assert expected_keys == set(evidence.keys())


# ---------------------------------------------------------------------------
# E12: estimated_monthly_savings_usd is always None (no price API)
# ---------------------------------------------------------------------------


def test_savings_always_none() -> None:
    """E12: Without Retail Prices API, savings must be None."""
    findings = _run(resources=[_vm(os_type="Windows", license_type=None)])
    assert len(findings) == 1
    assert findings[0].estimated_monthly_savings_usd is None


# ---------------------------------------------------------------------------
# E13: Recommendation renders template correctly
# ---------------------------------------------------------------------------


def test_recommendation_renders() -> None:
    """E13: Recommendation text includes sku and location from the resource."""
    findings = _run(resources=[_vm(sku="Standard_E8s_v5", location="westeurope")])
    assert len(findings) == 1
    rec = findings[0].recommendation
    assert "Standard_E8s_v5" in rec
    assert "westeurope" in rec


# ---------------------------------------------------------------------------
# E14: CSV backward-compat — old rows without os_type/license_type still load
# ---------------------------------------------------------------------------


def test_csv_backward_compat() -> None:
    """E14: AzureResource without os_type/license_type defaults to None."""
    resource = AzureResource(
        resource_id="/subscriptions/00000000/rg/t/vm/legacy",
        resource_type="virtualMachine",
    )
    assert resource.os_type is None
    assert resource.license_type is None


# ---------------------------------------------------------------------------
# E15: os_type validation — only Windows/Linux/None allowed
# ---------------------------------------------------------------------------


def test_os_type_literal_validation() -> None:
    """E15: Invalid os_type raises pydantic validation error."""
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        AzureResource(
            resource_id="/subscriptions/00000000/rg/t/vm/bad",
            resource_type="virtualMachine",
            os_type="FreeBSD",  # type: ignore[arg-type]
        )
