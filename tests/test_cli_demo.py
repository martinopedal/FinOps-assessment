"""End-to-end test for `finops-assess demo`."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from finops_assess.cli import main


def test_demo_command_writes_json_and_html(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo-report"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output

    json_path = out_dir / "demo-report.json"
    html_path = out_dir / "demo-report.html"
    assert json_path.exists() and json_path.stat().st_size > 0
    assert html_path.exists() and html_path.stat().st_size > 0

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run"]["pii_redaction"] is True
    assert payload["run"]["mode"] == "read-only"
    # 12 rules fire on the synthetic tenant per the M2 PR description.
    rule_counts = payload["summary"]["rule_counts"]
    fired = sum(1 for v in rule_counts.values() if v)
    assert fired >= 10, f"expected >=10 rules to fire on the demo tenant, got {fired}"

    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "FinOps assessment report" in html


def test_run_command_supports_html_format(tmp_path: Path) -> None:
    """`finops-assess run --format both` writes both reports next to --output."""
    samples = Path(__file__).resolve().parents[1] / "samples"
    out_json = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(samples),
            "--output",
            str(out_json),
            "--format",
            "both",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_json.exists()
    assert (tmp_path / "report.html").exists()


def test_run_html_only_requires_html_output(tmp_path: Path) -> None:
    samples = Path(__file__).resolve().parents[1] / "samples"
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--input", str(samples), "--format", "html"])
    assert result.exit_code != 0
    assert "html-output" in result.output.lower() or "html_output" in result.output.lower()


def test_demo_without_pdf_flag_does_not_write_pdf(tmp_path: Path) -> None:
    """Default `demo` must work without the 'pdf' extra installed.

    Lives here (not in test_cli_pdf.py) because that module is skipped
    wholesale when WeasyPrint is missing — exactly the environment we
    most need to assert the no-PDF default behaviour in.
    """
    out_dir = tmp_path / "demo-report"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert (out_dir / "demo-report.json").exists()
    assert (out_dir / "demo-report.html").exists()
    assert not (out_dir / "demo-report.pdf").exists()
