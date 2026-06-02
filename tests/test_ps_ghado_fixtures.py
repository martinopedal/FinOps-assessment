"""Drift gate + self-check tests for the PowerShell GitHub + ADO conformance goldens.

Phase-4 conformance (docs/plan.md §5a / §6):

* **Layer 5** (canonical artifact equality, *with findings*): the
  committed ``demo-report-github.canonical.json`` and
  ``demo-report-ado.canonical.json`` are the ``report-github-v1`` and
  ``report-ado-v1`` projections of a real Python report; the PowerShell
  engine's report, pushed through the *same*
  ``scripts/canonicalize_report.py`` profile, must match byte-for-byte
  (asserted from the Pester suite).
* **CSV reporter**: ``demo-report-github.csv`` and ``demo-report-ado.csv``
  are the Python ``csv_reporter`` output over the surface findings in
  natural report order; the hand-rolled PowerShell CSV writer must match
  byte-for-byte.

This test regenerates all four goldens in memory and fails on drift, so a
PR that changes the GitHub/ADO rules, the CSV reporter, the canonicaliser,
or the demo data must run ``python scripts/generate_ps_ghado_fixtures.py``
and commit the result.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_ghado_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_GH_JSON = _FIXTURE_DIR / "demo-report-github.canonical.json"
_GH_CSV = _FIXTURE_DIR / "demo-report-github.csv"
_ADO_JSON = _FIXTURE_DIR / "demo-report-ado.canonical.json"
_ADO_CSV = _FIXTURE_DIR / "demo-report-ado.csv"

_GH_RULE_IDS = {
    "GH.INACTIVE_SEAT_90D",
    "GH.COPILOT_INACTIVE_30D",
    "GH.GHAS_OVER_PROVISIONED",
    "GH.RUNNER_TIER_MISMATCH",
}
_ADO_RULE_IDS = {
    "ADO.INACTIVE_BASIC_90D",
    "ADO.STAKEHOLDER_ELIGIBLE",
    "ADO.PARALLEL_JOBS_OVER_PROVISIONED",
    "ADO.TEST_PLANS_UNUSED",
}


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_ghado_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ghado_goldens_are_committed() -> None:
    assert _GH_JSON.is_file(), "run scripts/generate_ps_ghado_fixtures.py"
    assert _GH_CSV.is_file(), "run scripts/generate_ps_ghado_fixtures.py"
    assert _ADO_JSON.is_file(), "run scripts/generate_ps_ghado_fixtures.py"
    assert _ADO_CSV.is_file(), "run scripts/generate_ps_ghado_fixtures.py"


def test_ghado_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_ghado_fixtures.py` and commit."
        )


def test_ghado_goldens_use_lf_only() -> None:
    for path in (_GH_JSON, _GH_CSV, _ADO_JSON, _ADO_CSV):
        assert b"\r\n" not in path.read_bytes(), f"{path.name} must use LF newlines"


def test_github_golden_exercises_every_rule() -> None:
    """The demo tenant must trigger all four GitHub rules (non-vacuous slice)."""
    payload = json.loads(_GH_JSON.read_text(encoding="utf-8"))
    counts = payload["summary"]["rule_counts"]
    assert set(counts) == _GH_RULE_IDS, "every GH rule must be present in rule_counts"
    for rule_id in _GH_RULE_IDS:
        assert counts[rule_id] >= 1, f"{rule_id} produced no findings in the demo tenant"


def test_ado_golden_exercises_every_rule() -> None:
    """The demo tenant must trigger all four ADO rules (non-vacuous slice)."""
    payload = json.loads(_ADO_JSON.read_text(encoding="utf-8"))
    counts = payload["summary"]["rule_counts"]
    assert set(counts) == _ADO_RULE_IDS, "every ADO rule must be present in rule_counts"
    for rule_id in _ADO_RULE_IDS:
        assert counts[rule_id] >= 1, f"{rule_id} produced no findings in the demo tenant"


def test_github_golden_is_tenant_stable_and_redacted() -> None:
    payload = json.loads(_GH_JSON.read_text(encoding="utf-8"))
    assert payload["run"]["salt_mode"] == "tenant_stable"
    assert payload["run"]["pii_redaction"] is True
    for finding in payload["findings"]:
        assert finding["principal"].startswith("sha256:"), "principals must be salted-hashed"
        assert finding["surface"] == "github"


def test_ado_golden_is_tenant_stable_and_redacted() -> None:
    payload = json.loads(_ADO_JSON.read_text(encoding="utf-8"))
    assert payload["run"]["salt_mode"] == "tenant_stable"
    assert payload["run"]["pii_redaction"] is True
    for finding in payload["findings"]:
        assert finding["principal"].startswith("sha256:"), "principals must be salted-hashed"
        assert finding["surface"] == "ado"


def test_money_is_float_typed() -> None:
    for path in (_GH_JSON, _ADO_JSON):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for finding in payload["findings"]:
            savings = finding["estimated_monthly_savings_usd"]
            if savings is not None:
                assert isinstance(savings, float), (
                    f"{path.name}: savings must canonicalise as float, not int"
                )


def _canon() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import canonicalize_report

    return canonicalize_report


def test_github_profile_rejects_missing_rule_count() -> None:
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"].pop("GH.INACTIVE_SEAT_90D", None)
    with pytest.raises(ValueError, match="missing GH"):
        canon.canonicalize(broken, "report-github-v1")  # type: ignore[attr-defined]


def test_ado_profile_rejects_missing_rule_count() -> None:
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"].pop("ADO.INACTIVE_BASIC_90D", None)
    with pytest.raises(ValueError, match="missing ADO"):
        canon.canonicalize(broken, "report-ado-v1")  # type: ignore[attr-defined]


def test_github_profile_rejects_non_github_surface() -> None:
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    for finding in broken["findings"]:
        if str(finding.get("rule_id", "")).startswith("GH."):
            finding["surface"] = "m365"
            break
    with pytest.raises(ValueError, match="non-github surface"):
        canon.canonicalize(broken, "report-github-v1")  # type: ignore[attr-defined]


def test_ado_profile_rejects_non_ado_surface() -> None:
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    for finding in broken["findings"]:
        if str(finding.get("rule_id", "")).startswith("ADO."):
            finding["surface"] = "azure"
            break
    with pytest.raises(ValueError, match="non-ado surface"):
        canon.canonicalize(broken, "report-ado-v1")  # type: ignore[attr-defined]
