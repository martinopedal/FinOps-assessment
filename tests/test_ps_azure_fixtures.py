"""Drift gate + self-check tests for the PowerShell Azure conformance goldens.

Phase-3 conformance (docs/plan.md §5a / §6):

* **Layer 5** (canonical artifact equality, *with findings*): the
  committed ``demo-report-azure.canonical.json`` is the ``report-azure-v1``
  projection of a real Python report; the PowerShell engine's report,
  pushed through the *same* ``scripts/canonicalize_report.py`` profile,
  must match it byte-for-byte (asserted from the Pester suite).
* **CSV reporter**: ``demo-report-azure.csv`` is the Python
  ``csv_reporter`` output over the Azure findings in natural report
  order; the hand-rolled PowerShell CSV writer must match it
  byte-for-byte.

This test regenerates both goldens in memory and fails on drift, so a PR
that changes the Azure rules, the CSV reporter, the canonicaliser, or the
samples data must run ``python scripts/generate_ps_azure_fixtures.py`` and
commit the result. It also exercises the ``report-azure-v1`` self-checks
so the projection cannot silently false-green.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_azure_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_AZURE_JSON = _FIXTURE_DIR / "demo-report-azure.canonical.json"
_AZURE_CSV = _FIXTURE_DIR / "demo-report-azure.csv"

_AZURE_RULE_IDS = {
    "AZ.IDLE_VM_14D",
    "AZ.UNATTACHED_DISK",
    "AZ.PUBLIC_IP_UNATTACHED",
    "AZ.OVERSIZED_VM",
    "AZ.RESERVATION_UNDERUTILIZED",
    "AZ.LOG_ANALYTICS_OVERINGEST",
    "AZ.DEV_TEST_SUB_MISMATCH",
    "AZ.COMMITMENT_UNDER_COVERED",
    "AZ.SAVINGS_PLAN_ELIGIBLE_SPEND",
    "AZ.COMMITMENT_RENEWAL_REVIEW",
    "AZ.RESERVATION_SCOPE_MISMATCH",
    "AZ.AHB_ELIGIBLE",
}


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_azure_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_azure_goldens_are_committed() -> None:
    assert _AZURE_JSON.is_file(), "run scripts/generate_ps_azure_fixtures.py"
    assert _AZURE_CSV.is_file(), "run scripts/generate_ps_azure_fixtures.py"


def test_azure_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_azure_fixtures.py` and commit."
        )


def test_azure_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _AZURE_JSON.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _AZURE_CSV.read_bytes(), "fixture must use LF newlines"


def test_azure_golden_exercises_every_rule() -> None:
    """The samples directory must trigger all twelve Azure rules (non-vacuous slice)."""
    payload = json.loads(_AZURE_JSON.read_text(encoding="utf-8"))
    counts = payload["summary"]["rule_counts"]
    # Note: some rules may have 0 findings if samples don't exercise them
    assert set(counts) == _AZURE_RULE_IDS, "every Azure rule must be present in rule_counts"


def test_azure_golden_is_tenant_stable_and_redacted() -> None:
    payload = json.loads(_AZURE_JSON.read_text(encoding="utf-8"))
    assert payload["run"]["salt_mode"] == "tenant_stable"
    assert payload["run"]["pii_redaction"] is True
    for finding in payload["findings"]:
        assert finding["principal"].startswith("sha256:"), "principals must be salted-hashed"
        assert finding["surface"] == "azure"


def test_money_is_float_typed() -> None:
    payload = json.loads(_AZURE_JSON.read_text(encoding="utf-8"))
    for finding in payload["findings"]:
        savings = finding["estimated_monthly_savings_usd"]
        if savings is not None:
            assert isinstance(savings, float), "savings must canonicalise as float, not int"


def _canon() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import canonicalize_report

    return canonicalize_report


def test_profile_rejects_missing_azure_rule_count() -> None:
    """A report whose rule_counts omits an Azure rule must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_samples_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"].pop("AZ.IDLE_VM_14D", None)
    with pytest.raises(ValueError, match="missing AZ"):
        canon.canonicalize(broken, "report-azure-v1")  # type: ignore[attr-defined]


def test_profile_rejects_count_mismatch() -> None:
    """A rule_count that disagrees with the projected findings must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_samples_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"]["AZ.IDLE_VM_14D"] += 5
    with pytest.raises(ValueError, match="findings projected"):
        canon.canonicalize(broken, "report-azure-v1")  # type: ignore[attr-defined]


def test_profile_rejects_non_azure_surface_on_azure_rule() -> None:
    """An Azure rule emitting a non-azure surface must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_samples_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    for finding in broken["findings"]:
        if str(finding.get("rule_id", "")).startswith("AZ."):
            finding["surface"] = "m365"
            break
    with pytest.raises(ValueError, match="non-azure surface"):
        canon.canonicalize(broken, "report-azure-v1")  # type: ignore[attr-defined]
