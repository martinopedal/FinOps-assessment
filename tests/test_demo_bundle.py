"""Test that the bundled demo data matches the canonical samples/ tree."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

REPO_SAMPLES = Path(__file__).resolve().parents[1] / "samples"
BUNDLED_FILES = (
    "users.csv",
    "license_assignments.csv",
    "usage.csv",
    "azure_resources.csv",
    "azure_reservations.csv",
    "azure_log_workspaces.csv",
    "github_seats.csv",
    "github_orgs.csv",
    "ado_seats.csv",
    "ado_orgs.csv",
    "overrides.yaml",
)


@pytest.mark.parametrize("name", BUNDLED_FILES)
def test_bundled_demo_matches_samples(name: str) -> None:
    """`finops_assess.demo` must stay byte-identical to top-level samples/."""
    repo_path = REPO_SAMPLES / name
    bundled = resources.files("finops_assess.demo") / name
    with resources.as_file(bundled) as bundled_path:
        assert repo_path.read_bytes() == Path(bundled_path).read_bytes(), (
            f"Bundled demo data for {name} has drifted from samples/{name}; "
            "re-copy from samples/ into src/finops_assess/demo/ to re-sync."
        )
