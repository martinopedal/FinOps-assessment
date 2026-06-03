#!/usr/bin/env python3
"""Generate PowerShell FOCUS conformance goldens (Phase 5e)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from finops_assess.catalog import load_catalog  # noqa: E402
from finops_assess.collectors import collect_from_directory  # noqa: E402
from finops_assess.engine import run_rules  # noqa: E402
from finops_assess.persona import assign_personas  # noqa: E402
from finops_assess.reporters.focus_aligned import write_focus_aligned_export  # noqa: E402
from finops_assess.reporters.json_reporter import build_report  # noqa: E402
from finops_assess.rules import load_personas, load_rules  # noqa: E402

SAMPLES_DIR = _REPO_ROOT / "samples"
FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
FOCUS_CSV_GOLDEN = FIXTURE_DIR / "demo-focus.csv"
FOCUS_MANIFEST_GOLDEN = FIXTURE_DIR / "demo-focus.csv.manifest.json"

FIXED_SALT = "conformance-fixed-salt-v1"
FIXED_NOW = "2025-06-01"


def _build_samples_report() -> dict:
    dataset = collect_from_directory(SAMPLES_DIR)
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    persona_assignments = assign_personas(dataset, personas)
    findings, summary = run_rules(
        rules=rules,
        catalog=catalog,
        personas=personas,
        persona_assignments=persona_assignments,
        dataset=dataset,
        redact_pii=True,
        salt=FIXED_SALT,
    )
    return build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=SAMPLES_DIR,
        redact_pii=True,
    )


def regenerate() -> dict[Path, str]:
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    previous_now = os.environ.get("FINOPS_NOW_OVERRIDE")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    os.environ["FINOPS_NOW_OVERRIDE"] = FIXED_NOW
    scratch_dir = _REPO_ROOT / "scripts" / "_focus_fixture_tmp"
    scratch_csv = scratch_dir / "focus.csv"
    try:
        source_report = _build_samples_report()
        scratch_dir.mkdir(parents=True, exist_ok=True)
        csv_path, manifest_path = write_focus_aligned_export(source_report, scratch_csv)
        focus_csv = csv_path.read_text(encoding="utf-8")
        focus_manifest = manifest_path.read_text(encoding="utf-8")
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
        if previous_now is None:
            os.environ.pop("FINOPS_NOW_OVERRIDE", None)
        else:
            os.environ["FINOPS_NOW_OVERRIDE"] = previous_now
        if scratch_csv.exists():
            scratch_csv.unlink()
        scratch_manifest = scratch_csv.parent / (scratch_csv.name + ".manifest.json")
        if scratch_manifest.exists():
            scratch_manifest.unlink()
        if scratch_dir.exists() and not any(scratch_dir.iterdir()):
            scratch_dir.rmdir()
    return {FOCUS_CSV_GOLDEN: focus_csv, FOCUS_MANIFEST_GOLDEN: focus_manifest}


def _check() -> int:
    expected = regenerate()
    stale: list[Path] = []
    for path, contents in expected.items():
        if not path.exists() or path.read_bytes() != contents.encode("utf-8"):
            stale.append(path)
    if stale:
        for path in stale:
            rel = path.relative_to(_REPO_ROOT)
            print(f"stale: {rel}; run python scripts/generate_ps_focus_fixtures.py")
        return 1
    print("ok: focus fixtures are up-to-date")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        return _check()

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for path, contents in regenerate().items():
        path.write_text(contents, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
