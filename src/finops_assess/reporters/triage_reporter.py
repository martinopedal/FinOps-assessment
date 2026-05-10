"""JSON and CSV writers for advisory triage artefacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from finops_assess.triage import TriageReport

TRIAGE_CSV_COLUMNS: tuple[str, ...] = (
    "finding_ref",
    "source_finding_index",
    "rule_id",
    "surface",
    "severity",
    "confidence",
    "principal",
    "priority_bucket",
    "priority_rationale",
    "suggested_owner_role",
    "current_sku",
    "recommended_sku",
    "estimated_monthly_savings_usd",
    "evidence_ref",
    "verification_checklist",
    "followup_questions",
    "advisory",
)

_FORMULA_PREFIXES: frozenset[str] = frozenset(("=", "+", "-", "@", "\t", "\r"))


def _sanitize_cell(value: Any) -> str:
    """Render a CSV cell while neutralising spreadsheet formula prefixes."""
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return str(value)
    text = str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def write_triage_json(report: TriageReport, output: Path) -> Path:
    """Write a triage report as deterministic JSON."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
        newline="",
    )
    return output


def write_triage_csv(report: TriageReport, output: Path) -> Path:
    """Write a triage report as a stable flat CSV."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(TRIAGE_CSV_COLUMNS),
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for item in report.items:
            row = item.model_dump(mode="json")
            row["verification_checklist"] = " | ".join(item.verification_checklist)
            row["followup_questions"] = " | ".join(item.followup_questions)
            writer.writerow(
                {column: _sanitize_cell(row.get(column)) for column in TRIAGE_CSV_COLUMNS}
            )
    return output
