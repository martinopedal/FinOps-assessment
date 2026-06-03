"""Drift gate tests for PowerShell triage conformance goldens."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_triage_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_TRIAGE_JSON = _FIXTURE_DIR / "demo-triage.json"
_TRIAGE_CSV = _FIXTURE_DIR / "demo-triage.csv"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_triage_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_triage_goldens_are_committed() -> None:
    assert _TRIAGE_JSON.is_file(), "run scripts/generate_ps_triage_fixtures.py"
    assert _TRIAGE_CSV.is_file(), "run scripts/generate_ps_triage_fixtures.py"


def test_triage_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_triage_fixtures.py` and commit."
        )


def test_triage_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _TRIAGE_JSON.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _TRIAGE_CSV.read_bytes(), "fixture must use LF newlines"


def test_triage_golden_summary_is_non_vacuous() -> None:
    payload = json.loads(_TRIAGE_JSON.read_text(encoding="utf-8"))
    assert payload["run"]["mode"] == "advisory"
    assert payload["summary"]["total_items"] == len(payload["items"])
    assert payload["source"]["report_path"] == "<redacted>/demo-report.json"
    assert sum(payload["summary"]["priority_counts"].values()) == payload["summary"]["total_items"]
