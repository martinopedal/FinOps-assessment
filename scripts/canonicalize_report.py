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

``report-m365-v1``
    The Phase-2 bar: **M365 rule-slice parity**, including full finding
    contents. The Python engine implements every rule across all four
    surfaces; the native PowerShell engine implements only the eight
    ``M365.*`` rules in Phase 2. A whole-report compare would therefore
    diverge on the non-M365 ``rule_counts`` and findings. This profile
    narrows the comparison to the M365 slice both engines can produce
    identically:

      * the whole ``run`` block,
      * every ``M365.*`` finding **with full contents** (recommendation,
        savings, evidence, confidence, …), filtered by ``rule_id``
        prefix and sorted by a deterministic composite key so finding
        emission order is treated as non-contractual,
      * the dataset-derived ``summary`` counts, ``salt_mode``, the
        optional ``pii_redaction`` marker, ``persona_distribution``, and
        ``rule_counts`` **filtered to ``M365.*`` keys**.

    It **masks** ``rules_skipped_no_impl`` and ``total_findings`` (the
    PowerShell engine skips the 20 non-M365 rules; the Python engine
    skips none). To keep the projection non-vacuous it self-validates:
    every projected finding must carry ``surface == "m365"``, every
    ``M365.*`` ``rule_count`` must equal the number of projected findings
    for that rule, and all eight known ``M365.*`` rule ids must be
    present in ``rule_counts``. Money is coerced to ``float`` so a
    whole-dollar value renders identically regardless of which engine
    emitted ``12`` vs ``12.0``. This profile proves "both engines run the
    M365 rules over the same normalised dataset under deterministic
    redaction and produce identical findings", and claims nothing about
    azure/github/ado rules yet.

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

PROFILES = ("report-structural-v1", "report-m365-v1")

#: The eight M365 rule ids the PowerShell engine implements in Phase 2.
#: Used by ``report-m365-v1`` to assert the slice is fully exercised.
_M365_RULE_IDS = frozenset(
    {
        "M365.UNUSED_LICENSE_30D",
        "M365.OVER_LICENSED_VS_PERSONA",
        "M365.DUPLICATE_BUNDLE",
        "M365.DISABLED_USER_LICENSED",
        "M365.SHARED_MAILBOX_LICENSED",
        "M365.GUEST_PREMIUM_LICENSED",
        "M365.COPILOT_INACTIVE_60D",
        "M365.E5_FEATURES_UNUSED",
    }
)

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


def _finding_sort_key(finding: dict[str, Any]) -> str:
    """Deterministic composite sort key for a finding.

    Finding emission order is treated as non-contractual for the
    conformance slice: both engines' findings are sorted by this key in
    the canonicaliser so a different traversal order on either side does
    not break the byte compare. The key is stable JSON so ties are broken
    reproducibly.
    """
    return json.dumps(
        [
            finding.get("rule_id") or "",
            finding.get("principal") or "",
            finding.get("current_sku") or "",
            finding.get("recommended_sku") or "",
            json.dumps(finding.get("evidence") or {}, sort_keys=True, ensure_ascii=False),
        ],
        sort_keys=True,
        ensure_ascii=False,
    )


def _coerce_money(finding: dict[str, Any]) -> dict[str, Any]:
    """Return ``finding`` with ``estimated_monthly_savings_usd`` as float-or-None.

    Without this, ``12`` (int) and ``12.0`` (float) would canonicalise to
    different bytes (``12`` vs ``12.0``) depending on which engine emitted
    the value. Coercing to ``float`` pins the representation.
    """
    out = dict(finding)
    savings = out.get("estimated_monthly_savings_usd")
    if savings is not None:
        out["estimated_monthly_savings_usd"] = float(savings)
    return out


def _project_m365(report: dict[str, Any]) -> dict[str, Any]:
    """Return the ``report-m365-v1`` projection of ``report``."""
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

    m365_findings = [
        f for f in findings if isinstance(f, dict) and str(f.get("rule_id", "")).startswith("M365.")
    ]
    for f in m365_findings:
        if f.get("surface") != "m365":
            raise ValueError(
                f"M365 rule {f.get('rule_id')!r} produced a non-m365 surface: {f.get('surface')!r}"
            )

    rule_counts = summary.get("rule_counts")
    if not isinstance(rule_counts, dict):
        raise ValueError("report.summary.rule_counts must be a JSON object")
    m365_rule_counts = {k: v for k, v in rule_counts.items() if str(k).startswith("M365.")}

    missing = sorted(_M365_RULE_IDS - set(m365_rule_counts))
    if missing:
        raise ValueError(f"report.summary.rule_counts missing M365 rules: {missing}")

    observed: dict[str, int] = {}
    for f in m365_findings:
        rid = str(f.get("rule_id"))
        observed[rid] = observed.get(rid, 0) + 1
    for rid, declared in m365_rule_counts.items():
        if observed.get(rid, 0) != declared:
            raise ValueError(
                f"rule_count for {rid} is {declared} but {observed.get(rid, 0)} findings projected"
            )

    projected_summary: dict[str, Any] = {
        key: summary[key] for key in _STRUCTURAL_SUMMARY_KEYS if key in summary
    }
    projected_summary["rule_counts"] = m365_rule_counts

    projected_findings = sorted((_coerce_money(f) for f in m365_findings), key=_finding_sort_key)

    return {
        "run": dict(run),
        "summary": projected_summary,
        "findings": projected_findings,
    }


def canonicalize(report: dict[str, Any], profile: str) -> str:
    """Return the canonical string for ``report`` under ``profile``.

    The returned string has no trailing newline; callers that write it to
    a file should append exactly one ``"\\n"``.
    """
    if profile == "report-structural-v1":
        projected = _project_structural(report)
    elif profile == "report-m365-v1":
        projected = _project_m365(report)
    else:
        raise ValueError(f"unknown canonicaliser profile: {profile!r}")

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
