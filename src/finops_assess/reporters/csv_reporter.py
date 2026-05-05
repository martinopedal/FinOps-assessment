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


# Leading characters that Excel / Sheets interpret as the start of a
# formula. Tenant-controlled strings (principals, SKU IDs, recommendation
# text) starting with any of these get a single-quote prefix so they are
# rendered as text instead of evaluated as a formula. This is the OWASP
# "CSV / formula injection" mitigation.
_FORMULA_PREFIXES: frozenset[str] = frozenset(("=", "+", "-", "@", "\t", "\r"))


def _sanitize_cell(value: Any) -> str:
    """Render ``value`` as a CSV cell, neutralising formula-injection prefixes.

    Numeric values (``int`` / ``float`` / ``bool``) are rendered as-is —
    a legitimate negative number like ``-12.5`` is not a formula. Only
    string-like values that start with a dangerous character are
    prefixed with ``'`` so spreadsheet apps render them as text.
    """
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return str(value)
    text = str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def _row_for(finding: dict[str, Any]) -> dict[str, str]:
    """Project one finding dict onto the CSV column set.

    ``None`` is rendered as the empty string (Excel / pandas treat that
    as NA on import). ``evidence`` is serialised as a compact JSON
    string in the ``evidence_json`` column so the structured payload
    survives the flattening round-trip. Tenant-controlled string cells
    are passed through :func:`_sanitize_cell` to neutralise CSV-formula
    injection (cells starting with ``=``, ``+``, ``-``, ``@``, tab, or
    CR get a leading ``'``).
    """
    row: dict[str, str] = {}
    for column in COLUMNS:
        if column == "evidence_json":
            evidence = finding.get("evidence") or {}
            # JSON output always starts with '{' or '[' — safe by construction.
            row[column] = json.dumps(evidence, sort_keys=True, default=str)
            continue
        row[column] = _sanitize_cell(finding.get(column))
    return row


def write_csv_report(report: dict[str, Any], output: Path) -> Path:
    """Write the report's findings to ``output`` as a flat CSV.

    Uses ``\\n`` line terminator and ``QUOTE_MINIMAL`` so byte output is
    deterministic across Linux / macOS / Windows. Excel auto-detects
    the delimiter on open; for explicit Excel-locale handling, users
    can re-import with the Text Import Wizard.

    Returns the output path that was written, as a :class:`~pathlib.Path`
    (relative inputs stay relative — callers that need an absolute path
    should call :meth:`~pathlib.Path.resolve` themselves).
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
