"""Canonical JSON report writer."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finops_assess import __version__
from finops_assess.models import Finding, PersonaAssignment


def _generated_at() -> str:
    """Return the report timestamp, honouring ``SOURCE_DATE_EPOCH``.

    Defaults to ``datetime.now(UTC)`` so day-to-day runs continue to embed
    the wall-clock time. When ``SOURCE_DATE_EPOCH`` is set (the
    reproducible-builds.org convention already honoured by
    :mod:`finops_assess.reporters.pdf_reporter`), the report timestamp is
    derived from that epoch instead, making JSON / HTML / CSV / PDF output
    byte-deterministic across runs of the same input. This is what
    ``scripts/generate_docs.py`` relies on to produce the committed
    ``examples/`` artefacts.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError, OSError):
            # Malformed or out-of-range env var (very large epochs raise
            # OverflowError on Linux and OSError on Windows from the
            # underlying C ``localtime`` / ``gmtime``): fall through to
            # wall-clock time rather than failing the whole run on a
            # transient operator error.
            pass
    return datetime.now(UTC).isoformat(timespec="seconds")


def _redact_input_path(input_path: Path, redact_pii: bool) -> str:
    """Drop the directory portion of ``input_path`` when redaction is on.

    Operator workstations frequently have absolute paths like
    ``/Users/alice/customers/contoso/...`` or
    ``C:\\Users\\bob\\Engagements\\Acme\\...`` which themselves leak
    user, customer, or engagement names. With redaction enabled we
    record only the leaf name so the report can still be correlated
    with the directory the operator chose without exposing the path.
    """
    if not redact_pii:
        return str(input_path)
    return f"<redacted>/{Path(input_path).name}"


def build_report(
    *,
    findings: list[Finding],
    summary: dict[str, Any],
    persona_assignments: dict[str, PersonaAssignment],
    input_path: Path,
    redact_pii: bool,
) -> dict[str, Any]:
    """Build the canonical report dictionary."""
    persona_distribution: dict[str, int] = {}
    for assn in persona_assignments.values():
        persona_distribution[assn.persona_id] = persona_distribution.get(assn.persona_id, 0) + 1

    return {
        "run": {
            "tool": "finops-assess",
            "version": __version__,
            "generated_at": _generated_at(),
            "input": _redact_input_path(input_path, redact_pii),
            "pii_redaction": redact_pii,
            "mode": "read-only",
        },
        "summary": {
            **summary,
            "persona_distribution": persona_distribution,
        },
        "findings": [f.model_dump(exclude_none=False) for f in findings],
    }


def write_json_report(report: dict[str, Any], output: Path | None) -> str:
    """Serialise ``report`` to JSON; write to ``output`` if given, else return string."""
    payload = json.dumps(report, indent=2, sort_keys=False, default=str)
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    return payload
