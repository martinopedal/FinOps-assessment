"""Drift gate tests for PowerShell FOCUS conformance goldens."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_ps_focus_fixtures.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
_FOCUS_CSV = _FIXTURE_DIR / "demo-focus.csv"
_FOCUS_MANIFEST = _FIXTURE_DIR / "demo-focus.csv.manifest.json"
_HEADER = (
    "ServiceProviderName,HostProviderName,ServiceName,ServiceCategory,ServiceSubcategory,"
    "ChargeCategory,ChargeClass,ChargeFrequency,ChargeDescription,SkuId,ResourceId,"
    "ResourceType,BillingPeriodStart,BillingPeriodEnd,PricingCurrency,ListCost,"
    "ContractedCost,BilledCost,EffectiveCost,EstimatedMonthlySavingsUsd,"
    "AdvisoryFindingKey,RuleId,Severity"
)


def _load_generator() -> object:
    if str(_REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("generate_ps_focus_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_focus_goldens_are_committed() -> None:
    assert _FOCUS_CSV.is_file(), "run scripts/generate_ps_focus_fixtures.py"
    assert _FOCUS_MANIFEST.is_file(), "run scripts/generate_ps_focus_fixtures.py"


def test_focus_goldens_match_regenerated_bytes() -> None:
    generator = _load_generator()
    expected = generator.regenerate()  # type: ignore[attr-defined]
    for path, contents in expected.items():
        assert path.read_bytes() == contents.encode("utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} is stale; run "
            "`python scripts/generate_ps_focus_fixtures.py` and commit."
        )


def test_focus_goldens_use_lf_only() -> None:
    assert b"\r\n" not in _FOCUS_CSV.read_bytes(), "fixture must use LF newlines"
    assert b"\r\n" not in _FOCUS_MANIFEST.read_bytes(), "fixture must use LF newlines"


def test_focus_golden_is_non_vacuous() -> None:
    csv_lines = _FOCUS_CSV.read_text(encoding="utf-8").splitlines()
    assert csv_lines[0] == _HEADER
    payload = json.loads(_FOCUS_MANIFEST.read_text(encoding="utf-8"))
    assert payload["row_count"] == len(csv_lines) - 1
