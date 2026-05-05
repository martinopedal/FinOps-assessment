"""Pydantic models for catalog, persona, rule, and normalised-record data."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Cloud = Literal["m365", "azure", "github", "ado"]
Severity = Literal["info", "low", "medium", "high"]
Confidence = Literal["high", "medium", "low"]


class CatalogEntry(BaseModel):
    """A single licensable SKU or service plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1)
    cloud: Cloud
    list_price_usd_month: float | None = Field(default=None, ge=0)
    source_url: str | None = None
    includes: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    successor_of: list[str] = Field(default_factory=list)
    notes: str | None = None


class Persona(BaseModel):
    """A target user archetype, expressed via required feature tags."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    description: str | None = None
    required_features: list[str] = Field(default_factory=list)
    title_patterns: list[str] = Field(default_factory=list)
    group_patterns: list[str] = Field(default_factory=list)


class Rule(BaseModel):
    """A declarative savings rule definition (engine impl arrives in M2)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    surface: Cloud
    severity: Severity = "medium"
    summary: str
    recommendation_template: str
    inactivity_days: int | None = Field(default=None, ge=1)
    enabled: bool = True


class Finding(BaseModel):
    """A rule-engine output row."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    surface: Cloud
    severity: Severity
    principal: str
    current_sku: str | None = None
    recommended_sku: str | None = None
    estimated_monthly_savings_usd: float | None = None
    recommendation: str
    evidence_ref: str | None = None
    confidence: Confidence = "high"
    evidence: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalised-record models - emitted by the CSV collector (M2) and, later,
# by the live Graph / ARM / GitHub / ADO collectors (M4-M6). Every collector
# is responsible for producing exactly these shapes; the rule engine never
# sees raw API rows.
# ---------------------------------------------------------------------------


class UserRecord(BaseModel):
    """A normalised principal (human user, guest, shared mailbox, or service)."""

    model_config = ConfigDict(extra="forbid")

    principal: str = Field(..., min_length=1)
    display_name: str | None = None
    user_type: Literal["member", "guest", "shared_mailbox", "service"] = "member"
    account_enabled: bool = True
    job_title: str | None = None
    department: str | None = None
    groups: list[str] = Field(default_factory=list)
    mailbox_size_gb: float | None = Field(default=None, ge=0)
    last_sign_in_days: int | None = Field(default=None, ge=0)


class LicenseAssignment(BaseModel):
    """A SKU assignment for a principal."""

    model_config = ConfigDict(extra="forbid")

    principal: str = Field(..., min_length=1)
    sku_id: str = Field(..., min_length=1)
    assigned_date: str | None = None


class UsageSignal(BaseModel):
    """Per-principal activity signal for a service plan or capability tag.

    ``signal`` is a free-form key the rule engine recognises (e.g.
    ``copilot``, ``defender_o365``, ``purview_dlp``, ``entra_p2``,
    ``exchange``, ``sharepoint``, ``teams``). ``last_activity_days`` is the
    number of days since the last observed activity; ``null`` means
    "never observed".
    """

    model_config = ConfigDict(extra="forbid")

    principal: str = Field(..., min_length=1)
    signal: str = Field(..., min_length=1)
    last_activity_days: int | None = Field(default=None, ge=0)


class AzureResource(BaseModel):
    """A normalised Azure resource snapshot used by the M2 Azure rules."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(..., min_length=1)
    resource_type: Literal[
        "virtualMachine",
        "managedDisk",
        "publicIp",
    ]
    sku: str | None = None
    location: str | None = None
    # Activity / utilisation signals (rules pick what they need)
    avg_cpu_pct: float | None = Field(default=None, ge=0, le=100)
    p95_cpu_pct: float | None = Field(default=None, ge=0, le=100)
    p95_mem_pct: float | None = Field(default=None, ge=0, le=100)
    avg_net_kbps: float | None = Field(default=None, ge=0)
    days_inactive: int | None = Field(default=None, ge=0)
    attached: bool | None = None
    associated: bool | None = None
    monthly_cost_usd: float | None = Field(default=None, ge=0)
    recommended_sku: str | None = None


class PersonaAssignment(BaseModel):
    """The persona resolved for one principal, with the signal that won."""

    model_config = ConfigDict(extra="forbid")

    principal: str
    persona_id: str
    matched_by: Literal["override", "title", "group", "fallback"] = "fallback"
    confidence: Confidence = "medium"


class NormalizedDataset(BaseModel):
    """The complete input the rule engine consumes."""

    model_config = ConfigDict(extra="forbid")

    users: list[UserRecord] = Field(default_factory=list)
    assignments: list[LicenseAssignment] = Field(default_factory=list)
    usage: list[UsageSignal] = Field(default_factory=list)
    azure_resources: list[AzureResource] = Field(default_factory=list)
    overrides: dict[str, str] = Field(default_factory=dict)
