"""FinOps practice-review report section (advisory, derived view).

This module renders a *derived* report section that surfaces four
operator-facing posture cues: pricing assumptions, data-quality
warnings, commitment posture, and SKU-mix posture. It is **advisory
only** — it does not, and must not, produce a maturity certification,
a score, a level, or a rating.

Architectural contract (Maya, 2026-05-12 §11 stage-3 plan, #31):

* This section is a *derived view* over the canonical JSON report
  dictionary. It reads ``report["run"]``, ``report["summary"]``, and
  ``report["findings"]`` only.
* It does NOT extend the canonical JSON schema. Adding new top-level
  fields to the canonical report (e.g., commitment coverage, family
  summaries) is out of scope here and lands in its own §11 PR with a
  schema bump.
* When an upstream data shape is not yet available in the canonical
  report (commitment coverage from #28, family summaries surfaced into
  the JSON contract), the relevant sub-section degrades gracefully to
  a "data not yet available" line rather than crashing.
* Wording is vendor-neutral and operator-facing. We do not name a
  "winner" SKU family, we do not direct the operator to purchase
  actions, and we do not phrase data-quality observations as customer
  error — they are framed as snapshot freshness / dataset completeness
  cues.

See ``.squad/decisions/inbox/maya-derived-report-views-2026-05-12.md``
for the general principle this module instantiates.
"""

from __future__ import annotations

from html import escape
from typing import Any

#: The advisory disclaimer rendered at the top of every practice-review
#: section. The wording is deliberate: it states the advisory posture
#: positively and negates the certification claim without using the
#: words "level", "score", "certified", "certification", or "rating"
#: in body content (the test-suite guard relies on this — the
#: disclaimer line is excluded from the forbidden-word scan because
#: even a negation of those words would trip a substring check).
ADVISORY_DISCLAIMER = (
    "This section is advisory only. It summarises operator-facing posture "
    "cues derived from the canonical report and does not constitute a "
    "maturity assessment, grade, or compliance verdict."
)

ADVISORY_HEADER = "Advisory"
SECTION_HEADING = "FinOps practice review"


def _pricing_assumptions(report: dict[str, Any]) -> dict[str, Any]:
    """Summarise the list-price assumptions implied by the findings.

    Today's canonical report does not carry an explicit
    ``pricing_assumptions`` block (that would be a schema addition,
    out of scope here). We derive an honest summary from what *is*
    in the report: how many findings carry an estimated saving, and
    the total. The wording makes clear that catalogue list prices
    were used as the default basis and that customer-supplied prices
    are not distinguished in the current schema.
    """
    findings: list[dict[str, Any]] = list(report.get("findings", []))
    with_savings = [f for f in findings if f.get("estimated_monthly_savings_usd") is not None]
    total = sum(float(f.get("estimated_monthly_savings_usd") or 0.0) for f in with_savings)
    return {
        "findings_with_estimated_savings": len(with_savings),
        "total_estimated_monthly_savings_usd": total,
        "basis": (
            "Estimated savings are derived from public list-price catalogue "
            "defaults bundled with this tool. Customer-negotiated pricing is "
            "not distinguished in the current report schema; treat the totals "
            "as an order-of-magnitude advisory figure, not a quote."
        ),
    }


def _data_quality_warnings(report: dict[str, Any]) -> list[str]:
    """Derive data-quality warnings from the canonical summary.

    Wording rule (Noor's stage-4 check): warnings describe the *dataset*
    — its freshness, completeness, or coverage — never the customer's
    operational hygiene.
    """
    summary: dict[str, Any] = dict(report.get("summary", {}) or {})
    warnings: list[str] = []

    principals = int(summary.get("principals_evaluated", 0) or 0)
    assignments = int(summary.get("assignments_evaluated", 0) or 0)
    azure_resources = int(summary.get("azure_resources_evaluated", 0) or 0)

    if principals == 0:
        warnings.append(
            "Input snapshot contains no principals — the M365 surface "
            "evaluated against an empty dataset. Verify the user-export "
            "collector ran successfully before relying on this report."
        )
    if assignments == 0:
        warnings.append(
            "Input snapshot contains no licence assignments — the "
            "assignment dataset is empty or was not collected for this run."
        )
    if azure_resources == 0:
        warnings.append(
            "Input snapshot contains no Azure resources — the Azure "
            "surface evaluated against an empty dataset; Azure findings "
            "in this report (if any) reflect catalogue defaults only."
        )

    skipped = list(summary.get("rules_skipped_no_impl", []) or [])
    if skipped:
        warnings.append(
            f"Catalogue declares {len(skipped)} rule(s) without a runnable "
            "implementation in this build — rule coverage for this snapshot "
            "is partial. The skipped rule IDs are listed in the Summary "
            "section above."
        )

    if summary.get("pii_redaction") == "disabled":
        warnings.append(
            "PII redaction is disabled for this run — principal identifiers "
            "in the findings table are not salted-hashed."
        )

    return warnings


def _commitment_posture(report: dict[str, Any]) -> dict[str, Any]:
    """Summarise commitment coverage vs utilisation posture.

    The canonical commitment-coverage contract (issue #28, Diego) is
    not yet merged onto main, so the field is not yet emitted into the
    JSON report. We probe for it defensively and degrade to
    "data not yet available" when absent — same pattern as SKU-mix
    posture below. When the upstream PR lands and starts emitting a
    ``commitment_coverage`` summary, this function picks it up
    without further reporter changes.
    """
    summary: dict[str, Any] = dict(report.get("summary", {}) or {})
    payload = summary.get("commitment_coverage")
    if not isinstance(payload, dict) or not payload:
        return {
            "available": False,
            "message": (
                "Commitment-coverage data is not yet surfaced in the "
                "canonical report schema. This sub-section will populate "
                "once the upstream commitment-posture contract lands."
            ),
        }
    return {"available": True, "payload": payload}


def _sku_mix_posture(report: dict[str, Any]) -> dict[str, Any]:
    """Summarise M365 family-level SKU-mix posture.

    Aggregate family summaries (``M365FamilySummary``) exist on the
    in-memory dataset model but are not (yet) exposed in the canonical
    JSON report; surfacing them is a schema-addition PR of its own.
    Until then we degrade gracefully, exactly like the commitment
    sub-section.

    Wording rule (Noor's stage-4 check): we surface *coverage*
    (assigned vs active) per family without naming a preferred family
    or directing the operator toward any specific SKU.
    """
    summary: dict[str, Any] = dict(report.get("summary", {}) or {})
    families = summary.get("m365_family_summaries")
    if not isinstance(families, list) or not families:
        return {
            "available": False,
            "message": (
                "M365 family-level SKU-mix summaries are not yet surfaced "
                "in the canonical report schema. This sub-section will "
                "populate once family summaries land in the report contract."
            ),
            "families": [],
        }
    normalised: list[dict[str, Any]] = []
    for fam in families:
        if not isinstance(fam, dict):
            continue
        normalised.append(
            {
                "family_name": str(fam.get("family_name", "")),
                "total_assigned": int(fam.get("total_assigned", 0) or 0),
                "distinct_users_with_assignment": int(
                    fam.get("distinct_users_with_assignment", 0) or 0
                ),
                "distinct_active_users": int(fam.get("distinct_active_users", 0) or 0),
                "distinct_inactive_users": int(fam.get("distinct_inactive_users", 0) or 0),
                "coverage_note": fam.get("coverage_note"),
            }
        )
    return {"available": True, "message": None, "families": normalised}


def build_practice_review(report: dict[str, Any]) -> dict[str, Any]:
    """Build the structured practice-review context from a canonical report dict.

    Returns a dict containing the advisory disclaimer and the four
    sub-sections. The HTML renderer below consumes this; tests and
    other reporters (CSV / future surfaces) may consume it directly.
    """
    return {
        "header": ADVISORY_HEADER,
        "heading": SECTION_HEADING,
        "disclaimer": ADVISORY_DISCLAIMER,
        "pricing_assumptions": _pricing_assumptions(report),
        "data_quality_warnings": _data_quality_warnings(report),
        "commitment_posture": _commitment_posture(report),
        "sku_mix_posture": _sku_mix_posture(report),
    }


def _render_pricing_block(pa: dict[str, Any]) -> str:
    n = pa["findings_with_estimated_savings"]
    total = pa["total_estimated_monthly_savings_usd"]
    return (
        "<h3>Pricing assumptions</h3>\n"
        f"<p>{escape(pa['basis'])}</p>\n"
        "<ul>\n"
        f"  <li>Findings carrying an estimated monthly saving: <strong>{n}</strong></li>\n"
        f"  <li>Sum of estimated monthly savings across those findings: "
        f"<strong>${total:.2f}</strong></li>\n"
        "</ul>\n"
    )


def _render_data_quality_block(warnings: list[str]) -> str:
    if not warnings:
        return (
            "<h3>Data-quality warnings</h3>\n"
            '<p class="empty">No data-quality warnings derived from this '
            "snapshot. Dataset coverage and rule implementation are "
            "complete for the surfaces evaluated.</p>\n"
        )
    items = "\n".join(f"  <li>{escape(w)}</li>" for w in warnings)
    return f"<h3>Data-quality warnings</h3>\n<ul>\n{items}\n</ul>\n"


def _render_commitment_block(cp: dict[str, Any]) -> str:
    if not cp.get("available"):
        return f'<h3>Commitment posture</h3>\n<p class="empty">{escape(cp["message"])}</p>\n'
    payload = cp.get("payload", {})
    rows = "\n".join(
        f'  <li><span class="mono">{escape(str(k))}</span>: {escape(str(v))}</li>'
        for k, v in payload.items()
    )
    return (
        "<h3>Commitment posture</h3>\n"
        "<p>Coverage and utilisation cues derived from upstream "
        "commitment-coverage data. Posture cues only — this section does "
        "not recommend purchase actions.</p>\n"
        "<ul>\n"
        f"{rows}\n"
        "</ul>\n"
    )


def _render_sku_mix_block(sm: dict[str, Any]) -> str:
    if not sm.get("available"):
        return f'<h3>SKU-mix posture</h3>\n<p class="empty">{escape(sm["message"])}</p>\n'
    rows: list[str] = []
    for fam in sm["families"]:
        coverage_note = fam.get("coverage_note") or ""
        rows.append(
            "  <tr>"
            f'<td class="mono">{escape(fam["family_name"])}</td>'
            f"<td>{fam['total_assigned']}</td>"
            f"<td>{fam['distinct_users_with_assignment']}</td>"
            f"<td>{fam['distinct_active_users']}</td>"
            f"<td>{fam['distinct_inactive_users']}</td>"
            f"<td>{escape(coverage_note)}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return (
        "<h3>SKU-mix posture</h3>\n"
        "<p>Per-family assigned-vs-active coverage cues. Vendor-neutral "
        "and presented without ranking — no SKU family is named as "
        "preferred or recommended over another.</p>\n"
        "<table>\n"
        "  <thead><tr>"
        "<th>Family</th><th>Total assigned</th><th>Distinct users</th>"
        "<th>Active users</th><th>Inactive users</th><th>Note</th>"
        "</tr></thead>\n"
        "  <tbody>\n"
        f"{body}\n"
        "  </tbody>\n"
        "</table>\n"
    )


def render_practice_review_section(report: dict[str, Any]) -> str:
    """Render the practice-review section as a self-contained HTML fragment.

    Returned HTML is safe to splice into the main report templates with
    Jinja's ``|safe`` filter — all dynamic values are escaped via
    :func:`html.escape` at construction.
    """
    ctx = build_practice_review(report)
    return (
        '<section class="practice-review">\n'
        f"  <h2>{escape(ctx['heading'])} "
        f'<span class="pill">{escape(ctx["header"])}</span></h2>\n'
        f'  <p class="disclaimer"><em>{escape(ctx["disclaimer"])}</em></p>\n'
        f"  {_render_pricing_block(ctx['pricing_assumptions'])}"
        f"  {_render_data_quality_block(ctx['data_quality_warnings'])}"
        f"  {_render_commitment_block(ctx['commitment_posture'])}"
        f"  {_render_sku_mix_block(ctx['sku_mix_posture'])}"
        "</section>\n"
    )
