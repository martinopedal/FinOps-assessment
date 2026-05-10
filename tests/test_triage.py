"""Tests for advisory triage artefact generation."""

from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from finops_assess.reporters.triage_reporter import write_triage_csv, write_triage_json
from finops_assess.triage import TriageItem, build_triage


def _report(principal: str = "sha256:deadbeef") -> dict[str, object]:
    return {
        "run": {
            "tool": "finops-assess",
            "version": "0.1.0",
            "schema_version": "1.0",
            "generated_at": "2026-05-10T00:00:00+00:00",
            "input": "<redacted>/samples",
            "pii_redaction": True,
            "mode": "read-only",
        },
        "summary": {"total_findings": 1},
        "findings": [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "severity": "high",
                "principal": principal,
                "current_sku": "SPE_E3",
                "recommended_sku": None,
                "estimated_monthly_savings_usd": 36.0,
                "recommendation": "Consider reclaiming the unused license.",
                "evidence_ref": None,
                "confidence": "high",
                "evidence": {"days_inactive": 45},
            }
        ],
    }


def test_build_triage_preserves_redacted_principal_and_marks_advisory() -> None:
    report = build_triage(_report())

    assert report.run["mode"] == "advisory"
    assert report.run["pii_redaction"] is True
    assert report.items[0].principal == "sha256:deadbeef"
    assert report.items[0].advisory is True
    assert report.items[0].finding_ref.startswith("finding:")
    assert report.items[0].suggested_owner_role == "license-admin"


def test_triage_can_pass_through_unredacted_source_without_rehashing() -> None:
    source = _report("alice@example.com")
    source["run"]["pii_redaction"] = False  # type: ignore[index]
    report = build_triage(source)

    assert report.run["pii_redaction"] is False
    assert report.items[0].principal == "alice@example.com"


def test_advisory_false_is_rejected() -> None:
    item = build_triage(_report()).items[0].model_dump()
    item["advisory"] = False
    with pytest.raises(ValidationError):
        TriageItem.model_validate(item)


def test_build_triage_and_reporters_do_not_require_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(socket, "socket", fail_socket)
    report = build_triage(_report())
    write_triage_json(report, tmp_path / "triage.json")
    write_triage_csv(report, tmp_path / "triage.csv")

    assert (tmp_path / "triage.json").exists()
    assert (tmp_path / "triage.csv").exists()


def test_triage_output_is_deterministic(tmp_path: Path) -> None:
    report = build_triage(_report(), source_path=tmp_path / "report.json")
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_triage_json(report, a)
    write_triage_json(report, b)

    assert a.read_bytes() == b.read_bytes()
    payload = json.loads(a.read_text(encoding="utf-8"))
    assert payload["source"]["report_path"] == "<redacted>/report.json"


def test_triage_csv_has_stable_columns_and_lf(tmp_path: Path) -> None:
    path = tmp_path / "triage.csv"
    write_triage_csv(build_triage(_report()), path)

    raw = path.read_bytes()
    assert b"\r\n" not in raw
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["finding_ref"].startswith("finding:")
    assert rows[0]["priority_bucket"] == "p1"
    assert rows[0]["advisory"] == "True"


@pytest.mark.parametrize(
    ("severity", "confidence", "savings", "bucket"),
    [
        ("high", "high", 0, "p1"),
        ("high", "medium", 0, "p2"),
        ("medium", "high", 150, "p2"),
        ("medium", "high", 10, "p3"),
        ("low", "medium", 10, "p3"),
        ("low", "low", None, "p4"),
    ],
)
def test_priority_mapping(
    severity: str, confidence: str, savings: float | None, bucket: str
) -> None:
    source = _report()
    finding = source["findings"][0]  # type: ignore[index]
    finding["severity"] = severity
    finding["confidence"] = confidence
    finding["estimated_monthly_savings_usd"] = savings

    assert build_triage(source).items[0].priority_bucket == bucket
