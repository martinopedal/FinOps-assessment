"""Drift gate tests for PowerShell full-document HTML conformance golden."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_html_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_HTML = _FIXTURE_DIR / "demo-report.html"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_html_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_golden_is_committed() -> None:
    assert _HTML.is_file(), "run scripts/generate_ps_html_fixtures.py"


def test_html_golden_matches_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_html_fixtures.py` and commit."
        )


def test_html_golden_uses_lf_only() -> None:
    assert b"\r\n" not in _HTML.read_bytes(), "fixture must use LF newlines"


def test_html_golden_is_non_vacuous() -> None:
    payload = _HTML.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in payload
    assert "<h2>Microsoft 365</h2>" in payload
    assert "<h2>Azure</h2>" in payload
    assert "<h2>GitHub</h2>" in payload
    assert "<h2>Azure DevOps</h2>" in payload
    assert '<section class="practice-review">' in payload
