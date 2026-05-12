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
    assert len(dataset.azure_resources) == 5
    assert len(dataset.azure_reservations) == 2
    assert len(dataset.azure_log_workspaces) == 2
    assert len(dataset.github_seats) == 4
    assert len(dataset.github_orgs) == 1
    assert len(dataset.ado_seats) == 5
    assert len(dataset.ado_orgs) == 1
    assert dataset.overrides["alice@contoso.example"] == "frontline_worker"


def test_collect_handles_missing_files(tmp_path: Path) -> None:
    dataset = collect_from_directory(tmp_path)
    assert dataset.users == []
    assert dataset.assignments == []
    assert dataset.usage == []
    assert dataset.azure_resources == []
    assert dataset.azure_reservations == []
    assert dataset.azure_log_workspaces == []
    assert dataset.azure_region_prices == []
    assert dataset.github_seats == []
    assert dataset.github_orgs == []
    assert dataset.ado_seats == []
    assert dataset.ado_orgs == []
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


def test_collect_parses_azure_region_price_observation_with_defaults(tmp_path: Path) -> None:
    (tmp_path / "azure_region_prices.csv").write_text(
        "region,sku_name,meter_id,unit_price\n"
        "westeurope,Standard_D2s_v5,11111111-1111-1111-1111-111111111111,0.12\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    observation = dataset.azure_region_prices[0]

    assert observation.region == "westeurope"
    assert observation.sku_name == "Standard_D2s_v5"
    assert observation.meter_id == "11111111-1111-1111-1111-111111111111"
    assert observation.unit_price == pytest.approx(0.12)
    assert observation.source == "azure_retail_prices_api"
    assert observation.currency_code == "USD"
    assert observation.retail_price is None


def test_collect_rejects_unknown_azure_region_price_columns(tmp_path: Path) -> None:
    (tmp_path / "azure_region_prices.csv").write_text(
        "region,sku_name,meter_id,unit_price,unexpected\n"
        "westeurope,Standard_D2s_v5,11111111-1111-1111-1111-111111111111,0.12,oops\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown CSV column"):
        collect_from_directory(tmp_path)


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
