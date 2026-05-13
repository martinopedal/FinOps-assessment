"""CliRunner integration test for ``--cleanup-orphans`` (Yuki PR #78 A-6).

Pre-existing ``test_playbook_cleanup_orphans.py`` covers the
library-level ``find_orphaned_jsonl`` helper.  This module exercises
the actual CLI flag plumbing in ``cli.py`` so a regression in the
flag wiring would be caught.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from finops_assess.cli import main


def _write_orphan(directory: Path) -> Path:
    """Drop a tempfile in ``directory`` that matches the .jsonl pattern but has no manifest."""
    fd, name = tempfile.mkstemp(prefix="orphan-", suffix=".jsonl", dir=str(directory))
    Path(name).write_text("orphan-row\n", encoding="utf-8")
    import os as _os

    _os.close(fd)
    return Path(name)


def test_cleanup_orphans_cli_removes_orphaned_jsonl(tmp_path: Path) -> None:
    """`finops-assess run ... --format playbook --cleanup-orphans` must remove orphans."""
    # Stage a CSV input directory matching the demo fixture shape.
    from finops_assess.demo import materialise_demo_data

    demo_input = materialise_demo_data(tmp_path / "demo")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    orphan = _write_orphan(out_dir)
    assert orphan.exists()

    out_jsonl = out_dir / "report.jsonl"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(demo_input),
            "--format",
            "playbook",
            "--playbook-output",
            str(out_jsonl),
            "--cleanup-orphans",
            "--skip-warnings",
        ],
    )
    assert result.exit_code == 0, f"CLI failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert not orphan.exists(), "Orphan should have been deleted by --cleanup-orphans"
    assert out_jsonl.exists(), "Playbook JSONL should have been written"
    manifest = out_jsonl.parent / (out_jsonl.name + ".manifest.json")
    assert manifest.exists(), "Manifest should have been written"
    # The CLI must report orphan removal on stderr.
    assert "orphan" in result.stderr.lower(), (
        f"Expected stderr mention of orphan removal; got: {result.stderr!r}"
    )
    # And the manifest must declare the new (honest) per-run stability.
    parsed = json.loads(manifest.read_text(encoding="utf-8"))
    assert parsed["pii_handling"]["mode"] == "salted_hash"
    stability = parsed["pii_handling"]["ticket_key_stability_by_surface"]
    assert stability["azure"] == "per_run"


def test_cleanup_orphans_cli_default_off_preserves_orphans(tmp_path: Path) -> None:
    """Without --cleanup-orphans the orphan must survive the run."""
    from finops_assess.demo import materialise_demo_data

    demo_input = materialise_demo_data(tmp_path / "demo")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    orphan = _write_orphan(out_dir)

    out_jsonl = out_dir / "report.jsonl"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--input",
            str(demo_input),
            "--format",
            "playbook",
            "--playbook-output",
            str(out_jsonl),
            "--skip-warnings",
        ],
    )
    assert result.exit_code == 0, f"CLI failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert orphan.exists(), "Orphan must survive when --cleanup-orphans is absent"
    assert out_jsonl.exists(), "Playbook JSONL should have been written"
