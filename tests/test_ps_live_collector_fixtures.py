"""Drift gate tests for PowerShell live collector fixtures (graph + arm + github + ado slices)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_live_collector_fixtures.py"
_GRAPH_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "graph"
_GRAPH_INPUT_DIR = _GRAPH_FIXTURE_DIR / "_input"
_ARM_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "arm"
_ARM_INPUT_DIR = _ARM_FIXTURE_DIR / "_input"
_GITHUB_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "github"
_GITHUB_INPUT_DIR = _GITHUB_FIXTURE_DIR / "_input"
_ADO_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "ado"
_ADO_INPUT_DIR = _ADO_FIXTURE_DIR / "_input"


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_live_collector_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_collector_fixtures_are_committed() -> None:
    assert (_GRAPH_FIXTURE_DIR / "users.csv").is_file()
    assert (_GRAPH_FIXTURE_DIR / "license_assignments.csv").is_file()
    assert (_GRAPH_FIXTURE_DIR / "usage.csv").is_file()

    assert (_ARM_FIXTURE_DIR / "azure_resources.csv").is_file()
    assert (_ARM_FIXTURE_DIR / "azure_reservations.csv").is_file()
    assert (_ARM_FIXTURE_DIR / "azure_log_workspaces.csv").is_file()
    assert (_ARM_FIXTURE_DIR / "azure_benefit_recommendations.csv").is_file()
    assert (_GITHUB_FIXTURE_DIR / "github_seats.csv").is_file()
    assert (_GITHUB_FIXTURE_DIR / "github_orgs.csv").is_file()
    assert (_ADO_FIXTURE_DIR / "ado_seats.csv").is_file()
    assert (_ADO_FIXTURE_DIR / "ado_orgs.csv").is_file()


def test_live_collector_fixtures_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, content in expected.items():
        assert path.read_bytes() == content.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_live_collector_fixtures.py` and commit."
        )


def test_live_collector_input_json_is_valid() -> None:
    users_payload = json.loads((_GRAPH_INPUT_DIR / "users.json").read_text(encoding="utf-8"))
    assert isinstance(users_payload, dict)
    assert "value" in users_payload

    subscriptions_payload = json.loads(
        (_ARM_INPUT_DIR / "subscriptions.json").read_text(encoding="utf-8")
    )
    assert isinstance(subscriptions_payload, dict)
    assert "value" in subscriptions_payload

    consumed_payload = json.loads(
        (_GITHUB_INPUT_DIR / "consumed_licenses.json").read_text(encoding="utf-8")
    )
    assert isinstance(consumed_payload, list)

    copilot_payload = json.loads(
        (_GITHUB_INPUT_DIR / "copilot_seats.json").read_text(encoding="utf-8")
    )
    assert isinstance(copilot_payload, dict)
    assert "seats" in copilot_payload

    userentitlements_payload = json.loads(
        (_ADO_INPUT_DIR / "userentitlements.json").read_text(encoding="utf-8")
    )
    assert isinstance(userentitlements_payload, dict)
    assert "page_1" in userentitlements_payload
    assert "page_2" in userentitlements_payload

    projects_payload = json.loads((_ADO_INPUT_DIR / "projects.json").read_text(encoding="utf-8"))
    assert isinstance(projects_payload, dict)
    assert "value" in projects_payload


def test_live_collector_fixtures_use_lf_only() -> None:
    fixtures = (
        _GRAPH_FIXTURE_DIR / "users.csv",
        _GRAPH_FIXTURE_DIR / "license_assignments.csv",
        _GRAPH_FIXTURE_DIR / "usage.csv",
        _ARM_FIXTURE_DIR / "azure_resources.csv",
        _ARM_FIXTURE_DIR / "azure_reservations.csv",
        _ARM_FIXTURE_DIR / "azure_log_workspaces.csv",
        _ARM_FIXTURE_DIR / "azure_benefit_recommendations.csv",
        _GITHUB_FIXTURE_DIR / "github_seats.csv",
        _GITHUB_FIXTURE_DIR / "github_orgs.csv",
        _ADO_FIXTURE_DIR / "ado_seats.csv",
        _ADO_FIXTURE_DIR / "ado_orgs.csv",
    )
    for fixture in fixtures:
        assert b"\r\n" not in fixture.read_bytes()
