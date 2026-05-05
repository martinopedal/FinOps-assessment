"""Tests for the flat-CSV findings reporter."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from finops_assess.reporters import CSV_COLUMNS
from finops_assess.reporters.csv_reporter import write_csv_report


def _report(findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.0.1",
            "generated_at": "2026-05-05T00:00:00+00:00",
            "input": "<redacted>/samples",
            "pii_redaction": True,
            "mode": "read-only",
        },
        "summary": {"rule_counts": {}, "rules_skipped_no_impl": []},
        "findings": findings if findings is not None else [],
    }


def _sample_findings() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": "M365.UNUSED_LICENSE_30D",
            "surface": "m365",
            "severity": "medium",
            "principal": "sha256:deadbeef",
            "current_sku": "SPE_E3",
            "recommended_sku": None,
            "estimated_monthly_savings_usd": 36.0,
            "recommendation": "Consider removing the unused E3 license.",
            "evidence_ref": None,
            "confidence": "high",
            "evidence": {"days_inactive": 45, "signals": ["mailbox", "office"]},
        },
        {
            "rule_id": "AZ.IDLE_VM_14D",
            "surface": "azure",
            "severity": "high",
            "principal": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            "current_sku": "Standard_D4s_v5",
            "recommended_sku": None,
            "estimated_monthly_savings_usd": 140.5,
            "recommendation": "Verify and then deallocate the idle VM.",
            "evidence_ref": None,
            "confidence": "medium",
            "evidence": {},
        },
    ]


def test_writes_header_only_for_empty_report(tmp_path: Path) -> None:
    output = tmp_path / "findings.csv"
    write_csv_report(_report(), output)
    text = output.read_text(encoding="utf-8")
    # Header line + trailing newline only.
    assert text == ",".join(CSV_COLUMNS) + "\n"


def test_round_trips_findings_through_dictreader(tmp_path: Path) -> None:
    output = tmp_path / "findings.csv"
    write_csv_report(_report(_sample_findings()), output)

    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    assert list(rows[0].keys()) == list(CSV_COLUMNS)

    first = rows[0]
    assert first["rule_id"] == "M365.UNUSED_LICENSE_30D"
    assert first["surface"] == "m365"
    assert first["severity"] == "medium"
    assert first["confidence"] == "high"
    # Redacted principal must survive untouched.
    assert first["principal"] == "sha256:deadbeef"
    # None becomes empty string, not the literal "None".
    assert first["recommended_sku"] == ""
    assert first["evidence_ref"] == ""
    assert first["estimated_monthly_savings_usd"] == "36.0"
    # Evidence dict survives via JSON round-trip.
    assert json.loads(first["evidence_json"]) == {
        "days_inactive": 45,
        "signals": ["mailbox", "office"],
    }
    # Empty evidence becomes "{}", not "" — so consumers can always parse.
    assert json.loads(rows[1]["evidence_json"]) == {}


def test_uses_lf_line_terminator_for_determinism(tmp_path: Path) -> None:
    output = tmp_path / "findings.csv"
    write_csv_report(_report(_sample_findings()), output)
    raw = output.read_bytes()
    assert b"\r\n" not in raw
    assert raw.count(b"\n") == 3  # header + 2 findings


def test_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dir" / "findings.csv"
    write_csv_report(_report(_sample_findings()), output)
    assert output.exists()


def test_neutralises_csv_formula_injection(tmp_path: Path) -> None:
    """Tenant-controlled cells starting with formula prefixes get a `'`.

    Without this, opening the report in Excel / Sheets would evaluate
    crafted strings (e.g. ``=HYPERLINK(...)``) as formulas — a classic
    CSV-injection vector. Numeric cells must NOT be sanitised so a
    legitimate negative savings value still pivots as a number.
    """
    findings = [
        {
            "rule_id": "M365.UNUSED_LICENSE_30D",
            "surface": "m365",
            "severity": "low",
            "principal": '=HYPERLINK("http://evil/","click")',
            "current_sku": "+SPE_E3",
            "recommended_sku": "@admin",
            "estimated_monthly_savings_usd": -12.5,  # legit negative number
            "recommendation": "-rm -rf /",
            "evidence_ref": "\tinjected",
            "confidence": "low",
            "evidence": {"note": "=1+1"},  # JSON-wrapped → safe (starts with '{')
        }
    ]
    output = tmp_path / "findings.csv"
    write_csv_report(_report(findings), output)

    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    row = rows[0]
    # All four formula-trigger prefixes are neutralised on string cells.
    assert row["principal"].startswith("'=")
    assert row["current_sku"].startswith("'+")
    assert row["recommended_sku"].startswith("'@")
    assert row["recommendation"].startswith("'-")
    assert row["evidence_ref"].startswith("'\t")
    # Numeric values pass through unmodified — even when negative.
    assert row["estimated_monthly_savings_usd"] == "-12.5"
    # JSON-wrapped evidence is safe by construction (starts with `{`).
    assert json.loads(row["evidence_json"]) == {"note": "=1+1"}
