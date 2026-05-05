"""CSV collector — reads a directory of normalised CSV files into ``NormalizedDataset``.

Expected files (all optional; missing files yield empty lists):

* ``users.csv`` — header columns map to :class:`UserRecord` fields.
* ``license_assignments.csv`` — :class:`LicenseAssignment` fields.
* ``usage.csv`` — :class:`UsageSignal` fields.
* ``azure_resources.csv`` — :class:`AzureResource` fields.
* ``overrides.yaml`` — ``{ principal: persona_id }`` mapping for explicit
  persona pinning (highest-priority signal in the persona engine).

Files with a UTF-8 BOM are tolerated. Empty cells become ``None`` (not the
string ``""``) so pydantic can apply its own defaults.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from finops_assess.models import (
    AzureResource,
    LicenseAssignment,
    NormalizedDataset,
    UsageSignal,
    UserRecord,
)

logger = logging.getLogger(__name__)

_BOOL_TRUE = {"true", "1", "yes", "y", "t"}
_BOOL_FALSE = {"false", "0", "no", "n", "f", ""}

M = TypeVar("M", bound=BaseModel)


def _coerce_row(model: type[M], row: dict[str, str]) -> dict[str, Any]:
    """Normalise CSV string cells to the types pydantic expects."""
    out: dict[str, Any] = {}
    fields = model.model_fields
    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip()
        if key not in fields:
            # Forbid extras explicitly — the schema is the contract.
            raise ValueError(f"{model.__name__}: unknown CSV column '{key}'")
        value = (raw_value or "").strip()
        if value == "":
            # Let pydantic apply its default rather than passing empty strings.
            continue
        annotation = fields[key].annotation
        annotation_str = repr(annotation)
        if "bool" in annotation_str:
            lowered = value.lower()
            if lowered in _BOOL_TRUE:
                out[key] = True
                continue
            if lowered in _BOOL_FALSE:
                out[key] = False
                continue
            raise ValueError(f"{model.__name__}.{key}: cannot parse bool '{value}'")
        if "list" in annotation_str:
            out[key] = [item.strip() for item in value.split("|") if item.strip()]
            continue
        out[key] = value
    return out


def _read_csv(path: Path, model: type[M]) -> list[M]:
    if not path.is_file():
        return []
    rows: list[M] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_no, raw in enumerate(reader, start=2):
            try:
                coerced = _coerce_row(model, raw)
                rows.append(model.model_validate(coerced))
            except (ValidationError, ValueError) as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return rows


def _read_overrides(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping of principal → persona_id")
    return {str(k): str(v) for k, v in doc.items()}


def collect_from_directory(input_dir: Path) -> NormalizedDataset:
    """Build a :class:`NormalizedDataset` from CSVs in ``input_dir``."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"input directory not found: {input_dir}")

    return NormalizedDataset(
        users=_read_csv(input_dir / "users.csv", UserRecord),
        assignments=_read_csv(input_dir / "license_assignments.csv", LicenseAssignment),
        usage=_read_csv(input_dir / "usage.csv", UsageSignal),
        azure_resources=_read_csv(input_dir / "azure_resources.csv", AzureResource),
        overrides=_read_overrides(input_dir / "overrides.yaml"),
    )
