"""Catalog loader and validator.

Run as a module to validate the on-disk catalog:

    python -m finops_assess.catalog validate
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml
from pydantic import ValidationError

from finops_assess.data_paths import DataRoot, default_data_root
from finops_assess.models import CatalogEntry

DEFAULT_CATALOG_ROOT = Path(__file__).resolve().parents[2] / "data" / "catalog"


def _iter_yaml_files(root: DataRoot) -> Iterable[Path | Traversable]:
    if isinstance(root, Path):
        yield from sorted(root.rglob("*.yaml"))
        yield from sorted(root.rglob("*.yml"))
        return
    for child in sorted(root.iterdir(), key=lambda item: str(item)):
        if child.is_dir():
            yield from _iter_yaml_files(child)
        elif child.is_file() and child.name.endswith((".yaml", ".yml")):
            yield child


def _default_catalog_root() -> DataRoot:
    return default_data_root().joinpath("catalog")


def load_catalog(root: DataRoot | None = None) -> list[CatalogEntry]:
    """Load and validate every catalog YAML file under ``root``."""
    root = root or _default_catalog_root()
    entries: list[CatalogEntry] = []
    seen_ids: set[str] = set()

    for path in _iter_yaml_files(root):
        with path.open(encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or []
        if not isinstance(doc, list):
            raise ValueError(f"{path}: top-level YAML must be a list")
        for raw in doc:
            entry = CatalogEntry.model_validate(raw)
            if entry.id in seen_ids:
                raise ValueError(f"{path}: duplicate catalog id '{entry.id}'")
            seen_ids.add(entry.id)
            entries.append(entry)
    return entries


def _cli(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "validate":
        print("usage: python -m finops_assess.catalog validate", file=sys.stderr)
        return 2
    try:
        entries = load_catalog()
    except (ValidationError, ValueError, yaml.YAMLError) as exc:
        print(f"catalog validation FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"catalog OK: {len(entries)} entries loaded")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli(sys.argv))
