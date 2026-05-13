"""Reporters package — JSON, HTML, CSV, and PDF (M7) outputs.

The PDF reporter requires the optional ``[pdf]`` extra (WeasyPrint plus
its native dependencies). ``Branding``, ``build_pdf_html``,
``build_pdf_report``, and ``write_pdf_report`` are always importable;
the WeasyPrint dependency is loaded lazily inside ``build_pdf_report``.
"""

from finops_assess.reporters.csv_reporter import COLUMNS as CSV_COLUMNS
from finops_assess.reporters.csv_reporter import write_csv_report
from finops_assess.reporters.focus_aligned import (
    build_focus_aligned_manifest,
    write_focus_aligned_export,
)
from finops_assess.reporters.html_reporter import build_html_report, write_html_report
from finops_assess.reporters.json_reporter import write_json_report
from finops_assess.reporters.pdf_reporter import (
    Branding,
    build_pdf_html,
    build_pdf_report,
    write_pdf_report,
)
from finops_assess.reporters.triage_reporter import (
    TRIAGE_CSV_COLUMNS,
    write_triage_csv,
    write_triage_json,
)

__all__ = [
    "CSV_COLUMNS",
    "TRIAGE_CSV_COLUMNS",
    "Branding",
    "build_focus_aligned_manifest",
    "build_html_report",
    "build_pdf_html",
    "build_pdf_report",
    "write_csv_report",
    "write_focus_aligned_export",
    "write_html_report",
    "write_json_report",
    "write_pdf_report",
    "write_triage_csv",
    "write_triage_json",
]
