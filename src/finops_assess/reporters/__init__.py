"""Reporters package — JSON, HTML, CSV, PDF, and playbook JSONL outputs.

The PDF reporter requires the optional ``[pdf]`` extra (WeasyPrint plus
its native dependencies). ``Branding``, ``build_pdf_html``,
``build_pdf_report``, and ``write_pdf_report`` are always importable;
the WeasyPrint dependency is loaded lazily inside ``build_pdf_report``.

The playbook reporter (``write_playbook_export``) exports findings as a
JSONL file (one row per finding) alongside a sidecar manifest, using
atomic-write Option C (tempfile + fsync + os.replace).
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
from finops_assess.reporters.playbook import (
    PlaybookTemplateNotFoundError,
    find_orphaned_jsonl,
    write_playbook_export,
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
    "PlaybookTemplateNotFoundError",
    "build_focus_aligned_manifest",
    "build_html_report",
    "build_pdf_html",
    "build_pdf_report",
    "find_orphaned_jsonl",
    "write_csv_report",
    "write_focus_aligned_export",
    "write_html_report",
    "write_json_report",
    "write_pdf_report",
    "write_playbook_export",
    "write_triage_csv",
    "write_triage_json",
]
