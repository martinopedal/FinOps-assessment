"""Tests for the playbook reporter — core smoke tests.

Generative parametrize over every shipped rule_id ensures each template
renders without error, produces non-empty required fields, and conforms to
the row schema contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from finops_assess.reporters.playbook import PlaybookTemplateNotFoundError, render_row
from finops_assess.rules import load_rules

RULES = load_rules()
RULE_IDS = [r.id for r in RULES]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_finding(rule_id: str, surface: str, severity: str) -> dict[str, Any]:
    """Build a minimal finding dict for the given rule, with empty evidence."""
    return {
        "rule_id": rule_id,
        "surface": surface,
        "severity": severity,
        "principal": "sha256:cafebabe000000000000000000000000cafebabe000000000000000000000000",
        "current_sku": "MOCK_SKU",
        "recommended_sku": "MOCK_SKU_LOWER",
        "estimated_monthly_savings_usd": 10.0,
        "recommendation": "Advisory test.",
        "evidence_ref": None,
        "confidence": "high",
        "evidence": {},
    }


# ---------------------------------------------------------------------------
# Test 1 — smoke: every shipped template renders without error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_render_row_smoke(rule_id: str) -> None:
    """Rendering a minimal finding for every shipped rule must not raise."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)
    assert isinstance(row, dict)


# ---------------------------------------------------------------------------
# Test 2 — required fields are present and non-empty in every row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_render_row_required_fields(rule_id: str) -> None:
    """Every rendered row must carry non-empty title, description, steps, checklist."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)

    assert row["playbook_schema_version"] == "0.1"
    assert row["ticket_key"].startswith("sha256:")
    assert len(row["ticket_key"]) == 64 + 7  # "sha256:" + 64 hex chars
    assert row["finding_revision"] == 1
    assert row["title"], f"title is empty for {rule_id}"
    assert row["description"], f"description is empty for {rule_id}"
    assert len(row["remediation_steps"]) >= 1, f"no remediation_steps for {rule_id}"
    assert len(row["verification_checklist"]) >= 1, f"no verification_checklist for {rule_id}"
    assert isinstance(row["references"], list)


# ---------------------------------------------------------------------------
# Test 3 — ticket_key is a valid sha256: prefixed hex string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_ticket_key_format(rule_id: str) -> None:
    """ticket_key must match the sha256:<64-hex-chars> pattern."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)
    key = row["ticket_key"]
    assert key.startswith("sha256:"), f"{rule_id}: ticket_key={key!r} does not start with sha256:"
    hex_part = key[7:]
    assert len(hex_part) == 64, f"{rule_id}: hex part len={len(hex_part)}"
    assert all(c in "0123456789abcdef" for c in hex_part), f"{rule_id}: non-hex in ticket_key"


# ---------------------------------------------------------------------------
# Test 4 — template_render_inputs is a sorted list of strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_template_render_inputs_sorted(rule_id: str) -> None:
    """template_render_inputs must be a sorted list of non-empty strings."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)
    inputs = row["template_render_inputs"]
    assert isinstance(inputs, list)
    assert all(isinstance(s, str) and s for s in inputs)
    assert inputs == sorted(inputs), f"{rule_id}: template_render_inputs not sorted: {inputs}"


# ---------------------------------------------------------------------------
# Test 5 — adapter_hints present with expected sub-dicts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_adapter_hints_structure(rule_id: str) -> None:
    """adapter_hints must contain servicenow, jira, and github sub-dicts."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)
    hints = row["adapter_hints"]
    assert "servicenow" in hints
    assert "jira" in hints
    assert "github" in hints
    assert isinstance(hints["servicenow"]["urgency"], int)
    assert isinstance(hints["jira"]["labels"], list)


# ---------------------------------------------------------------------------
# Test 6 — missing template raises PlaybookTemplateNotFoundError
# ---------------------------------------------------------------------------


def test_missing_template_raises() -> None:
    """render_row must raise PlaybookTemplateNotFoundError for an unknown rule_id."""
    finding = _minimal_finding("NONEXISTENT.RULE_ID", "azure", "high")
    with pytest.raises(PlaybookTemplateNotFoundError) as exc_info:
        render_row(finding)
    assert "NONEXISTENT.RULE_ID" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 7 — surface field is preserved in the row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_surface_in_row(rule_id: str) -> None:
    """Row surface must match the finding's surface."""
    rule = next(r for r in RULES if r.id == rule_id)
    finding = _minimal_finding(rule_id, rule.surface, rule.severity)
    row = render_row(finding)
    assert row["surface"] == rule.surface


# ---------------------------------------------------------------------------
# Test 8 — write_playbook_export round-trip with all rules
# ---------------------------------------------------------------------------


def test_write_playbook_export_all_rules(tmp_path: Path) -> None:
    """write_playbook_export with one finding per rule must produce a valid JSONL + manifest."""
    import os

    from finops_assess.reporters.playbook import write_playbook_export

    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        findings = []
        for rule in RULES:
            findings.append(_minimal_finding(rule.id, rule.surface, rule.severity))

        report: dict[str, Any] = {
            "run": {
                "tool": "finops-assess",
                "version": "0.1.0",
                "schema_version": "1.0",
                "generated_at": "1970-01-01T00:00:00+00:00",
                "pii_redaction": True,
                "mode": "read-only",
                "input": "<test>",
            },
            "findings": findings,
        }

        out = tmp_path / "playbook.jsonl"
        jsonl_path, manifest_path = write_playbook_export(report, out, skip_warnings=True)

        assert jsonl_path.exists()
        assert manifest_path.exists()

        rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == len(RULES)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["row_count"] == len(RULES)
        assert manifest["output_artifacts"]["jsonl_sha256"]
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)


# ---------------------------------------------------------------------------
# Test 9 — rows are sorted by (surface, rule_id, ticket_key, evidence_ref)
# ---------------------------------------------------------------------------


def test_rows_are_sorted(tmp_path: Path) -> None:
    """Rows in the JSONL must be sorted by (surface, rule_id, ticket_key, evidence_ref)."""
    import os

    from finops_assess.reporters.playbook import _sort_key, write_playbook_export

    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        findings = [_minimal_finding(r.id, r.surface, r.severity) for r in RULES]
        report: dict[str, Any] = {
            "run": {
                "tool": "finops-assess",
                "version": "0.1.0",
                "schema_version": "1.0",
                "generated_at": "1970-01-01T00:00:00+00:00",
                "pii_redaction": True,
                "mode": "read-only",
                "input": "<test>",
            },
            "findings": findings,
        }
        out = tmp_path / "playbook.jsonl"
        jsonl_path, _ = write_playbook_export(report, out, skip_warnings=True)
        rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        keys = [_sort_key(r) for r in rows]
        assert keys == sorted(keys), "Rows are not in sort-key order"
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
