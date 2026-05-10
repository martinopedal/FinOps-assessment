"""Tests for the docs/example-report regeneration script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_docs.py"


def _load_script_module():
    """Import ``scripts/generate_docs.py`` as a module for direct calls."""
    spec = importlib.util.spec_from_file_location("generate_docs", SCRIPT_PATH)
    assert spec and spec.loader, "could not load scripts/generate_docs.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_rules_markdown_lists_every_rule() -> None:
    """The auto-generated rules reference must mention every YAML rule id."""
    from finops_assess.rules import load_rules

    module = _load_script_module()
    md = module.render_rules_markdown()

    assert md.startswith("# Rule reference")
    assert "auto-generated" in md
    for rule in load_rules():
        assert f"`{rule.id}`" in md, f"rule {rule.id} missing from generated docs/rules.md"


def test_regenerate_examples_is_deterministic(tmp_path: Path) -> None:
    """Two runs of the script must produce byte-identical example reports."""
    module = _load_script_module()

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    module.regenerate_examples(out_a)
    module.regenerate_examples(out_b)

    for name in (
        "demo-report.json",
        "demo-report.html",
        "demo-report.csv",
        "demo-triage.json",
        "demo-triage.csv",
    ):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), (
            f"{name} differs between two regenerations — determinism is broken"
        )


def test_example_report_uses_source_date_epoch(tmp_path: Path) -> None:
    """SOURCE_DATE_EPOCH=0 must surface as a 1970-01-01 generated_at value."""
    module = _load_script_module()
    module.regenerate_examples(tmp_path)
    payload = json.loads((tmp_path / "demo-report.json").read_text(encoding="utf-8"))
    assert payload["run"]["generated_at"].startswith("1970-01-01T00:00:00")


def test_check_mode_passes_for_committed_artifacts() -> None:
    """The committed examples/ + docs/rules.md must match what the script generates."""
    module = _load_script_module()
    rc = module.main(["--check"])
    assert rc == 0, (
        "Committed docs/rules.md or examples/ are stale. "
        "Run `python scripts/generate_docs.py` and commit the result."
    )


def test_json_reporter_honours_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`build_report` must read SOURCE_DATE_EPOCH for `run.generated_at`."""
    from finops_assess.reporters.json_reporter import build_report

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")  # 2023-11-14T22:13:20Z
    report = build_report(
        findings=[],
        summary={
            "rule_counts": {},
            "rules_skipped_no_impl": [],
            "total_findings": 0,
            "principals_evaluated": 0,
            "assignments_evaluated": 0,
            "azure_resources_evaluated": 0,
        },
        persona_assignments={},
        input_path=tmp_path / "anywhere",
        redact_pii=True,
    )
    assert report["run"]["generated_at"] == "2023-11-14T22:13:20+00:00"


def test_json_reporter_falls_back_when_source_date_epoch_malformed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A malformed env var must not break the run; we fall back to wall-clock."""
    from finops_assess.reporters.json_reporter import build_report

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-number")
    report = build_report(
        findings=[],
        summary={
            "rule_counts": {},
            "rules_skipped_no_impl": [],
            "total_findings": 0,
            "principals_evaluated": 0,
            "assignments_evaluated": 0,
            "azure_resources_evaluated": 0,
        },
        persona_assignments={},
        input_path=tmp_path / "anywhere",
        redact_pii=True,
    )
    # Should be a valid ISO-8601 UTC timestamp, not "not-a-number".
    assert report["run"]["generated_at"].endswith("+00:00")
    assert "1970" not in report["run"]["generated_at"]
