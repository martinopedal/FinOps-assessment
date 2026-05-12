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
