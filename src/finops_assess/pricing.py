"""Pydantic models for Azure pricing observations.

This module defines the data contract for region-price observations —
**not catalog constants**. These models are intended to be populated by:
- Customer-supplied pricing exports (CSV/JSON)
- Live collectors querying the Azure Retail Prices API
- Cost Management exports containing effective rates

Observations are runtime data supplied by the operator or collector; they
are NOT packaged with the repo under `data/catalog/`. The catalog contains
SKU metadata, feature tags, and bundle relationships; pricing observations
contain time-stamped, region-specific, currency-specific price points.

This separation allows the tool to operate with list prices (default) or
customer-specific effective rates (EA/MCA/CSP discounts) without hard-coding
tenant-specific agreements into source control.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Acceptable sources for pricing observations. This is intentionally a small
# closed set — any new source requires a reviewed schema update.
PricingSource = Literal[
    "azure_retail_api",  # Azure Retail Prices API (list price)
    "cost_management_export",  # Cost Management export (effective rate)
    "customer_supplied",  # Operator-provided CSV/JSON
]


class AzureRegionPriceObservation(BaseModel):
    """A single region-price observation for an Azure SKU or meter.

    This is an **observation**, NOT a catalog constant. It represents a
    price point observed at a specific time, from a specific source, in a
    specific region and currency. Rules use these observations to detect
    region-price variance, meter anomalies, and SKU region right-sizing
    opportunities.

    **Key design choices:**
    - `currency` is explicit and constrained to USD for now. When multi-currency
      support is added, this field will be expanded to include other ISO 4217
      codes, and rules will handle currency normalization explicitly.
    - `unit_price_usd` is the canonical price field. It is ≥0 and represents
      the price per `unit_of_measure` (e.g., per hour, per GB, per 100 hours).
    - `observed_at` is an ISO 8601 date string (YYYY-MM-DD). Collectors and
      customers supply this; the model does not generate timestamps. If the
      observation date is unknown, the collector should record the date the
      observation was retrieved, NOT leave it null.
    - `source` documents provenance: was this list price from the Retail Prices
      API, an effective rate from Cost Management, or a customer-supplied value?
    - `region` is the Azure region identifier (e.g., "eastus", "westeurope").
      Collectors are responsible for normalizing region names to the canonical
      Azure region identifier used in ARM (not display names).
    - `sku_id` is the Azure SKU ID or service identifier (e.g., "Standard_D2s_v3",
      "P10"). Rules may join this to catalog entries or use it as-is.
    - `meter_name` is optional and used when the observation is at meter
      granularity (Cost Management exports often report at meter level).

    **What makes an observation distinct:**
    An observation is uniquely identified by the tuple:
    `(sku_id, region, meter_name, observed_at, source)`. The same SKU in the
    same region may have multiple observations from different sources (list vs
    effective rate) or different time windows.

    **Observation freshness:**
    Rules should define their own staleness thresholds. A 90-day-old list price
    observation may be acceptable for some rules; a 7-day-old effective rate
    observation may be too old for others. The model does not enforce freshness.

    **Out of scope (deferred to #28, #30):**
    - Reservation / Savings Plan pricing (commitment-based rates)
    - Agreement-type discounts (EA/MCA/CSP multipliers)
    - Sovereign cloud regions (requires security/compliance review first)
    """

    model_config = ConfigDict(extra="forbid")

    region: str = Field(
        ..., min_length=1, description="Azure region identifier (e.g., 'eastus', 'westeurope')"
    )
    sku_id: str = Field(
        ..., min_length=1, description="Azure SKU or service ID (e.g., 'Standard_D2s_v3', 'P10')"
    )
    meter_name: str | None = Field(
        default=None, description="Meter name if observation is at meter granularity"
    )
    unit_price_usd: float = Field(..., ge=0, description="Price per unit of measure in USD")
    currency: Literal["USD"] = Field(default="USD", description="Currency code (USD only for now)")
    unit_of_measure: str | None = Field(
        default=None, description="Unit of measure (e.g., '1 Hour', '1 GB', '100 Hours')"
    )
    observed_at: str = Field(
        ..., min_length=10, max_length=10, description="ISO 8601 date (YYYY-MM-DD)"
    )
    source: PricingSource = Field(..., description="Provenance of the observation")


class AzureRegionPriceDataset(BaseModel):
    """A collection of region-price observations.

    This wrapper exists so that collectors and customers can supply a versioned
    batch of observations with metadata about when the dataset was generated,
    what it covers, and any disclaimers.

    Rules consume individual observations from the `observations` list; the
    dataset-level metadata is for auditing and freshness checks.
    """

    model_config = ConfigDict(extra="forbid")

    observations: list[AzureRegionPriceObservation] = Field(default_factory=list)
    dataset_generated_at: str | None = Field(
        default=None, description="ISO 8601 timestamp when this dataset was generated"
    )
    dataset_version: str | None = Field(
        default=None, description="Optional version identifier for this dataset"
    )
    notes: str | None = Field(default=None, description="Human-readable notes about this dataset")
