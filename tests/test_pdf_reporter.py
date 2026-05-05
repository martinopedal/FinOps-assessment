"""Tests for the PDF reporter (M7).

The HTML-builder layer (``build_pdf_html``) is exercised on every
matrix cell — it has no WeasyPrint dependency. The full PDF render
path is only run when the optional ``[pdf]`` extra is installed.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from finops_assess.reporters.pdf_reporter import (
    Branding,
    _epoch_from_generated_at,
    build_pdf_html,
)


def _minimal_report(findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.0.1",
            "generated_at": "2026-05-05T00:00:00+00:00",
            "input": "<redacted>/samples",
            "pii_redaction": True,
            "mode": "read-only",
        },
        "summary": {
            "rule_counts": {"M365.UNUSED_LICENSE_30D": 1},
            "rules_skipped_no_impl": [],
            "persona_distribution": {"information_worker": 2, "frontline_worker": 1},
        },
        "findings": findings
        or [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "severity": "medium",
                "principal": "abc123",
                "current_sku": "SPE_E3",
                "recommended_sku": None,
                "estimated_monthly_savings_usd": 36.0,
                "recommendation": "Consider removing the unused E3 license.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"days_inactive": 45},
            }
        ],
    }


# --- HTML-builder layer (always runs) ---------------------------------------


def test_build_pdf_html_renders_minimal_report() -> None:
    html = build_pdf_html(_minimal_report())
    assert html.startswith("<!DOCTYPE html>")
    assert "FinOps assessment" in html
    assert "M365.UNUSED_LICENSE_30D" in html
    assert "SPE_E3" in html
    # Cover-page exec summary uses whole-dollar formatting.
    assert "$36" in html
    # Surface labels appear.
    assert "Microsoft 365" in html


def test_build_pdf_html_includes_cover_page_executive_summary() -> None:
    html = build_pdf_html(_minimal_report())
    # Cover labels.
    assert "Findings" in html
    assert "Rules fired" in html
    assert "Est. monthly savings" in html
    assert "Principals assessed" in html
    # Read-only callout from the cover page.
    assert "Read-only by construction" in html
    # @page rule + page numbers in the footer.
    assert "@page" in html
    assert "counter(page)" in html


def test_build_pdf_html_branding_name_and_color_render() -> None:
    branding = Branding.from_options(name="Contoso Ltd", accent_color="#cf222e")
    html = build_pdf_html(_minimal_report(), branding=branding)
    assert "Contoso Ltd" in html
    assert "#cf222e" in html
    # Default unbranded run has no name.
    html_default = build_pdf_html(_minimal_report())
    assert "Contoso Ltd" not in html_default


def test_build_pdf_html_xss_payload_in_recommendation_is_escaped() -> None:
    payload = "<script>alert('xss')</script>"
    report = _minimal_report(
        findings=[
            {
                "rule_id": "M365.X",
                "surface": "m365",
                "severity": "high",
                "principal": "<img src=x onerror=alert(1)>",
                "current_sku": "SPE_E3",
                "recommended_sku": "STANDARDPACK",
                "estimated_monthly_savings_usd": 12.0,
                "recommendation": payload,
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"note": "<b>raw</b>"},
            }
        ]
    )
    html = build_pdf_html(report)
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "<b>raw</b>" not in html


def test_branding_color_must_be_hex_literal() -> None:
    with pytest.raises(ValueError, match="accent_color"):
        Branding.from_options(accent_color="red; } body { background: red; } /*")
    with pytest.raises(ValueError, match="accent_color"):
        Branding.from_options(accent_color="#xyz")


def test_branding_direct_construction_also_validates() -> None:
    """Construction via ``Branding(...)`` must enforce the same validators.

    A reviewer flagged that `from_options` could be bypassed by calling
    the dataclass constructor directly with malicious values; the
    validators now run in ``__post_init__`` so neither path is unsafe.
    """
    with pytest.raises(ValueError, match="accent_color"):
        Branding(accent_color="red; } body{}")
    with pytest.raises(ValueError, match="page_size"):
        Branding(page_size="Tabloid")
    with pytest.raises(ValueError, match="logo_data_uri"):
        Branding(logo_data_uri="javascript:alert(1)")
    with pytest.raises(ValueError, match="logo_data_uri"):
        Branding(logo_data_uri="data:image/svg+xml;base64,PHN2Zy8+")


def test_branding_direct_construction_normalises_page_size() -> None:
    assert Branding(page_size="a4").page_size == "A4"


def test_branding_page_size_is_allow_listed() -> None:
    assert Branding.from_options(page_size="a4").page_size == "A4"
    with pytest.raises(ValueError, match="page_size"):
        Branding.from_options(page_size="Tabloid")


def test_branding_logo_rejects_unsupported_type(tmp_path: Path) -> None:
    bogus = tmp_path / "logo.svg"
    bogus.write_bytes(b"<svg/>")
    with pytest.raises(ValueError, match="unsupported type"):
        Branding.from_options(logo_path=bogus)


def test_branding_logo_rejects_oversized_file(tmp_path: Path) -> None:
    big = tmp_path / "logo.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024))
    with pytest.raises(ValueError, match="max is"):
        Branding.from_options(logo_path=big)


def test_branding_logo_rejects_extension_magic_byte_mismatch(tmp_path: Path) -> None:
    """A .png with JPEG magic bytes is a spoof attempt; reject it cleanly."""
    spoof = tmp_path / "logo.png"
    spoof.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-payload")
    with pytest.raises(ValueError, match="magic bytes"):
        Branding.from_options(logo_path=spoof)


def test_branding_logo_rejects_unrecognised_magic_bytes(tmp_path: Path) -> None:
    """A .png whose body is not actually a PNG should be rejected."""
    bad = tmp_path / "logo.png"
    bad.write_bytes(b"this is plain text, not a PNG")
    with pytest.raises(ValueError, match="magic-byte signature"):
        Branding.from_options(logo_path=bad)


def test_branding_logo_embeds_as_data_uri(tmp_path: Path) -> None:
    # A real PNG signature so the magic-byte check passes.
    raw = b"\x89PNG\r\n\x1a\nfake-payload"
    logo = tmp_path / "brand.png"
    logo.write_bytes(raw)
    branding = Branding.from_options(logo_path=logo)
    assert branding.logo_data_uri is not None
    assert branding.logo_data_uri.startswith("data:image/png;base64,")
    expected = base64.b64encode(raw).decode("ascii")
    assert expected in branding.logo_data_uri
    html = build_pdf_html(_minimal_report(), branding=branding)
    assert branding.logo_data_uri in html


def test_findings_grouped_by_surface_with_severity_order() -> None:
    findings = [
        {
            "rule_id": "AZ.IDLE_VM_14D",
            "surface": "azure",
            "severity": "low",
            "principal": "vm-1",
            "current_sku": None,
            "recommended_sku": None,
            "estimated_monthly_savings_usd": None,
            "recommendation": "Power off.",
            "evidence_ref": None,
            "confidence": "high",
            "evidence": {},
        },
        {
            "rule_id": "AZ.OVERSIZED_VM",
            "surface": "azure",
            "severity": "high",
            "principal": "vm-2",
            "current_sku": "Standard_D8s_v5",
            "recommended_sku": "Standard_D4s_v5",
            "estimated_monthly_savings_usd": 100.0,
            "recommendation": "Right-size.",
            "evidence_ref": None,
            "confidence": "high",
            "evidence": {},
        },
    ]
    html = build_pdf_html(_minimal_report(findings=findings))
    high_pos = html.find("AZ.OVERSIZED_VM")
    low_pos = html.find("AZ.IDLE_VM_14D")
    assert 0 < high_pos < low_pos
    assert html.count("No findings.") >= 1


def test_top_surfaces_aggregated_by_savings() -> None:
    findings = [
        {
            "rule_id": "AZ.X",
            "surface": "azure",
            "severity": "high",
            "principal": "p",
            "estimated_monthly_savings_usd": 100.0,
            "recommendation": "r",
            "current_sku": None,
            "recommended_sku": None,
            "evidence_ref": None,
            "confidence": "high",
            "evidence": {},
        },
        {
            "rule_id": "M365.X",
            "surface": "m365",
            "severity": "low",
            "principal": "p",
            "estimated_monthly_savings_usd": 5.0,
            "recommendation": "r",
            "current_sku": None,
            "recommended_sku": None,
            "evidence_ref": None,
            "confidence": "high",
            "evidence": {},
        },
    ]
    html = build_pdf_html(_minimal_report(findings=findings))
    azure_pos = html.find("Azure</strong>")
    m365_pos = html.find("Microsoft 365</strong>")
    # Azure should appear before M365 in the "top surfaces" pill list.
    assert 0 < azure_pos < m365_pos


def test_epoch_from_generated_at_handles_z_suffix() -> None:
    expected = _epoch_from_generated_at("2026-05-05T00:00:00+00:00")
    assert expected is not None
    # The Z suffix and explicit +00:00 must round-trip to the same epoch.
    assert _epoch_from_generated_at("2026-05-05T00:00:00Z") == expected
    assert _epoch_from_generated_at(None) is None
    assert _epoch_from_generated_at("not-a-date") is None


def test_pdf_report_missing_extra_raises_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When WeasyPrint is unavailable, the error names the extra to install."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "weasyprint":
            raise ImportError("not installed in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from finops_assess.reporters.pdf_reporter import build_pdf_report

    with pytest.raises(RuntimeError, match=r"finops-assess\[pdf\]"):
        build_pdf_report(_minimal_report())


def test_cli_pdf_missing_extra_renders_clickexception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI must surface the missing-extra error as a clean Click error.

    Without the wrapper this would be a Python traceback on stderr; with
    it the user sees a single ``Error: …`` line and a non-zero exit code.
    """
    import builtins

    from click.testing import CliRunner

    from finops_assess.cli import main

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "weasyprint":
            raise ImportError("not installed in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    samples = Path(__file__).resolve().parents[1] / "samples"
    out_pdf = tmp_path / "report.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--input", str(samples), "--format", "pdf", "--pdf-output", str(out_pdf)],
    )
    assert result.exit_code != 0
    # Click renders ClickException as "Error: <message>" — no traceback.
    assert "Traceback" not in result.output
    assert "finops-assess[pdf]" in result.output


# --- Full WeasyPrint render (skipped if extra not installed) ----------------

weasyprint = pytest.importorskip("weasyprint")


def test_pdf_render_starts_with_pdf_magic_bytes() -> None:
    from finops_assess.reporters.pdf_reporter import build_pdf_report

    pdf = build_pdf_report(_minimal_report())
    assert pdf.startswith(b"%PDF-")
    # WeasyPrint always closes with %%EOF (possibly with trailing newline).
    assert b"%%EOF" in pdf[-32:]


def test_pdf_render_is_deterministic() -> None:
    """Two renders of the same report payload must be byte-identical."""
    from finops_assess.reporters.pdf_reporter import build_pdf_report

    report = _minimal_report()
    pdf1 = build_pdf_report(report)
    pdf2 = build_pdf_report(report)
    assert pdf1 == pdf2, "PDF output must be deterministic for reproducible builds"


def test_pdf_render_with_branding_is_deterministic() -> None:
    from finops_assess.reporters.pdf_reporter import build_pdf_report

    branding = Branding.from_options(name="Acme", accent_color="#cf222e", page_size="A4")
    report = _minimal_report()
    pdf1 = build_pdf_report(report, branding=branding)
    pdf2 = build_pdf_report(report, branding=branding)
    assert pdf1 == pdf2


def test_write_pdf_report_writes_file(tmp_path: Path) -> None:
    from finops_assess.reporters.pdf_reporter import write_pdf_report

    out = tmp_path / "nested" / "report.pdf"
    payload = write_pdf_report(_minimal_report(), out)
    assert out.exists()
    assert out.read_bytes() == payload
    assert out.read_bytes().startswith(b"%PDF-")
