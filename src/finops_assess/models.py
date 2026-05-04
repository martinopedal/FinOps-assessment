"""Pydantic models for catalog, persona, and rule data."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Cloud = Literal["m365", "azure", "github", "ado"]
Severity = Literal["info", "low", "medium", "high"]


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
