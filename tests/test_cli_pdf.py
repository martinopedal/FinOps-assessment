"""End-to-end CLI tests for the M7 PDF reporter."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from finops_assess.cli import main

# The CLI tests exercise the full WeasyPrint render path; skip the file
# entirely if the optional 'pdf' extra is not installed.
pytest.importorskip("weasyprint")


def test_run_pdf_format_writes_pdf(tmp_path: Path) -> None:
    samples = Path(__file__).resolve().parents[1] / "samples"
    out_pdf = tmp_path / "report.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(samples),
            "--format",
            "pdf",
            "--pdf-output",
            str(out_pdf),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_pdf.exists()
    assert out_pdf.read_bytes().startswith(b"%PDF-")


def test_run_format_all_writes_three_reports(tmp_path: Path) -> None:
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
            "all",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_json.exists()
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "report.pdf").exists()
    assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF-")


def test_run_pdf_format_requires_pdf_output(tmp_path: Path) -> None:
    samples = Path(__file__).resolve().parents[1] / "samples"
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--input", str(samples), "--format", "pdf"])
    assert result.exit_code != 0
    assert "pdf-output" in result.output.lower() or "pdf_output" in result.output.lower()


def test_run_pdf_with_branding(tmp_path: Path) -> None:
    samples = Path(__file__).resolve().parents[1] / "samples"
    out_pdf = tmp_path / "branded.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(samples),
            "--format",
            "pdf",
            "--pdf-output",
            str(out_pdf),
            "--branding-name",
            "Contoso",
            "--branding-color",
            "#cf222e",
            "--branding-page-size",
            "A4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_pdf.read_bytes().startswith(b"%PDF-")


def test_run_pdf_branding_color_is_validated(tmp_path: Path) -> None:
    samples = Path(__file__).resolve().parents[1] / "samples"
    out_pdf = tmp_path / "branded.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(samples),
            "--format",
            "pdf",
            "--pdf-output",
            str(out_pdf),
            "--branding-color",
            "not-a-hex-literal",
        ],
    )
    assert result.exit_code != 0


def test_demo_pdf_flag_writes_pdf(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo-report"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "--output-dir", str(out_dir), "--pdf"])
    assert result.exit_code == 0, result.output
    pdf_path = out_dir / "demo-report.pdf"
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    assert pdf_path.read_bytes().startswith(b"%PDF-")


def test_demo_without_pdf_flag_does_not_write_pdf(tmp_path: Path) -> None:
    """Default `demo` must work without the 'pdf' extra installed."""
    out_dir = tmp_path / "demo-report"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert not (out_dir / "demo-report.pdf").exists()
