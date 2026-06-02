"""Drift gate for the PowerShell normalise-core conformance golden fixture.

The committed ``tests/fixtures/ps_conformance/demo-normalised.json`` is the
Python oracle for **layer-2** of the cross-engine conformance contract
(docs/plan.md §5a). The native PowerShell normaliser is deep-compared
against it in Pester. This test regenerates the fixture in memory and fails
on any drift, so a PR that changes the demo CSVs or the normalised models
must regenerate and commit the fixture
(``python scripts/generate_ps_conformance_fixtures.py``).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_conformance_fixtures.py"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance" / "demo-normalised.json"


def _load_generator() -> object:
    spec = importlib.util.spec_from_file_location("generate_ps_conformance_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conformance_fixture_is_committed() -> None:
    assert _FIXTURE.is_file(), "run scripts/generate_ps_conformance_fixtures.py"


def test_conformance_fixture_matches_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.build_golden()  # type: ignore[attr-defined]
    assert _FIXTURE.read_bytes() == expected.encode("utf-8"), (
        "tests/fixtures/ps_conformance/demo-normalised.json is stale; run "
        "`python scripts/generate_ps_conformance_fixtures.py` and commit."
    )


def test_conformance_fixture_uses_lf_only() -> None:
    assert b"\r\n" not in _FIXTURE.read_bytes(), "fixture must use LF newlines"


def test_check_mode_reports_clean() -> None:
    generator = _load_generator()
    assert generator.check_fixture() is False, (  # type: ignore[attr-defined]
        "check_fixture() reports drift against the committed fixture"
    )


def test_fixture_has_every_dataset_field() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    for field in (
        "users",
        "assignments",
        "usage",
        "m365_family_summaries",
        "azure_resources",
        "azure_reservations",
        "azure_log_workspaces",
        "azure_benefit_recommendations",
        "github_seats",
        "github_orgs",
        "ado_seats",
        "ado_orgs",
        "overrides",
    ):
        assert field in payload, f"golden fixture missing dataset field '{field}'"
