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
    min_uncovered_usd: float | None = Field(default=None, ge=0)
    enabled: bool = True
    evidence_key_version: int = Field(
        default=1,
        ge=1,
        description=(
            "Version of the AdvisoryFindingKey hash algorithm for this rule. "
            "Defaults to 1 (v0.5.0 algorithm: sha256(rule_id \\x00 resource_id \\x00 "
            "normalized_evidence_json)). Bump to 2+ when the rule's evidence shape changes "
            "in a way that would silently break cross-run joins; also bump "
            "manifest_schema_version to '0.2' in the same PR."
        ),
    )
    adapter_class: str = Field(
        default="generic",
        min_length=1,
        description=(
            "Adapter class hint for the playbook reporter. "
            "Default 'generic' emits adapter_hints for ServiceNow/Jira/GitHub. "
            "Future values: 'azure_cost', 'identity', 'github_seat'."
        ),
    )


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


# ---------------------------------------------------------------------------
# M365 SKU-mix and family-level summary models (D.6 frontier epic).
# These aggregate per-family coverage and usage signals to support
# SKU-mix fragmentation, Entra P2 unused, security add-on overlap,
# Copilot SKU-mix review, and GSA unused-or-overlap rules.
#
# Family taxonomy paraphrased from M365 Maps (https://m365maps.com/);
# linked as reference, never copied (hard rule 3).
# ---------------------------------------------------------------------------

M365FamilyName = Literal[
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


class M365FamilySummary(BaseModel):
    """Aggregate M365/Entra/security/Copilot/GSA family-level coverage.

    Supports SKU-mix fragmentation, Entra P2 unused, security add-on overlap,
    Copilot SKU-mix review, and GSA unused-or-overlap rules. NO per-principal
    fields—only aggregate counts. NO tenant IDs or subscription IDs (Noor's
    sovereign-cloud catch: default PII redaction does not protect against
    tenant-id leakage in GSA scenarios).

    ``total_assigned`` counts all SKU assignments in this family (a user with
    2 SKUs from the same family contributes 2). ``distinct_users_with_assignment``
    counts unique principals. ``distinct_active_users`` and
    ``distinct_inactive_users`` partition principals by sign-in activity.

    ``feature_usage_signals`` is optional and family-specific: e.g., for
    ``entra_p2`` family, might include ``{"pim_assignments": 5,
    "identity_protection_policies": 3}``—aggregate counts only, NO user lists.
    """

    model_config = ConfigDict(extra="forbid")

    family_name: M365FamilyName
    total_assigned: int = Field(default=0, ge=0)
    distinct_users_with_assignment: int = Field(default=0, ge=0)
    distinct_active_users: int = Field(default=0, ge=0)
    distinct_inactive_users: int = Field(default=0, ge=0)
    feature_usage_signals: dict[str, int] = Field(default_factory=dict)
    coverage_note: str | None = None


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
    # Subscription / environment metadata (used by AZ.DEV_TEST_SUB_MISMATCH)
    subscription_id: str | None = None
    subscription_offer: str | None = None
    env_tag: str | None = None
    # OS / licence-bring metadata (used by AZ.AHB_ELIGIBLE)
    os_type: Literal["Windows", "Linux"] | None = None
    license_type: str | None = None


class AzureReservation(BaseModel):
    """A normalised Azure Reservation / Savings Plan snapshot.

    ``utilization_pct`` is the average utilization over the trailing 30 days
    (0-100). Rules abstain when the signal is absent rather than assuming
    zero utilization.

    ``scope`` carries the API's ``appliedScopeType`` discriminator string
    (``"Single"`` / ``"Shared"`` / ``"ManagementGroup"``, case-insensitive
    in CSV mode). The field name is a legacy from the M5 Azure rules; a
    future issue may rename it to ``applied_scope_type``.

    ``applied_scope_subscription_ids`` is the operator-owned list of
    subscription ARNs the discount is applied to (``Microsoft.Capacity``
    reservations API ``properties.appliedScopes``). ``None`` means the
    signal is absent (CSV-mode operators may leave the column blank);
    ``AZ.RESERVATION_SCOPE_MISMATCH`` abstains on ``None``. An empty list
    on a ``Single``-scope row is contradictory; the rule logs WARN and
    abstains on that row.

    ``expiry_date`` is the commitment expiration date (ISO 8601 YYYY-MM-DD).
    ``auto_renew`` is the operator's renewal-intent flag; ``None`` means the
    signal is absent (CSV-mode operators may leave it blank). Both fields
    drive ``AZ.COMMITMENT_RENEWAL_REVIEW``; rules abstain on ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    reservation_id: str = Field(..., min_length=1)
    reservation_name: str | None = None
    sku: str | None = None
    scope: str | None = None
    utilization_pct: float | None = Field(default=None, ge=0, le=100)
    monthly_cost_usd: float | None = Field(default=None, ge=0)
    expiry_date: str | None = Field(default=None, min_length=10, max_length=10)
    auto_renew: bool | None = None
    applied_scope_subscription_ids: list[str] | None = None


class AzureLogWorkspace(BaseModel):
    """A normalised Log Analytics workspace ingest snapshot.

    ``daily_gb`` is the average daily ingest volume. ``recommended_tier`` is
    set by the collector when a commitment tier would be more cost-effective
    than pay-as-you-go pricing (based on the daily ingest volume). Rules fire
    when ``recommended_tier`` is populated, indicating the workspace is not on
    the optimal tier.
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    workspace_name: str | None = None
    daily_gb: float | None = Field(default=None, ge=0)
    commitment_tier_gb: float | None = Field(default=None, ge=0)
    recommended_tier: str | None = None
    est_savings_pct: float | None = Field(default=None, ge=0, le=100)
    monthly_cost_usd: float | None = Field(default=None, ge=0)


class AzureBenefitRecommendation(BaseModel):
    """A normalised Azure Benefit Recommendations API observation.

    Each row represents one (scope, term, lookback_period) recommendation
    returned by the Cost Management ``benefitRecommendations`` endpoint.
    Rules consume these to surface uncovered on-demand spend that could
    be moved under a Savings Plan or Reservation commitment.

    The collector emits one row per unique (scope, term, lookback_period);
    the rule de-duplicates to one finding per (scope, term).
    """

    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    scope_kind: Literal["Single", "Shared"] | None = None
    term: Literal["P1Y", "P3Y"]
    lookback_period: Literal["Last7Days", "Last30Days", "Last60Days"]
    arm_sku_name: str | None = None
    cost_without_benefit_usd: float | None = Field(default=None, ge=0)
    recommended_hourly_commit_usd: float | None = Field(default=None, ge=0)
    net_savings_usd: float | None = Field(default=None, ge=0)
    wastage_usd: float | None = Field(default=None, ge=0)
    benefit_kind: Literal["SavingsPlan", "Reservation"] = "SavingsPlan"


GitHubSeatType = Literal[
    "enterprise",
    "team",
    "copilot_business",
    "copilot_enterprise",
    "ghas_committer",
]


class GitHubSeat(BaseModel):
    """A normalised GitHub seat (Enterprise/Team/Copilot/GHAS-committer).

    ``last_activity_days`` is the number of days since the last observed
    contribution, review, issue activity, or sign-in (``None`` means
    "never observed"). ``copilot_acceptances_30d`` is only meaningful for
    Copilot seats; ``None`` means we lack the signal, ``0`` means the
    seat is provably inactive.
    """

    model_config = ConfigDict(extra="forbid")

    principal: str = Field(..., min_length=1)
    org: str | None = None
    seat_type: GitHubSeatType
    sku_id: str | None = None
    last_activity_days: int | None = Field(default=None, ge=0)
    copilot_acceptances_30d: int | None = Field(default=None, ge=0)


class GitHubOrg(BaseModel):
    """A normalised GitHub org-level snapshot for org-scoped rules.

    Drives ``GH.GHAS_OVER_PROVISIONED`` (where billable committers exceed
    repos that are actually producing scanning signal) and
    ``GH.RUNNER_TIER_MISMATCH`` (where included runner minutes are
    materially under- or over-utilised). All counts are optional; rules
    abstain rather than fabricate when a signal is missing.
    """

    model_config = ConfigDict(extra="forbid")

    org: str = Field(..., min_length=1)
    ghas_repo_count: int | None = Field(default=None, ge=0)
    actively_scanned_repos: int | None = Field(default=None, ge=0)
    active_committers: int | None = Field(default=None, ge=0)
    runner_tier: str | None = None
    runner_minutes_used: int | None = Field(default=None, ge=0)
    runner_minutes_included: int | None = Field(default=None, ge=0)


class PersonaAssignment(BaseModel):
    """The persona resolved for one principal, with the signal that won."""

    model_config = ConfigDict(extra="forbid")

    principal: str
    persona_id: str
    matched_by: Literal["override", "title", "group", "fallback"] = "fallback"
    confidence: Confidence = "medium"


AdoSeatType = Literal["stakeholder", "basic", "basic_plus_test"]


class AdoSeat(BaseModel):
    """A normalised Azure DevOps seat / access-level assignment.

    ``last_activity_days`` is days since the last work-item, code, or pipeline
    activity (``None`` means no telemetry). ``only_stakeholder_activity`` is
    ``True`` when the only observed activity is board reads and comments, making
    the user a candidate for the free Stakeholder tier. ``last_test_plan_days``
    is days since the last Test Plans activity — only meaningful for
    ``basic_plus_test`` seats.
    """

    model_config = ConfigDict(extra="forbid")

    principal: str = Field(..., min_length=1)
    org: str | None = None
    seat_type: AdoSeatType
    sku_id: str | None = None
    last_activity_days: int | None = Field(default=None, ge=0)
    only_stakeholder_activity: bool | None = None
    last_test_plan_days: int | None = Field(default=None, ge=0)


class AdoOrgUsage(BaseModel):
    """Org-level Azure DevOps pipeline usage snapshot.

    Drives ``ADO.PARALLEL_JOBS_OVER_PROVISIONED``. All counts are optional;
    the rule abstains when either signal is absent.
    """

    model_config = ConfigDict(extra="forbid")

    org: str = Field(..., min_length=1)
    purchased_parallel_jobs: int | None = Field(default=None, ge=0)
    p95_concurrent_jobs: int | None = Field(default=None, ge=0)


class NormalizedDataset(BaseModel):
    """The complete input the rule engine consumes."""

    model_config = ConfigDict(extra="forbid")

    users: list[UserRecord] = Field(default_factory=list)
    assignments: list[LicenseAssignment] = Field(default_factory=list)
    usage: list[UsageSignal] = Field(default_factory=list)
    m365_family_summaries: list[M365FamilySummary] = Field(default_factory=list)
    azure_resources: list[AzureResource] = Field(default_factory=list)
    azure_reservations: list[AzureReservation] = Field(default_factory=list)
    azure_log_workspaces: list[AzureLogWorkspace] = Field(default_factory=list)
    azure_benefit_recommendations: list[AzureBenefitRecommendation] = Field(default_factory=list)
    github_seats: list[GitHubSeat] = Field(default_factory=list)
    github_orgs: list[GitHubOrg] = Field(default_factory=list)
    ado_seats: list[AdoSeat] = Field(default_factory=list)
    ado_orgs: list[AdoOrgUsage] = Field(default_factory=list)
    overrides: dict[str, str] = Field(default_factory=dict)
