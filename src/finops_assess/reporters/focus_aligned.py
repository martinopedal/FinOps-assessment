"""FOCUS-aligned advisory CSV exporter (v0.5.0 — Azure-only).

Exports a ``finops-assess`` JSON findings report as a FOCUS 1.3-shaped
advisory CSV alongside a sidecar ``manifest.json``.

.. warning::
    This export is **NOT** a FOCUS 1.3 conformant Cost-and-Usage dataset.
    Rows describe corrective recommendations, not billed consumption. Cost
    columns (BilledCost, ContractedCost, EffectiveCost, ListCost) are
    intentionally empty; advisory savings are surfaced in
    EstimatedMonthlySavingsUsd. See ``docs/focus-export.md`` before loading.

Azure-only in v0.5.0: Microsoft 365, GitHub, and Azure DevOps findings are
filtered out and counted in ``surfaces_skipped``. See the D7 tracking issue
for the v0.6.0 M365 unblock contract.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from finops_assess import __version__
from finops_assess.reporters._determinism import generated_at_iso

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column contract — single source of truth for CSV header order and manifest.
# ---------------------------------------------------------------------------

COLUMN_ORDER: tuple[str, ...] = (
    "ServiceProviderName",
    "HostProviderName",
    "ServiceName",
    "ServiceCategory",
    "ServiceSubcategory",
    "ChargeCategory",
    "ChargeClass",
    "ChargeFrequency",
    "ChargeDescription",
    "SkuId",
    "ResourceId",
    "ResourceType",
    "BillingPeriodStart",
    "BillingPeriodEnd",
    "PricingCurrency",
    # Cost columns — intentionally empty in advisory output (blocker 1).
    "ListCost",
    "ContractedCost",
    "BilledCost",
    "EffectiveCost",
    # Advisory-specific columns (non-FOCUS).
    "EstimatedMonthlySavingsUsd",
    "AdvisoryFindingKey",
    "RuleId",
    "Severity",
)

# FOCUS 1.3 mandatory + supported columns we emit empty or omit entirely.
_UNSUPPORTED_COLUMNS: tuple[str, ...] = (
    "BilledCost",
    "BillingAccountId",
    "BillingAccountName",
    "CommitmentDiscountId",
    "CommitmentDiscountName",
    "CommitmentDiscountType",
    "ContractedCost",
    "ContractedUnitPrice",
    "EffectiveCost",
    "ListCost",
    "ListUnitPrice",
    "PricingQuantity",
    "PricingUnit",
    "Region",
    "SkuPriceId",
    "UsageQuantity",
    "UsageUnit",
)

_CONFORMANCE_RATIONALE = (
    "Rows describe corrective recommendations, not billed consumption. "
    "Cost columns (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally "
    "empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. "
    "See docs/focus-export.md."
)

# ---------------------------------------------------------------------------
# AdvisoryFindingKey helpers
# ---------------------------------------------------------------------------


def _canonicalise(value: Any) -> Any:
    """Recursively canonicalise an evidence value for deterministic JSON serialisation.

    Rules:
    - ``None`` → ``""`` (null collapses to empty string)
    - ``bool`` → bool (serialised as JSON true/false)
    - ``int`` → int (exact)
    - ``float`` → ``repr(float)`` (consistent precision; NaN/Inf excluded by allow_nan=False)
    - ``str`` → str (verbatim)
    - ``list`` → element-wise canonicalised, **order preserved** (see algorithm spec rule #5)
    - ``dict`` → key-sorted, value-canonicalised, recursive
    - anything else → raises ``TypeError``
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_canonicalise(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalise(v) for key, v in sorted(value.items())}
    raise TypeError(f"unhashable evidence value type: {type(value).__name__}")


def _normalize_evidence(evidence: dict[str, Any]) -> str:
    """Canonicalise the evidence dict to a single deterministic JSON string."""
    return json.dumps(
        _canonicalise(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def advisory_finding_key(finding: dict[str, Any]) -> str:
    """Compute the AdvisoryFindingKey for a single finding dict.

    Stable across runs for the same ``(rule_id, resource_id, evidence)`` tuple.
    ``resource_id`` is ``finding["principal"]`` — under the Azure-only D1 scope,
    the principal IS the ARM resource ID.

    The payload is ``SHA-256(json.dumps([rule_id, resource_id, evidence_json]))``.
    Using a JSON array as the envelope is unambiguous regardless of the characters
    present in the individual components (NUL bytes, special chars, etc.), because
    JSON string encoding escapes them uniformly (NUL → ``\\u0000``).
    """
    rule_id: str = finding["rule_id"]
    resource_id: str = finding["principal"]
    normalized = _normalize_evidence(finding.get("evidence") or {})
    envelope = json.dumps(
        [rule_id, resource_id, normalized],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(envelope.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# BillingPeriod derivation (D4 — calendar-month bucketing)
# ---------------------------------------------------------------------------


def _billing_period(finding: dict[str, Any]) -> tuple[str, str]:
    """Derive BillingPeriodStart / BillingPeriodEnd from the finding's evidence.

    D4 decision: BillingPeriodStart = first day of the month containing
    ``finding["evidence"]["observation_window_end"]`` at 00:00:00 UTC.
    BillingPeriodEnd = first day of the *next* month at 00:00:00 UTC.

    Falls back to the current UTC month when the evidence key is absent or
    unparseable, so the column is always populated.

    Known limitation (R4): findings relevant to multiple months collapse to
    the observation-window-end month. Documented in docs/focus-export.md
    § "Calendar-month bucketing — known limitation".
    """
    from datetime import UTC, datetime

    raw = (finding.get("evidence") or {}).get("observation_window_end")
    dt: datetime | None = None
    if raw:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(raw), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                break
            except ValueError:
                continue
    if dt is None:
        dt = datetime.now(UTC)

    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    # Pure-stdlib month rollover: add enough days to reach the next month.
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    # ISO 8601 date-only strings (FOCUS BillingPeriod convention).
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Column projection
# ---------------------------------------------------------------------------


def _row_for(finding: dict[str, Any]) -> dict[str, str]:
    """Project a single finding dict onto the FOCUS-aligned advisory column set."""
    bp_start, bp_end = _billing_period(finding)
    savings = finding.get("estimated_monthly_savings_usd")
    savings_str = "" if savings is None else str(savings)

    return {
        "ServiceProviderName": "Microsoft",
        "HostProviderName": "Microsoft",
        "ServiceName": "Azure",
        "ServiceCategory": "Compute",
        "ServiceSubcategory": "",
        "ChargeCategory": "Advisory",
        "ChargeClass": "Optimization",
        "ChargeFrequency": "Monthly",
        "ChargeDescription": finding.get("recommendation", ""),
        "SkuId": finding.get("current_sku") or "",
        "ResourceId": finding.get("principal", ""),
        "ResourceType": "",
        "BillingPeriodStart": bp_start,
        "BillingPeriodEnd": bp_end,
        "PricingCurrency": "USD",
        # Cost columns — empty by design (blocker 1).
        "ListCost": "",
        "ContractedCost": "",
        "BilledCost": "",
        "EffectiveCost": "",
        # Advisory-specific.
        "EstimatedMonthlySavingsUsd": savings_str,
        "AdvisoryFindingKey": advisory_finding_key(finding),
        "RuleId": finding.get("rule_id", ""),
        "Severity": finding.get("severity", ""),
    }


# ---------------------------------------------------------------------------
# Surface filtering
# ---------------------------------------------------------------------------


def _partition_findings(
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Split findings into Azure-only rows and a per-surface skip count dict."""
    azure_rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = {"ado": 0, "github": 0, "m365": 0}
    for f in findings:
        surface = f.get("surface", "")
        if surface == "azure":
            azure_rows.append(f)
        elif surface in skipped:
            skipped[surface] += 1
        else:
            # Unknown surface — count as skipped without crashing.
            skipped[surface] = skipped.get(surface, 0) + 1
    return azure_rows, skipped


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def build_focus_aligned_manifest(
    report: dict[str, Any],
    *,
    azure_rows: list[dict[str, Any]],
    skipped: dict[str, int],
) -> dict[str, Any]:
    """Build the sidecar manifest dict for a FOCUS-aligned advisory export.

    The manifest contract is ``manifest_schema_version: "0.1"`` (v0.5.0).
    Fields are declared in the order specified by Maya's stage-3 plan so that
    ``json.dumps(..., sort_keys=False)`` produces the contract-compliant field
    order documented in ``docs/schema.md``.

    PII handling
    ------------
    The engine's ``ctx.redact()`` salts every principal — including Azure
    resource IDs — with a per-run secret when ``pii_redaction=True``
    (default).  ``ResourceId`` is therefore the salted hash, not a
    cleartext ARM resource ID, and ``AdvisoryFindingKey`` rotates with
    the per-run salt for cross-run joins.  ``known_limitation`` mirrors
    the playbook reporter's contract (Noor PR #78 NIT #2 + #73).
    """
    run = report.get("run", {})
    pii_redaction = bool(run.get("pii_redaction", True))
    if pii_redaction:
        pii_handling: dict[str, Any] = {
            "mode": "azure_resource_id_per_run_salted_hash",
            "known_limitation": (
                "ResourceId is the engine's salted hash of the cleartext ARM "
                "resource ID under default redaction; AdvisoryFindingKey rotates "
                "with the per-run salt and is unsafe for cross-run joins. "
                "Re-runs will produce duplicate advisory rows. Engine "
                "tenant-stable salting is deferred to #73; until then, run "
                "with --no-pii-redaction or accept the per-run instability."
            ),
        }
    else:
        pii_handling = {
            "mode": "azure_resource_id_cleartext",
            "known_limitation": None,
        }
    return {
        "manifest_schema_version": "0.1",
        "tool": {"name": "finops-assess", "version": __version__},
        "generated_at": generated_at_iso(),
        "source_report": {
            "path": run.get("input", ""),
            "schema_version": run.get("schema_version", "1.0"),
            "pii_redaction": pii_redaction,
        },
        "dataset_type": "advisory",
        "focus_version": "1.3",
        "conformance_level": "non-conformant",
        "conformance_rationale": _CONFORMANCE_RATIONALE,
        "surfaces_included": sorted({"azure"}),
        "surfaces_skipped": dict(sorted(skipped.items())),
        "row_count": len(azure_rows),
        "unsupported_columns": list(_UNSUPPORTED_COLUMNS),
        "join_keys": [
            {
                "column": "ResourceId",
                "joins_to": "FOCUS.ResourceId",
                "stability": "per_run" if pii_redaction else "stable",
            },
            {
                "column": "AdvisoryFindingKey",
                "joins_to": None,
                "stability": "per_run" if pii_redaction else "stable",
                "notes": (
                    "Stable across runs for the same (rule_id, resource_id, evidence) "
                    "ONLY when --no-pii-redaction is set; otherwise rotates with the "
                    "per-run salt. Not a FOCUS column."
                ),
            },
        ],
        "pii_handling": pii_handling,
        "non_additive_warning": True,
        "column_order": list(COLUMN_ORDER),
        "evidence_key_fields": ["rule_id", "resource_id", "normalized_evidence"],
        "evidence_key_algorithm": (
            "sha256(json_envelope([rule_id, resource_id, normalized_evidence_json]))"
        ),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_focus_aligned_export(
    report: dict[str, Any],
    output_csv: Path,
) -> tuple[Path, Path]:
    """Write a FOCUS-aligned advisory CSV and sidecar manifest.

    Returns ``(csv_path, manifest_path)`` — both as resolved ``Path`` objects
    relative to the caller's working directory (inputs that are already absolute
    are returned unchanged).

    The CSV uses LF line endings and UTF-8 encoding regardless of platform.
    The manifest JSON is written alongside the CSV at
    ``<output_csv>.manifest.json``.

    Callers are responsible for ensuring the parent directory is writable;
    this function creates parent dirs automatically.
    """
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    all_findings: list[dict[str, Any]] = report.get("findings", [])
    azure_rows, skipped = _partition_findings(all_findings)

    # Write CSV.
    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(COLUMN_ORDER),
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for finding in azure_rows:
            writer.writerow(_row_for(finding))

    # Build and write manifest.
    manifest = build_focus_aligned_manifest(report, azure_rows=azure_rows, skipped=skipped)
    manifest_path = output_csv.parent / (output_csv.name + ".manifest.json")
    payload = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)
    manifest_path.write_text(payload + "\n", encoding="utf-8", newline="")

    return output_csv, manifest_path
