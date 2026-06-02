"""Drift gate + schema validation for the PowerShell report conformance goldens.

Phase-1c conformance (docs/plan.md §5a):

* **Layer 4** (same JSON schema): every Python report validates against
  ``src/finops_assess/schemas/report.schema.json``; the PowerShell Pester
  suite validates its report against the same schema with ``Test-Json``.
* **Layer 5** (canonical artifact equality): the committed
  ``demo-report-structural.canonical.json`` is the ``report-structural-v1``
  projection of a real Python report; the PowerShell engine's report,
  pushed through the *same* ``scripts/canonicalize_report.py`` profile,
  must match it byte-for-byte.
* **Layer 2** (personas): ``demo-personas.json`` is the Python
  persona-assignment oracle the ported PowerShell persona engine is
  deep-compared against.

This test regenerates both goldens in memory and fails on drift, so a PR
that changes the report envelope, persona engine, or demo data must run
``python scripts/generate_ps_report_fixtures.py`` and commit the result.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_report_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_STRUCTURAL = _FIXTURE_DIR / "demo-report-structural.canonical.json"
_PERSONAS = _FIXTURE_DIR / "demo-personas.json"
_SCHEMA = _REPO_ROOT / "src" / "finops_assess" / "schemas" / "report.schema.json"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_report_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_goldens_are_committed() -> None:
    assert _STRUCTURAL.is_file(), "run scripts/generate_ps_report_fixtures.py"
    assert _PERSONAS.is_file(), "run scripts/generate_ps_report_fixtures.py"


def test_report_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_report_fixtures.py` and commit."
        )


def test_report_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _STRUCTURAL.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _PERSONAS.read_bytes(), "fixture must use LF newlines"


def test_structural_golden_masks_finding_contents() -> None:
    payload = json.loads(_STRUCTURAL.read_text(encoding="utf-8"))
    assert payload["findings"] == "<array:masked>", (
        "the structural profile must collapse findings to the fixed sentinel "
        "so a report with findings and one without project identically"
    )
    for masked in ("rule_counts", "rules_skipped_no_impl", "total_findings"):
        assert masked not in payload["summary"], (
            f"rule-dependent summary key '{masked}' must be masked in the structural projection"
        )


def test_real_python_report_validates_against_schema() -> None:
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=report, schema=schema)


def test_schema_rejects_a_broken_report() -> None:
    """The schema must be non-vacuous: a report missing run.mode is invalid."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    broken = {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "1970-01-01T00:00:00+00:00",
            "input": "<redacted>/demo",
            "pii_redaction": True,
            "salt_mode": "per_run",
        },
        "summary": {
            "principals_evaluated": 0,
            "assignments_evaluated": 0,
            "azure_resources_evaluated": 0,
            "salt_mode": "per_run",
            "persona_distribution": {},
        },
        "findings": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=broken, schema=schema)


def test_canonicaliser_rejects_non_array_findings() -> None:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import canonicalize_report

    bad = {"run": {}, "summary": {}, "findings": {"not": "an array"}}
    with pytest.raises(ValueError, match="findings must be a JSON array"):
        canonicalize_report.canonicalize(bad, "report-structural-v1")
