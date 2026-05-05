"""Bundled synthetic-tenant demo data.

Mirrors ``samples/`` at the repo root so that ``finops-assess demo`` works
after ``pip install`` without requiring a checkout. The two trees are kept
in sync by ``tests/test_demo_bundle.py``.
"""

from __future__ import annotations

from contextlib import ExitStack
from importlib import resources
from pathlib import Path

_DEMO_FILES = (
    "users.csv",
    "license_assignments.csv",
    "usage.csv",
    "azure_resources.csv",
    "overrides.yaml",
)


def materialise_demo_data(target_dir: Path) -> Path:
    """Copy the bundled demo CSVs and overrides into ``target_dir``.

    Using a real on-disk directory keeps the existing collector code path
    (which uses :class:`pathlib.Path`) unchanged regardless of whether the
    package is installed as a wheel, an editable install, or run from a
    source checkout.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    package = resources.files("finops_assess.demo")
    with ExitStack() as stack:
        for name in _DEMO_FILES:
            src_path = stack.enter_context(resources.as_file(package / name))
            (target_dir / name).write_bytes(Path(src_path).read_bytes())
    return target_dir
