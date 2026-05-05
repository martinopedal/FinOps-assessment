"""Canonical JSON report writer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finops_assess import __version__
from finops_assess.models import Finding, PersonaAssignment


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
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
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
