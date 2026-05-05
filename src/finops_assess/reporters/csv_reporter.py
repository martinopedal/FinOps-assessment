"""Flat-CSV reporter for pivoting findings in Excel / Sheets.

Consumes the canonical report dictionary produced by
:func:`finops_assess.reporters.json_reporter.build_report`, so it
inherits PII redaction and any other normalisation already applied
upstream — the CSV reporter never sees raw :class:`~finops_assess.models.Finding`
objects.

One row per finding. The column order is fixed and documented so
downstream pivot tables and CI grep checks can rely on it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

# Public, stable column order. Adding a column is a non-breaking change;
# reordering or removing one is a breaking change to anyone pivoting on
# this output.
COLUMNS: tuple[str, ...] = (
    "rule_id",
    "surface",
    "severity",
    "confidence",
    "principal",
    "current_sku",
    "recommended_sku",
    "estimated_monthly_savings_usd",
    "recommendation",
    "evidence_ref",
    "evidence_json",
)


def _row_for(finding: dict[str, Any]) -> dict[str, str]:
    """Project one finding dict onto the CSV column set.

    ``None`` is rendered as the empty string (Excel / pandas treat that
    as NA on import). ``evidence`` is serialised as a compact JSON
    string in the ``evidence_json`` column so the structured payload
    survives the flattening round-trip.
    """
    row: dict[str, str] = {}
    for column in COLUMNS:
        if column == "evidence_json":
            evidence = finding.get("evidence") or {}
            row[column] = json.dumps(evidence, sort_keys=True, default=str)
            continue
        value = finding.get(column)
        row[column] = "" if value is None else str(value)
    return row


def write_csv_report(report: dict[str, Any], output: Path) -> Path:
    """Write the report's findings to ``output`` as a flat CSV.

    Uses ``\\n`` line terminator and ``QUOTE_MINIMAL`` so byte output is
    deterministic across Linux / macOS / Windows. Excel auto-detects
    the delimiter on open; for explicit Excel-locale handling, users
    can re-import with the Text Import Wizard.

    Returns the resolved output path so callers can echo it.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    findings = report.get("findings", [])
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(COLUMNS),
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for finding in findings:
            writer.writerow(_row_for(finding))
    return output
