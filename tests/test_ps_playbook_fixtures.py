"""Drift gate tests for PowerShell playbook conformance goldens."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_playbook_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_PLAYBOOK_JSONL = _FIXTURE_DIR / "demo-playbook.jsonl"
_PLAYBOOK_MANIFEST = _FIXTURE_DIR / "demo-playbook.jsonl.manifest.json"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_playbook_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_playbook_goldens_are_committed() -> None:
    assert _PLAYBOOK_JSONL.is_file(), "run scripts/generate_ps_playbook_fixtures.py"
    assert _PLAYBOOK_MANIFEST.is_file(), "run scripts/generate_ps_playbook_fixtures.py"


def test_playbook_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_playbook_fixtures.py` and commit."
        )


def test_playbook_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _PLAYBOOK_JSONL.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _PLAYBOOK_MANIFEST.read_bytes(), "fixture must use LF newlines"


def test_playbook_golden_manifest_summary_is_non_vacuous() -> None:
    manifest = json.loads(_PLAYBOOK_MANIFEST.read_text(encoding="utf-8"))
    rows = _PLAYBOOK_JSONL.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 40
    assert manifest["row_count"] == 40
    assert manifest["pii_handling"]["salt_mode"] == "tenant_stable"
    assert manifest["pii_handling"]["known_limitation"] is None
