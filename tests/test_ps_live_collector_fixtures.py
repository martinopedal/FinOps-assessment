"""Drift gate tests for PowerShell live collector fixtures (graph slice)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_live_collector_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "graph"
_INPUT_DIR = _FIXTURE_DIR / "_input"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_live_collector_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_graph_live_collector_fixtures_are_committed() -> None:
    assert (_FIXTURE_DIR / "users.csv").is_file()
    assert (_FIXTURE_DIR / "license_assignments.csv").is_file()
    assert (_FIXTURE_DIR / "usage.csv").is_file()


def test_graph_live_collector_fixtures_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, content in expected.items():
        assert path.read_bytes() == content.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_live_collector_fixtures.py` and commit."
        )


def test_graph_live_collector_input_json_is_valid() -> None:
    users_payload = json.loads((_INPUT_DIR / "users.json").read_text(encoding="utf-8"))
    assert isinstance(users_payload, dict)
    assert "value" in users_payload


def test_graph_live_collector_fixtures_use_lf_only() -> None:
    for fixture in ("users.csv", "license_assignments.csv", "usage.csv"):
        assert b"\r\n" not in (_FIXTURE_DIR / fixture).read_bytes()
