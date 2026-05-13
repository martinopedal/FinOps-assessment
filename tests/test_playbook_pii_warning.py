"""Tests for the PII warning emitted when non-Azure findings are present.

When PII redaction is on AND findings from M365/GitHub/ADO surfaces are
present, the CLI must emit a warning to stderr explaining that ticket_key
is per_run for those surfaces.

The warning must be suppressed by ``--skip-warnings``.
"""

from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from finops_assess.reporters.playbook import write_playbook_export


def _m365_report(pii_redaction: bool = True) -> dict[str, Any]:
    """Minimal report with one M365 finding."""
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "1970-01-01T00:00:00+00:00",
            "pii_redaction": pii_redaction,
            "mode": "read-only",
            "input": "<test>",
        },
        "findings": [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "severity": "high",
                "principal": "sha256:cafebabe000000000000000000000000cafebabe000000000000000000000000",
                "current_sku": "ENTERPRISEPREMIUM",
                "recommended_sku": None,
                "estimated_monthly_savings_usd": 35.0,
                "recommendation": "Reclaim license.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {},
            }
        ],
    }


def _azure_only_report(pii_redaction: bool = True) -> dict[str, Any]:
    """Minimal report with one Azure finding only."""
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "1970-01-01T00:00:00+00:00",
            "pii_redaction": pii_redaction,
            "mode": "read-only",
            "input": "<test>",
        },
        "findings": [
            {
                "rule_id": "AZ.IDLE_VM_14D",
                "surface": "azure",
                "severity": "high",
                "principal": "/subscriptions/test/VM/test-vm",
                "current_sku": "Standard_D4s_v3",
                "recommended_sku": "Standard_D2s_v3",
                "estimated_monthly_savings_usd": 85.0,
                "recommendation": "Idle VM.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"avg_cpu_pct": 2.1, "avg_net_kbps": 15.5},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test 1 — warning emitted for M365 findings with PII redaction on
# ---------------------------------------------------------------------------


def test_pii_warning_emitted_for_m365(tmp_path: Path) -> None:
    """write_playbook_export must emit a stderr warning for M365 findings with PII on."""
    out = tmp_path / "playbook.jsonl"
    captured = StringIO()

    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"

    try:
        with patch.object(sys, "stderr", captured):
            # We patch click.echo to capture stderr output.
            stderr_output: list[str] = []

            def _mock_echo(msg: object = "", *, file: object = None, **_kw: object) -> None:
                if file is sys.stderr:
                    stderr_output.append(str(msg))

            with patch("finops_assess.reporters.playbook._get_click_echo", return_value=_mock_echo):
                write_playbook_export(_m365_report(pii_redaction=True), out, skip_warnings=False)

        assert any("ticket_key" in msg for msg in stderr_output), (
            f"Expected PII warning in stderr; got: {stderr_output}"
        )
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 2 — warning suppressed by skip_warnings=True
# ---------------------------------------------------------------------------


def test_pii_warning_suppressed_by_skip_warnings(tmp_path: Path) -> None:
    """skip_warnings=True must suppress the PII stderr warning."""
    out = tmp_path / "playbook.jsonl"
    stderr_output: list[str] = []

    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"

    def _mock_echo(msg: object = "", *, file: object = None, **_kw: object) -> None:
        if file is sys.stderr:
            stderr_output.append(str(msg))

    try:
        with patch("finops_assess.reporters.playbook._get_click_echo", return_value=_mock_echo):
            write_playbook_export(_m365_report(pii_redaction=True), out, skip_warnings=True)
        assert stderr_output == [], f"Unexpected stderr output: {stderr_output}"
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 3 — no warning for Azure-only findings
# ---------------------------------------------------------------------------


def test_no_pii_warning_for_azure_only(tmp_path: Path) -> None:
    """No warning should be emitted when all findings are Azure (cleartext principal)."""
    out = tmp_path / "playbook.jsonl"
    stderr_output: list[str] = []

    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"

    def _mock_echo(msg: object = "", *, file: object = None, **_kw: object) -> None:
        if file is sys.stderr:
            stderr_output.append(str(msg))

    try:
        with patch("finops_assess.reporters.playbook._get_click_echo", return_value=_mock_echo):
            write_playbook_export(_azure_only_report(pii_redaction=True), out, skip_warnings=False)
        assert stderr_output == [], f"Unexpected stderr output: {stderr_output}"
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 4 — no warning when PII redaction is off
# ---------------------------------------------------------------------------


def test_no_pii_warning_when_redaction_off(tmp_path: Path) -> None:
    """No warning when pii_redaction is False (cleartext mode)."""
    out = tmp_path / "playbook.jsonl"
    stderr_output: list[str] = []

    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"

    def _mock_echo(msg: object = "", *, file: object = None, **_kw: object) -> None:
        if file is sys.stderr:
            stderr_output.append(str(msg))

    try:
        with patch("finops_assess.reporters.playbook._get_click_echo", return_value=_mock_echo):
            write_playbook_export(_m365_report(pii_redaction=False), out, skip_warnings=False)
        assert stderr_output == [], f"Unexpected stderr output: {stderr_output}"
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 5 — manifest reflects pii_handling.mode correctly
# ---------------------------------------------------------------------------


def test_manifest_pii_mode_salted_hash(tmp_path: Path) -> None:
    """Manifest pii_handling.mode must be 'salted_hash' when PII redaction is on."""
    import json

    out = tmp_path / "playbook.jsonl"
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        _, manifest_path = write_playbook_export(
            _m365_report(pii_redaction=True), out, skip_warnings=True
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["pii_handling"]["mode"] == "salted_hash"
        # M365 must be per_run
        assert manifest["pii_handling"]["ticket_key_stability_by_surface"]["m365"] == "per_run"
        # Azure must be stable
        assert manifest["pii_handling"]["ticket_key_stability_by_surface"]["azure"] == "stable"
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
