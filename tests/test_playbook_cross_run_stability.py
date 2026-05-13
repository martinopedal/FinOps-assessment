"""Cross-run stability regression test for the playbook reporter.

Pinned by Noor PR #78 stage-4 BLOCKING #1 (the manifest claimed
``azure: stable`` while the engine emitted per-run-salted Azure
principals; the test gap that allowed it to slip past was the absence
of an end-to-end two-run probe).

This module wires the real ``run_rules`` engine into the playbook
reporter and asserts:

1. With default ``redact_pii=True``: the same Azure finding rendered
   in two engine runs produces DIFFERENT ``ticket_key`` values, AND
   the manifest correctly declares every surface ``per_run``.
2. With ``redact_pii=False``: the same Azure finding produces the SAME
   ``ticket_key`` across runs, AND the manifest correctly declares
   every surface ``stable``.

If a future plan re-asserts a per-surface invariant on ``ticket_key``,
this test is the cross-run truth probe that should run before merge —
not a hand-crafted fixture spot-check (which is exactly what allowed
PR #78 to ship the dishonest manifest in the first place).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from finops_assess.engine import run_rules
from finops_assess.models import (
    AzureResource,
    NormalizedDataset,
    Rule,
)
from finops_assess.reporters.json_reporter import build_report
from finops_assess.reporters.playbook import write_playbook_export


def _idle_vm_dataset() -> NormalizedDataset:
    """Synthetic dataset that AZ.IDLE_VM_14D will fire on."""
    return NormalizedDataset(
        azure_resources=[
            AzureResource(
                resource_id=(
                    "/subscriptions/22222222-0000-0000-0000-000000000000"
                    "/resourceGroups/rg-cross-run/providers/Microsoft.Compute"
                    "/virtualMachines/vm-idle-cross-run-01"
                ),
                resource_type="virtualMachine",
                sku="Standard_D4s_v3",
                avg_cpu_pct=1.5,
                p95_cpu_pct=2.0,
                avg_net_kbps=10.0,
                days_inactive=20,
                monthly_cost_usd=140.0,
            ),
        ],
    )


def _idle_vm_rule() -> Rule:
    """Mirror the shipped AZ.IDLE_VM_14D rule definition."""
    return Rule(
        id="AZ.IDLE_VM_14D",
        surface="azure",
        severity="high",
        summary="Idle Azure virtual machine over 14 days.",
        recommendation_template=(
            "Verify the workload owner, then consider deallocating or right-sizing the VM."
        ),
        inactivity_days=14,
    )


def _engine_run(*, redact_pii: bool, salt: str | None = None) -> dict[str, object]:
    """Drive the real engine, then build a JSON report dict."""
    rule = _idle_vm_rule()
    findings, summary = run_rules(
        rules=[rule],
        catalog=[],
        personas=[],
        persona_assignments={},
        dataset=_idle_vm_dataset(),
        redact_pii=redact_pii,
        salt=salt,
    )
    if not findings:
        pytest.skip("AZ.IDLE_VM_14D did not fire on the synthetic dataset")
    report = build_report(
        findings=findings,
        summary=summary,
        persona_assignments={},
        input_path=Path("<cross-run-test>"),
        redact_pii=redact_pii,
    )
    return report


def _ticket_keys(report: dict[str, object], tmp_path: Path, label: str) -> list[str]:
    """Render the report through the playbook writer and return its ticket_keys."""
    out = tmp_path / f"{label}.jsonl"
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        jsonl_path, _manifest = write_playbook_export(report, out, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    keys: list[str] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            keys.append(json.loads(line)["ticket_key"])
    return keys


def _manifest_dict(report: dict[str, object], tmp_path: Path, label: str) -> dict[str, object]:
    out = tmp_path / f"{label}.jsonl"
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        _, manifest_path = write_playbook_export(report, out, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    return json.loads(manifest_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test A — under default redaction, ticket_key MUST rotate AND manifest MUST agree
# ---------------------------------------------------------------------------


def test_azure_ticket_key_per_run_under_default_redaction(tmp_path: Path) -> None:
    """Two engine runs with redact_pii=True (default) must produce DIFFERENT
    Azure ticket_keys for the same finding, AND the manifest must declare
    azure as 'per_run' (BLOCKING #1 regression net).
    """
    # Two independent engine runs; each draws its own per-run salt.
    report_run1 = _engine_run(redact_pii=True)
    report_run2 = _engine_run(redact_pii=True)

    keys_run1 = _ticket_keys(report_run1, tmp_path, "run1")
    keys_run2 = _ticket_keys(report_run2, tmp_path, "run2")

    assert keys_run1 and keys_run2, "Both runs must produce at least one ticket"
    assert keys_run1 != keys_run2, (
        "Azure ticket_keys must differ across two engine runs under default redaction "
        "(per-run salt rotates the principal hash). If this test passes, the engine "
        "started honouring a tenant-stable salt — update the manifest contract too."
    )

    manifest = _manifest_dict(report_run1, tmp_path, "manifest_check")
    stability = manifest["pii_handling"]["ticket_key_stability_by_surface"]  # type: ignore[index]
    assert stability["azure"] == "per_run", (
        "Manifest must declare azure as 'per_run' under default redaction "
        "(see Noor PR #78 BLOCKING #1)."
    )
    kl = manifest["pii_handling"]["known_limitation"]  # type: ignore[index]
    assert isinstance(kl, str) and "#73" in kl, (
        "known_limitation must be a non-empty string referencing #73 when any surface is per_run."
    )


# ---------------------------------------------------------------------------
# Test B — with --no-pii-redaction, ticket_key MUST be stable AND manifest MUST agree
# ---------------------------------------------------------------------------


def test_azure_ticket_key_stable_when_redaction_off(tmp_path: Path) -> None:
    """Two engine runs with redact_pii=False must produce IDENTICAL Azure
    ticket_keys for the same finding, AND the manifest must declare every
    surface 'stable' with known_limitation null.
    """
    report_run1 = _engine_run(redact_pii=False)
    report_run2 = _engine_run(redact_pii=False)

    keys_run1 = _ticket_keys(report_run1, tmp_path, "clear1")
    keys_run2 = _ticket_keys(report_run2, tmp_path, "clear2")

    assert keys_run1 and keys_run2, "Both runs must produce at least one ticket"
    assert keys_run1 == keys_run2, (
        "Azure ticket_keys must be byte-identical across runs with --no-pii-redaction "
        "(principal is the cleartext ARM resource ID)."
    )

    manifest = _manifest_dict(report_run1, tmp_path, "manifest_clear")
    stability = manifest["pii_handling"]["ticket_key_stability_by_surface"]  # type: ignore[index]
    for surface in ("azure", "ado", "github", "m365"):
        assert stability[surface] == "stable", (
            f"Without redaction, {surface} must report stable; manifest claims {stability[surface]!r}"
        )
    assert manifest["pii_handling"]["known_limitation"] is None, (  # type: ignore[index]
        "known_limitation must be null when every surface is stable."
    )


# ---------------------------------------------------------------------------
# Test C — with tenant-stable salt, ticket_key MUST be stable AND manifest MUST agree
# ---------------------------------------------------------------------------


def test_azure_ticket_key_stable_with_tenant_stable_salt(tmp_path: Path) -> None:
    """Two engine runs with the same tenant-stable salt must produce IDENTICAL
    Azure ticket_keys for the same finding, AND the manifest must declare every
    surface 'stable' with known_limitation null.
    """
    # Run 1 with explicit salt
    report_run1 = _engine_run(redact_pii=True, salt="tenant-stable-salt-abcd1234")
    # Run 2 with the SAME salt
    report_run2 = _engine_run(redact_pii=True, salt="tenant-stable-salt-abcd1234")

    keys_run1 = _ticket_keys(report_run1, tmp_path, "stable1")
    keys_run2 = _ticket_keys(report_run2, tmp_path, "stable2")

    assert keys_run1 and keys_run2, "Both runs must produce at least one ticket"
    assert keys_run1 == keys_run2, (
        "Azure ticket_keys must be identical across runs with tenant-stable salt "
        "(principal is a stable salted hash)."
    )

    manifest = _manifest_dict(report_run1, tmp_path, "manifest_stable")
    assert manifest["pii_handling"]["salt_mode"] == "tenant_stable", (  # type: ignore[index]
        "Manifest must report salt_mode='tenant_stable' when an explicit salt is provided."
    )
    stability = manifest["pii_handling"]["ticket_key_stability_by_surface"]  # type: ignore[index]
    for surface in ("azure", "ado", "github", "m365"):
        assert stability[surface] == "stable", (
            f"With tenant-stable salt, {surface} must report stable; manifest claims {stability[surface]!r}"
        )
    assert manifest["pii_handling"]["known_limitation"] is None, (  # type: ignore[index]
        "known_limitation must be null when tenant-stable salt is used."
    )


def test_manifest_salt_mode_per_run_by_default(tmp_path: Path) -> None:
    """Manifest reports salt_mode='per_run' when no explicit salt is provided."""
    report = _engine_run(redact_pii=True)
    manifest = _manifest_dict(report, tmp_path, "manifest_per_run")

    assert manifest["pii_handling"]["salt_mode"] == "per_run", (  # type: ignore[index]
        "Manifest must report salt_mode='per_run' when no explicit salt is provided."
    )
    assert manifest["pii_handling"]["known_limitation"] is not None, (  # type: ignore[index]
        "known_limitation must be present when salt_mode is per_run."
    )
