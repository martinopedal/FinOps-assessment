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
import typing
from pathlib import Path

import annotated_types as at
from pydantic import BaseModel

from finops_assess.catalog import load_catalog
from finops_assess.models import (
    AdoOrgUsage,
    AdoSeat,
    AzureBenefitRecommendation,
    AzureLogWorkspace,
    AzureReservation,
    AzureResource,
    GitHubOrg,
    GitHubSeat,
    LicenseAssignment,
    M365FamilySummary,
    UsageSignal,
    UserRecord,
)
from finops_assess.rules import load_personas, load_rules

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTION_DIR = REPO_ROOT / "powershell" / "FinOpsAssess" / "data"

CATALOG_FILE = "catalog.json"
PERSONAS_FILE = "personas.json"
RULES_FILE = "rules.json"
SCHEMA_FILE = "schema.json"

# Each NormalizedDataset list field, the record model that validates its
# rows, and the CSV file the offline collector reads it from. Mirrors
# ``finops_assess.collectors.csv_collector.collect_from_directory`` and
# the field order of ``NormalizedDataset``. ``csv = None`` marks a dataset
# field that is NOT populated from a CSV (the PowerShell normaliser still
# emits it as an empty list for dataset-shape parity).
DATASET_FIELDS: list[tuple[str, type[BaseModel], str | None]] = [
    ("users", UserRecord, "users.csv"),
    ("assignments", LicenseAssignment, "license_assignments.csv"),
    ("usage", UsageSignal, "usage.csv"),
    ("m365_family_summaries", M365FamilySummary, None),
    ("azure_resources", AzureResource, "azure_resources.csv"),
    ("azure_reservations", AzureReservation, "azure_reservations.csv"),
    ("azure_log_workspaces", AzureLogWorkspace, "azure_log_workspaces.csv"),
    (
        "azure_benefit_recommendations",
        AzureBenefitRecommendation,
        "azure_benefit_recommendations.csv",
    ),
    ("github_seats", GitHubSeat, "github_seats.csv"),
    ("github_orgs", GitHubOrg, "github_orgs.csv"),
    ("ado_seats", AdoSeat, "ado_seats.csv"),
    ("ado_orgs", AdoOrgUsage, "ado_orgs.csv"),
]

OVERRIDES_FILE = "overrides.yaml"


def _to_json(items: object) -> str:
    """Serialise ``items`` to canonical, byte-stable JSON.

    Sorted object keys + LF + two-space indent + trailing newline. List
    order is preserved as given (loader order); only keys within objects
    are sorted.
    """
    return json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _field_kind(annotation: object) -> tuple[str, bool, object | None]:
    """Classify a pydantic field annotation.

    Returns ``(kind, nullable, enum_values)`` where ``kind`` is one of
    ``string``/``int``/``float``/``bool``/``list``/``literal``. Optional
    types (``X | None``) are unwrapped and reported as ``nullable=True``.
    Named ``Literal`` aliases (e.g. ``GitHubSeatType``) resolve correctly
    because ``typing.get_origin`` sees through the alias to ``Literal``.
    """
    nullable = False
    inner = annotation
    if typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        nullable = type(None) in typing.get_args(annotation)
        if len(args) == 1:
            inner = args[0]

    inner_origin = typing.get_origin(inner)
    if inner_origin is typing.Literal:
        return "literal", nullable, list(typing.get_args(inner))
    if inner_origin in (list, typing.List):  # noqa: UP006 - runtime origin check
        return "list", nullable, None
    if inner is bool:
        return "bool", nullable, None
    if inner is int:
        return "int", nullable, None
    if inner is float:
        return "float", nullable, None
    if inner is str:
        return "string", nullable, None
    # dict (overrides) and any unforeseen shape fall through as "string";
    # no record model uses dict fields, so this is unreachable for records.
    return "string", nullable, None


def _field_spec(name: str, field: object) -> dict[str, object]:
    """Build the projected spec for one model field."""
    annotation = field.annotation  # type: ignore[attr-defined]
    kind, nullable, enum_values = _field_kind(annotation)

    spec: dict[str, object] = {
        "name": name,
        "kind": kind,
        "nullable": nullable,
        "required": bool(field.is_required()),  # type: ignore[attr-defined]
    }
    if enum_values is not None:
        spec["enum"] = enum_values

    # Numeric / length constraints, mirrored from annotated-types metadata.
    for meta in field.metadata:  # type: ignore[attr-defined]
        if isinstance(meta, at.Ge):
            spec["ge"] = meta.ge
        elif isinstance(meta, at.Le):
            spec["le"] = meta.le
        elif isinstance(meta, at.MinLen):
            spec["min_length"] = meta.min_length
        elif isinstance(meta, at.MaxLen):
            spec["max_length"] = meta.max_length

    return spec


def _model_spec(model: type[BaseModel]) -> list[dict[str, object]]:
    """Project a model's fields in declaration order."""
    return [_field_spec(name, field) for name, field in model.model_fields.items()]


def build_schema_projection() -> str:
    """Return the canonical JSON projection of the normalised-record schema.

    The PowerShell CSV normaliser reads this to coerce and validate CSV
    cells generically against the same field types, nullability, enum
    membership, and numeric/length bounds that pydantic enforces in
    Python, so it stays in lockstep with ``models.py`` instead of
    hand-coding each record shape.
    """
    models_used = {field[1].__name__: field[1] for field in DATASET_FIELDS}
    schema: dict[str, object] = {
        "dataset_fields": [
            {"field": name, "model": model.__name__, "csv": csv}
            for name, model, csv in DATASET_FIELDS
        ],
        "overrides": {"file": OVERRIDES_FILE, "kind": "mapping"},
        "bool_true": sorted({"true", "1", "yes", "y", "t"}),
        "bool_false": sorted({"false", "0", "no", "n", "f"}),
        "list_separator": "|",
        "models": {name: _model_spec(model) for name, model in sorted(models_used.items())},
    }
    return _to_json(schema)


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
        SCHEMA_FILE: build_schema_projection(),
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
