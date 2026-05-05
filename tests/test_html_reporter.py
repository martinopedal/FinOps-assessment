"""Tests for the HTML reporter — autoescape, surface grouping, no remote assets."""

from __future__ import annotations

import re
from typing import Any

import pytest

from finops_assess.reporters.html_reporter import build_html_report


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


def test_renders_minimal_report_to_html() -> None:
    html = build_html_report(_minimal_report())
    assert html.startswith("<!DOCTYPE html>")
    assert "FinOps assessment report" in html
    assert "M365.UNUSED_LICENSE_30D" in html
    assert "SPE_E3" in html
    assert "$36.00" in html  # appears in both the findings table and the savings card
    # Surface label appears
    assert "Microsoft 365" in html


def test_no_remote_assets_in_html() -> None:
    """Self-contained file: no external CSS / JS / font / image references."""
    html = build_html_report(_minimal_report())
    # The footer link to the project repo is the only http(s) reference allowed.
    forbidden_patterns = [
        re.compile(r"<link[^>]+href=[\"']https?://", re.IGNORECASE),
        re.compile(r"<script[^>]+src=[\"']https?://", re.IGNORECASE),
        re.compile(r"<img[^>]+src=[\"']https?://", re.IGNORECASE),
        re.compile(r"@import\s+[\"']?https?://", re.IGNORECASE),
        re.compile(r"url\(\s*[\"']?https?://", re.IGNORECASE),
    ]
    for pat in forbidden_patterns:
        assert pat.search(html) is None, f"remote asset reference found: {pat.pattern}"


def test_xss_payload_in_recommendation_is_escaped() -> None:
    """Operator-controlled fields must not render as live HTML."""
    payload = "<script>alert('xss')</script>"
    report = _minimal_report(
        findings=[
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
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
    html = build_html_report(report)
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;" in html
    # The principal string injection attempt is also escaped.
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    # Evidence JSON is rendered through |tojson then autoescaped, so no raw <b>.
    assert "<b>raw</b>" not in html


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
    html = build_html_report(_minimal_report(findings=findings))
    # Severity high appears before severity low in the Azure section.
    high_pos = html.find("AZ.OVERSIZED_VM")
    low_pos = html.find("AZ.IDLE_VM_14D")
    assert 0 < high_pos < low_pos
    # Surfaces with no findings render an "empty" placeholder.
    assert html.count("No findings.") >= 1


@pytest.mark.parametrize(
    "field,value",
    [("recommendation", "Use & inspect <tags>"), ("principal", "user&name<")],
)
def test_ampersand_and_brackets_escaped(field: str, value: str) -> None:
    findings = [
        {
            "rule_id": "M365.X",
            "surface": "m365",
            "severity": "info",
            "principal": "p",
            "current_sku": None,
            "recommended_sku": None,
            "estimated_monthly_savings_usd": None,
            "recommendation": "r",
            "evidence_ref": None,
            "confidence": "low",
            "evidence": {},
        }
    ]
    findings[0][field] = value
    html = build_html_report(_minimal_report(findings=findings))
    assert "&amp;" in html
