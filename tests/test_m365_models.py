"""Tests for M365 family-summary models (D.6 frontier epic)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finops_assess.models import M365FamilySummary, NormalizedDataset


def test_m365_family_summary_round_trip() -> None:
    """Valid M365FamilySummary can be constructed and serialized."""
    summary = M365FamilySummary(
        family_name="entra_p2",
        total_assigned=50,
        distinct_users_with_assignment=45,
        distinct_active_users=40,
        distinct_inactive_users=5,
        feature_usage_signals={"pim_assignments": 12, "identity_protection_policies": 3},
        coverage_note="Entra P2 assigned but PIM usage low",
    )
    assert summary.family_name == "entra_p2"
    assert summary.total_assigned == 50
    assert summary.distinct_users_with_assignment == 45
    assert summary.feature_usage_signals["pim_assignments"] == 12
    # Round-trip
    data = summary.model_dump()
    reconstructed = M365FamilySummary.model_validate(data)
    assert reconstructed == summary


def test_m365_family_summary_defaults() -> None:
    """Counts default to 0 when omitted."""
    summary = M365FamilySummary(family_name="m365_e5_tier")
    assert summary.total_assigned == 0
    assert summary.distinct_users_with_assignment == 0
    assert summary.distinct_active_users == 0
    assert summary.distinct_inactive_users == 0
    assert summary.feature_usage_signals == {}
    assert summary.coverage_note is None


def test_m365_family_summary_rejects_extra_fields() -> None:
    """extra='forbid' rejects unknown fields (e.g., tenant_id, user_id)."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        M365FamilySummary(
            family_name="gsa",
            total_assigned=10,
            tenant_id="00000000-0000-0000-0000-000000000000",  # FORBIDDEN
        )


def test_m365_family_summary_rejects_per_principal_fields() -> None:
    """Ensure no per-principal PII leakage (Noor's stage-4 catch)."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        M365FamilySummary(
            family_name="copilot_m365",
            total_assigned=100,
            user_id="user@example.com",  # FORBIDDEN
        )


def test_m365_family_summary_rejects_invalid_family_name() -> None:
    """Literal constraint: invalid family names rejected."""
    with pytest.raises(ValidationError, match="Input should be"):
        M365FamilySummary(
            family_name="invalid_family_123",  # type: ignore[arg-type]
            total_assigned=5,
        )


def test_m365_family_summary_rejects_negative_counts() -> None:
    """Counts must be non-negative."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        M365FamilySummary(
            family_name="m365_e3_tier",
            total_assigned=-5,
        )


def test_m365_family_summary_all_family_names_valid() -> None:
    """All documented family names are accepted."""
    families = [
        "m365_e1_tier",
        "m365_e3_tier",
        "m365_e5_tier",
        "office365",
        "entra_p1",
        "entra_p2",
        "ems_e3",
        "ems_e5",
        "defender_o365_p1",
        "defender_o365_p2",
        "defender_cloud_apps",
        "copilot_m365",
        "copilot_pro",
        "copilot_studio",
        "gsa",
    ]
    for fam in families:
        summary = M365FamilySummary(family_name=fam, total_assigned=1)  # type: ignore[arg-type]
        assert summary.family_name == fam


def test_normalized_dataset_accepts_m365_family_summaries() -> None:
    """NormalizedDataset accepts m365_family_summaries field."""
    dataset = NormalizedDataset(
        m365_family_summaries=[
            M365FamilySummary(
                family_name="m365_e5_tier",
                total_assigned=100,
                distinct_users_with_assignment=95,
                distinct_active_users=90,
                distinct_inactive_users=5,
            ),
            M365FamilySummary(
                family_name="entra_p2",
                total_assigned=50,
                distinct_users_with_assignment=48,
                distinct_active_users=45,
                distinct_inactive_users=3,
                feature_usage_signals={"pim_assignments": 10},
            ),
        ]
    )
    assert len(dataset.m365_family_summaries) == 2
    assert dataset.m365_family_summaries[0].family_name == "m365_e5_tier"
    assert dataset.m365_family_summaries[1].feature_usage_signals["pim_assignments"] == 10


def test_normalized_dataset_defaults_empty_m365_family_summaries() -> None:
    """NormalizedDataset defaults m365_family_summaries to empty list."""
    dataset = NormalizedDataset()
    assert dataset.m365_family_summaries == []


def test_m365_family_summary_feature_usage_signals_aggregate_only() -> None:
    """feature_usage_signals must be aggregate counts, not user lists."""
    # Valid: dict[str, int] with aggregate counts
    summary = M365FamilySummary(
        family_name="defender_o365_p2",
        total_assigned=200,
        feature_usage_signals={"anti_phishing_policies": 5, "safe_links_clicks": 1200},
    )
    assert summary.feature_usage_signals["safe_links_clicks"] == 1200

    # Invalid: non-int values rejected by pydantic
    with pytest.raises(ValidationError):
        M365FamilySummary(
            family_name="defender_cloud_apps",
            total_assigned=50,
            feature_usage_signals={"users": ["alice", "bob"]},  # type: ignore[dict-item]
        )
