"""Tests for the --cleanup-orphans flag (CLI integration).

Covers:
- find_orphaned_jsonl correctly identifies orphaned JSONL files
- Orphaned files are removed when cleanup is performed
- Valid (non-orphaned) exports survive cleanup
- Empty directory produces no orphans
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from finops_assess.reporters.playbook import find_orphaned_jsonl, write_playbook_export


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


def _minimal_report() -> dict[str, Any]:
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
                "principal": "/subscriptions/test/VM/test-vm",
                "current_sku": "Standard_D4s_v3",
                "recommended_sku": None,
                "estimated_monthly_savings_usd": None,
                "recommendation": "Idle VM.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"avg_cpu_pct": 2.1, "avg_net_kbps": 15.5},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test 1 — empty directory has no orphans
# ---------------------------------------------------------------------------


def test_empty_directory_no_orphans(tmp_path: Path) -> None:
    """An empty directory must yield an empty orphan list."""
    orphans = find_orphaned_jsonl(tmp_path)
    assert orphans == []


# ---------------------------------------------------------------------------
# Test 2 — JSONL without manifest is an orphan
# ---------------------------------------------------------------------------


def test_jsonl_no_manifest_is_orphan(tmp_path: Path) -> None:
    """A .jsonl file with no sibling manifest is an orphan."""
    jsonl = tmp_path / "orphan.jsonl"
    jsonl.write_text('{"x":1}\n', encoding="utf-8", newline="")
    orphans = find_orphaned_jsonl(tmp_path)
    assert jsonl in orphans


# ---------------------------------------------------------------------------
# Test 3 — JSONL with mismatched sha256 is an orphan
# ---------------------------------------------------------------------------


def test_jsonl_mismatched_sha256_is_orphan(tmp_path: Path) -> None:
    """A .jsonl file whose manifest sha256 is wrong is an orphan."""
    jsonl = tmp_path / "bad.jsonl"
    jsonl.write_text('{"x":1}\n', encoding="utf-8", newline="")
    manifest = tmp_path / "bad.jsonl.manifest.json"
    manifest.write_text(
        json.dumps({"output_artifacts": {"jsonl_sha256": "0" * 64, "jsonl_byte_count": 999}}),
        encoding="utf-8",
        newline="",
    )
    orphans = find_orphaned_jsonl(tmp_path)
    assert jsonl in orphans


# ---------------------------------------------------------------------------
# Test 4 — JSONL with corrupt (non-JSON) manifest is an orphan
# ---------------------------------------------------------------------------


def test_jsonl_corrupt_manifest_is_orphan(tmp_path: Path) -> None:
    """A .jsonl file whose manifest is not valid JSON is treated as an orphan."""
    jsonl = tmp_path / "corrupt.jsonl"
    jsonl.write_text('{"x":1}\n', encoding="utf-8", newline="")
    manifest = tmp_path / "corrupt.jsonl.manifest.json"
    manifest.write_text("not valid json", encoding="utf-8", newline="")
    orphans = find_orphaned_jsonl(tmp_path)
    assert jsonl in orphans


# ---------------------------------------------------------------------------
# Test 5 — valid export is not an orphan
# ---------------------------------------------------------------------------


def test_valid_export_not_orphan(tmp_path: Path) -> None:
    """A JSONL written by write_playbook_export must not be identified as an orphan."""
    out = tmp_path / "valid.jsonl"
    _write(_minimal_report(), out)
    orphans = find_orphaned_jsonl(tmp_path)
    assert out not in orphans


# ---------------------------------------------------------------------------
# Test 6 — cleanup removes orphan, valid survives
# ---------------------------------------------------------------------------


def test_cleanup_removes_orphan_keeps_valid(tmp_path: Path) -> None:
    """cleanup_orphans pattern: orphaned files removed; valid export survives."""
    # Write a valid export.
    valid_out = tmp_path / "valid.jsonl"
    _write(_minimal_report(), valid_out)

    # Plant an orphan.
    orphan = tmp_path / "orphan.jsonl"
    orphan.write_text('{"rule_id":"stale"}\n', encoding="utf-8", newline="")

    orphans = find_orphaned_jsonl(tmp_path)
    assert orphan in orphans
    assert valid_out not in orphans

    # Simulate what --cleanup-orphans does in the CLI.
    for o in orphans:
        o.unlink()

    assert not orphan.exists(), "Orphan was not removed"
    assert valid_out.exists(), "Valid export was incorrectly removed"


# ---------------------------------------------------------------------------
# Test 7 — multiple orphans are all listed
# ---------------------------------------------------------------------------


def test_multiple_orphans_all_listed(tmp_path: Path) -> None:
    """When multiple orphaned .jsonl files exist, all must be returned."""
    for name in ("orphan-a.jsonl", "orphan-b.jsonl", "orphan-c.jsonl"):
        (tmp_path / name).write_text('{"x":1}\n', encoding="utf-8", newline="")

    orphans = find_orphaned_jsonl(tmp_path)
    assert len(orphans) == 3
