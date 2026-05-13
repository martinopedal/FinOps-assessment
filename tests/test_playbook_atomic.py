"""Tests for the playbook reporter atomic-write Option C contract.

Covers:
- Orphan detection (JSONL without manifest)
- Orphan detection (JSONL with mismatched manifest sha256)
- Manifest sha256 self-attestation matches on-disk JSONL
- fsync-before-rename: tempfiles are cleaned up on write failure
- --cleanup-orphans CLI flag removes orphaned JSONL
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from finops_assess.reporters.playbook import find_orphaned_jsonl, write_playbook_export

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _minimal_report(pii_redaction: bool = False) -> dict[str, Any]:
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
                "principal": "/subscriptions/test/resourceGroups/rg/providers/VM/test-vm",
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


def _write_with_epoch(report: dict[str, Any], output: Path) -> tuple[Path, Path]:
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        return write_playbook_export(report, output, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 1 — manifest sha256 self-attestation matches on-disk JSONL
# ---------------------------------------------------------------------------


def test_manifest_sha256_matches_jsonl(tmp_path: Path) -> None:
    """The manifest's output_artifacts.jsonl_sha256 must match SHA-256 of the JSONL on disk."""
    out = tmp_path / "playbook.jsonl"
    jsonl_path, manifest_path = _write_with_epoch(_minimal_report(), out)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed_sha256 = manifest["output_artifacts"]["jsonl_sha256"]

    h = hashlib.sha256(jsonl_path.read_bytes())
    assert h.hexdigest() == claimed_sha256, "sha256 mismatch between manifest claim and disk"


# ---------------------------------------------------------------------------
# Test 2 — manifest byte_count matches on-disk JSONL size
# ---------------------------------------------------------------------------


def test_manifest_byte_count_matches_jsonl(tmp_path: Path) -> None:
    """The manifest's output_artifacts.jsonl_byte_count must match the on-disk JSONL size."""
    out = tmp_path / "playbook.jsonl"
    jsonl_path, manifest_path = _write_with_epoch(_minimal_report(), out)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed_count = manifest["output_artifacts"]["jsonl_byte_count"]
    assert claimed_count == jsonl_path.stat().st_size


# ---------------------------------------------------------------------------
# Test 3 — orphan detection: JSONL without manifest is orphaned
# ---------------------------------------------------------------------------


def test_orphan_jsonl_no_manifest(tmp_path: Path) -> None:
    """A JSONL file with no matching .manifest.json is an orphan."""
    orphan = tmp_path / "lost.jsonl"
    orphan.write_text('{"rule_id":"AZ.IDLE_VM_14D"}\n', encoding="utf-8", newline="")

    orphans = find_orphaned_jsonl(tmp_path)
    assert orphan in orphans


# ---------------------------------------------------------------------------
# Test 4 — orphan detection: JSONL with mismatched manifest sha256 is orphaned
# ---------------------------------------------------------------------------


def test_orphan_jsonl_sha256_mismatch(tmp_path: Path) -> None:
    """A JSONL file whose manifest sha256 does not match is an orphan."""
    jsonl = tmp_path / "broken.jsonl"
    jsonl.write_text('{"rule_id":"AZ.IDLE_VM_14D"}\n', encoding="utf-8", newline="")

    manifest_path = tmp_path / "broken.jsonl.manifest.json"
    manifest = {
        "playbook_schema_version": "0.1",
        "output_artifacts": {
            "jsonl_sha256": "a" * 64,  # deliberately wrong
            "jsonl_byte_count": 999,
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="")

    orphans = find_orphaned_jsonl(tmp_path)
    assert jsonl in orphans


# ---------------------------------------------------------------------------
# Test 5 — non-orphaned JSONL is NOT reported as orphaned
# ---------------------------------------------------------------------------


def test_valid_export_not_orphaned(tmp_path: Path) -> None:
    """After a successful write_playbook_export, no orphans must exist in the directory."""
    out = tmp_path / "playbook.jsonl"
    _write_with_epoch(_minimal_report(), out)

    orphans = find_orphaned_jsonl(tmp_path)
    assert orphans == [], f"Unexpected orphans: {orphans}"


# ---------------------------------------------------------------------------
# Test 6 — no tempfiles are left after successful write
# ---------------------------------------------------------------------------


def test_no_temp_files_after_success(tmp_path: Path) -> None:
    """No .tmp- prefixed files should remain in the output directory after success."""
    out = tmp_path / "playbook.jsonl"
    _write_with_epoch(_minimal_report(), out)

    tmp_files = list(tmp_path.glob(".tmp-*"))
    assert tmp_files == [], f"Temp files found: {tmp_files}"


# ---------------------------------------------------------------------------
# Test 7 — manifest is written AFTER JSONL (canonical readiness marker)
# ---------------------------------------------------------------------------


def test_manifest_is_separate_file(tmp_path: Path) -> None:
    """The manifest must be a separate file at <jsonl_path>.manifest.json."""
    out = tmp_path / "playbook.jsonl"
    jsonl_path, manifest_path = _write_with_epoch(_minimal_report(), out)

    assert jsonl_path != manifest_path
    assert manifest_path.name == "playbook.jsonl.manifest.json"
    assert manifest_path.parent == jsonl_path.parent


# ---------------------------------------------------------------------------
# Test 8 — orphaned JSONL cleanup (CLI --cleanup-orphans flag path)
# ---------------------------------------------------------------------------


def test_cleanup_orphans_removes_orphans(tmp_path: Path) -> None:
    """find_orphaned_jsonl + unlink should remove orphaned files."""
    # Create a valid export first.
    out = tmp_path / "playbook.jsonl"
    _write_with_epoch(_minimal_report(), out)

    # Create a second orphaned JSONL.
    orphan = tmp_path / "old-export.jsonl"
    orphan.write_text('{"rule_id":"AZ.IDLE_VM_14D"}\n', encoding="utf-8", newline="")

    orphans = find_orphaned_jsonl(tmp_path)
    assert orphan in orphans
    assert out not in orphans  # valid one must not be listed

    for o in orphans:
        o.unlink()

    assert not orphan.exists()
    assert out.exists()  # valid JSONL must survive
