"""Golden-file tests for the playbook reporter.

Tests 11 & 12: byte-identical comparison of the emitted JSONL and manifest
against committed golden fixtures.

Golden fixtures live at ``tests/fixtures/playbook/golden-azure.{jsonl,jsonl.manifest.json}``
and are pinned to LF line endings via .gitattributes.

Regenerate with::

    SOURCE_DATE_EPOCH=0 python - << 'EOF'
    import os, json
    os.environ['SOURCE_DATE_EPOCH'] = '0'
    from finops_assess.reporters.playbook import write_playbook_export
    from pathlib import Path
    # ... (see scripts/generate_docs.py)
    EOF
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from finops_assess.reporters.playbook import write_playbook_export

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "playbook"


def _write(report: dict[str, Any], output: Path) -> tuple[Path, Path]:
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        return write_playbook_export(report, output, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


def _golden_report() -> dict[str, Any]:
    """Exact report used to generate the committed golden fixtures."""
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "1970-01-01T00:00:00+00:00",
            "pii_redaction": False,
            "mode": "read-only",
            "input": "<test>",
        },
        "findings": [
            {
                "rule_id": "AZ.IDLE_VM_14D",
                "surface": "azure",
                "severity": "high",
                "principal": (
                    "/subscriptions/11111111-0000-0000-0000-000000000000"
                    "/resourceGroups/rg-test/providers/Microsoft.Compute"
                    "/virtualMachines/vm-test-01"
                ),
                "current_sku": "Standard_D4s_v3",
                "recommended_sku": "Standard_D2s_v3",
                "estimated_monthly_savings_usd": 85.0,
                "recommendation": "Idle VM — consider deallocating.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"avg_cpu_pct": 2.1, "avg_net_kbps": 15.5},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test 11 — golden JSONL byte-identical
# ---------------------------------------------------------------------------


def test_golden_jsonl_byte_identical(tmp_path: Path) -> None:
    """Regenerated JSONL must be byte-identical to the committed golden fixture."""
    golden = FIXTURES / "golden-azure.jsonl"
    if not golden.exists():
        pytest.skip("Golden fixture not yet committed — run scripts/generate_docs.py first")

    out = tmp_path / "golden-azure.jsonl"
    jsonl_path, _ = _write(_golden_report(), out)
    assert jsonl_path.read_bytes() == golden.read_bytes(), (
        "JSONL differs from golden fixture. "
        "If the template changed intentionally, regenerate: "
        "SOURCE_DATE_EPOCH=0 python scripts/generate_docs.py"
    )


# ---------------------------------------------------------------------------
# Test 12 — golden manifest byte-identical
# ---------------------------------------------------------------------------


def test_golden_manifest_byte_identical(tmp_path: Path) -> None:
    """Regenerated manifest must be byte-identical to the committed golden fixture."""
    golden_manifest = FIXTURES / "golden-azure.jsonl.manifest.json"
    if not golden_manifest.exists():
        pytest.skip("Golden manifest not yet committed — run scripts/generate_docs.py first")

    out = tmp_path / "golden-azure.jsonl"
    _, manifest_path = _write(_golden_report(), out)
    assert manifest_path.read_bytes() == golden_manifest.read_bytes(), (
        "Manifest differs from golden fixture. "
        "Regenerate: SOURCE_DATE_EPOCH=0 python scripts/generate_docs.py"
    )


# ---------------------------------------------------------------------------
# Test 13 — golden JSONL has expected structure
# ---------------------------------------------------------------------------


def test_golden_jsonl_structure() -> None:
    """Golden JSONL must parse correctly and contain expected fields."""
    golden = FIXTURES / "golden-azure.jsonl"
    if not golden.exists():
        pytest.skip("Golden fixture not yet committed")

    lines = golden.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"Expected 1 row, got {len(lines)}"
    row = json.loads(lines[0])

    assert row["rule_id"] == "AZ.IDLE_VM_14D"
    assert row["surface"] == "azure"
    assert row["severity"] == "high"
    assert row["playbook_schema_version"] == "0.1"
    assert row["ticket_key"].startswith("sha256:")
    assert row["finding_revision"] == 1
    assert row["title"]
    assert len(row["remediation_steps"]) >= 1


# ---------------------------------------------------------------------------
# Test 14 — golden manifest has expected structure
# ---------------------------------------------------------------------------


def test_golden_manifest_structure() -> None:
    """Golden manifest must contain expected fields with correct values."""
    golden_manifest = FIXTURES / "golden-azure.jsonl.manifest.json"
    if not golden_manifest.exists():
        pytest.skip("Golden manifest not yet committed")

    manifest = json.loads(golden_manifest.read_text(encoding="utf-8"))

    assert manifest["playbook_schema_version"] == "0.1"
    assert manifest["row_count"] == 1
    assert manifest["tool"]["name"] == "finops-assess"
    assert len(manifest["output_artifacts"]["jsonl_sha256"]) == 64
    assert manifest["output_artifacts"]["jsonl_byte_count"] > 0
    assert "azure" in manifest["surfaces"]
