"""Drift gate + self-check tests for the PowerShell M365 conformance goldens.

Phase-2 conformance (docs/plan.md §5a / §6):

* **Layer 5** (canonical artifact equality, *with findings*): the
  committed ``demo-report-m365.canonical.json`` is the ``report-m365-v1``
  projection of a real Python report; the PowerShell engine's report,
  pushed through the *same* ``scripts/canonicalize_report.py`` profile,
  must match it byte-for-byte (asserted from the Pester suite).
* **CSV reporter**: ``demo-report-m365.csv`` is the Python
  ``csv_reporter`` output over the M365 findings in natural report
  order; the hand-rolled PowerShell CSV writer must match it
  byte-for-byte.

This test regenerates both goldens in memory and fails on drift, so a PR
that changes the M365 rules, the CSV reporter, the canonicaliser, or the
demo data must run ``python scripts/generate_ps_m365_fixtures.py`` and
commit the result. It also exercises the ``report-m365-v1`` self-checks
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
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_m365_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_M365_JSON = _FIXTURE_DIR / "demo-report-m365.canonical.json"
_M365_CSV = _FIXTURE_DIR / "demo-report-m365.csv"

_M365_RULE_IDS = {
    "M365.UNUSED_LICENSE_30D",
    "M365.OVER_LICENSED_VS_PERSONA",
    "M365.DUPLICATE_BUNDLE",
    "M365.DISABLED_USER_LICENSED",
    "M365.SHARED_MAILBOX_LICENSED",
    "M365.GUEST_PREMIUM_LICENSED",
    "M365.COPILOT_INACTIVE_60D",
    "M365.E5_FEATURES_UNUSED",
}


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_m365_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m365_goldens_are_committed() -> None:
    assert _M365_JSON.is_file(), "run scripts/generate_ps_m365_fixtures.py"
    assert _M365_CSV.is_file(), "run scripts/generate_ps_m365_fixtures.py"


def test_m365_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_m365_fixtures.py` and commit."
        )


def test_m365_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _M365_JSON.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _M365_CSV.read_bytes(), "fixture must use LF newlines"


def test_m365_golden_exercises_every_rule() -> None:
    """The demo tenant must trigger all eight M365 rules (non-vacuous slice)."""
    payload = json.loads(_M365_JSON.read_text(encoding="utf-8"))
    counts = payload["summary"]["rule_counts"]
    assert set(counts) == _M365_RULE_IDS, "every M365 rule must be present in rule_counts"
    for rule_id in _M365_RULE_IDS:
        assert counts[rule_id] >= 1, f"{rule_id} produced no findings in the demo tenant"


def test_m365_golden_is_tenant_stable_and_redacted() -> None:
    payload = json.loads(_M365_JSON.read_text(encoding="utf-8"))
    assert payload["run"]["salt_mode"] == "tenant_stable"
    assert payload["run"]["pii_redaction"] is True
    for finding in payload["findings"]:
        assert finding["principal"].startswith("sha256:"), "principals must be salted-hashed"
        assert finding["surface"] == "m365"


def test_money_is_float_typed() -> None:
    payload = json.loads(_M365_JSON.read_text(encoding="utf-8"))
    for finding in payload["findings"]:
        savings = finding["estimated_monthly_savings_usd"]
        if savings is not None:
            assert isinstance(savings, float), "savings must canonicalise as float, not int"


def _canon() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import canonicalize_report

    return canonicalize_report


def test_profile_rejects_missing_m365_rule_count() -> None:
    """A report whose rule_counts omits an M365 rule must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"].pop("M365.DUPLICATE_BUNDLE", None)
    with pytest.raises(ValueError, match="missing M365 rules"):
        canon.canonicalize(broken, "report-m365-v1")  # type: ignore[attr-defined]


def test_profile_rejects_count_mismatch() -> None:
    """A rule_count that disagrees with the projected findings must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    broken["summary"]["rule_counts"]["M365.DUPLICATE_BUNDLE"] += 5
    with pytest.raises(ValueError, match="findings projected"):
        canon.canonicalize(broken, "report-m365-v1")  # type: ignore[attr-defined]


def test_profile_rejects_non_m365_surface_on_m365_rule() -> None:
    """An M365 rule emitting a non-m365 surface must be rejected."""
    canon = _canon()
    generator = _load_generator()
    report = generator._build_demo_report()  # type: ignore[attr-defined]
    broken = copy.deepcopy(report)
    for finding in broken["findings"]:
        if str(finding.get("rule_id", "")).startswith("M365."):
            finding["surface"] = "azure"
            break
    with pytest.raises(ValueError, match="non-m365 surface"):
        canon.canonicalize(broken, "report-m365-v1")  # type: ignore[attr-defined]
