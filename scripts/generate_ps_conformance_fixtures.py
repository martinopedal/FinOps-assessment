"""Regenerate the cross-engine normalise-core conformance golden fixture.

The native PowerShell engine (``powershell/FinOpsAssess``) reimplements the
offline CSV normaliser
(:func:`finops_assess.collectors.csv_collector.collect_from_directory`).
To prove **layer-2** of the conformance contract (docs/plan.md §5a -- "same
normalised dataset"), we commit a golden JSON snapshot of the Python
engine's normalised view of the bundled demo tenant. A Pester test
(``powershell/tests/Get-FinOpsNormalizedDataset.Tests.ps1``) runs the
PowerShell normaliser over the *same* demo directory and deep-compares
(type-aware: numbers as numbers) against this golden, so any divergence at
the source -- before any rule fires -- fails CI.

Python is the oracle: the golden is ``collect_from_directory(demo)`` dumped
with :meth:`pydantic.BaseModel.model_dump` (JSON mode) so it carries the
fully validated, defaulted record shapes.

Determinism / drift gate
------------------------
Output is byte-stable: UTF-8, LF newlines, two-space indent, sorted object
keys, single trailing newline. List order (CSV row order) is preserved.
``tests/test_ps_conformance_fixtures.py`` regenerates in memory and fails on
any drift, so a PR that changes the demo CSVs or the normalised models must
regenerate and commit this fixture.

Usage
-----
::

    python scripts/generate_ps_conformance_fixtures.py            # write
    python scripts/generate_ps_conformance_fixtures.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finops_assess.collectors.csv_collector import collect_from_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "src" / "finops_assess" / "demo"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
FIXTURE_FILE = "demo-normalised.json"


def build_golden(demo_dir: Path | None = None) -> str:
    """Serialise the normalised demo dataset to canonical, byte-stable JSON."""
    dataset = collect_from_directory(demo_dir or DEMO_DIR)
    payload = dataset.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_if_changed(path: Path, contents: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = contents.encode("utf-8")
    if path.is_file() and path.read_bytes() == encoded:
        return False
    # newline="" so the explicit "\n" is not re-translated to CRLF on Windows.
    path.write_text(contents, encoding="utf-8", newline="")
    return True


def write_fixture(target_dir: Path | None = None) -> bool:
    """Write the golden fixture. Returns True if it changed."""
    target_dir = target_dir or FIXTURE_DIR
    return _write_if_changed(target_dir / FIXTURE_FILE, build_golden())


def check_fixture(target_dir: Path | None = None) -> bool:
    """Return True if the committed fixture is missing or out of date."""
    target_dir = target_dir or FIXTURE_DIR
    path = target_dir / FIXTURE_FILE
    return not path.is_file() or path.read_bytes() != build_golden().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the committed fixture differs.",
    )
    args = parser.parse_args(argv)

    if args.check:
        if not check_fixture():
            print("PowerShell normalise conformance fixture is up to date.")
            return 0
        print(
            "ERROR: regenerated normalise conformance fixture differs from the committed copy.",
            file=sys.stderr,
        )
        print(
            "Run `python scripts/generate_ps_conformance_fixtures.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    if write_fixture():
        print(f"wrote tests/fixtures/ps_conformance/{FIXTURE_FILE}")
    else:
        print("PowerShell normalise conformance fixture already up to date.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
