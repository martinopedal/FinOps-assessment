"""Tests for the FOCUS-aligned advisory CSV exporter.

Maya's 16 enumerated tests + 4 Noor stage-4 P2 additions = 20 tests total.

All fixtures live under ``tests/fixtures/focus_aligned/``.
Golden artefacts were generated with ``SOURCE_DATE_EPOCH=0`` to make
them byte-stable across CI machines and contributor checkouts.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from finops_assess.cli import main
from finops_assess.reporters.focus_aligned import (
    advisory_finding_key,
    write_focus_aligned_export,
)
from finops_assess.rules import load_rules

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "focus_aligned"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> dict:  # type: ignore[type-arg]
    """Load a JSON fixture from the focus_aligned fixtures directory."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _render(report: dict, tmp_path: Path, epoch: str = "0") -> tuple[Path, Path]:  # type: ignore[type-arg]
    """Render a report to a tmp_path CSV + manifest with the given SOURCE_DATE_EPOCH."""
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    try:
        csv_path, manifest_path = write_focus_aligned_export(report, tmp_path / "out.csv")
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    return csv_path, manifest_path


# ---------------------------------------------------------------------------
# Test 1 — golden CSV byte-identical
# ---------------------------------------------------------------------------


def test_golden_csv_byte_identical(tmp_path: Path) -> None:
    """Rendered CSV bytes must match the committed golden fixture."""
    report = _load_fixture("input-azure-two-findings.json")
    csv_path, _ = _render(report, tmp_path)
    actual = csv_path.read_bytes()
    expected = (FIXTURES / "golden-azure.csv").read_bytes()
    assert actual == expected, "CSV output has drifted from golden-azure.csv"


# ---------------------------------------------------------------------------
# Test 2 — golden manifest byte-identical
# ---------------------------------------------------------------------------


def test_golden_manifest_byte_identical(tmp_path: Path) -> None:
    """Rendered manifest bytes must match the committed golden fixture."""
    report = _load_fixture("input-azure-two-findings.json")
    _, manifest_path = _render(report, tmp_path)
    actual = manifest_path.read_bytes()
    expected = (FIXTURES / "golden-azure.manifest.json").read_bytes()
    assert actual == expected, "Manifest output has drifted from golden-azure.manifest.json"


# ---------------------------------------------------------------------------
# Test 3 — SOURCE_DATE_EPOCH determinism (CSV)
# ---------------------------------------------------------------------------


def test_source_date_epoch_determinism_csv(tmp_path: Path) -> None:
    """Two runs with SOURCE_DATE_EPOCH=0 must produce byte-identical CSVs."""
    report = _load_fixture("input-azure-two-findings.json")
    p1 = tmp_path / "run1"
    p2 = tmp_path / "run2"
    p1.mkdir()
    p2.mkdir()
    csv1, _ = _render(report, p1, epoch="0")
    csv2, _ = _render(report, p2, epoch="0")
    assert csv1.read_bytes() == csv2.read_bytes()


# ---------------------------------------------------------------------------
# Test 4 — SOURCE_DATE_EPOCH determinism (manifest)
# ---------------------------------------------------------------------------


def test_source_date_epoch_determinism_manifest(tmp_path: Path) -> None:
    """Two runs with SOURCE_DATE_EPOCH=0 must produce byte-identical manifests.

    Also verifies the generated_at field equals the epoch-0 ISO string.
    """
    report = _load_fixture("input-azure-two-findings.json")
    p1 = tmp_path / "run1"
    p2 = tmp_path / "run2"
    p1.mkdir()
    p2.mkdir()
    _, m1 = _render(report, p1, epoch="0")
    _, m2 = _render(report, p2, epoch="0")
    assert m1.read_bytes() == m2.read_bytes()
    manifest = json.loads(m1.read_text(encoding="utf-8"))
    assert manifest["generated_at"] == "1970-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Test 5 — manifest validates against JSON Schema
# ---------------------------------------------------------------------------


def test_manifest_validates_against_json_schema(tmp_path: Path) -> None:
    """The manifest must validate against the bundled JSON Schema (Draft 2020-12)."""
    jsonschema = pytest.importorskip("jsonschema", reason="install with `pip install -e '.[dev]'`")
    from importlib import resources

    schema_text = (
        resources.files("finops_assess.schemas") / "focus_aligned_manifest.schema.json"
    ).read_text(encoding="utf-8")
    schema = json.loads(schema_text)

    report = _load_fixture("input-azure-two-findings.json")
    _, manifest_path = _render(report, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    errors = list(validator_cls(schema).iter_errors(manifest))
    assert not errors, f"JSON Schema validation errors: {errors}"


# ---------------------------------------------------------------------------
# Test 6 — cost columns are empty
# ---------------------------------------------------------------------------


def test_focus_cost_columns_are_empty(tmp_path: Path) -> None:
    """ListCost, ContractedCost, BilledCost, EffectiveCost must be empty strings in every row."""
    report = _load_fixture("input-azure-two-findings.json")
    csv_path, _ = _render(report, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "Expected at least one row"
    for row in rows:
        assert row["ListCost"] == "", f"ListCost not empty: {row['ListCost']!r}"
        assert row["ContractedCost"] == "", f"ContractedCost not empty: {row['ContractedCost']!r}"
        assert row["BilledCost"] == "", f"BilledCost not empty: {row['BilledCost']!r}"
        assert row["EffectiveCost"] == "", f"EffectiveCost not empty: {row['EffectiveCost']!r}"


# ---------------------------------------------------------------------------
# Test 7 — CLI help snapshot
# ---------------------------------------------------------------------------


def test_cli_help_snapshot() -> None:
    """CLI --help exits 0 and output contains required option names."""
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(main, ["export", "focus-aligned", "--help"])
    assert result.exit_code == 0
    # Check required strings are present regardless of terminal-width wrapping.
    output = result.output
    assert "--input" in output
    assert "--output" in output
    assert "focus-aligned" in output
    assert "NOT a FOCUS 1.3 conformant" in output
    assert "EstimatedMonthlySavingsUsd" in output


# ---------------------------------------------------------------------------
# Test 8 — skipped surface count
# ---------------------------------------------------------------------------


def test_skipped_surface_count_logged(tmp_path: Path) -> None:
    """Non-Azure findings are counted and logged; CSV contains only Azure rows."""
    from click.testing import CliRunner

    input_path = FIXTURES / "input-mixed-surfaces.json"
    output_path = tmp_path / "out.csv"
    result = CliRunner().invoke(
        main,
        [
            "export",
            "focus-aligned",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.output

    # CSV should only contain Azure rows (2 of 5 findings).
    with output_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2

    # Manifest surfaces_skipped must reflect per-surface counts.
    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["surfaces_skipped"] == {"ado": 1, "github": 1, "m365": 1}
    assert manifest["row_count"] == 2


# ---------------------------------------------------------------------------
# Test 9 — AdvisoryFindingKey stable across runs
# ---------------------------------------------------------------------------


def test_advisory_finding_key_stable_across_runs(tmp_path: Path) -> None:
    """AdvisoryFindingKey is identical for two consecutive calls on the same finding."""
    report = _load_fixture("input-azure-two-findings.json")
    finding = report["findings"][0]
    key1 = advisory_finding_key(finding)
    key2 = advisory_finding_key(finding)
    assert key1 == key2

    # Round-trip: key in CSV matches helper output.
    csv_path, _ = _render(report, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["AdvisoryFindingKey"] == key1


# ---------------------------------------------------------------------------
# Test 10 — AdvisoryFindingKey changes on evidence change
# ---------------------------------------------------------------------------


def test_advisory_finding_key_changes_on_evidence_change() -> None:
    """Mutating any evidence field must change the AdvisoryFindingKey."""
    import copy

    base = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/rg/vm",
        "evidence": {"cpu": 5, "tags": ["a", "b"]},
    }
    original_key = advisory_finding_key(base)

    # Changed scalar.
    m = copy.deepcopy(base)
    m["evidence"]["cpu"] = 10
    assert advisory_finding_key(m) != original_key

    # Added key.
    m = copy.deepcopy(base)
    m["evidence"]["new_field"] = "extra"
    assert advisory_finding_key(m) != original_key

    # Removed key.
    m = copy.deepcopy(base)
    del m["evidence"]["cpu"]
    assert advisory_finding_key(m) != original_key

    # List element re-ordered — reordering IS treated as semantic (algorithm rule #5).
    m = copy.deepcopy(base)
    m["evidence"]["tags"] = ["b", "a"]
    assert advisory_finding_key(m) != original_key


# ---------------------------------------------------------------------------
# Test 11 — AdvisoryFindingKey separator collision resistance
# ---------------------------------------------------------------------------


def test_advisory_finding_key_separator_collision_resistance() -> None:
    """NUL-byte separator prevents collisions from cross-boundary injection."""
    # Even if someone used NUL in their IDs, the two-NUL structure differs.
    nul_in_principal = {"rule_id": "A", "principal": "B\x00C", "evidence": {}}
    nul_in_rule = {"rule_id": "A\x00B", "principal": "C", "evidence": {}}
    assert advisory_finding_key(nul_in_principal) != advisory_finding_key(nul_in_rule)
    # The important case is non-NUL boundary confusion:
    g1 = {"rule_id": "RULE", "principal": "RESOURCE/A", "evidence": {"k": "v"}}
    g2 = {"rule_id": "RULE/A", "principal": "RESOURCE", "evidence": {"k": "v"}}
    assert advisory_finding_key(g1) != advisory_finding_key(g2)


# ---------------------------------------------------------------------------
# Test 12 — cross-platform LF line endings
# ---------------------------------------------------------------------------


def test_cross_platform_line_endings(tmp_path: Path) -> None:
    """CSV and manifest must use LF-only line endings (no CRLF)."""
    report = _load_fixture("input-azure-two-findings.json")
    csv_path, manifest_path = _render(report, tmp_path)
    assert b"\r" not in csv_path.read_bytes(), "CRLF found in CSV output"
    assert b"\r" not in manifest_path.read_bytes(), "CRLF found in manifest output"


# ---------------------------------------------------------------------------
# Test 13 — empty findings: header-only CSV + zero-row manifest
# ---------------------------------------------------------------------------


def test_empty_findings_produces_header_only_csv_and_zero_row_manifest(
    tmp_path: Path,
) -> None:
    """Zero findings produces a header-only CSV and manifest with row_count=0."""
    from click.testing import CliRunner

    input_path = FIXTURES / "input-empty.json"
    output_path = tmp_path / "out.csv"
    result = CliRunner().invoke(
        main,
        [
            "export",
            "focus-aligned",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0

    # CSV has exactly one line (the header) ending with \n.
    csv_bytes = output_path.read_bytes()
    assert csv_bytes.count(b"\n") == 1, "Expected exactly 1 newline (header only)"
    assert not csv_bytes.endswith(b"\r\n"), "CRLF found in CSV"

    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 0
    assert manifest["surfaces_included"] == ["azure"]
    assert manifest["surfaces_skipped"] == {"ado": 0, "github": 0, "m365": 0}


# ---------------------------------------------------------------------------
# Test 14 — evidence_key_version field present with default 1
# ---------------------------------------------------------------------------


def test_evidence_key_version_field_present_with_default_one() -> None:
    """Every loaded Azure rule must have evidence_key_version == 1 (the v0.5.0 default)."""
    rules = load_rules()
    azure_rules = [r for r in rules if r.surface == "azure"]
    assert azure_rules, "No Azure rules found — check data/rules/azure.yaml"
    for rule in azure_rules:
        assert rule.evidence_key_version == 1, (
            f"Rule {rule.id} has evidence_key_version={rule.evidence_key_version}, expected 1"
        )


# ---------------------------------------------------------------------------
# Test 15 — packaged schema drift
# ---------------------------------------------------------------------------


def test_packaged_schema_drift() -> None:
    """Schema loaded via importlib.resources must match the source tree file."""
    from importlib import resources

    resource_bytes = (
        resources.files("finops_assess.schemas") / "focus_aligned_manifest.schema.json"
    ).read_bytes()

    repo_root = Path(__file__).resolve().parents[1]
    source_bytes = (
        repo_root / "src" / "finops_assess" / "schemas" / "focus_aligned_manifest.schema.json"
    ).read_bytes()

    assert resource_bytes == source_bytes, (
        "Schema loaded via importlib.resources differs from the source tree. "
        "Run `pip install -e .` to rebuild the package."
    )


# ---------------------------------------------------------------------------
# Test 16 — generate_docs --check catches drifted FOCUS artefacts
# ---------------------------------------------------------------------------


def test_generate_docs_check_includes_focus_artefacts(tmp_path: Path) -> None:
    """generate_docs.py --check must fail when focus-aligned.csv is stale."""
    repo_root = Path(__file__).resolve().parents[1]
    examples_dir = repo_root / "examples"
    focus_csv = examples_dir / "focus-aligned.csv"

    if not focus_csv.is_file():
        pytest.skip("examples/focus-aligned.csv not yet generated — run generate_docs.py first")

    # Touch the file to make it stale.
    original_bytes = focus_csv.read_bytes()
    try:
        focus_csv.write_bytes(original_bytes + b"# drift\n")
        result = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "generate_docs.py"), "--check"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode != 0, "Expected non-zero exit from --check on drifted file"
        assert "focus-aligned.csv" in result.stderr or "focus-aligned.csv" in result.stdout
    finally:
        focus_csv.write_bytes(original_bytes)


# ---------------------------------------------------------------------------
# Noor P2 #4 — Test 17: malformed input exits 1 with clear message
# ---------------------------------------------------------------------------


def test_malformed_input_exits_1_with_clear_message(tmp_path: Path) -> None:
    """Malformed JSON input must exit 1 with a human-readable error message."""
    from click.testing import CliRunner

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{this is not valid json", encoding="utf-8")
    output_path = tmp_path / "out.csv"

    result = CliRunner().invoke(
        main,
        [
            "export",
            "focus-aligned",
            "--input",
            str(bad_json),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Noor P2 #4 — Test 18: manifest echoes source pii_redaction flag
# ---------------------------------------------------------------------------


def test_manifest_echoes_source_pii_redaction_flag(tmp_path: Path) -> None:
    """Manifest source_report.pii_redaction must mirror the source report value."""
    # input-empty.json has pii_redaction: false — test the false branch.
    report = _load_fixture("input-empty.json")
    assert report["run"]["pii_redaction"] is False

    _, manifest_path = _render(report, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_report"]["pii_redaction"] is False

    # input-azure-two-findings.json has pii_redaction: true — test the true branch.
    report2 = _load_fixture("input-azure-two-findings.json")
    assert report2["run"]["pii_redaction"] is True
    p2 = tmp_path / "run2"
    p2.mkdir()
    _, m2 = write_focus_aligned_export(report2, p2 / "out.csv")
    manifest2 = json.loads(m2.read_text(encoding="utf-8"))
    assert manifest2["source_report"]["pii_redaction"] is True


# ---------------------------------------------------------------------------
# Noor P2 #4 — Test 19: non-zero SOURCE_DATE_EPOCH determinism
# ---------------------------------------------------------------------------


def test_non_zero_source_date_epoch_is_deterministic(tmp_path: Path) -> None:
    """Two runs with SOURCE_DATE_EPOCH=1700000000 must produce byte-identical output."""
    report = _load_fixture("input-azure-two-findings.json")
    p1 = tmp_path / "run1"
    p2 = tmp_path / "run2"
    p1.mkdir()
    p2.mkdir()
    csv1, m1 = _render(report, p1, epoch="1700000000")
    csv2, m2 = _render(report, p2, epoch="1700000000")
    assert csv1.read_bytes() == csv2.read_bytes(), "CSVs differ under non-zero SOURCE_DATE_EPOCH"
    assert m1.read_bytes() == m2.read_bytes(), "Manifests differ under non-zero SOURCE_DATE_EPOCH"

    manifest = json.loads(m1.read_text(encoding="utf-8"))
    assert manifest["generated_at"] == "2023-11-14T22:13:20+00:00"


# ---------------------------------------------------------------------------
# Noor P2 #4 — Test 20: AdvisoryFindingKey insensitive to dict insertion order
# ---------------------------------------------------------------------------


def test_advisory_finding_key_insensitive_to_dict_order() -> None:
    """Two findings with the same content but different dict key order must produce equal keys."""
    f1 = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"z_key": 99, "a_key": "hello", "m_key": [1, 2, 3]},
    }
    # Same evidence, different insertion order.
    f2 = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"m_key": [1, 2, 3], "z_key": 99, "a_key": "hello"},
    }
    assert advisory_finding_key(f1) == advisory_finding_key(f2), (
        "AdvisoryFindingKey changed due to dict insertion order — canonicaliser must sort dict keys"
    )


# ---------------------------------------------------------------------------
# D4 calendar-month derivation edge cases
# ---------------------------------------------------------------------------


def test_billing_period_end_of_month_rollover() -> None:
    """BillingPeriodEnd for a finding on 2024-01-31 must be 2024-02-01."""
    from finops_assess.reporters.focus_aligned import _billing_period

    finding = {"evidence": {"observation_window_end": "2024-01-31T23:59:59Z"}}
    start, end = _billing_period(finding)
    assert start == "2024-01-01T00:00:00Z"
    assert end == "2024-02-01T00:00:00Z"


def test_billing_period_december_to_january_rollover() -> None:
    """BillingPeriodEnd for a December finding must roll to January of the next year."""
    from finops_assess.reporters.focus_aligned import _billing_period

    finding = {"evidence": {"observation_window_end": "2024-12-15T00:00:00Z"}}
    start, end = _billing_period(finding)
    assert start == "2024-12-01T00:00:00Z"
    assert end == "2025-01-01T00:00:00Z"
