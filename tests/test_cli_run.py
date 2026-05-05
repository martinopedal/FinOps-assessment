"""End-to-end CLI smoke test for `finops-assess run` and `catalog refresh`."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from finops_assess.cli import main

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_run_against_samples_emits_findings(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main,
        ["run", "--input", str(SAMPLES), "--output", str(output), "--no-pii-redaction"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run"]["mode"] == "read-only"
    assert payload["run"]["pii_redaction"] is False
    assert payload["summary"]["total_findings"] >= 12
    fired = [rid for rid, n in payload["summary"]["rule_counts"].items() if n > 0]
    assert len(fired) >= 10


def test_run_default_redaction_hashes_principals(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main,
        ["run", "--input", str(SAMPLES), "--output", str(output)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    for finding in payload["findings"]:
        if finding["surface"] == "azure":
            continue
        assert "@" not in finding["principal"]


def test_catalog_refresh_against_local_fixture(tmp_path: Path) -> None:
    csv_path = FIXTURES / "ms_skus_minimal.csv"
    result = CliRunner().invoke(main, ["catalog", "refresh", "--source", str(csv_path)])
    assert result.exit_code == 0, result.output
    assert "Upstream SKUs:" in result.output
    assert "coverage:" in result.output


def test_catalog_coverage_exits_nonzero_on_gap() -> None:
    csv_path = FIXTURES / "ms_skus_with_gap.csv"
    result = CliRunner().invoke(main, ["catalog", "coverage", "--source", str(csv_path)])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    ids = {entry["id"] for entry in payload["missing"]}
    assert "TOTALLY_NEW_SKU_2099" in ids
