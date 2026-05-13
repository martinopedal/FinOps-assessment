"""Tests for manifest JSON Schema validation.

Every manifest emitted by write_playbook_export must validate against
``schemas/playbook_manifest.schema.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

from finops_assess.reporters.playbook import write_playbook_export


def _load_schema() -> dict[str, Any]:  # type: ignore[type-arg]
    """Load the playbook manifest JSON Schema from package data."""
    from importlib.resources import files

    schema_text = (
        files("finops_assess").joinpath("schemas").joinpath("playbook_manifest.schema.json")
    ).read_text(encoding="utf-8")
    return json.loads(schema_text)  # type: ignore[no-any-return]


def _load_row_schema() -> dict[str, Any]:  # type: ignore[type-arg]
    """Load the playbook row JSON Schema from package data."""
    from importlib.resources import files

    schema_text = (
        files("finops_assess").joinpath("schemas").joinpath("playbook_row.schema.json")
    ).read_text(encoding="utf-8")
    return json.loads(schema_text)  # type: ignore[no-any-return]


def _minimal_report(pii_redaction: bool = True) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Test 1 — manifest validates against the JSON Schema
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_manifest_validates_against_schema(tmp_path: Path) -> None:
    """The emitted manifest must validate against playbook_manifest.schema.json."""
    _, manifest_path = _write(_minimal_report(), tmp_path / "out.jsonl")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = _load_schema()
    jsonschema.validate(manifest, schema)


# ---------------------------------------------------------------------------
# Test 2 — every JSONL row validates against the row schema
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_rows_validate_against_schema(tmp_path: Path) -> None:
    """Every row in the emitted JSONL must validate against playbook_row.schema.json."""
    jsonl_path, _ = _write(_minimal_report(), tmp_path / "out.jsonl")
    schema = _load_row_schema()
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    for i, row in enumerate(rows):
        jsonschema.validate(row, schema), f"Row {i} failed schema validation"


# ---------------------------------------------------------------------------
# Test 3 — schema files are loadable from package data (importlib.resources)
# ---------------------------------------------------------------------------


def test_schema_files_loadable() -> None:
    """Both schema files must be loadable from package data."""
    manifest_schema = _load_schema()
    row_schema = _load_row_schema()
    assert manifest_schema["title"].startswith("Playbook export manifest")
    assert row_schema["title"].startswith("Playbook row")


# ---------------------------------------------------------------------------
# Test 4 — manifest required fields are present
# ---------------------------------------------------------------------------


def test_manifest_required_fields_present(tmp_path: Path) -> None:
    """The manifest must contain all required top-level fields."""
    _, manifest_path = _write(_minimal_report(), tmp_path / "out.jsonl")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    required = [
        "playbook_schema_version",
        "tool",
        "generated_at",
        "source_report",
        "row_count",
        "output_artifacts",
        "pii_handling",
        "surfaces",
        "sort_key",
        "templates_source",
    ]
    for field in required:
        assert field in manifest, f"Required manifest field '{field}' missing"


# ---------------------------------------------------------------------------
# Test 5 — schema version is "0.1"
# ---------------------------------------------------------------------------


def test_manifest_schema_version_is_01(tmp_path: Path) -> None:
    """The manifest playbook_schema_version must be '0.1' in v0.5.0."""
    _, manifest_path = _write(_minimal_report(), tmp_path / "out.jsonl")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["playbook_schema_version"] == "0.1"
