"""Tests for Azure pricing observation models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finops_assess.pricing import (
    AzureRegionPriceDataset,
    AzureRegionPriceObservation,
)


def test_observation_round_trip() -> None:
    """Minimal observation serializes and deserializes correctly."""
    obs = AzureRegionPriceObservation(
        region="eastus",
        sku_id="Standard_D2s_v3",
        unit_price_usd=0.096,
        observed_at="2026-05-12",
        source="azure_retail_api",
    )
    data = obs.model_dump()
    obs2 = AzureRegionPriceObservation.model_validate(data)
    assert obs2.region == "eastus"
    assert obs2.sku_id == "Standard_D2s_v3"
    assert obs2.unit_price_usd == 0.096
    assert obs2.currency == "USD"
    assert obs2.observed_at == "2026-05-12"
    assert obs2.source == "azure_retail_api"
    assert obs2.meter_name is None
    assert obs2.unit_of_measure is None


def test_observation_with_all_fields() -> None:
    """Observation with all optional fields populated."""
    obs = AzureRegionPriceObservation(
        region="westeurope",
        sku_id="P10",
        meter_name="Premium SSD Managed Disks - P10 LRS - Disk",
        unit_price_usd=19.71,
        currency="USD",
        unit_of_measure="1/Month",
        observed_at="2026-05-12",
        source="cost_management_export",
    )
    assert obs.meter_name == "Premium SSD Managed Disks - P10 LRS - Disk"
    assert obs.unit_of_measure == "1/Month"


def test_observation_forbid_extra_fields() -> None:
    """Extra fields in the input are rejected (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05-12",
            source="azure_retail_api",
            extra_field="should_fail",  # type: ignore[call-arg]
        )
    assert "extra_field" in str(exc_info.value).lower()


def test_observation_negative_price_rejected() -> None:
    """Negative unit_price_usd is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=-0.096,
            observed_at="2026-05-12",
            source="azure_retail_api",
        )
    assert "greater than or equal to 0" in str(exc_info.value).lower()


def test_observation_zero_price_allowed() -> None:
    """Zero unit_price_usd is allowed (free tier)."""
    obs = AzureRegionPriceObservation(
        region="eastus",
        sku_id="Free_Tier",
        unit_price_usd=0.0,
        observed_at="2026-05-12",
        source="customer_supplied",
    )
    assert obs.unit_price_usd == 0.0


def test_observation_missing_required_fields() -> None:
    """Missing required fields are rejected."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(  # type: ignore[call-arg]
            region="eastus",
            sku_id="Standard_D2s_v3",
            # unit_price_usd is missing
            observed_at="2026-05-12",
            source="azure_retail_api",
        )


def test_observation_invalid_source_rejected() -> None:
    """Invalid source literal is rejected."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05-12",
            source="unknown_source",  # type: ignore[arg-type]
        )


def test_observation_empty_region_rejected() -> None:
    """Empty region string is rejected (min_length=1)."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05-12",
            source="azure_retail_api",
        )


def test_observation_empty_sku_id_rejected() -> None:
    """Empty sku_id string is rejected (min_length=1)."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="",
            unit_price_usd=0.096,
            observed_at="2026-05-12",
            source="azure_retail_api",
        )


def test_observation_invalid_date_format_rejected() -> None:
    """Observed_at must be exactly 10 characters (YYYY-MM-DD)."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05-12T10:00:00Z",  # ISO 8601 timestamp, not date
            source="azure_retail_api",
        )


def test_observation_short_date_rejected() -> None:
    """Observed_at shorter than 10 characters is rejected."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05",
            source="azure_retail_api",
        )


def test_dataset_round_trip() -> None:
    """Dataset with observations serializes and deserializes correctly."""
    dataset = AzureRegionPriceDataset(
        observations=[
            AzureRegionPriceObservation(
                region="eastus",
                sku_id="Standard_D2s_v3",
                unit_price_usd=0.096,
                observed_at="2026-05-12",
                source="azure_retail_api",
            ),
            AzureRegionPriceObservation(
                region="westeurope",
                sku_id="Standard_D2s_v3",
                unit_price_usd=0.104,
                observed_at="2026-05-12",
                source="azure_retail_api",
            ),
        ],
        dataset_generated_at="2026-05-12T10:00:00Z",
        dataset_version="1.0",
        notes="List prices from Azure Retail Prices API",
    )
    data = dataset.model_dump()
    dataset2 = AzureRegionPriceDataset.model_validate(data)
    assert len(dataset2.observations) == 2
    assert dataset2.observations[0].region == "eastus"
    assert dataset2.observations[1].region == "westeurope"
    assert dataset2.dataset_generated_at == "2026-05-12T10:00:00Z"
    assert dataset2.dataset_version == "1.0"
    assert dataset2.notes == "List prices from Azure Retail Prices API"


def test_dataset_empty_observations() -> None:
    """Dataset with no observations is valid."""
    dataset = AzureRegionPriceDataset(observations=[])
    assert dataset.observations == []
    assert dataset.dataset_generated_at is None
    assert dataset.dataset_version is None
    assert dataset.notes is None


def test_dataset_forbid_extra_fields() -> None:
    """Extra fields in dataset are rejected (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        AzureRegionPriceDataset(
            observations=[],
            extra_field="should_fail",  # type: ignore[call-arg]
        )
    assert "extra_field" in str(exc_info.value).lower()


def test_dataset_minimal() -> None:
    """Minimal dataset (no metadata) is valid."""
    dataset = AzureRegionPriceDataset()
    assert dataset.observations == []
    assert dataset.dataset_generated_at is None
    assert dataset.dataset_version is None
    assert dataset.notes is None


def test_observation_currency_default() -> None:
    """Currency defaults to 'USD'."""
    obs = AzureRegionPriceObservation(
        region="eastus",
        sku_id="Standard_D2s_v3",
        unit_price_usd=0.096,
        observed_at="2026-05-12",
        source="azure_retail_api",
    )
    assert obs.currency == "USD"


def test_observation_currency_explicit_usd() -> None:
    """Explicitly setting currency to 'USD' is allowed."""
    obs = AzureRegionPriceObservation(
        region="eastus",
        sku_id="Standard_D2s_v3",
        unit_price_usd=0.096,
        currency="USD",
        observed_at="2026-05-12",
        source="azure_retail_api",
    )
    assert obs.currency == "USD"


def test_observation_non_usd_currency_rejected() -> None:
    """Non-USD currency is rejected (Literal['USD'])."""
    with pytest.raises(ValidationError):
        AzureRegionPriceObservation(
            region="westeurope",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.088,
            currency="EUR",  # type: ignore[arg-type]
            observed_at="2026-05-12",
            source="azure_retail_api",
        )


def test_observation_all_sources_valid() -> None:
    """All defined PricingSource literals are valid."""
    sources = ["azure_retail_api", "cost_management_export", "customer_supplied"]
    for src in sources:
        obs = AzureRegionPriceObservation(
            region="eastus",
            sku_id="Standard_D2s_v3",
            unit_price_usd=0.096,
            observed_at="2026-05-12",
            source=src,  # type: ignore[arg-type]
        )
        assert obs.source == src


# ---------------------------------------------------------------------------
# Azure commitment observation tests
# ---------------------------------------------------------------------------


def test_commitment_observation_round_trip() -> None:
    """Minimal commitment observation serializes and deserializes correctly."""
    from finops_assess.pricing import AzureCommitmentObservation

    obs = AzureCommitmentObservation(
        commitment_id="abc-123",
        commitment_type="reserved_instance",
        scope="single_subscription",
        observed_at="2026-05-12",
        source="cost_management_api",
    )
    data = obs.model_dump()
    obs2 = AzureCommitmentObservation.model_validate(data)
    assert obs2.commitment_id == "abc-123"
    assert obs2.commitment_type == "reserved_instance"
    assert obs2.scope == "single_subscription"
    assert obs2.observed_at == "2026-05-12"
    assert obs2.source == "cost_management_api"
    assert obs2.commitment_name is None
    assert obs2.sku_id is None
    assert obs2.region is None
    assert obs2.utilization_pct is None
    assert obs2.coverage_pct is None


def test_commitment_observation_all_fields() -> None:
    """Commitment observation with all optional fields populated."""
    from finops_assess.pricing import AzureCommitmentObservation

    obs = AzureCommitmentObservation(
        commitment_id="ri-d2s-v3-001",
        commitment_name="Production VM RI",
        commitment_type="reserved_instance",
        sku_id="Standard_D2s_v3",
        region="eastus",
        scope="shared_subscription",
        utilization_pct=85.5,
        utilization_window_days=30,
        coverage_pct=72.3,
        coverage_window_days=30,
        monthly_cost_usd=1234.56,
        expiry_date="2027-05-12",
        observed_at="2026-05-12",
        source="reservation_summaries_api",
        notes="High utilization, consider renewal",
    )
    assert obs.commitment_name == "Production VM RI"
    assert obs.sku_id == "Standard_D2s_v3"
    assert obs.region == "eastus"
    assert obs.utilization_pct == 85.5
    assert obs.utilization_window_days == 30
    assert obs.coverage_pct == 72.3
    assert obs.coverage_window_days == 30
    assert obs.monthly_cost_usd == 1234.56
    assert obs.expiry_date == "2027-05-12"
    assert obs.notes == "High utilization, consider renewal"


def test_commitment_observation_forbid_extra() -> None:
    """Extra fields in commitment observation are rejected (extra='forbid')."""
    from finops_assess.pricing import AzureCommitmentObservation

    with pytest.raises(ValidationError) as exc_info:
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            observed_at="2026-05-12",
            source="cost_management_api",
            extra_field="should_fail",  # type: ignore[call-arg]
        )
    assert "extra_field" in str(exc_info.value).lower()


def test_commitment_observation_validation_bounds() -> None:
    """Commitment observation validation: utilization/coverage in [0, 100], cost >= 0."""
    from finops_assess.pricing import AzureCommitmentObservation

    # utilization_pct > 100 rejected
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            utilization_pct=150.0,
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # coverage_pct < 0 rejected
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            coverage_pct=-10.0,
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # monthly_cost_usd < 0 rejected
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            monthly_cost_usd=-100.0,
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # zero cost allowed
    obs = AzureCommitmentObservation(
        commitment_id="abc-123",
        commitment_type="reserved_instance",
        scope="single_subscription",
        monthly_cost_usd=0.0,
        observed_at="2026-05-12",
        source="customer_supplied",
    )
    assert obs.monthly_cost_usd == 0.0


def test_commitment_observation_enum_literals() -> None:
    """Invalid commitment_type, scope, source are rejected."""
    from finops_assess.pricing import AzureCommitmentObservation

    # Invalid commitment_type
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="invalid_type",  # type: ignore[arg-type]
            scope="single_subscription",
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # Invalid scope
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="invalid_scope",  # type: ignore[arg-type]
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # Invalid source
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            observed_at="2026-05-12",
            source="invalid_source",  # type: ignore[arg-type]
        )


def test_commitment_observation_expiry_date_format() -> None:
    """Expiry_date must be exactly 10 characters (YYYY-MM-DD)."""
    from finops_assess.pricing import AzureCommitmentObservation

    # ISO 8601 timestamp rejected (too long)
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            expiry_date="2027-05-12T00:00:00Z",
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # Short date rejected
    with pytest.raises(ValidationError):
        AzureCommitmentObservation(
            commitment_id="abc-123",
            commitment_type="reserved_instance",
            scope="single_subscription",
            expiry_date="2027-05",
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # Valid YYYY-MM-DD accepted
    obs = AzureCommitmentObservation(
        commitment_id="abc-123",
        commitment_type="reserved_instance",
        scope="single_subscription",
        expiry_date="2027-05-12",
        observed_at="2026-05-12",
        source="cost_management_api",
    )
    assert obs.expiry_date == "2027-05-12"


def test_eligible_spend_observation_round_trip() -> None:
    """Minimal eligible spend observation serializes and deserializes correctly."""
    from finops_assess.pricing import SavingsPlanEligibleSpendObservation

    obs = SavingsPlanEligibleSpendObservation(
        resource_type="virtualMachine",
        eligible_spend_usd=5000.0,
        window_days=30,
        observed_at="2026-05-12",
        source="cost_management_api",
    )
    data = obs.model_dump()
    obs2 = SavingsPlanEligibleSpendObservation.model_validate(data)
    assert obs2.resource_type == "virtualMachine"
    assert obs2.eligible_spend_usd == 5000.0
    assert obs2.window_days == 30
    assert obs2.observed_at == "2026-05-12"
    assert obs2.source == "cost_management_api"
    assert obs2.region is None
    assert obs2.notes is None


def test_eligible_spend_observation_forbid_extra() -> None:
    """Extra fields in eligible spend observation are rejected (extra='forbid')."""
    from finops_assess.pricing import SavingsPlanEligibleSpendObservation

    with pytest.raises(ValidationError) as exc_info:
        SavingsPlanEligibleSpendObservation(
            resource_type="virtualMachine",
            eligible_spend_usd=5000.0,
            window_days=30,
            observed_at="2026-05-12",
            source="cost_management_api",
            extra_field="should_fail",  # type: ignore[call-arg]
        )
    assert "extra_field" in str(exc_info.value).lower()


def test_eligible_spend_observation_validation_bounds() -> None:
    """Eligible spend observation validation: spend >= 0."""
    from finops_assess.pricing import SavingsPlanEligibleSpendObservation

    # negative spend rejected
    with pytest.raises(ValidationError):
        SavingsPlanEligibleSpendObservation(
            resource_type="virtualMachine",
            eligible_spend_usd=-1000.0,
            window_days=30,
            observed_at="2026-05-12",
            source="cost_management_api",
        )

    # zero spend allowed
    obs = SavingsPlanEligibleSpendObservation(
        resource_type="virtualMachine",
        eligible_spend_usd=0.0,
        window_days=30,
        observed_at="2026-05-12",
        source="customer_supplied",
    )
    assert obs.eligible_spend_usd == 0.0


def test_commitment_dataset_round_trip() -> None:
    """Dataset with commitment and eligible spend observations serializes/deserializes correctly."""
    from finops_assess.pricing import (
        AzureCommitmentDataset,
        AzureCommitmentObservation,
        SavingsPlanEligibleSpendObservation,
    )

    dataset = AzureCommitmentDataset(
        commitments=[
            AzureCommitmentObservation(
                commitment_id="ri-001",
                commitment_type="reserved_instance",
                scope="shared_subscription",
                utilization_pct=80.0,
                observed_at="2026-05-12",
                source="cost_management_api",
            ),
            AzureCommitmentObservation(
                commitment_id="sp-001",
                commitment_type="savings_plan_compute",
                scope="management_group",
                coverage_pct=65.0,
                observed_at="2026-05-12",
                source="reservation_summaries_api",
            ),
        ],
        eligible_spend_observations=[
            SavingsPlanEligibleSpendObservation(
                resource_type="virtualMachine",
                eligible_spend_usd=10000.0,
                window_days=30,
                observed_at="2026-05-12",
                source="cost_management_api",
            ),
        ],
        dataset_generated_at="2026-05-12T10:00:00Z",
        dataset_version="1.0",
        notes="Monthly commitment review",
    )
    data = dataset.model_dump()
    dataset2 = AzureCommitmentDataset.model_validate(data)
    assert len(dataset2.commitments) == 2
    assert len(dataset2.eligible_spend_observations) == 1
    assert dataset2.commitments[0].commitment_id == "ri-001"
    assert dataset2.commitments[1].commitment_id == "sp-001"
    assert dataset2.eligible_spend_observations[0].resource_type == "virtualMachine"
    assert dataset2.dataset_generated_at == "2026-05-12T10:00:00Z"
    assert dataset2.dataset_version == "1.0"


def test_commitment_dataset_empty() -> None:
    """Empty commitment dataset is valid."""
    from finops_assess.pricing import AzureCommitmentDataset

    dataset = AzureCommitmentDataset()
    assert dataset.commitments == []
    assert dataset.eligible_spend_observations == []
    assert dataset.dataset_generated_at is None
    assert dataset.dataset_version is None
    assert dataset.notes is None


def test_commitment_dataset_forbid_extra() -> None:
    """Extra fields in commitment dataset are rejected (extra='forbid')."""
    from finops_assess.pricing import AzureCommitmentDataset

    with pytest.raises(ValidationError) as exc_info:
        AzureCommitmentDataset(
            commitments=[],
            extra_field="should_fail",  # type: ignore[call-arg]
        )
    assert "extra_field" in str(exc_info.value).lower()


def test_commitment_language_guardrail() -> None:
    """Commitment models must NOT contain prohibited action verbs in docstrings, field descriptions, or Literal values.

    This test iterates every commitment-related model defined in pricing.py and checks:
    - Class docstrings
    - Every Field(..., description="...") literal string
    - Every Literal[...] enum value used in field annotations

    Prohibited verbs are imperative action verbs that would violate the read-only posture:
    purchase, buy, exchange, modify (as imperative actions, with word boundaries).

    Past-tense forms like "purchased" are descriptive and allowed.
    """
    import re
    import typing
    from typing import get_args, get_origin

    from finops_assess.pricing import (
        AzureCommitmentDataset,
        AzureCommitmentObservation,
        SavingsPlanEligibleSpendObservation,
    )

    # Prohibited action verbs (as standalone words)
    prohibited_patterns = [
        r"\bpurchase\b",
        r"\bbuy\b",
        r"\bexchange\b",
        r"\bmodify\b",
    ]

    def _extract_literal_values(annotation: typing.Any) -> list[str]:
        """Walk Annotated/Optional/Union wrappers to find Literal[...] values."""
        if get_origin(annotation) is typing.Literal:
            return [str(v) for v in get_args(annotation)]
        args = get_args(annotation)
        out = []
        for a in args:
            out.extend(_extract_literal_values(a))
        return out

    def _check_text_for_prohibited_verbs(
        text: str, model_name: str, surface: str, prohibited_patterns: list[str]
    ) -> None:
        """Check a text surface for prohibited verbs, excluding past-tense 'purchased'."""
        for pattern in prohibited_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            # Filter out "purchased" (past tense is descriptive, not imperative)
            for match in matches:
                verb = match.group()
                start = max(0, match.start() - 3)
                end = match.end() + 2
                context = text[start:end].lower()
                # Allow "purchased" (past tense), but reject imperative "purchase"
                if verb.lower() == "purchase" and "purchased" in context:
                    continue
                # If we get here, it's a prohibited verb in imperative form
                raise AssertionError(
                    f"Prohibited verb '{verb}' found in {model_name}.{surface}: "
                    f"violates read-only posture (context: '{text[max(0, match.start() - 20) : match.end() + 20]}')"
                )

    # Models to check
    commitment_models = [
        AzureCommitmentObservation,
        SavingsPlanEligibleSpendObservation,
        AzureCommitmentDataset,
    ]

    for model_cls in commitment_models:
        model_name = model_cls.__name__

        # Check class docstring
        class_doc = model_cls.__doc__ or ""
        _check_text_for_prohibited_verbs(class_doc, model_name, "__doc__", prohibited_patterns)

        # Check every field's description
        for field_name, field_info in model_cls.model_fields.items():
            field_description = field_info.description or ""
            if field_description:
                _check_text_for_prohibited_verbs(
                    field_description, model_name, f"{field_name}.description", prohibited_patterns
                )

            # Check every Literal value in the field's annotation
            literal_values = _extract_literal_values(field_info.annotation)
            for literal_value in literal_values:
                _check_text_for_prohibited_verbs(
                    literal_value, model_name, f"{field_name}.Literal", prohibited_patterns
                )
