"""Reporters package — JSON, HTML, and PDF (M7) outputs.

The PDF reporter requires the optional ``[pdf]`` extra (WeasyPrint plus
its native dependencies). ``Branding``, ``build_pdf_html``,
``build_pdf_report``, and ``write_pdf_report`` are always importable;
the WeasyPrint dependency is loaded lazily inside ``build_pdf_report``.
"""

from finops_assess.reporters.html_reporter import build_html_report, write_html_report
from finops_assess.reporters.json_reporter import write_json_report
from finops_assess.reporters.pdf_reporter import (
    Branding,
    build_pdf_html,
    build_pdf_report,
    write_pdf_report,
)

__all__ = [
    "Branding",
    "build_html_report",
    "build_pdf_html",
    "build_pdf_report",
    "write_html_report",
    "write_json_report",
    "write_pdf_report",
]
