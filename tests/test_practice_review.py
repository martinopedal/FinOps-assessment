"""Tests for the FinOps practice-review report section (issue #31).

These tests enforce the architectural contract Maya set in the §11
stage-3 plan: the section is advisory only, never uses certification /
scoring / level / rating language, degrades gracefully when upstream
posture data is not yet in the canonical schema, and always carries
the advisory disclaimer.
"""

from __future__ import annotations

import re
from typing import Any

from finops_assess.reporters.html_reporter import build_html_report
from finops_assess.reporters.practice_review import (
    ADVISORY_DISCLAIMER,
    ADVISORY_HEADER,
    SECTION_HEADING,
    build_practice_review,
    render_practice_review_section,
)

# Words that must never appear in practice-review *body* content.
# The disclaimer line is excluded from this scan because it lives in
# its own paragraph and may legitimately negate these concepts in
# future copy revisions — the guard targets posture content.
_FORBIDDEN_WORDS = ("Level", "Score", "Certified", "Certification", "Rating")


def _minimal_report(
    *,
    summary_overrides: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rule_counts": {"M365.UNUSED_LICENSE_30D": 1},
        "rules_skipped_no_impl": [],
        "total_findings": 1,
        "principals_evaluated": 3,
        "assignments_evaluated": 5,
        "azure_resources_evaluated": 2,
        "persona_distribution": {"information_worker": 2, "frontline_worker": 1},
    }
    if summary_overrides:
        summary.update(summary_overrides)
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.0.1",
            "schema_version": "1.0",
            "generated_at": "2026-05-12T00:00:00+00:00",
            "input": "<redacted>/samples",
            "pii_redaction": True,
            "mode": "read-only",
        },
        "summary": summary,
        "findings": findings
        if findings is not None
        else [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "severity": "medium",
                "principal": "abc123",
                "current_sku": "SPE_E3",
                "recommended_sku": None,
                "estimated_monthly_savings_usd": 36.0,
                "recommendation": "Consider removing the unused licence.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"days_inactive": 45},
            }
        ],
    }


def _body_without_disclaimer(html: str) -> str:
    """Return the rendered section with the disclaimer paragraph stripped.

    The disclaimer paragraph is bounded by a deterministic CSS class
    (``disclaimer``); we strip the single line it occupies so the
    forbidden-word scan asserts on posture *body* content only.
    """
    return re.sub(
        r'<p class="disclaimer">.*?</p>',
        "",
        html,
        flags=re.DOTALL,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_section_renders_with_full_data() -> None:
    report = _minimal_report(
        summary_overrides={
            "m365_family_summaries": [
                {
                    "family_name": "m365_base",
                    "total_assigned": 10,
                    "distinct_users_with_assignment": 10,
                    "distinct_active_users": 8,
                    "distinct_inactive_users": 2,
                    "coverage_note": "Healthy active-to-assigned ratio.",
                }
            ],
            "commitment_coverage": {
                "azure_reservations_covered_pct": "62%",
                "azure_reservations_utilised_pct": "91%",
            },
        }
    )
    html = render_practice_review_section(report)

    assert SECTION_HEADING in html
    assert ADVISORY_HEADER in html
    assert "Pricing assumptions" in html
    assert "Data-quality warnings" in html
    assert "Commitment posture" in html
    assert "SKU-mix posture" in html
    # Family row populated from summary.m365_family_summaries
    assert "m365_base" in html
    # Commitment payload surfaced
    assert "azure_reservations_covered_pct" in html


def test_section_includes_total_estimated_savings_from_findings() -> None:
    report = _minimal_report()
    html = render_practice_review_section(report)
    # Single finding at $36.00 — should appear in the pricing block.
    assert "$36.00" in html


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_section_renders_with_missing_commitment_data() -> None:
    """When Diego's #28 commitment-coverage contract has not landed yet,
    the sub-section must render a 'data not yet available' line — not crash."""
    report = _minimal_report()  # no commitment_coverage key in summary
    html = render_practice_review_section(report)

    assert "Commitment posture" in html
    assert "not yet surfaced" in html or "not yet" in html
    # And must NOT crash or render a partial payload table:
    assert "azure_reservations_covered_pct" not in html


def test_section_renders_with_missing_sku_mix_data() -> None:
    """When family summaries are not surfaced into canonical JSON yet,
    the SKU-mix sub-section degrades gracefully."""
    report = _minimal_report()  # no m365_family_summaries key in summary
    html = render_practice_review_section(report)

    assert "SKU-mix posture" in html
    assert "not yet surfaced" in html or "not yet" in html
    # No table headers leaked when families are empty:
    assert "<th>Family</th>" not in html


def test_section_renders_with_completely_empty_dataset() -> None:
    """Operator runs against an empty input dir — must still render."""
    report = _minimal_report(
        summary_overrides={
            "principals_evaluated": 0,
            "assignments_evaluated": 0,
            "azure_resources_evaluated": 0,
        },
        findings=[],
    )
    html = render_practice_review_section(report)
    # All three empty-dataset warnings should fire.
    assert "no principals" in html
    assert "no licence assignments" in html
    assert "no Azure resources" in html


# ---------------------------------------------------------------------------
# Architectural guardrails (Noor stage-4)
# ---------------------------------------------------------------------------


def test_no_certification_language_in_section_body() -> None:
    """Hard guard against scoring / level / certification / rating
    language anywhere in posture content (disclaimer excluded — see
    module docstring)."""
    report = _minimal_report(
        summary_overrides={
            "m365_family_summaries": [
                {
                    "family_name": "m365_base",
                    "total_assigned": 10,
                    "distinct_users_with_assignment": 10,
                    "distinct_active_users": 8,
                    "distinct_inactive_users": 2,
                    "coverage_note": None,
                }
            ],
            "commitment_coverage": {"azure_reservations_covered_pct": "60%"},
        }
    )
    html = render_practice_review_section(report)
    body = _body_without_disclaimer(html)
    for forbidden in _FORBIDDEN_WORDS:
        assert forbidden not in body, (
            f"Forbidden certification-style word {forbidden!r} found in "
            f"practice-review body content."
        )


def test_advisory_disclaimer_always_present_full_data() -> None:
    report = _minimal_report(
        summary_overrides={
            "m365_family_summaries": [
                {
                    "family_name": "m365_base",
                    "total_assigned": 1,
                    "distinct_users_with_assignment": 1,
                    "distinct_active_users": 1,
                    "distinct_inactive_users": 0,
                    "coverage_note": None,
                }
            ],
            "commitment_coverage": {"azure_reservations_covered_pct": "60%"},
        }
    )
    assert ADVISORY_DISCLAIMER in render_practice_review_section(report)


def test_advisory_disclaimer_always_present_missing_data() -> None:
    report = _minimal_report()
    assert ADVISORY_DISCLAIMER in render_practice_review_section(report)


def test_advisory_disclaimer_always_present_empty_dataset() -> None:
    report = _minimal_report(
        summary_overrides={
            "principals_evaluated": 0,
            "assignments_evaluated": 0,
            "azure_resources_evaluated": 0,
        },
        findings=[],
    )
    assert ADVISORY_DISCLAIMER in render_practice_review_section(report)


def test_disclaimer_contains_no_forbidden_certification_words() -> None:
    """The disclaimer itself is also held to the no-forbidden-words bar
    so a future copy revision cannot smuggle scoring language in via
    the disclaimer line."""
    for forbidden in _FORBIDDEN_WORDS:
        assert forbidden not in ADVISORY_DISCLAIMER


# ---------------------------------------------------------------------------
# Wiring into the main HTML report
# ---------------------------------------------------------------------------


def test_practice_review_section_wired_into_html_report() -> None:
    """The section is rendered by build_html_report end-to-end."""
    html = build_html_report(_minimal_report())
    assert SECTION_HEADING in html
    assert ADVISORY_DISCLAIMER in html
    # Section appears once, after the surface sections (sanity)
    assert html.count(SECTION_HEADING) == 1


# ---------------------------------------------------------------------------
# Structured builder
# ---------------------------------------------------------------------------


def test_build_practice_review_returns_structured_dict() -> None:
    ctx = build_practice_review(_minimal_report())
    assert ctx["heading"] == SECTION_HEADING
    assert ctx["header"] == ADVISORY_HEADER
    assert ctx["disclaimer"] == ADVISORY_DISCLAIMER
    assert "pricing_assumptions" in ctx
    assert "data_quality_warnings" in ctx
    assert "commitment_posture" in ctx
    assert "sku_mix_posture" in ctx
    # Graceful degradation flags wired into structured payload, not just HTML
    assert ctx["commitment_posture"]["available"] is False
    assert ctx["sku_mix_posture"]["available"] is False
