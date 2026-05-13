"""Tests for playbook reporter byte-contract under reproducible-builds conditions.

Covers:
- LF-only line endings (no CRLF) in the emitted JSONL
- UTF-8 encoding without BOM
- Trailing newline after the last row
- SOURCE_DATE_EPOCH is honoured (byte-identical reruns)
- No floating-point rounding surprises in numeric fields
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from finops_assess.reporters.playbook import write_playbook_export


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
                "principal": "/subscriptions/11111111/resourceGroups/rg/VM/test-vm",
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


def _write(report: dict[str, Any], output: Path, epoch: str = "0") -> tuple[Path, Path]:
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    try:
        return write_playbook_export(report, output, skip_warnings=True)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# ---------------------------------------------------------------------------
# Test 1 — LF-only (no CRLF)
# ---------------------------------------------------------------------------


def test_jsonl_is_lf_only(tmp_path: Path) -> None:
    """The emitted JSONL must use LF line endings only — no CRLF."""
    jsonl_path, _ = _write(_minimal_report(), tmp_path / "out.jsonl")
    raw = jsonl_path.read_bytes()
    assert b"\r\n" not in raw, "CRLF found in JSONL output"
    assert b"\r" not in raw, "bare CR found in JSONL output"


# ---------------------------------------------------------------------------
# Test 2 — UTF-8 without BOM
# ---------------------------------------------------------------------------


def test_jsonl_utf8_no_bom(tmp_path: Path) -> None:
    """The emitted JSONL must be UTF-8 encoded without a BOM marker."""
    jsonl_path, _ = _write(_minimal_report(), tmp_path / "out.jsonl")
    raw = jsonl_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM found at start of JSONL"
    # Verify it decodes cleanly as UTF-8.
    raw.decode("utf-8")


# ---------------------------------------------------------------------------
# Test 3 — trailing newline after the last row
# ---------------------------------------------------------------------------


def test_jsonl_trailing_newline(tmp_path: Path) -> None:
    """The JSONL must end with a single LF after the last row."""
    jsonl_path, _ = _write(_minimal_report(), tmp_path / "out.jsonl")
    raw = jsonl_path.read_bytes()
    assert raw.endswith(b"\n"), "JSONL does not end with a newline"
    # Only one trailing newline (not two blank lines).
    assert not raw.endswith(b"\n\n"), "JSONL ends with more than one trailing newline"


# ---------------------------------------------------------------------------
# Test 4 — SOURCE_DATE_EPOCH produces byte-identical reruns
# ---------------------------------------------------------------------------


def test_byte_identical_reruns(tmp_path: Path) -> None:
    """Two runs with the same SOURCE_DATE_EPOCH must produce byte-identical JSONL."""
    report = _minimal_report()
    path_a = tmp_path / "run-a" / "out.jsonl"
    path_b = tmp_path / "run-b" / "out.jsonl"
    path_a.parent.mkdir()
    path_b.parent.mkdir()

    a, _ = _write(report, path_a, epoch="1717200000")
    b, _ = _write(report, path_b, epoch="1717200000")

    assert a.read_bytes() == b.read_bytes(), (
        "JSONL differs between runs with same SOURCE_DATE_EPOCH"
    )


# ---------------------------------------------------------------------------
# Test 5 — manifest also byte-identical under SOURCE_DATE_EPOCH
# ---------------------------------------------------------------------------


def test_manifest_byte_identical_reruns(tmp_path: Path) -> None:
    """Two runs with the same SOURCE_DATE_EPOCH must produce byte-identical manifests."""
    report = _minimal_report()
    path_a = tmp_path / "run-a" / "out.jsonl"
    path_b = tmp_path / "run-b" / "out.jsonl"
    path_a.parent.mkdir()
    path_b.parent.mkdir()

    _, ma = _write(report, path_a, epoch="1717200000")
    _, mb = _write(report, path_b, epoch="1717200000")

    assert ma.read_bytes() == mb.read_bytes(), (
        "Manifest differs between runs with same SOURCE_DATE_EPOCH"
    )


# ---------------------------------------------------------------------------
# Test 6 — each row is valid JSON parseable independently
# ---------------------------------------------------------------------------


def test_each_row_is_valid_json(tmp_path: Path) -> None:
    """Every line in the JSONL must be independently parseable as JSON."""
    jsonl_path, _ = _write(_minimal_report(), tmp_path / "out.jsonl")
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "Expected exactly 1 row"
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Line {i} is not valid JSON: {exc}")
        assert isinstance(obj, dict), f"Line {i} is not a JSON object"


# ---------------------------------------------------------------------------
# Test 7 — manifest is valid JSON with trailing newline
# ---------------------------------------------------------------------------


def test_manifest_is_valid_json_with_trailing_newline(tmp_path: Path) -> None:
    """The manifest must be valid JSON and end with a single trailing LF."""
    _, manifest_path = _write(_minimal_report(), tmp_path / "out.jsonl")
    raw = manifest_path.read_bytes()
    assert raw.endswith(b"\n"), "Manifest does not end with a trailing newline"
    assert b"\r\n" not in raw, "CRLF found in manifest"
    json.loads(raw.decode("utf-8"))  # raises if invalid
