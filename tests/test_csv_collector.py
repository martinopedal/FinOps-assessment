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
    assert len(dataset.azure_benefit_recommendations) == 2
    rec = dataset.azure_benefit_recommendations[0]
    assert rec.recommendation_id.startswith(
        "/providers/Microsoft.CostManagement/benefitRecommendations/"
    )
    assert rec.scope.startswith("/subscriptions/")
    assert rec.scope_kind == "Single"
    assert rec.term in ("P1Y", "P3Y")
    assert rec.lookback_period in ("Last7Days", "Last30Days", "Last60Days")
    assert rec.benefit_kind in ("SavingsPlan", "Reservation")
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
    assert dataset.azure_benefit_recommendations == []
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


def test_azure_benefit_recommendations_csv_round_trip(tmp_path: Path) -> None:
    """Plan §3.1 + §3.8 test #11: strict-column round-trip for the new file.

    Asserts every model field populates correctly through the strict-column
    loader and that an unknown column triggers the `extra="forbid"` rejection.
    """
    (tmp_path / "azure_benefit_recommendations.csv").write_text(
        "recommendation_id,scope,scope_kind,term,lookback_period,arm_sku_name,"
        "cost_without_benefit_usd,recommended_hourly_commit_usd,net_savings_usd,"
        "wastage_usd,benefit_kind\n"
        "/providers/Microsoft.CostManagement/benefitRecommendations/r1,"
        "/subscriptions/00000000-0000-0000-0000-000000000001,Single,P1Y,Last30Days,"
        "Microsoft.Compute/virtualMachines/Standard_D4s_v5,1450.00,1.85,180.50,12.40,SavingsPlan\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_benefit_recommendations) == 1
    rec = dataset.azure_benefit_recommendations[0]
    assert rec.recommendation_id == (
        "/providers/Microsoft.CostManagement/benefitRecommendations/r1"
    )
    assert rec.scope == "/subscriptions/00000000-0000-0000-0000-000000000001"
    assert rec.scope_kind == "Single"
    assert rec.term == "P1Y"
    assert rec.lookback_period == "Last30Days"
    assert rec.arm_sku_name == "Microsoft.Compute/virtualMachines/Standard_D4s_v5"
    assert rec.cost_without_benefit_usd == 1450.00
    assert rec.recommended_hourly_commit_usd == 1.85
    assert rec.net_savings_usd == 180.50
    assert rec.wastage_usd == 12.40
    assert rec.benefit_kind == "SavingsPlan"


def test_azure_benefit_recommendations_csv_rejects_unknown_column(tmp_path: Path) -> None:
    """Strict-column contract: unknown header rejected with a clear error."""
    (tmp_path / "azure_benefit_recommendations.csv").write_text(
        "recommendation_id,scope,term,lookback_period,unknown_col\n"
        "rec-1,/subscriptions/x,P1Y,Last30Days,oops\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown CSV column"):
        collect_from_directory(tmp_path)
