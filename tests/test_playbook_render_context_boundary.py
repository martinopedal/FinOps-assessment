"""Render-context boundary tests for the playbook reporter.

Pinned by Noor PR #78 stage-4 AMENDMENT #2.

Engine-generated evidence is in-scope-trusted in v0.5.0, but the render
context boundary should still be defended: a (mis-named or hostile)
``evidence`` entry like ``{"principal": "<cleartext UPN>"}`` must not
override the redacted reserved field and leak through the rendered
title or description.  ``render_row`` defends this by spreading
``**evidence`` FIRST and the reserved keys SECOND, so reserved keys
always win on conflict.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from finops_assess.reporters.playbook import render_row, write_playbook_export


def _finding_with_evidence_override() -> dict[str, Any]:
    """Build a finding whose evidence dict tries to override 'principal'."""
    return {
        "rule_id": "AZ.IDLE_VM_14D",
        "surface": "azure",
        "severity": "high",
        # Reserved redacted principal (engine-emitted shape).
        "principal": "sha256:redactedaaaaaaaaaaaaaaaa",
        "current_sku": "Standard_D4s_v3",
        "recommended_sku": "Standard_D2s_v3",
        "estimated_monthly_savings_usd": 85.0,
        "recommendation": "Idle VM.",
        "evidence_ref": None,
        "confidence": "high",
        # Hostile / mis-named evidence: should NOT win the render-context spread.
        "evidence": {
            "principal": "alice@contoso.com",
            "rule_id": "M365.SOMETHING_ELSE",
            "surface": "m365",
            "severity": "info",
            "avg_cpu_pct": 1.2,
            "avg_net_kbps": 5.0,
        },
    }


def test_evidence_cannot_override_reserved_principal() -> None:
    """Evidence dict must not leak a cleartext principal into the rendered output."""
    row = render_row(_finding_with_evidence_override())
    cleartext = "alice@contoso.com"
    redacted = "sha256:redactedaaaaaaaaaaaaaaaa"
    # The redacted reserved principal must appear in the rendered description / title;
    # the cleartext value from evidence must NOT.
    assert cleartext not in row["title"], f"Cleartext leaked into title: {row['title']!r}"
    assert cleartext not in row["description"], (
        f"Cleartext leaked into description: {row['description']!r}"
    )
    assert redacted in row["title"] or redacted in row["description"], (
        "Redacted reserved principal should appear in the rendered output"
    )


def test_evidence_cannot_override_reserved_rule_id_or_surface() -> None:
    """Reserved rule_id / surface must not be overridden by hostile evidence keys."""
    row = render_row(_finding_with_evidence_override())
    # Top-level row fields must reflect the engine-emitted reserved values, not the
    # evidence override.
    assert row["rule_id"] == "AZ.IDLE_VM_14D"
    assert row["surface"] == "azure"


def test_evidence_override_does_not_leak_via_jsonl(tmp_path: Path) -> None:
    """End-to-end: write a finding with hostile evidence and assert the JSONL is clean."""
    out = tmp_path / "playbook.jsonl"
    report = {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "1970-01-01T00:00:00+00:00",
            "pii_redaction": True,
            "mode": "read-only",
            "input": "<test>",
        },
        "findings": [_finding_with_evidence_override()],
    }
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        jsonl_path, _ = write_playbook_export(report, out, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    raw = jsonl_path.read_text(encoding="utf-8")
    assert "alice@contoso.com" not in raw, (
        "Cleartext UPN from evidence dict leaked into the JSONL output"
    )
    line = next(line for line in raw.splitlines() if line.strip())
    row = json.loads(line)
    assert row["principal"] == "sha256:redactedaaaaaaaaaaaaaaaa"
    assert row["rule_id"] == "AZ.IDLE_VM_14D"
    assert row["surface"] == "azure"
