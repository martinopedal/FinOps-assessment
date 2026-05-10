"""CLI tests for `finops-assess triage`."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from finops_assess.cli import main

EXAMPLE_REPORT = Path(__file__).resolve().parents[1] / "examples" / "demo-report.json"


def test_triage_command_writes_json_and_csv(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        ["triage", "--input", str(EXAMPLE_REPORT), "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "advisory" in result.output.lower()
    assert (tmp_path / "triage.json").exists()
    assert (tmp_path / "triage.csv").exists()
    payload = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    assert payload["run"]["mode"] == "advisory"
    assert payload["summary"]["total_items"] == len(payload["items"])


def test_triage_rejects_no_pii_redaction_flag(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "triage",
            "--input",
            str(EXAMPLE_REPORT),
            "--output-dir",
            str(tmp_path),
            "--no-pii-redaction",
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_triage_copilot_helper_is_explicit_opt_in_and_gracefully_skips(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        main,
        [
            "triage",
            "--input",
            str(EXAMPLE_REPORT),
            "--output-dir",
            str(tmp_path),
            "--enable-copilot-helper",
            "--copilot-helper",
            "sdk",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    assert payload["run"]["copilot_helper"] in {"sdk", "unavailable"}
