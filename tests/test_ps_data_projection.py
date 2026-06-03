"""Drift test for the PowerShell engine's JSON data projection.

The native PowerShell engine reads catalogue/persona/rule data from a
committed JSON projection under ``powershell/FinOpsAssess/data/`` that is
generated from the shared YAML by
``scripts/generate_ps_data_projection.py``. These tests fail if the
committed projection has drifted from what the Python loaders would
produce, so any PR that edits the shared YAML must regenerate and commit
the projection.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from finops_assess.catalog import load_catalog
from finops_assess.rules import load_personas, load_rules

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTION_DIR = REPO_ROOT / "powershell" / "FinOpsAssess" / "data"
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_ps_data_projection.py"


def _load_generator():
    """Import the generator module by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("generate_ps_data_projection", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()

PROJECTIONS = {
    "catalog.json": (GEN.build_catalog_projection, load_catalog),
    "personas.json": (GEN.build_personas_projection, load_personas),
    "rules.json": (GEN.build_rules_projection, load_rules),
}

# schema.json / playbooks.json are objects, not lists of model instances,
# so they get byte/LF/parse coverage but not loader-order parity checks.
GENERATED_FILES = sorted([*PROJECTIONS, "schema.json", "playbooks.json"])

SCHEMA_BUILDERS = {
    "schema.json": GEN.build_schema_projection,
    "playbooks.json": GEN.build_playbooks_projection,
}


@pytest.mark.parametrize("filename", GENERATED_FILES)
def test_projection_file_exists(filename: str) -> None:
    assert (PROJECTION_DIR / filename).is_file(), (
        f"Missing projection {filename}; run scripts/generate_ps_data_projection.py"
    )


@pytest.mark.parametrize("filename", sorted(PROJECTIONS))
def test_projection_is_byte_identical_to_regeneration(filename: str) -> None:
    """The committed projection must byte-match a fresh regeneration."""
    builder, _ = PROJECTIONS[filename]
    expected = builder().encode("utf-8")
    actual = (PROJECTION_DIR / filename).read_bytes()
    assert actual == expected, (
        f"{filename} has drifted from the shared YAML. "
        "Run `python scripts/generate_ps_data_projection.py` and commit the result."
    )


@pytest.mark.parametrize("filename", GENERATED_FILES)
def test_projection_is_lf_no_bom(filename: str) -> None:
    raw = (PROJECTION_DIR / filename).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{filename} must not have a UTF-8 BOM"
    assert b"\r\n" not in raw, f"{filename} must use LF line endings"
    assert raw.endswith(b"\n"), f"{filename} must end with a single trailing newline"


@pytest.mark.parametrize("filename", sorted(PROJECTIONS))
def test_projection_parses_and_matches_loader_order(filename: str) -> None:
    """JSON parses to a list whose ids match the loader iteration order."""
    _, loader = PROJECTIONS[filename]
    parsed = json.loads((PROJECTION_DIR / filename).read_text(encoding="utf-8"))
    assert isinstance(parsed, list)
    loaded = list(loader())
    assert len(parsed) == len(loaded)
    assert [item["id"] for item in parsed] == [obj.id for obj in loaded]


@pytest.mark.parametrize("filename", sorted(SCHEMA_BUILDERS))
def test_schema_projection_is_byte_identical_to_regeneration(filename: str) -> None:
    expected = SCHEMA_BUILDERS[filename]().encode("utf-8")
    actual = (PROJECTION_DIR / filename).read_bytes()
    assert actual == expected, (
        f"{filename} has drifted from models.py. "
        "Run `python scripts/generate_ps_data_projection.py` and commit the result."
    )


def test_schema_dataset_fields_match_normalized_dataset() -> None:
    """The schema projection's dataset fields mirror NormalizedDataset.

    Guards against a new normalised-dataset field landing in Python
    without the PowerShell normaliser learning about it (it would
    otherwise silently omit the new collection).
    """
    from finops_assess.models import NormalizedDataset

    schema = json.loads((PROJECTION_DIR / "schema.json").read_text(encoding="utf-8"))
    projected = [entry["field"] for entry in schema["dataset_fields"]]
    # NormalizedDataset list fields, in declaration order, excluding the
    # non-list ``overrides`` mapping which the projection tracks separately.
    dataset_list_fields = [
        name for name, field in NormalizedDataset.model_fields.items() if name != "overrides"
    ]
    assert projected == dataset_list_fields


def test_schema_models_cover_every_dataset_field() -> None:
    schema = json.loads((PROJECTION_DIR / "schema.json").read_text(encoding="utf-8"))
    referenced = {entry["model"] for entry in schema["dataset_fields"]}
    assert referenced == set(schema["models"].keys())


def test_playbooks_projection_matches_rule_ids() -> None:
    payload = json.loads((PROJECTION_DIR / "playbooks.json").read_text(encoding="utf-8"))
    rule_ids = {rule.id for rule in load_rules()}
    assert set(payload.keys()) == rule_ids


def test_playbooks_projection_entry_shape() -> None:
    payload = json.loads((PROJECTION_DIR / "playbooks.json").read_text(encoding="utf-8"))
    for _rule_id, entry in payload.items():
        assert sorted(entry.keys()) == ["render_inputs", "surface", "template"]
        assert isinstance(entry["surface"], str)
        assert isinstance(entry["template"], str)
        assert isinstance(entry["render_inputs"], list)
        assert entry["render_inputs"] == sorted(entry["render_inputs"])


def test_check_projection_reports_no_drift() -> None:
    """The generator's own --check helper agrees the projection is current."""
    assert GEN.check_projection() == []
