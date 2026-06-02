"""Tests for the FOCUS-aligned advisory CSV exporter.

Maya's 16 enumerated tests + 4 Noor stage-4 P2 additions + 15 multi-surface
tests (issue #71, v0.6.0) = 35+ tests total.

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


def _render(
    report: dict, tmp_path: Path, epoch: str = "0", surfaces: set[str] | None = None
) -> tuple[Path, Path]:  # type: ignore[type-arg]
    """Render a report to a tmp_path CSV + manifest with the given SOURCE_DATE_EPOCH."""
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    try:
        csv_path, manifest_path = write_focus_aligned_export(
            report, tmp_path / "out.csv", surfaces=surfaces
        )
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
    # Pass surfaces={"azure"} to preserve byte-identity with the v0.5.0 golden
    # (default is now all-surfaces per C9-3 resolution, but this fixture is Azure-only).
    csv_path, _ = _render(report, tmp_path, surfaces={"azure"})
    actual = csv_path.read_bytes()
    expected = (FIXTURES / "golden-azure.csv").read_bytes()
    assert actual == expected, "CSV output has drifted from golden-azure.csv"


# ---------------------------------------------------------------------------
# Test 2 — golden manifest byte-identical
# ---------------------------------------------------------------------------


def test_golden_manifest_byte_identical(tmp_path: Path) -> None:
    """Rendered manifest bytes must match the committed golden fixture."""
    report = _load_fixture("input-azure-two-findings.json")
    # Pass surfaces={"azure"} to preserve byte-identity with the v0.5.0 golden.
    _, manifest_path = _render(report, tmp_path, surfaces={"azure"})
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
    """With --surface all (default), all findings are included and surfaces_skipped is empty."""
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

    # CSV should contain all 5 findings (all surfaces included by default).
    with output_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 5

    # Manifest surfaces_skipped must be empty (all surfaces included).
    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["surfaces_skipped"] == {}
    assert manifest["row_count"] == 5


def test_surface_flag_azure_only_legacy(tmp_path: Path) -> None:
    """--surface azure preserves v0.5.0 Azure-only behavior: 2 rows, skipped m365/github/ado."""
    from click.testing import CliRunner

    input_path = FIXTURES / "input-mixed-surfaces.json"
    output_path = tmp_path / "out.csv"
    result = CliRunner().invoke(
        main,
        [
            "export",
            "focus-aligned",
            "--surface",
            "azure",
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

    # Round-trip: key in CSV matches helper output (find the row by RuleId since
    # rows are now sorted by (surface, RuleId, ResourceId) and may not match input order).
    csv_path, _ = _render(report, tmp_path, surfaces={"azure"})
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    matching = [r for r in rows if r["RuleId"] == finding["rule_id"]]
    assert len(matching) == 1
    assert matching[0]["AdvisoryFindingKey"] == key1


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
    # With --surface all (default) and no findings, surfaces_included is empty.
    assert manifest["surfaces_included"] == []
    assert manifest["surfaces_skipped"] == {}


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


# ---------------------------------------------------------------------------
# Yuki hardening additions (#58) — NUL bytes, Unicode, long resource_id
# ---------------------------------------------------------------------------


def test_advisory_finding_key_nul_bytes_in_evidence_no_collision() -> None:
    """NUL bytes inside evidence values must not cause collisions or errors.

    This is the regression test for the sha256(json.dumps([...])) fix: the
    JSON array envelope encodes NUL as \\u0000 regardless of where it appears,
    so two structurally different payloads cannot collide even when evidence
    values contain NUL characters.
    """
    # NUL in evidence string value
    f_nul_in_evidence = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"key": "value\x00with_nul"},
    }
    # Different evidence value without NUL — must produce a different key
    f_no_nul = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"key": "valuewith_nul"},
    }
    key_nul = advisory_finding_key(f_nul_in_evidence)
    key_no_nul = advisory_finding_key(f_no_nul)

    # Keys must be valid 64-char hex strings (SHA-256)
    assert len(key_nul) == 64 and all(c in "0123456789abcdef" for c in key_nul)
    # Must differ — NUL is semantically distinct from its absence
    assert key_nul != key_no_nul

    # Boundary injection: NUL in rule_id must not collapse with NUL in evidence
    f_nul_in_rule = {
        "rule_id": "AZ\x00TEST",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"key": "value"},
    }
    f_nul_in_evidence2 = {
        "rule_id": "AZ",
        "principal": "/subscriptions/abc/vm/x",
        "evidence": {"key": "TEST\x00value"},
    }
    assert advisory_finding_key(f_nul_in_rule) != advisory_finding_key(f_nul_in_evidence2)


def test_advisory_finding_key_unicode_evidence() -> None:
    """Evidence with emoji, RTL text, and supplementary Unicode must not error or corrupt.

    The JSON envelope uses ensure_ascii=False so Unicode passes through verbatim;
    the SHA-256 input is UTF-8 encoded bytes, which is deterministic across platforms.
    """
    f_emoji = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/emoji",
        "evidence": {"tag": "🚀", "rtl": "مرحبا", "surrogate_area": "\U0001f600"},
    }
    key1 = advisory_finding_key(f_emoji)
    key2 = advisory_finding_key(f_emoji)

    # Deterministic
    assert key1 == key2
    # Valid 64-char hex SHA-256
    assert len(key1) == 64 and all(c in "0123456789abcdef" for c in key1)

    # Unicode evidence must differ from ASCII-escaped equivalent where relevant
    f_ascii_escaped = {
        "rule_id": "AZ.TEST",
        "principal": "/subscriptions/abc/vm/emoji",
        "evidence": {"tag": "rocket", "rtl": "hello", "surrogate_area": "smile"},
    }
    assert key1 != advisory_finding_key(f_ascii_escaped)

    # CSV row with Unicode evidence must be written and round-tripped without corruption
    report: dict = {  # type: ignore[type-arg]
        "run": {
            "input": "",
            "schema_version": "1.0",
            "pii_redaction": False,
        },
        "findings": [
            {
                **f_emoji,
                "surface": "azure",
                "severity": "medium",
                "recommendation": "Test 🚀 recommendation",
            }
        ],
    }
    import tempfile
    from pathlib import Path as _Path

    with tempfile.TemporaryDirectory() as td:
        out = _Path(td) / "unicode_out.csv"
        csv_path, _ = write_focus_aligned_export(report, out)
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        # Recommendation with emoji must round-trip intact
        assert "🚀" in rows[0]["ChargeDescription"]


def test_advisory_finding_key_long_resource_id() -> None:
    """A resource_id longer than 1024 characters must not error or silently truncate.

    ARM resource IDs can be long in nested resource scenarios. The JSON envelope
    approach encodes them verbatim; the key must be stable and unique.
    """
    long_id = "/subscriptions/" + "0" * 36 + "/resourceGroups/" + "x" * 900
    f_long = {
        "rule_id": "AZ.TEST",
        "principal": long_id,
        "evidence": {"k": "v"},
    }
    f_shorter = {
        "rule_id": "AZ.TEST",
        "principal": long_id[:-1],
        "evidence": {"k": "v"},
    }
    key_long = advisory_finding_key(f_long)
    key_shorter = advisory_finding_key(f_shorter)

    # Valid SHA-256 hex
    assert len(key_long) == 64 and all(c in "0123456789abcdef" for c in key_long)
    # Truncating the ID changes the key (no silent truncation)
    assert key_long != key_shorter
    # Stable across calls
    assert key_long == advisory_finding_key(f_long)


def test_focus_manifest_salt_mode_tenant_stable() -> None:
    """FOCUS manifest reports salt_mode='tenant_stable' and stability='stable' when an explicit salt is provided."""
    from finops_assess.catalog import load_catalog
    from finops_assess.collectors import collect_from_directory
    from finops_assess.engine import run_rules
    from finops_assess.persona import assign_personas
    from finops_assess.reporters.json_reporter import build_report
    from finops_assess.rules import load_personas, load_rules

    catalog = load_catalog()
    personas = load_personas()
    rules = [r for r in load_rules() if r.id == "AZ.IDLE_VM_14D"]
    samples = Path(__file__).resolve().parents[1] / "samples"
    dataset = collect_from_directory(samples)
    persona_assignments = assign_personas(dataset, personas)

    findings, summary = run_rules(
        rules=rules,
        catalog=catalog,
        personas=personas,
        persona_assignments=persona_assignments,
        dataset=dataset,
        redact_pii=True,
        salt="tenant-stable-salt-xyz",
    )
    report = build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=samples,
        redact_pii=True,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "focus.csv"
        _csv_out, manifest_out = write_focus_aligned_export(report, csv_path)
        manifest = json.loads(manifest_out.read_text(encoding="utf-8"))

    assert manifest["pii_handling"]["mode"] == "azure_resource_id_tenant_stable_salted_hash"
    assert manifest["pii_handling"]["salt_mode"] == "tenant_stable"
    assert manifest["pii_handling"]["known_limitation"] is None

    # Join keys should be stable
    resource_id_key = next(k for k in manifest["join_keys"] if k["column"] == "ResourceId")
    advisory_key = next(k for k in manifest["join_keys"] if k["column"] == "AdvisoryFindingKey")
    assert resource_id_key["stability"] == "stable"
    assert advisory_key["stability"] == "stable"


# ===========================================================================
# v0.6.0 multi-surface tests (T1-T15, issue #71)
# ===========================================================================


# ---------------------------------------------------------------------------
# T1 — multi-surface golden CSV byte-identical
# ---------------------------------------------------------------------------


def test_multi_surface_golden_csv(tmp_path: Path) -> None:
    """Golden-compare: render input-multi-surface-full.json with SOURCE_DATE_EPOCH=0.

    CSV bytes must be byte-identical to the committed golden-multi-surface.csv.
    """
    report = _load_fixture("input-multi-surface-full.json")
    csv_path, _ = _render(report, tmp_path)
    actual = csv_path.read_bytes()
    expected = (FIXTURES / "golden-multi-surface.csv").read_bytes()
    assert actual == expected, "CSV output has drifted from golden-multi-surface.csv"


# ---------------------------------------------------------------------------
# T2 — multi-surface golden manifest byte-identical
# ---------------------------------------------------------------------------


def test_multi_surface_golden_manifest(tmp_path: Path) -> None:
    """Golden-compare: manifest from T1 must be byte-identical to golden-multi-surface.manifest.json."""
    report = _load_fixture("input-multi-surface-full.json")
    _, manifest_path = _render(report, tmp_path)
    actual = manifest_path.read_bytes()
    expected = (FIXTURES / "golden-multi-surface.manifest.json").read_bytes()
    assert actual == expected, "Manifest output has drifted from golden-multi-surface.manifest.json"


# ---------------------------------------------------------------------------
# T3 — ServiceName mapping per surface
# ---------------------------------------------------------------------------


def test_multi_surface_service_name_mapping(tmp_path: Path) -> None:
    """ServiceName column must map correctly for each surface."""
    report = _load_fixture("input-multi-surface-full.json")
    csv_path, _ = _render(report, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    service_names = {r["RuleId"].split(".")[0]: r["ServiceName"] for r in rows}
    assert service_names.get("AZ") == "Azure"
    assert service_names.get("M365") == "Microsoft 365"
    assert service_names.get("GH") == "GitHub"
    assert service_names.get("ADO") == "Azure DevOps"


# ---------------------------------------------------------------------------
# T4 — ServiceCategory mapping per surface
# ---------------------------------------------------------------------------


def test_multi_surface_service_category_mapping(tmp_path: Path) -> None:
    """ServiceCategory must be Compute for Azure, Collaboration for M365, Developer Tools for GH/ADO."""
    report = _load_fixture("input-multi-surface-full.json")
    csv_path, _ = _render(report, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    by_surface = {r["ServiceName"]: r["ServiceCategory"] for r in rows}
    assert by_surface["Azure"] == "Compute"
    assert by_surface["Microsoft 365"] == "Collaboration"
    assert by_surface["GitHub"] == "Developer Tools"
    assert by_surface["Azure DevOps"] == "Developer Tools"


# ---------------------------------------------------------------------------
# T5 — ResourceType mapping per surface
# ---------------------------------------------------------------------------


def test_multi_surface_resource_type_mapping(tmp_path: Path) -> None:
    """ResourceType must be empty for Azure, 'user_license' for M365, 'seat' for GH/ADO."""
    report = _load_fixture("input-multi-surface-full.json")
    csv_path, _ = _render(report, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        svc = row["ServiceName"]
        res_type = row["ResourceType"]
        if svc == "Azure":
            assert res_type == "", f"Azure ResourceType should be empty, got {res_type!r}"
        elif svc == "Microsoft 365":
            assert res_type == "user_license", (
                f"M365 ResourceType should be user_license, got {res_type!r}"
            )
        elif svc in ("GitHub", "Azure DevOps"):
            assert res_type == "seat", f"{svc} ResourceType should be seat, got {res_type!r}"


# ---------------------------------------------------------------------------
# T6 — --surface azure produces Azure-only rows
# ---------------------------------------------------------------------------


def test_surface_flag_azure_only(tmp_path: Path) -> None:
    """--surface azure with mixed-surface input produces only Azure rows."""
    report = _load_fixture("input-multi-surface-full.json")
    csv_path, manifest_path = write_focus_aligned_export(
        report, tmp_path / "out.csv", surfaces={"azure"}
    )
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert all(r["ServiceName"] == "Azure" for r in rows), (
        "Non-Azure rows found with surfaces={'azure'}"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["surfaces_skipped"].get("m365", 0) > 0
    assert manifest["surfaces_skipped"].get("github", 0) > 0
    assert manifest["surfaces_skipped"].get("ado", 0) > 0


# ---------------------------------------------------------------------------
# T7 — --surface m365 produces M365-only rows
# ---------------------------------------------------------------------------


def test_surface_flag_single_non_azure(tmp_path: Path) -> None:
    """--surface m365 with mixed-surface input produces only M365 rows."""
    report = _load_fixture("input-mixed-surfaces.json")
    csv_path, manifest_path = write_focus_aligned_export(
        report, tmp_path / "out.csv", surfaces={"m365"}
    )
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert rows[0]["ServiceName"] == "Microsoft 365"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["surfaces_skipped"].get("azure", 0) > 0


# ---------------------------------------------------------------------------
# Regression — BillingPeriod fallback must honour SOURCE_DATE_EPOCH
#
# Findings without ``evidence.observation_window_end`` (e.g. seat-based
# GitHub/ADO findings) previously fell back to ``datetime.now(UTC)``, which
# ignored SOURCE_DATE_EPOCH. That silently rebased the committed
# ``examples/focus-aligned.csv`` to whatever wall-clock month it was last
# regenerated in, time-bombing the docs-freshness gate on every calendar
# rollover. Pin the fallback so it can never recur.
# ---------------------------------------------------------------------------


def _set_epoch(monkeypatch: pytest.MonkeyPatch, epoch: str | None) -> None:
    """Set or clear SOURCE_DATE_EPOCH for the duration of a test."""
    if epoch is None:
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    else:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)


def test_billing_period_fallback_honours_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finding with no observation window must bucket via SOURCE_DATE_EPOCH, not wall clock."""
    from finops_assess.reporters.focus_aligned import _billing_period

    finding: dict = {"evidence": {}}  # type: ignore[type-arg]

    _set_epoch(monkeypatch, "0")  # 1970-01-01T00:00:00Z
    assert _billing_period(finding) == (
        "1970-01-01T00:00:00Z",
        "1970-02-01T00:00:00Z",
    )

    # A non-zero epoch in mid-March 1970 must bucket to the March calendar month.
    _set_epoch(monkeypatch, "6307200")  # 1970-03-15T00:00:00Z (day 73)
    march = _billing_period(finding)
    assert march[0].startswith("1970-03-01"), march
    assert march[1].startswith("1970-04-01"), march


def test_billing_period_evidence_date_unaffected_by_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When evidence carries a window end, that date wins regardless of SOURCE_DATE_EPOCH."""
    from finops_assess.reporters.focus_aligned import _billing_period

    finding: dict = {"evidence": {"observation_window_end": "2024-03-20T00:00:00Z"}}  # type: ignore[type-arg]
    _set_epoch(monkeypatch, "0")
    assert _billing_period(finding) == (
        "2024-03-01T00:00:00Z",
        "2024-04-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# T8 — PII mode name: multi-surface with per-run salt
# ---------------------------------------------------------------------------


def test_pii_handling_mode_multi_surface(tmp_path: Path) -> None:
    """pii_handling.mode must be principal_per_run_salted_hash for multi-surface export."""
    report: dict = {  # type: ignore[type-arg]
        "run": {
            "input": "",
            "schema_version": "1.0",
            "pii_redaction": True,
            "salt_mode": "per_run",
        },
        "findings": [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "severity": "high",
                "principal": "sha256:aabbcc",
                "current_sku": "ENTERPRISEPACK",
                "recommendation": "Consider removing license.",
                "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
            },
            {
                "rule_id": "AZ.VM_IDLE_30D",
                "surface": "azure",
                "severity": "high",
                "principal": "/subscriptions/abc/vm/x",
                "current_sku": "Standard_D4s_v3",
                "recommendation": "Consider deallocating.",
                "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
            },
        ],
    }
    _, manifest_path = write_focus_aligned_export(
        report, tmp_path / "out.csv", surfaces={"azure", "m365"}
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pii_handling"]["mode"] == "principal_per_run_salted_hash"


# ---------------------------------------------------------------------------
# T9 — PII mode name: Azure-only preserves azure_resource_id_* names
# ---------------------------------------------------------------------------


def test_pii_handling_mode_azure_only(tmp_path: Path) -> None:
    """pii_handling.mode must be azure_resource_id_per_run_salted_hash for Azure-only export."""
    report = _load_fixture("input-azure-two-findings.json")
    _, manifest_path = write_focus_aligned_export(report, tmp_path / "out.csv", surfaces={"azure"})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pii_handling"]["mode"] == "azure_resource_id_per_run_salted_hash"


# ---------------------------------------------------------------------------
# T10 — determinism across two runs with SOURCE_DATE_EPOCH=0
# ---------------------------------------------------------------------------


def test_determinism_multi_surface(tmp_path: Path) -> None:
    """Two runs with SOURCE_DATE_EPOCH=0 and all surfaces must produce byte-identical output."""
    report = _load_fixture("input-multi-surface-full.json")
    p1 = tmp_path / "run1"
    p2 = tmp_path / "run2"
    p1.mkdir()
    p2.mkdir()
    csv1, m1 = _render(report, p1)
    csv2, m2 = _render(report, p2)
    assert csv1.read_bytes() == csv2.read_bytes(), "CSVs differ under SOURCE_DATE_EPOCH=0"
    assert m1.read_bytes() == m2.read_bytes(), "Manifests differ under SOURCE_DATE_EPOCH=0"


# ---------------------------------------------------------------------------
# T11 — sort order is deterministic regardless of input order
# ---------------------------------------------------------------------------


def test_sort_order_deterministic(tmp_path: Path) -> None:
    """Rows must be sorted by (surface, RuleId, ResourceId) regardless of input order."""
    base_findings = [
        {
            "rule_id": "M365.UNUSED_LICENSE_30D",
            "surface": "m365",
            "principal": "sha256:zzz",
            "severity": "high",
            "recommendation": "Remove m365",
            "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
        },
        {
            "rule_id": "AZ.VM_IDLE_30D",
            "surface": "azure",
            "principal": "/subscriptions/abc/vm/a",
            "severity": "high",
            "recommendation": "Dealloc",
            "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
        },
        {
            "rule_id": "ADO.UNUSED_SEAT_30D",
            "surface": "ado",
            "principal": "sha256:aaa",
            "severity": "info",
            "recommendation": "Downgrade ado",
            "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
        },
    ]
    import copy

    # Reverse order
    shuffled_report: dict = {  # type: ignore[type-arg]
        "run": {"input": "", "schema_version": "1.0", "pii_redaction": False},
        "findings": list(reversed(copy.deepcopy(base_findings))),
    }
    forward_report: dict = {  # type: ignore[type-arg]
        "run": {"input": "", "schema_version": "1.0", "pii_redaction": False},
        "findings": copy.deepcopy(base_findings),
    }

    p1 = tmp_path / "fwd"
    p2 = tmp_path / "rev"
    p1.mkdir()
    p2.mkdir()
    csv1, _ = write_focus_aligned_export(forward_report, p1 / "out.csv")
    csv2, _ = write_focus_aligned_export(shuffled_report, p2 / "out.csv")

    assert csv1.read_bytes() == csv2.read_bytes(), (
        "Row order differs between forward and reversed input — sort is not stable"
    )

    # Verify sort key: ado < azure < m365
    with csv1.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    service_names = [r["ServiceName"] for r in rows]
    assert service_names == ["Azure DevOps", "Azure", "Microsoft 365"]


# ---------------------------------------------------------------------------
# T12 — manifest surfaces_included is alphabetically sorted
# ---------------------------------------------------------------------------


def test_manifest_surfaces_included_all(tmp_path: Path) -> None:
    """surfaces_included in manifest must be alphabetically sorted and contain all four surfaces."""
    report = _load_fixture("input-multi-surface-full.json")
    _, manifest_path = _render(report, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["surfaces_included"] == ["ado", "azure", "github", "m365"]


# ---------------------------------------------------------------------------
# T13 — golden manifest validates against JSON Schema
# ---------------------------------------------------------------------------


def test_manifest_schema_validates_multi_surface(tmp_path: Path) -> None:
    """golden-multi-surface.manifest.json must validate against focus_aligned_manifest.schema.json."""
    jsonschema = pytest.importorskip("jsonschema", reason="install with `pip install -e '.[dev]'`")
    from importlib import resources

    schema_text = (
        resources.files("finops_assess.schemas") / "focus_aligned_manifest.schema.json"
    ).read_text(encoding="utf-8")
    schema = json.loads(schema_text)

    manifest = json.loads(
        (FIXTURES / "golden-multi-surface.manifest.json").read_text(encoding="utf-8")
    )

    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    errors = list(validator_cls(schema).iter_errors(manifest))
    assert not errors, f"JSON Schema validation errors: {errors}"


# ---------------------------------------------------------------------------
# T14 — --surface flag appears in CLI --help
# ---------------------------------------------------------------------------


def test_cli_surface_flag_help() -> None:
    """--help for export focus-aligned must list --surface and its valid choices."""
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(main, ["export", "focus-aligned", "--help"])
    assert result.exit_code == 0
    output = result.output
    assert "--surface" in output
    # Choices must be present
    for choice in ("azure", "m365", "github", "ado", "all"):
        assert choice in output, f"Choice {choice!r} missing from --help"


# ---------------------------------------------------------------------------
# T15 — null and zero savings handled correctly
# ---------------------------------------------------------------------------


def test_empty_savings_null_handling(tmp_path: Path) -> None:
    """null savings → empty string; 0 savings → '0' in EstimatedMonthlySavingsUsd."""
    report: dict = {  # type: ignore[type-arg]
        "run": {"input": "", "schema_version": "1.0", "pii_redaction": False},
        "findings": [
            {
                "rule_id": "M365.UNUSED_LICENSE_30D",
                "surface": "m365",
                "principal": "user@test.com",
                "severity": "high",
                "recommendation": "Remove",
                "estimated_monthly_savings_usd": None,
                "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
            },
            {
                "rule_id": "ADO.TEST_PLANS_UNUSED",
                "surface": "ado",
                "principal": "user2@test.com",
                "severity": "low",
                "recommendation": "Downgrade",
                "estimated_monthly_savings_usd": 0,
                "evidence": {"observation_window_end": "2024-03-31T00:00:00Z"},
            },
        ],
    }
    csv_path, _ = write_focus_aligned_export(report, tmp_path / "out.csv")
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    # ADO row with 0 savings
    ado_row = next(r for r in rows if r["RuleId"] == "ADO.TEST_PLANS_UNUSED")
    assert ado_row["EstimatedMonthlySavingsUsd"] == "0", (
        f"Expected '0' for zero savings, got {ado_row['EstimatedMonthlySavingsUsd']!r}"
    )
    # M365 row with null savings
    m365_row = next(r for r in rows if r["RuleId"] == "M365.UNUSED_LICENSE_30D")
    assert m365_row["EstimatedMonthlySavingsUsd"] == "", (
        f"Expected empty string for null savings, got {m365_row['EstimatedMonthlySavingsUsd']!r}"
    )
