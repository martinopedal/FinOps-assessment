"""Tests for the CSV collector."""

from __future__ import annotations

from pathlib import Path

import pytest

from finops_assess.collectors import collect_from_directory

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_collect_samples_directory_loads_all_files() -> None:
    dataset = collect_from_directory(SAMPLES)
    assert len(dataset.users) >= 10
    assert len(dataset.assignments) >= 10
    assert len(dataset.usage) > 0
    assert len(dataset.azure_resources) == 4
    assert dataset.overrides["alice@contoso.example"] == "frontline_worker"


def test_collect_handles_missing_files(tmp_path: Path) -> None:
    dataset = collect_from_directory(tmp_path)
    assert dataset.users == []
    assert dataset.assignments == []
    assert dataset.usage == []
    assert dataset.azure_resources == []
    assert dataset.overrides == {}


def test_collect_rejects_unknown_input_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        collect_from_directory(tmp_path / "does-not-exist")


def test_collect_rejects_unknown_csv_columns(tmp_path: Path) -> None:
    (tmp_path / "users.csv").write_text(
        "principal,unknown_column\nalice@example.test,oops\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown CSV column"):
        collect_from_directory(tmp_path)


def test_collect_handles_utf8_bom(tmp_path: Path) -> None:
    (tmp_path / "users.csv").write_text(
        "\ufeffprincipal,display_name\nalice@example.test,Alice\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert dataset.users[0].principal == "alice@example.test"


def test_collect_parses_lists_via_pipe_separator(tmp_path: Path) -> None:
    (tmp_path / "users.csv").write_text(
        "principal,groups\nalice@example.test,sales|all-staff\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert dataset.users[0].groups == ["sales", "all-staff"]


def test_collect_rejects_rows_with_extra_cells(tmp_path: Path) -> None:
    """A row with more cells than the header must fail loudly (strict-column
    contract); previously the extras were silently dropped, hiding
    operator-entered data. Regression for PR review feedback.
    """
    # 2 header columns, 4 data cells → 2 extras under DictReader's `None` key.
    (tmp_path / "users.csv").write_text(
        "principal,display_name\nalice@example.test,Alice,extra1,extra2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="beyond the declared header columns"):
        collect_from_directory(tmp_path)
