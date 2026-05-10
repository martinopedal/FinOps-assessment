"""Helpers for locating authored and packaged data files."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

DataRoot = Path | Traversable

_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
_CHECKOUT_DATA_ROOT = _CHECKOUT_ROOT / "data"


def checkout_data_root() -> Path | None:
    """Return the repository-root data directory when running from a checkout."""
    if (_CHECKOUT_ROOT / "pyproject.toml").is_file() and (
        _CHECKOUT_DATA_ROOT / "personas.yaml"
    ).is_file():
        return _CHECKOUT_DATA_ROOT
    return None


def packaged_data_root() -> Traversable:
    """Return the installed package's bundled data resource root."""
    return resources.files("finops_assess").joinpath("data")


def default_data_root() -> DataRoot:
    """Return the authored checkout data root, falling back to packaged data."""
    return checkout_data_root() or packaged_data_root()
