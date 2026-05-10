"""Advisory triage artefacts built from an existing finops-assess report."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finops_assess.models import Cloud, Confidence, Severity

TRIAGE_SCHEMA_VERSION = "1.0"
ADVISORY_BANNER = (
    "Template-based advisory triage only. Verify findings before action; "
    "no remediation, write scopes, or de-redaction are performed."
)

PriorityBucket = Literal["p1", "p2", "p3", "p4"]
OwnerRole = Literal[
    "identity-admin",
    "license-admin",
    "azure-owner",
    "github-org-admin",
    "ado-org-admin",
    "finops-analyst",
]
CopilotHelperMode = Literal["disabled", "sdk", "cli", "unavailable"]

_OWNER_BY_SURFACE: dict[Cloud, OwnerRole] = {
    "m365": "license-admin",
    "azure": "azure-owner",
    "github": "github-org-admin",
    "ado": "ado-org-admin",
}

_CHECKLIST_BY_SURFACE: dict[Cloud, tuple[str, ...]] = {
    "m365": (
        "Confirm the assigned persona and business exception with the license owner.",
        "Review recent sign-in and workload activity before changing any license.",
        "Verify compliance, mailbox, guest, or break-glass exceptions are not present.",
    ),
    "azure": (
        "Confirm the resource is still owned and in scope for optimisation.",
        "Review recent metrics, tags, and change windows before resizing or stopping.",
        "Verify reservations, commitments, or environment tags with the FinOps owner.",
    ),
    "github": (
        "Confirm the seat, org, or repository ownership before changing entitlements.",
        "Review recent contribution, Copilot, GHAS, and runner usage signals.",
        "Verify security or release-engineering exceptions with the GitHub admin.",
    ),
    "ado": (
        "Confirm the Azure DevOps organisation and project ownership.",
        "Review work-item, code, pipeline, and Test Plans activity before changing access.",
        "Verify stakeholder eligibility or parallel-job needs with the ADO admin.",
    ),
}

_QUESTIONS_BY_SURFACE: dict[Cloud, tuple[str, ...]] = {
    "m365": (
        "Is the principal covered by a legal hold, eDiscovery, shared-mailbox, or service-account exception?",
        "Does the persona assignment match the user's current role?",
    ),
    "azure": (
        "Is this workload seasonal, recently deployed, or intentionally kept warm?",
        "Would a right-size or commitment change affect availability targets?",
    ),
    "github": (
        "Is the seat required for a pending project, compliance control, or release window?",
        "Are repository or runner signals delayed by billing-period timing?",
    ),
    "ado": (
        "Is the access level needed for upcoming sprint, test, or release work?",
        "Are project-level permissions or stakeholder limitations acceptable?",
    ),
}


class TriageItem(BaseModel):
    """One advisory triage row derived from one source finding."""

    model_config = ConfigDict(extra="forbid")

    finding_ref: str
    source_finding_index: int = Field(..., ge=0)
    rule_id: str
    surface: Cloud
    severity: Severity
    confidence: Confidence
    principal: str
    current_sku: str | None = None
    recommended_sku: str | None = None
    estimated_monthly_savings_usd: float | None = None
    evidence_ref: str | None = None
    priority_bucket: PriorityBucket
    priority_rationale: str
    suggested_owner_role: OwnerRole
    verification_checklist: list[str] = Field(..., min_length=1)
    followup_questions: list[str] = Field(..., min_length=1)
    advisory: Literal[True] = True


class TriageReport(BaseModel):
    """Schema-versioned advisory triage report."""

    model_config = ConfigDict(extra="forbid")

    run: dict[str, Any]
    source: dict[str, Any]
    summary: dict[str, Any]
    items: list[TriageItem]


def _finding_ref(finding: dict[str, Any]) -> str:
    """Return a stable derived identifier for a source finding."""
    stable = {
        "rule_id": finding.get("rule_id"),
        "surface": finding.get("surface"),
        "principal": finding.get("principal"),
        "current_sku": finding.get("current_sku"),
        "recommended_sku": finding.get("recommended_sku"),
        "evidence": finding.get("evidence") or {},
    }
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return "finding:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _bucket(severity: Severity, confidence: Confidence, savings: float | None) -> PriorityBucket:
    """Map rule severity, confidence, and savings signal to analyst queue priority."""
    if severity == "high" and confidence == "high":
        return "p1"
    if severity == "high" or (severity == "medium" and (savings or 0) >= 100):
        return "p2"
    if severity == "medium" or confidence == "medium":
        return "p3"
    return "p4"


def _owner_for(surface: Cloud, rule_id: str) -> OwnerRole:
    """Return the closed-vocabulary owner role for a finding."""
    if rule_id.startswith("M365.GUEST") or rule_id.startswith("M365.DISABLED"):
        return "identity-admin"
    if rule_id.startswith("AZ.RESERVATION") or rule_id.startswith("AZ.LOG"):
        return "finops-analyst"
    return _OWNER_BY_SURFACE.get(surface, "finops-analyst")


def _rationale(
    severity: Severity,
    confidence: Confidence,
    savings: float | None,
    priority: PriorityBucket,
) -> str:
    """Build a deterministic advisory priority rationale."""
    savings_text = "unknown savings" if savings is None else f"${savings:.2f}/mo estimated savings"
    return (
        f"{priority.upper()} because severity is {severity}, confidence is {confidence}, "
        f"and the finding has {savings_text}."
    )


def build_triage(
    report: dict[str, Any],
    *,
    source_path: Path | None = None,
    copilot_helper: CopilotHelperMode = "disabled",
) -> TriageReport:
    """Build a deterministic advisory triage report from a finops-assess report dict."""
    run = report.get("run") or {}
    source_findings = report.get("findings") or []
    items: list[TriageItem] = []
    for index, finding in enumerate(source_findings):
        surface: Cloud = finding["surface"]
        severity: Severity = finding["severity"]
        confidence: Confidence = finding.get("confidence", "high")
        savings = finding.get("estimated_monthly_savings_usd")
        priority = _bucket(severity, confidence, savings)
        items.append(
            TriageItem(
                finding_ref=_finding_ref(finding),
                source_finding_index=index,
                rule_id=finding["rule_id"],
                surface=surface,
                severity=severity,
                confidence=confidence,
                principal=finding["principal"],
                current_sku=finding.get("current_sku"),
                recommended_sku=finding.get("recommended_sku"),
                estimated_monthly_savings_usd=savings,
                evidence_ref=finding.get("evidence_ref"),
                priority_bucket=priority,
                priority_rationale=_rationale(severity, confidence, savings, priority),
                suggested_owner_role=_owner_for(surface, finding["rule_id"]),
                verification_checklist=list(_CHECKLIST_BY_SURFACE[surface]),
                followup_questions=list(_QUESTIONS_BY_SURFACE[surface]),
            )
        )

    counts: dict[str, int] = {}
    for item in items:
        counts[item.priority_bucket] = counts.get(item.priority_bucket, 0) + 1

    input_pii_redaction = bool(run.get("pii_redaction", True))
    return TriageReport(
        run={
            "tool": "finops-assess-triage",
            "version": run.get("version"),
            "schema_version": TRIAGE_SCHEMA_VERSION,
            "generated_at": run.get("generated_at"),
            "mode": "advisory",
            "pii_redaction": input_pii_redaction,
            "advisory": True,
            "advisory_banner": ADVISORY_BANNER,
            "copilot_helper": copilot_helper,
        },
        source={
            "tool": run.get("tool"),
            "mode": run.get("mode"),
            "schema_version": run.get("schema_version", "1.0"),
            "report_path": _source_report_path(source_path, input_pii_redaction),
            "findings_count": len(source_findings),
            "input_pii_redaction": input_pii_redaction,
        },
        summary={
            "total_items": len(items),
            "priority_counts": {
                bucket: counts.get(bucket, 0) for bucket in ("p1", "p2", "p3", "p4")
            },
        },
        items=items,
    )


def _source_report_path(path: Path | None, redact_pii: bool) -> str | None:
    """Return a source report path that respects the source redaction setting."""
    if path is None:
        return None
    if redact_pii:
        return f"<redacted>/{path.name}"
    return str(path)


def resolve_copilot_helper(preferred: Literal["auto", "sdk", "cli"]) -> CopilotHelperMode:
    """Resolve an explicitly enabled GitHub Copilot helper without sending data."""
    if preferred in ("auto", "sdk") and importlib.util.find_spec("github_copilot_sdk"):
        return "sdk"
    if preferred in ("auto", "cli") and shutil.which("gh") is not None:
        return "cli"
    return "unavailable"
