"""Tests for bundled catalogue, rule, and persona data."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import venv
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_DATA = REPO_ROOT / "data"


def _resource_files(root: Traversable) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for child in root.iterdir():
        if child.is_dir():
            for relative, payload in _resource_files(child).items():
                files[f"{child.name}/{relative}"] = payload
        elif child.is_file() and child.name != "__init__.py":
            files[child.name] = child.read_bytes()
    return files


def _repo_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_packaged_data_matches_repo_data() -> None:
    """The installed data mirror must stay byte-identical to repo-root data."""
    if not REPO_DATA.is_dir():
        pytest.skip("source-tree data/ directory is not available")

    repo_files = _repo_files(REPO_DATA)
    packaged_files = _resource_files(resources.files("finops_assess").joinpath("data"))
    assert packaged_files.keys() == repo_files.keys()
    assert {
        name: hashlib.sha256(payload).hexdigest() for name, payload in packaged_files.items()
    } == {name: hashlib.sha256(payload).hexdigest() for name, payload in repo_files.items()}


def test_packaged_data_has_required_surfaces() -> None:
    """Package resources include personas plus catalog and rule YAML for all surfaces."""
    data_root = resources.files("finops_assess").joinpath("data")
    assert data_root.joinpath("personas.yaml").is_file()
    for surface in ("m365", "azure", "github", "ado"):
        assert any(data_root.joinpath("catalog", surface).iterdir())
    assert any(data_root.joinpath("rules").iterdir())


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def test_built_wheel_can_validate_and_run_demo(tmp_path: Path) -> None:
    """A non-editable wheel install can find bundled data and run the demo."""
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
            str(REPO_ROOT),
        ],
        check=True,
        cwd=tmp_path,
    )
    wheels = sorted(wheelhouse.glob("finops_assess-*.whl"))
    assert len(wheels) == 1

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(venv_dir)
    python = _venv_python(venv_dir)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--force-reinstall", str(wheels[0])],
        check=True,
        cwd=tmp_path,
    )
    subprocess.run([str(python), "-m", "finops_assess.cli", "validate"], check=True, cwd=tmp_path)

    subprocess.run(
        [
            str(python),
            "-m",
            "finops_assess.cli",
            "demo",
            "--output-dir",
            str(tmp_path / "demo"),
        ],
        check=True,
        cwd=tmp_path,
    )
    report_path = tmp_path / "demo" / "demo-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["findings"]
