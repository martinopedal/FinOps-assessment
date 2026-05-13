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
    assert len(dataset.azure_resources) == 7
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


def test_azure_reservations_csv_round_trip_with_renewal_columns(tmp_path: Path) -> None:
    """Plan §3.8 test #15(a): round-trip the new ``expiry_date`` + ``auto_renew`` columns.

    Pin the strict-column loader's handling of the two renewal-review fields:
    ``expiry_date`` lands as the verbatim ISO 8601 string, ``auto_renew`` lands
    as a parsed boolean. Drives the AZ.COMMITMENT_RENEWAL_REVIEW evidence
    contract end-to-end through the loader.
    """
    (tmp_path / "azure_reservations.csv").write_text(
        "reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd,"
        "expiry_date,auto_renew\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-1/reservations/r-1,"
        "RI-VM-D4s,Standard_D4s_v5,shared,72.0,1450.00,2026-07-12,false\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-2/reservations/r-2,"
        "RI-SQL,GP_Gen5_8,single,85.0,720.00,2026-08-30,true\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_reservations) == 2
    a, b = dataset.azure_reservations
    assert a.expiry_date == "2026-07-12"
    assert a.auto_renew is False
    assert b.expiry_date == "2026-08-30"
    assert b.auto_renew is True


def test_azure_reservations_csv_legacy_loads_with_null_renewal_fields(tmp_path: Path) -> None:
    """Plan §3.8 test #15(b): backward-compat for legacy CSVs.

    A CSV written before the renewal-review fields existed (no ``expiry_date``
    or ``auto_renew`` columns) MUST still load through the strict-column loader,
    with both new fields defaulting to ``None``. The rule abstains on those
    rows; the operator can refresh the file via the live ARM collector when
    ready. Pinned by docs/plans/059-az-commitment-renewal-review.md §3.7.
    """
    (tmp_path / "azure_reservations.csv").write_text(
        "reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-1/reservations/r-1,"
        "RI-legacy,Standard_D4s_v5,shared,55.0,500.00\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_reservations) == 1
    legacy = dataset.azure_reservations[0]
    assert legacy.expiry_date is None
    assert legacy.auto_renew is None
    # Existing fields still populate.
    assert legacy.utilization_pct == 55.0
    assert legacy.monthly_cost_usd == 500.0


def test_azure_reservations_csv_empty_renewal_cells_become_null(tmp_path: Path) -> None:
    """Plan §3.7 implementer caveat: empty cells must resolve to ``None``,
    NOT to ``False`` via ``_BOOL_FALSE``. The strict-column loader's
    missing-key path treats blank cells as absent so pydantic applies the
    field default; the boolean coercion path never sees the empty string.
    """
    (tmp_path / "azure_reservations.csv").write_text(
        "reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd,"
        "expiry_date,auto_renew\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-1/reservations/r-1,"
        "RI-blank,Standard_D4s_v5,shared,72.0,1450.00,,\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_reservations) == 1
    row = dataset.azure_reservations[0]
    assert row.expiry_date is None
    assert row.auto_renew is None  # MUST be None, not False


def test_azure_reservations_csv_round_trip_with_scope_ids(tmp_path: Path) -> None:
    """Scope-mismatch §3.8 test #15(a): round-trip applied_scope_subscription_ids.

    Pin the strict-column loader's handling of the pipe-separated list field:
    non-empty cell → split on ``|`` into ``list[str]``; empty cell → ``None``.
    """
    (tmp_path / "azure_reservations.csv").write_text(
        "reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd,"
        "expiry_date,auto_renew,applied_scope_subscription_ids\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-1/reservations/r-1,"
        "RI-shared,Standard_D4s_v5,shared,72.0,1450.00,2026-07-12,false,\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-2/reservations/r-2,"
        "RI-single,GP_Gen5_8,single,85.0,720.00,2026-08-30,true,"
        "/subscriptions/sub-a|/subscriptions/sub-b\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_reservations) == 2
    shared_row, single_row = dataset.azure_reservations
    assert shared_row.applied_scope_subscription_ids is None
    assert single_row.applied_scope_subscription_ids == [
        "/subscriptions/sub-a",
        "/subscriptions/sub-b",
    ]


def test_azure_reservations_csv_legacy_loads_with_null_scope_ids(tmp_path: Path) -> None:
    """Backward-compat: legacy CSV without applied_scope_subscription_ids still loads."""
    (tmp_path / "azure_reservations.csv").write_text(
        "reservation_id,reservation_name,sku,scope,utilization_pct,monthly_cost_usd\n"
        "/providers/Microsoft.Capacity/reservationOrders/o-1/reservations/r-1,"
        "RI-legacy,Standard_D4s_v5,shared,55.0,500.00\n",
        encoding="utf-8",
    )
    dataset = collect_from_directory(tmp_path)
    assert len(dataset.azure_reservations) == 1
    legacy = dataset.azure_reservations[0]
    assert legacy.applied_scope_subscription_ids is None
    assert legacy.utilization_pct == 55.0
