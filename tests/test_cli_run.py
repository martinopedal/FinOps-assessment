"""End-to-end CLI smoke test for `finops-assess run` and `catalog refresh`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_run_emits_csv_via_format_flag(tmp_path: Path) -> None:
    csv_path = tmp_path / "findings.csv"
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--input",
            str(SAMPLES),
            "--format",
            "csv",
            "--csv-output",
            str(csv_path),
            "--no-pii-redaction",
        ],
    )
    assert result.exit_code == 0, result.output
    text = csv_path.read_text(encoding="utf-8")
    header, *rows = text.splitlines()
    assert header.startswith("rule_id,surface,severity,confidence,principal,")
    assert len(rows) >= 12  # mirrors the JSON-mode floor in test_run_against_samples


def test_run_format_all_emits_every_format(tmp_path: Path) -> None:
    pytest.importorskip("weasyprint")  # --format all includes PDF
    base = tmp_path / "report.json"
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--input",
            str(SAMPLES),
            "--output",
            str(base),
            "--format",
            "all",
            "--no-pii-redaction",
        ],
    )
    assert result.exit_code == 0, result.output
    assert base.exists()
    assert base.with_suffix(".html").exists()
    assert base.with_suffix(".csv").exists()
    assert base.with_suffix(".pdf").exists()


def test_run_format_csv_requires_output_path() -> None:
    result = CliRunner().invoke(
        main,
        ["run", "--input", str(SAMPLES), "--format", "csv"],
    )
    assert result.exit_code != 0
    assert "--csv-output" in result.output


def test_run_with_pii_salt_file_produces_stable_hashes() -> None:
    """Two runs with the same salt file produce identical principal hashes."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        tmp_path = Path(td)
        salt_file = tmp_path / "salt.txt"
        salt_file.write_text("test-tenant-stable-salt-abcd1234", encoding="utf-8")

        # Run 1
        out1 = tmp_path / "out1.json"
        result1 = runner.invoke(
            main,
            [
                "run",
                "--input",
                str(SAMPLES),
                "--output",
                str(out1),
                "--pii-salt-file",
                str(salt_file),
            ],
        )
        assert result1.exit_code == 0, result1.output
        report1 = json.loads(out1.read_text(encoding="utf-8"))

        # Run 2 with the SAME salt file
        out2 = tmp_path / "out2.json"
        result2 = runner.invoke(
            main,
            [
                "run",
                "--input",
                str(SAMPLES),
                "--output",
                str(out2),
                "--pii-salt-file",
                str(salt_file),
            ],
        )
        assert result2.exit_code == 0, result2.output
        report2 = json.loads(out2.read_text(encoding="utf-8"))

        # Extract principals from both runs
        principals1 = {f["principal"] for f in report1["findings"] if f.get("principal")}
        principals2 = {f["principal"] for f in report2["findings"] if f.get("principal")}

        # Principals should be identical
        assert principals1 == principals2, "Principals should be stable with same salt file"

        # Verify salt_mode is reported correctly
        assert report1["run"]["salt_mode"] == "tenant_stable"
        assert report2["run"]["salt_mode"] == "tenant_stable"


def test_run_with_pii_salt_env_produces_stable_hashes() -> None:
    """Two runs with the same FINOPS_PII_SALT env var produce identical principal hashes."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        tmp_path = Path(td)
        out1 = tmp_path / "out1.json"
        result1 = runner.invoke(
            main,
            ["run", "--input", str(SAMPLES), "--output", str(out1)],
            env={"FINOPS_PII_SALT": "env-salt-12345678"},
        )
        assert result1.exit_code == 0, result1.output
        report1 = json.loads(out1.read_text(encoding="utf-8"))

        # Run 2 with the SAME env var
        out2 = tmp_path / "out2.json"
        result2 = runner.invoke(
            main,
            ["run", "--input", str(SAMPLES), "--output", str(out2)],
            env={"FINOPS_PII_SALT": "env-salt-12345678"},
        )
        assert result2.exit_code == 0, result2.output
        report2 = json.loads(out2.read_text(encoding="utf-8"))

        # Extract principals from both runs
        principals1 = {f["principal"] for f in report1["findings"] if f.get("principal")}
        principals2 = {f["principal"] for f in report2["findings"] if f.get("principal")}

        # Principals should be identical
        assert principals1 == principals2, "Principals should be stable with same env salt"

        # Verify salt_mode is reported correctly
        assert report1["run"]["salt_mode"] == "tenant_stable"
        assert report2["run"]["salt_mode"] == "tenant_stable"


def test_run_salt_file_not_found_error() -> None:
    """Missing salt file raises a clear error."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        tmp_path = Path(td)
        missing = tmp_path / "nosuch.txt"
        out = tmp_path / "out.json"

        result = runner.invoke(
            main,
            ["run", "--input", str(SAMPLES), "--output", str(out), "--pii-salt-file", str(missing)],
        )
        assert result.exit_code != 0
        assert "Salt file not found" in result.output
