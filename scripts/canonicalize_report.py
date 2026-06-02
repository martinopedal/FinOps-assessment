#!/usr/bin/env python3
"""Shared cross-engine report canonicaliser (conformance layer 5).

Both the Python engine and the native PowerShell engine emit a JSON
report. Their raw serialisers differ (key order, whitespace, number
formatting), so *raw* byte-equality is not a meaningful parity bar
(see ``docs/plan.md`` §5a). Instead, each engine's report is pushed
through this single, shared canonicaliser under a named **profile**,
and only the *canonical* artefact is byte-compared against a committed
golden.

Keeping the canonicaliser in one place (invoked by both the Python
golden generator and the PowerShell Pester conformance test) guarantees
both engines are judged by the *same* rules.

Profiles
--------
``report-structural-v1``
    The Phase-1c bar: **structural / report-envelope parity**, not
    findings parity. The Python engine runs the real rules over the demo
    tenant and emits real findings; the PowerShell engine has no rule
    implementations yet (those land in later phases). So this profile
    deliberately compares only the parts both engines can produce
    identically today:

      * the whole ``run`` block (tool, version, schema_version,
        generated_at, input, pii_redaction, salt_mode, mode),
      * the dataset-derived ``summary`` counts (principals/assignments/
        azure_resources evaluated), ``salt_mode``, the optional
        ``pii_redaction`` marker, and ``persona_distribution``,

    and it **masks** the rule-dependent fields (``rule_counts``,
    ``rules_skipped_no_impl``, ``total_findings``) and the ``findings``
    *contents*. ``findings`` is still type-checked (it must be a JSON
    array) and then collapsed to a fixed sentinel so a report with real
    findings and a report with none canonicalise identically. This is an
    honest projection: it proves "both engines emit a schema-valid report
    envelope over the same normalised dataset with matching run metadata,
    dataset-derived counts, persona distribution, and a findings array",
    and it claims nothing about finding contents until the rule phases.

Canonical form: ``json.dumps(..., indent=2, sort_keys=True,
ensure_ascii=False, allow_nan=False)`` + a trailing newline, written
with ``newline=""`` so the bytes are identical on every OS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: Sentinel that replaces ``findings`` contents under the structural
#: profile. The value is fixed (independent of finding count) so a real
#: Python report and an empty PowerShell report project identically.
FINDINGS_MASK = "<array:masked>"

PROFILES = ("report-structural-v1",)

#: ``summary`` keys that depend on rule execution and are therefore
#: masked under ``report-structural-v1``.
_RULE_DEPENDENT_SUMMARY_KEYS = frozenset({"rule_counts", "rules_skipped_no_impl", "total_findings"})

#: ``summary`` keys carried through the structural profile, in the order
#: they should appear (canonical output sorts keys anyway; this list just
#: defines membership).
_STRUCTURAL_SUMMARY_KEYS = (
    "principals_evaluated",
    "assignments_evaluated",
    "azure_resources_evaluated",
    "salt_mode",
    "pii_redaction",
    "persona_distribution",
)


def _project_structural(report: dict[str, Any]) -> dict[str, Any]:
    """Return the ``report-structural-v1`` projection of ``report``."""
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")

    run = report.get("run")
    if not isinstance(run, dict):
        raise ValueError("report.run must be a JSON object")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("report.summary must be a JSON object")

    findings = report.get("findings")
    if not isinstance(findings, list):
        raise ValueError("report.findings must be a JSON array")

    projected_summary: dict[str, Any] = {
        key: summary[key] for key in _STRUCTURAL_SUMMARY_KEYS if key in summary
    }

    return {
        "run": dict(run),
        "summary": projected_summary,
        "findings": FINDINGS_MASK,
    }


def canonicalize(report: dict[str, Any], profile: str) -> str:
    """Return the canonical string for ``report`` under ``profile``.

    The returned string has no trailing newline; callers that write it to
    a file should append exactly one ``"\\n"``.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown canonicaliser profile: {profile!r}")

    projected = _project_structural(report)
    return json.dumps(
        projected,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


def canonicalize_text(report_text: str, profile: str) -> str:
    """Canonicalise a JSON report supplied as text. Appends a trailing newline."""
    report = json.loads(report_text)
    return canonicalize(report, profile) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        required=True,
        choices=PROFILES,
        help="Canonicaliser profile to apply.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the raw JSON report to canonicalise.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the canonical artefact (defaults to stdout).",
    )
    args = parser.parse_args(argv)

    report_text = args.input.read_text(encoding="utf-8-sig")
    try:
        canonical = canonicalize_text(report_text, args.profile)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"canonicalize_report: {exc}", file=sys.stderr)
        return 2

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(canonical, encoding="utf-8", newline="")
    else:
        sys.stdout.write(canonical)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
