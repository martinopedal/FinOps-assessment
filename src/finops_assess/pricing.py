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


# ---------------------------------------------------------------------------
# Azure commitment (Reserved Instance / Savings Plan) observation models
# ---------------------------------------------------------------------------

# Acceptable sources for commitment observations.
CommitmentObservationSource = Literal[
    "cost_management_api",  # Azure Cost Management REST API
    "reservation_summaries_api",  # Reservations Summaries API
    "customer_supplied",  # Operator-provided CSV/JSON
]


# Commitment type distinguishes RIs from Savings Plans.
CommitmentType = Literal[
    "reserved_instance",  # VM, SQL, Cosmos DB, etc. Reserved Instances
    "savings_plan_compute",  # Compute Savings Plan (VMs, App Service, etc.)
    "savings_plan_azure",  # Azure Savings Plan (broader coverage)
]


# Commitment scope indicates the boundary of commitment applicability.
CommitmentScope = Literal[
    "single_subscription",  # Scoped to one subscription
    "shared_subscription",  # Shared across multiple subscriptions
    "management_group",  # Scoped at management group level
]


class AzureCommitmentObservation(BaseModel):
    """An observation of a purchased Azure commitment (Reserved Instance or Savings Plan).

    This is an **observation**, NOT a recommendation or instruction. It represents
    a commitment that the customer has already purchased, as reported by Azure Cost
    Management APIs or supplied by the operator. Rules use these observations to
    detect underutilization, over-commitment, coverage gaps, scope mismatches, and
    renewal review opportunities.

    **Key design choices:**
    - `commitment_type` distinguishes RIs from Savings Plans (different coverage/scope
      semantics: RIs are resource-specific, SPs are consumption-based).
    - `utilization_pct` represents the percentage of purchased capacity that was
      actually used over a trailing window (e.g., 30 days). 0% means the commitment
      is entirely unused; 100% means fully utilized; >100% is not possible.
    - `coverage_pct` represents what portion of eligible on-demand spend is covered
      by this commitment over a trailing window. Low coverage suggests under-commitment;
      high coverage combined with low utilization suggests over-commitment.
    - `utilization_window_days` and `coverage_window_days` document the time windows
      for these metrics (typically 7, 30, or 90 days). Rules define their own
      staleness thresholds.
    - `scope` indicates whether the commitment is scoped to a single subscription,
      shared across subscriptions, or at management group level. Rules may flag
      scope mismatches (e.g., single-subscription RI applied to multi-subscription
      workload).
    - `expiry_date` is the commitment expiration date (ISO 8601 YYYY-MM-DD). Rules
      define their own renewal review windows (e.g., "flag commitments expiring
      within 90 days").
    - `observed_at` is the date this observation was recorded (ISO 8601 YYYY-MM-DD).
      Collectors should record the date the observation was retrieved, NOT leave it null.
    - `source` documents provenance: was this from Cost Management API, Reservation
      Summaries API, or customer-supplied CSV?

    **What makes an observation distinct:**
    A commitment observation is uniquely identified by `commitment_id`. The same
    commitment may have multiple observations over time (different `observed_at`),
    but each observation represents a snapshot at a specific point in time.

    **Observation freshness:**
    Rules should define their own staleness thresholds. A 90-day-old utilization
    observation may be too old for some rules; a 7-day-old observation may be
    sufficient for others. The model does not enforce freshness.

    **Out of scope (deferred to rule PRs):**
    - Commitment recommendations (e.g., "consider migrating RI to SP")
    - Commitment pricing/cost modeling (handled by separate pricing observations)
    - Commitment-to-resource mapping (collectors produce normalized records for rules)
    """

    model_config = ConfigDict(extra="forbid")

    commitment_id: str = Field(
        ..., min_length=1, description="Commitment ID (reservation ID or savings plan ID)"
    )
    commitment_name: str | None = Field(
        default=None, description="Optional human-readable commitment name"
    )
    commitment_type: CommitmentType = Field(
        ...,
        description="Type of commitment (reserved_instance, savings_plan_compute, savings_plan_azure)",
    )
    sku_id: str | None = Field(
        default=None,
        description="SKU covered by this commitment (e.g., 'Standard_D2s_v3' for RI; None for SPs)",
    )
    region: str | None = Field(
        default=None,
        description="Azure region (for region-scoped RIs; None for global SPs)",
    )
    scope: CommitmentScope = Field(
        ...,
        description="Commitment scope (single_subscription, shared_subscription, management_group)",
    )
    utilization_pct: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentage of purchased capacity actually used (0-100, trailing window)",
    )
    utilization_window_days: int | None = Field(
        default=None,
        ge=1,
        description="Trailing window for utilization metric (e.g., 7, 30, 90 days)",
    )
    coverage_pct: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentage of eligible on-demand spend covered by this commitment (0-100, trailing window)",
    )
    coverage_window_days: int | None = Field(
        default=None, ge=1, description="Trailing window for coverage metric (e.g., 7, 30, 90 days)"
    )
    monthly_cost_usd: float | None = Field(
        default=None, ge=0, description="Commitment cost per month in USD"
    )
    expiry_date: str | None = Field(
        default=None,
        min_length=10,
        max_length=10,
        description="Commitment expiration date (ISO 8601 YYYY-MM-DD)",
    )
    observed_at: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="ISO 8601 date when this observation was recorded (YYYY-MM-DD)",
    )
    source: CommitmentObservationSource = Field(..., description="Provenance of the observation")
    notes: str | None = Field(default=None, description="Optional collector/operator notes")


class SavingsPlanEligibleSpendObservation(BaseModel):
    """An observation of on-demand spend eligible for Savings Plan coverage.

    This is an **observation**, NOT a recommendation. It represents on-demand
    Azure consumption that COULD be covered by a Savings Plan commitment but
    currently is not. Rules use these observations to detect opportunities for
    commitment expansion.

    **Key design choices:**
    - `eligible_spend_usd` is the total on-demand spend (per month or trailing
      window) that would be eligible for Savings Plan discounts if a commitment
      were in place. This is NOT a recommendation to commit; it is a measurement.
    - `resource_type` indicates what kind of resource generated this spend (e.g.,
      "virtualMachine", "sqlDatabase", "appService"). Savings Plan eligibility
      varies by resource type and SP type (Compute SP vs Azure SP).
    - `window_days` documents the time window for this spend measurement (typically
      30 or 90 days). Rules define their own thresholds for "material" eligible spend.
    - `region` is optional and used when eligible spend is region-specific (Compute
      SPs are region-agnostic, but the underlying spend may be region-concentrated).

    **What makes an observation distinct:**
    An eligible spend observation is uniquely identified by `(resource_type, region,
    window_days, observed_at, source)`. The same resource type may have multiple
    observations from different sources or different time windows.

    **Out of scope (deferred to rule PRs):**
    - Savings Plan recommendations (e.g., "consider committing to X USD/hour")
    - ROI modeling (requires pricing data and commitment term length)
    - Resource-to-commitment mapping (collectors produce normalized records for rules)
    """

    model_config = ConfigDict(extra="forbid")

    resource_type: str = Field(
        ...,
        min_length=1,
        description="Resource type generating eligible spend (e.g., 'virtualMachine', 'sqlDatabase')",
    )
    region: str | None = Field(
        default=None, description="Azure region (optional; None for region-agnostic aggregates)"
    )
    eligible_spend_usd: float = Field(
        ..., ge=0, description="Monthly on-demand spend eligible for Savings Plan coverage (USD)"
    )
    window_days: int = Field(
        ..., ge=1, description="Trailing window for spend measurement (e.g., 30, 90 days)"
    )
    observed_at: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="ISO 8601 date when this observation was recorded (YYYY-MM-DD)",
    )
    source: CommitmentObservationSource = Field(..., description="Provenance of the observation")
    notes: str | None = Field(default=None, description="Optional collector/operator notes")


class AzureCommitmentDataset(BaseModel):
    """A collection of Azure commitment observations and eligible spend observations.

    This wrapper exists so that collectors and customers can supply a versioned
    batch of commitment-related observations with metadata about when the dataset
    was generated, what it covers, and any disclaimers.

    Rules consume individual observations from the `commitments` and
    `eligible_spend_observations` lists; the dataset-level metadata is for
    auditing and freshness checks.
    """

    model_config = ConfigDict(extra="forbid")

    commitments: list[AzureCommitmentObservation] = Field(default_factory=list)
    eligible_spend_observations: list[SavingsPlanEligibleSpendObservation] = Field(
        default_factory=list
    )
    dataset_generated_at: str | None = Field(
        default=None, description="ISO 8601 timestamp when this dataset was generated"
    )
    dataset_version: str | None = Field(
        default=None, description="Optional version identifier for this dataset"
    )
    notes: str | None = Field(default=None, description="Human-readable notes about this dataset")


# ---------------------------------------------------------------------------
# Pricing profile (agreement-type discounts) models
# ---------------------------------------------------------------------------

# Agreement type distinguishes list from negotiated discount mechanisms.
AgreementType = Literal["list", "ea", "mca", "csp", "mosp", "negotiated"]

# Scope indicates what the pricing profile applies to.
PricingProfileScope = Literal["azure", "m365", "github", "ado"]

# Source distinguishes default-list from customer-supplied.
PricingProfileSource = Literal["default_list", "customer_supplied"]


class PricingProfile(BaseModel):
    """A pricing profile representing agreement-type discounts.

    This model represents customer-specific agreement discounts (EA/MCA/CSP/MOSP/
    negotiated) as multipliers applied to list-price observations. It does NOT
    contain pricing data itself; it contains the multiplier and metadata needed
    to compute effective rates.

    **Default posture:** discount_multiplier=1.0 (list price), source="default_list".
    Rules can distinguish "no customer discount data" from "customer explicitly
    provided 1.0".

    **Currency matching:** Rules must verify `profile.currency == observation.currency`
    before applying the multiplier. Cross-currency application is undefined behavior.

    **Temporal validity:** Rules must verify `observation.observed_at` falls within
    `[effective_from, effective_to]` if those fields are provided. The model does
    not enforce temporal validation — rules are responsible for checking date ranges.

    **Scope:** Profiles are scoped to a surface (azure/m365/github/ado). Rules filter
    profiles by scope before applying. A customer with multiple agreements (EA for
    Azure, CSP for M365) supplies multiple profiles.

    **Out of scope (intentional design choices):**
    - No hardcoded tenant-specific discount values anywhere in this model or its
      defaults. The model REQUIRES customer-supplied data OR defaults to 1.0 (list).
    - No auto-conversion of currencies. If profile.currency != observation.currency,
      rules must reject the pairing or log a warning.
    - No agreement-to-observation mapping logic. Rules join observations with profiles;
      this model only defines the profile schema.
    """

    model_config = ConfigDict(extra="forbid")

    agreement_type: AgreementType = Field(
        ..., description="Agreement type (list, ea, mca, csp, mosp, negotiated)"
    )
    discount_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Discount multiplier applied to list price (0.0=free, 1.0=list, 0.85=15% discount)",
    )
    currency: Literal["USD"] = Field(
        default="USD",
        description="Currency for this pricing profile (must match observation currency)",
    )
    scope: PricingProfileScope = Field(
        ..., description="What this profile applies to (azure, m365, github, ado)"
    )
    effective_from: str | None = Field(
        default=None,
        min_length=10,
        max_length=10,
        description="Profile effective start date (ISO 8601 YYYY-MM-DD)",
    )
    effective_to: str | None = Field(
        default=None,
        min_length=10,
        max_length=10,
        description="Profile effective end date (ISO 8601 YYYY-MM-DD)",
    )
    source: PricingProfileSource = Field(
        default="default_list",
        description="Provenance: default_list (no customer data) or customer_supplied",
    )
    notes: str | None = Field(default=None, description="Optional notes about this pricing profile")
