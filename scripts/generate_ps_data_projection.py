"""Regenerate the PowerShell engine's JSON data projection.

The native PowerShell engine (``powershell/FinOpsAssess``) is delivered
side by side with the Python tool and must read the *same* catalogue,
persona, and rule data. Rather than parse YAML at runtime (which would
add a third-party PowerShell dependency and risk a second, subtly
different parser), we generate a JSON **projection** of the shared data
at build time so the runtime only needs the built-in ``ConvertFrom-Json``.

The projection is produced by the already-validated Python loaders
(:func:`finops_assess.catalog.load_catalog`,
:func:`finops_assess.rules.load_personas`,
:func:`finops_assess.rules.load_rules`), so it carries the fully
resolved shapes — including pydantic defaults such as ``rule.enabled``,
``evidence_key_version``, and ``adapter_class`` — and the PowerShell
engine never has to re-implement validation or defaulting.

Ordering
--------
Each projected list preserves the **loader iteration order** (sorted
file paths, then document order within a file), NOT a re-sort by ``id``.
This guarantees the PowerShell engine iterates the data in exactly the
same order the Python engine does, so any order-sensitive behaviour
stays in parity. Object keys within each entry are sorted for canonical,
byte-stable output (the PowerShell side reads by property name, so key
order is irrelevant to it).

Determinism / drift gate
------------------------
Output is byte-stable: UTF-8, LF newlines, two-space indent, sorted
object keys, single trailing newline. ``tests/test_ps_data_projection.py``
regenerates in memory and fails on any drift, so a PR that edits the
shared YAML must regenerate and commit the projection.

Usage
-----
::

    python scripts/generate_ps_data_projection.py            # write in place
    python scripts/generate_ps_data_projection.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finops_assess.catalog import load_catalog
from finops_assess.rules import load_personas, load_rules

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTION_DIR = REPO_ROOT / "powershell" / "FinOpsAssess" / "data"

CATALOG_FILE = "catalog.json"
PERSONAS_FILE = "personas.json"
RULES_FILE = "rules.json"


def _to_json(items: list[dict[str, object]]) -> str:
    """Serialise ``items`` to canonical, byte-stable JSON.

    Sorted object keys + LF + two-space indent + trailing newline. The
    list order is preserved as given (loader order); only keys within
    each object are sorted.
    """
    return json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_catalog_projection() -> str:
    """Return the canonical JSON projection of the catalogue."""
    return _to_json([entry.model_dump() for entry in load_catalog()])


def build_personas_projection() -> str:
    """Return the canonical JSON projection of the personas."""
    return _to_json([persona.model_dump() for persona in load_personas()])


def build_rules_projection() -> str:
    """Return the canonical JSON projection of the rules."""
    return _to_json([rule.model_dump() for rule in load_rules()])


def _projection() -> dict[str, str]:
    """Map output filename -> canonical JSON contents."""
    return {
        CATALOG_FILE: build_catalog_projection(),
        PERSONAS_FILE: build_personas_projection(),
        RULES_FILE: build_rules_projection(),
    }


def _write_if_changed(path: Path, contents: str) -> bool:
    """Write ``contents`` only if different. Returns True on change."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = contents.encode("utf-8")
    if path.is_file() and path.read_bytes() == encoded:
        return False
    # newline="" so the explicit "\n" we appended is not re-translated to
    # CRLF on Windows — the committed projection must be byte-identical
    # across OSes (the drift test byte-compares).
    path.write_text(contents, encoding="utf-8", newline="")
    return True


def write_projection(target_dir: Path | None = None) -> list[str]:
    """Write all projection files. Returns the names that changed."""
    target_dir = target_dir or PROJECTION_DIR
    changed: list[str] = []
    for name, contents in _projection().items():
        if _write_if_changed(target_dir / name, contents):
            changed.append(name)
    return changed


def check_projection(target_dir: Path | None = None) -> list[str]:
    """Return the names of files that are missing or out of date."""
    target_dir = target_dir or PROJECTION_DIR
    drifted: list[str] = []
    for name, contents in _projection().items():
        path = target_dir / name
        if not path.is_file() or path.read_bytes() != contents.encode("utf-8"):
            drifted.append(name)
    return drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if any projection file differs from the committed copy.",
    )
    args = parser.parse_args(argv)

    if args.check:
        drifted = check_projection()
        if not drifted:
            print("PowerShell data projection is up to date.")
            return 0
        print(
            "ERROR: regenerated PowerShell data projection differs from the committed copy.",
            file=sys.stderr,
        )
        for name in drifted:
            print(f"  drifted: powershell/FinOpsAssess/data/{name}", file=sys.stderr)
        print(
            "Run `python scripts/generate_ps_data_projection.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    changed = write_projection()
    if changed:
        for name in changed:
            print(f"wrote powershell/FinOpsAssess/data/{name}")
    else:
        print("PowerShell data projection already up to date.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
