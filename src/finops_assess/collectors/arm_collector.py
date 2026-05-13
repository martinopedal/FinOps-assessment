"""Azure ARM / Cost Management live collector — M5.

Pulls Azure resource inventory and utilisation metrics from the Azure
Resource Manager REST API and writes normalised CSV files for consumption
by ``finops-assess run``.

Authentication
--------------
Uses :class:`azure.identity.DefaultAzureCredential` — the same credential
chain as the Graph collector (OIDC workload identity in GitHub Actions, CLI
on developer workstations).  The service principal / managed identity must
hold the ``Reader`` role on each subscription being scanned.

Required **read-only** scopes: ``https://management.azure.com/.default``

No write scopes are requested.
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ARM_BASE = "https://management.azure.com"
_ARM_SCOPES = ["https://management.azure.com/.default"]
_RETAIL_PRICES_BASE = "https://prices.azure.com/api/retail/prices"

# ARM API versions used for each resource type.
_API_VERSIONS = {
    "subscriptions": "2022-12-01",
    "virtualMachines": "2023-09-01",
    "disks": "2023-10-02",
    "publicIPAddresses": "2023-11-01",
    "reservations": "2022-11-01",
    "benefitRecommendations": "2022-10-01",
    "workspaces": "2023-09-01",
    "workspaceUsages": "2020-08-01",
    "metrics": "2023-10-01",
}

_DEFAULT_PAGE_LIMIT = 500


def _require_deps() -> tuple[Any, Any]:
    try:
        import requests
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential, requests
    except ImportError as exc:
        raise RuntimeError(
            "The [live] extra is required for the ARM collector.  "
            "Install it with: pip install 'finops-assess[live]'"
        ) from exc


class _ArmClient:
    """Thin Azure REST client with bearer-token auth and pagination helpers."""

    def __init__(self, credential: Any, *, page_limit: int = _DEFAULT_PAGE_LIMIT) -> None:
        _, requests = _require_deps()
        self._session = requests.Session()
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        self._credential = credential
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._page_limit = page_limit

    def _get_token(self) -> str:
        now = time.monotonic()
        if self._token is None or now >= self._token_expiry - 60:
            tok = self._credential.get_token(*_ARM_SCOPES)
            self._token = tok.token
            self._token_expiry = now + tok.expires_on - time.time()
        assert self._token is not None
        return self._token

    def get(self, url: str, params: dict[str, str] | None = None) -> Any:
        _require_deps()
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        resp = self._session.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def list_all(self, url: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 0
        while url:
            page += 1
            if self._page_limit and page > self._page_limit:
                logger.warning("Reached page_limit=%d; truncating.", self._page_limit)
                break
            body = self.get(url, params=params)
            results.extend(body.get("value", []))
            url = body.get("nextLink", "")
            params = None  # nextLink already has params embedded
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource_group(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        return parts[parts.index("resourcegroups") + 1]
    except (ValueError, IndexError):
        return ""


def _renew_to_str(value: object) -> str:
    """Render the Microsoft.Capacity reservations API ``renew`` flag as a CSV cell.

    ``True`` / ``False`` map to lowercase strings the strict-column loader's
    ``_BOOL_TRUE`` / ``_BOOL_FALSE`` sets recognise. ``None`` and any other
    value map to the empty string so the strict-column loader treats the
    cell as missing and pydantic applies the model default
    (``auto_renew = None``, signal absent).
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _scope_ids_to_csv(value: object) -> str:
    """Render the API's appliedScopes list as a pipe-separated CSV cell.

    The strict-column CSV loader expects ``list[str]`` columns to be
    pipe-separated single cells (``csv_collector.py:103-104``). ``None``
    maps to the empty string (signal absent on Shared scope or when the
    API returned no list); a non-empty list maps to ``"|"``-joined ARNs.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "|".join(items)
    return ""


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _metric_window() -> tuple[str, str]:
    """14-day metric window in ISO-8601 UTC."""
    end = _now_utc()
    start = end - timedelta(days=14)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_vm_metrics(
    client: _ArmClient,
    resource_id: str,
) -> dict[str, float | None]:
    """Return avg and P95 CPU %, avg net KB/s for a VM over 14 days."""
    start, end = _metric_window()
    url = f"{_ARM_BASE}{resource_id}/providers/microsoft.insights/metrics"
    params = {
        "api-version": _API_VERSIONS["metrics"],
        "timespan": f"{start}/{end}",
        "interval": "PT1H",
        "metricnames": "Percentage CPU,Network In Total,Network Out Total",
        "aggregation": "Average,Percentile",
        "percentile": "95",
        "$top": "3",
    }
    try:
        body = client.get(url, params=params)
    except Exception as exc:
        logger.debug("Metrics unavailable for %s: %s", resource_id, exc)
        return {"avg_cpu_pct": None, "p95_cpu_pct": None, "avg_net_kbps": None}

    metrics: dict[str, list[float]] = {}
    for metric in body.get("value", []):
        name = (metric.get("name", {}).get("value") or "").lower().replace(" ", "")
        data_points: list[float] = []
        for ts in metric.get("timeseries") or []:
            for dp in ts.get("data") or []:
                val = dp.get("average")
                if val is not None:
                    data_points.append(val)
        if data_points:
            metrics[name] = data_points

    def avg(vals: list[float]) -> float | None:
        return sum(vals) / len(vals) if vals else None

    def percentile95(vals: list[float]) -> float | None:
        if not vals:
            return None
        sorted_vals = sorted(vals)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    cpu = metrics.get("percentagecpu", [])
    net_in = metrics.get("networkingtotal", metrics.get("networkintotal", []))
    net_out = metrics.get("networkouttotal", [])
    # Network is in bytes/hour; convert to KB/s
    net_combined = (
        [i + o for i, o in zip(net_in, net_out, strict=False)]
        if net_in and net_out
        else net_in or net_out
    )
    net_kbps = [b / 3600 / 1024 for b in net_combined]

    return {
        "avg_cpu_pct": avg(cpu),
        "p95_cpu_pct": percentile95(cpu),
        "avg_net_kbps": avg(net_kbps),
    }


# ---------------------------------------------------------------------------
# Data collection steps
# ---------------------------------------------------------------------------


def _list_subscriptions(client: _ArmClient) -> list[str]:
    url = f"{_ARM_BASE}/subscriptions?api-version={_API_VERSIONS['subscriptions']}"
    subs = client.list_all(url)
    ids = [
        s["subscriptionId"] for s in subs if s.get("state") == "Enabled" and s.get("subscriptionId")
    ]
    logger.info("Found %d enabled subscriptions.", len(ids))
    return ids


def _collect_vms(client: _ArmClient, sub_id: str) -> list[dict[str, Any]]:
    url = (
        f"{_ARM_BASE}/subscriptions/{sub_id}/providers/Microsoft.Compute/"
        f"virtualMachines?api-version={_API_VERSIONS['virtualMachines']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list VMs in %s: %s", sub_id, exc)
        return []


def _collect_disks(client: _ArmClient, sub_id: str) -> list[dict[str, Any]]:
    url = (
        f"{_ARM_BASE}/subscriptions/{sub_id}/providers/Microsoft.Compute/"
        f"disks?api-version={_API_VERSIONS['disks']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list disks in %s: %s", sub_id, exc)
        return []


def _collect_public_ips(client: _ArmClient, sub_id: str) -> list[dict[str, Any]]:
    url = (
        f"{_ARM_BASE}/subscriptions/{sub_id}/providers/Microsoft.Network/"
        f"publicIPAddresses?api-version={_API_VERSIONS['publicIPAddresses']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list public IPs in %s: %s", sub_id, exc)
        return []


def _collect_reservations(client: _ArmClient) -> list[dict[str, Any]]:
    url = (
        f"{_ARM_BASE}/providers/Microsoft.Capacity/reservations?"
        f"api-version={_API_VERSIONS['reservations']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list reservations: %s", exc)
        return []


def _collect_benefit_recommendations(client: _ArmClient, sub_id: str) -> list[dict[str, Any]]:
    """Collect Azure Benefit Recommendations from the Cost Management API."""
    url = (
        f"{_ARM_BASE}/subscriptions/{sub_id}/providers/Microsoft.CostManagement/"
        f"benefitRecommendations?api-version={_API_VERSIONS['benefitRecommendations']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list benefit recommendations in %s: %s", sub_id, exc)
        return []


# Allowed enum values from the Azure Cost Management Benefit Recommendations API.
# Reference: https://learn.microsoft.com/en-us/rest/api/cost-management/benefit-recommendations/list
_BR_SCOPE_KINDS = {"Single", "Shared"}
_BR_TERMS = {"P1Y", "P3Y"}
_BR_LOOKBACKS = {"Last7Days", "Last30Days", "Last60Days"}
_BR_SUPPORTED_KINDS = {"SavingsPlan", "Reservation"}


def _benefit_recommendation_scope_arn(rec: dict[str, Any], sub_id: str) -> str:
    """Derive the ARN-shaped scope identifier from a Benefit Recommendation row.

    ``properties.scope`` is the discriminator (literal ``"Single"`` or ``"Shared"``)
    and MUST NOT be used as the scope ARN. The actual identifier comes from:

    * ``properties.subscriptionId`` (+ optional ``properties.resourceGroup``) when
      ``properties.scope == "Single"``;
    * the recommendation's ``id`` URL path (parent of the
      ``/providers/Microsoft.CostManagement/...`` segment) when
      ``properties.scope == "Shared"`` (billing-account / billing-profile rooted).

    Falls back to the per-iteration ``/subscriptions/{sub_id}`` when the API
    omits the discriminator or the discriminator-specific fields.
    """
    props = rec.get("properties") or {}
    discriminator = props.get("scope") or ""

    if discriminator == "Single":
        sub_from_props = props.get("subscriptionId") or sub_id
        rg = props.get("resourceGroup")
        if rg:
            return f"/subscriptions/{sub_from_props}/resourceGroups/{rg}"
        return f"/subscriptions/{sub_from_props}"

    if discriminator == "Shared":
        rid = rec.get("id") or ""
        marker = "/providers/Microsoft.CostManagement/"
        if marker in rid:
            return rid.split(marker, 1)[0]
        return f"/subscriptions/{sub_id}"

    return f"/subscriptions/{sub_id}"


def _normalise_benefit_recommendation(rec: dict[str, Any], sub_id: str) -> dict[str, Any] | None:
    """Convert a raw Benefit Recommendation API row into the CSV row shape.

    Returns ``None`` (and emits a warning) when the row has an enum value the
    downstream pydantic model would reject. Defensive boundary filtering keeps
    a future API enum addition (e.g. ``term=P5Y``) from crashing the collector.
    """
    rid = rec.get("id") or ""
    props = rec.get("properties") or {}
    discriminator = props.get("scope") or ""
    term = props.get("term") or ""
    lookback = props.get("lookBackPeriod") or ""
    kind = rec.get("kind") or ""

    if discriminator and discriminator not in _BR_SCOPE_KINDS:
        logger.warning(
            "Skipping benefit recommendation %s in %s: unrecognised scope %r",
            rid,
            sub_id,
            discriminator,
        )
        return None
    if term and term not in _BR_TERMS:
        logger.warning(
            "Skipping benefit recommendation %s in %s: unrecognised term %r",
            rid,
            sub_id,
            term,
        )
        return None
    if lookback and lookback not in _BR_LOOKBACKS:
        logger.warning(
            "Skipping benefit recommendation %s in %s: unrecognised lookBackPeriod %r",
            rid,
            sub_id,
            lookback,
        )
        return None
    if kind and kind not in _BR_SUPPORTED_KINDS:
        logger.warning(
            "Skipping benefit recommendation %s in %s: unsupported kind %r",
            rid,
            sub_id,
            kind,
        )
        return None

    details = props.get("recommendationDetails") or {}
    return {
        "recommendation_id": rid,
        "scope": _benefit_recommendation_scope_arn(rec, sub_id),
        "scope_kind": discriminator,
        "term": term,
        "lookback_period": lookback,
        "arm_sku_name": props.get("armSkuName") or "",
        "cost_without_benefit_usd": str(details.get("costWithoutBenefit") or ""),
        "recommended_hourly_commit_usd": str(details.get("recommendedQuantity") or ""),
        "net_savings_usd": str(details.get("netSavings") or ""),
        "wastage_usd": str(details.get("wastage") or ""),
        "benefit_kind": kind or "SavingsPlan",
    }


def _collect_log_workspaces(client: _ArmClient, sub_id: str) -> list[dict[str, Any]]:
    url = (
        f"{_ARM_BASE}/subscriptions/{sub_id}/providers/Microsoft.OperationalInsights/"
        f"workspaces?api-version={_API_VERSIONS['workspaces']}"
    )
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Failed to list Log Analytics workspaces in %s: %s", sub_id, exc)
        return []


def _get_workspace_usage(client: _ArmClient, workspace_id: str) -> float | None:
    """Return average daily ingest GB over the last 30 days, or None."""
    url = f"{_ARM_BASE}{workspace_id}/usages?api-version={_API_VERSIONS['workspaceUsages']}"
    try:
        body = client.get(url)
        for item in body.get("value", []):
            if (item.get("name", {}).get("value") or "").lower() == "dataingestion":
                val = item.get("currentValue")
                if val is not None:
                    # currentValue is MB/day for a 30-day billing period; convert to GB
                    return round(float(val) / 1024, 3)
    except Exception as exc:
        logger.debug("Could not fetch workspace usage for %s: %s", workspace_id, exc)
    return None


# Commitment tier thresholds in GB/day.  Based on Azure LA pricing (approximate).
_LA_TIERS = [
    (100, "100gb_per_day_commitment"),
    (200, "200gb_per_day_commitment"),
    (300, "300gb_per_day_commitment"),
    (400, "400gb_per_day_commitment"),
    (500, "500gb_per_day_commitment"),
]
# Pay-as-you-go break-even: ≥10 GB/day the 100 GB commitment tier is cheaper.
_LA_PAYG_THRESHOLD = 10.0
_LA_COMMITMENT_SAVINGS_PCT = 15.0  # conservative estimate at the 100 GB tier


def _recommend_la_tier(daily_gb: float) -> tuple[str | None, float | None]:
    """Return (recommended_tier, est_savings_pct) for a workspace ingest level."""
    if daily_gb < _LA_PAYG_THRESHOLD:
        return None, None
    # Find the smallest commitment tier that covers the daily volume.
    for threshold, tier_name in _LA_TIERS:
        if daily_gb <= threshold:
            return tier_name, _LA_COMMITMENT_SAVINGS_PCT
    return _LA_TIERS[-1][1], _LA_COMMITMENT_SAVINGS_PCT


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def collect_arm(
    output_dir: Path,
    *,
    subscription_ids: list[str] | None = None,
    collect_metrics: bool = True,
    page_limit: int = _DEFAULT_PAGE_LIMIT,
    _credential: Any = None,
) -> None:
    """Pull Azure ARM data and write normalised CSV files to *output_dir*.

    Writes:
    * ``azure_resources.csv``
    * ``azure_reservations.csv``
    * ``azure_log_workspaces.csv``

    If *subscription_ids* is omitted the collector enumerates all enabled
    subscriptions the credential has Reader access to.

    Set *collect_metrics* to ``False`` to skip Azure Monitor metrics calls
    (useful when Reader on subscriptions doesn't include Monitoring Reader).

    The private *_credential* parameter is for testing only.
    """
    if _credential is None:
        DefaultAzureCredential, _ = _require_deps()
        _credential = DefaultAzureCredential()
    client = _ArmClient(_credential, page_limit=page_limit)
    output_dir = Path(output_dir)

    # Determine subscriptions ------------------------------------------------
    sub_ids = subscription_ids or _list_subscriptions(client)

    resource_rows: list[dict[str, Any]] = []
    reservation_rows: list[dict[str, Any]] = []
    workspace_rows: list[dict[str, Any]] = []

    # ---- VMs, Disks, Public IPs (per subscription) -------------------------
    for sub_id in sub_ids:
        logger.info("Scanning subscription %s …", sub_id)

        # VMs
        for vm in _collect_vms(client, sub_id):
            rid: str = vm.get("id") or ""
            props = vm.get("properties") or {}
            hw = (vm.get("properties") or {}).get("hardwareProfile") or {}
            sku = hw.get("vmSize") or ""
            location = vm.get("location") or ""
            tags = vm.get("tags") or {}
            env_tag = tags.get("env") or tags.get("environment") or tags.get("Environment")
            sub_offer = props.get("subscriptionOffer") or None

            metrics: dict[str, float | None] = {}
            if collect_metrics and rid:
                metrics = _get_vm_metrics(client, rid)

            resource_rows.append(
                {
                    "resource_id": rid,
                    "resource_type": "virtualMachine",
                    "sku": sku,
                    "location": location,
                    "avg_cpu_pct": ""
                    if (v := metrics.get("avg_cpu_pct")) is None
                    else str(round(float(v), 2)),
                    "p95_cpu_pct": ""
                    if (v := metrics.get("p95_cpu_pct")) is None
                    else str(round(float(v), 2)),
                    "p95_mem_pct": "",  # Memory metrics require guest agent diagnostics
                    "avg_net_kbps": ""
                    if (v := metrics.get("avg_net_kbps")) is None
                    else str(round(float(v), 2)),
                    "days_inactive": "",
                    "attached": "",
                    "associated": "",
                    "monthly_cost_usd": "",
                    "recommended_sku": "",
                    "subscription_id": sub_id,
                    "subscription_offer": sub_offer or "",
                    "env_tag": env_tag or "",
                    "os_type": (props.get("storageProfile", {}).get("osDisk", {}).get("osType"))
                    or "",
                    "license_type": props.get("licenseType") or "",
                }
            )

        # Disks
        for disk in _collect_disks(client, sub_id):
            rid = disk.get("id") or ""
            props = disk.get("properties") or {}
            sku_info = disk.get("sku") or {}
            sku = sku_info.get("name") or ""
            location = disk.get("location") or ""
            # A disk is "unmanaged" / detached when managedBy is absent/null.
            managed_by: str | None = props.get("managedBy")
            attached = bool(managed_by)
            # "diskState" can be "Unattached", "Attached", "Reserved", etc.
            disk_state = (props.get("diskState") or "").lower()
            if not attached or disk_state == "unattached":
                # Use time_created to estimate days_inactive
                time_created = props.get("timeCreated") or ""
                days_inactive: str = ""
                if time_created:
                    try:
                        dt = datetime.fromisoformat(time_created.replace("Z", "+00:00"))
                        days_inactive = str((_now_utc() - dt).days)
                    except ValueError:
                        pass
                resource_rows.append(
                    {
                        "resource_id": rid,
                        "resource_type": "managedDisk",
                        "sku": sku,
                        "location": location,
                        "avg_cpu_pct": "",
                        "p95_cpu_pct": "",
                        "p95_mem_pct": "",
                        "avg_net_kbps": "",
                        "days_inactive": days_inactive,
                        "attached": "false",
                        "associated": "",
                        "monthly_cost_usd": "",
                        "recommended_sku": "",
                        "subscription_id": sub_id,
                        "subscription_offer": "",
                        "env_tag": "",
                    }
                )

        # Public IPs
        for pip in _collect_public_ips(client, sub_id):
            rid = pip.get("id") or ""
            props = pip.get("properties") or {}
            sku_info = pip.get("sku") or {}
            sku = sku_info.get("name") or ""
            location = pip.get("location") or ""
            # Associated if ipConfiguration is present
            ip_config = props.get("ipConfiguration") or props.get("natGateway")
            associated = bool(ip_config)
            resource_rows.append(
                {
                    "resource_id": rid,
                    "resource_type": "publicIp",
                    "sku": sku,
                    "location": location,
                    "avg_cpu_pct": "",
                    "p95_cpu_pct": "",
                    "p95_mem_pct": "",
                    "avg_net_kbps": "",
                    "days_inactive": "",
                    "attached": "",
                    "associated": "true" if associated else "false",
                    "monthly_cost_usd": "",
                    "recommended_sku": "",
                    "subscription_id": sub_id,
                    "subscription_offer": "",
                    "env_tag": "",
                }
            )

        # Log Analytics workspaces
        for ws in _collect_log_workspaces(client, sub_id):
            rid = ws.get("id") or ""
            ws_name = ws.get("name") or ""
            props = ws.get("properties") or {}
            daily_gb = _get_workspace_usage(client, rid)
            rec_tier, est_pct = (
                _recommend_la_tier(daily_gb) if daily_gb is not None else (None, None)
            )
            sku_info = props.get("sku") or {}
            current_tier = sku_info.get("name") or ""
            workspace_rows.append(
                {
                    "workspace_id": rid,
                    "workspace_name": ws_name,
                    "daily_gb": "" if daily_gb is None else str(daily_gb),
                    "commitment_tier_gb": "",
                    "recommended_tier": rec_tier or "",
                    "est_savings_pct": "" if est_pct is None else str(est_pct),
                    "monthly_cost_usd": "",
                }
            )
            _ = current_tier  # reserved for future use

    # ---- Benefit Recommendations (per-subscription) -------------------------
    # M1/M3 fix: row construction lives in `_normalise_benefit_recommendation` so
    # the discriminator-vs-ARN derivation and friendly enum guards are unit-testable
    # without a live ARM client.
    benefit_recs_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    lookback_priority = {"Last60Days": 3, "Last30Days": 2, "Last7Days": 1}

    for sub_id in sub_ids:
        for rec in _collect_benefit_recommendations(client, sub_id):
            row = _normalise_benefit_recommendation(rec, sub_id)
            if row is None:
                continue

            scope_val = row["scope"]
            term = row["term"]
            lookback = row["lookback_period"]

            key = (scope_val, term)
            priority = lookback_priority.get(lookback, 0)

            # Keep the highest-lookback (or highest net savings on tie) per (scope, term)
            if key in benefit_recs_by_key:
                existing_priority = lookback_priority.get(
                    benefit_recs_by_key[key].get("lookback_period") or "", 0
                )
                if priority > existing_priority:
                    pass  # Replace existing
                elif priority == existing_priority:
                    # Tie: prefer higher net savings
                    existing_savings = float(benefit_recs_by_key[key].get("net_savings_usd") or 0.0)
                    new_savings = float(row["net_savings_usd"] or 0.0)
                    if new_savings <= existing_savings:
                        continue
                else:
                    continue  # Keep existing

            benefit_recs_by_key[key] = row

    benefit_rec_rows = list(benefit_recs_by_key.values())

    # ---- Reservations (tenant-level) ----------------------------------------
    for res in _collect_reservations(client):
        props = res.get("properties") or {}
        # Skip cancelled / failed / expired / pending rows -- only Succeeded
        # reservations are actionable as a renewal-review signal. See
        # docs/plans/059-az-commitment-renewal-review.md §2.2 (E9).
        if (props.get("displayProvisioningState") or "").lower() != "succeeded":
            continue
        rid = res.get("id") or ""
        sku_info = res.get("sku") or {}
        util = None
        util_data = props.get("utilization") or {}
        if util_data:
            # utilization.aggregates is a list of {grain, value} dicts;
            # we want the 30-day aggregate.
            for agg in util_data.get("aggregates") or []:
                if (agg.get("grain") or "").lower() in ("30days", "30d", "monthly"):
                    util = agg.get("value")
            if util is None:
                # Fall back to onDemandUtilizationPercentage if available
                util = util_data.get("onDemandUtilizationPercentage")

        reservation_rows.append(
            {
                "reservation_id": rid,
                "reservation_name": props.get("displayName") or "",
                "sku": sku_info.get("name") or "",
                "scope": props.get("appliedScopeType") or "",
                "utilization_pct": "" if util is None else str(round(float(util), 2)),
                "monthly_cost_usd": "",
                "expiry_date": props.get("expiryDate") or "",
                "auto_renew": _renew_to_str(props.get("renew")),
                "applied_scope_subscription_ids": _scope_ids_to_csv(props.get("appliedScopes")),
            }
        )

    # Write CSV files ---------------------------------------------------------
    _write_csv(
        output_dir / "azure_resources.csv",
        [
            "resource_id",
            "resource_type",
            "sku",
            "location",
            "avg_cpu_pct",
            "p95_cpu_pct",
            "p95_mem_pct",
            "avg_net_kbps",
            "days_inactive",
            "attached",
            "associated",
            "monthly_cost_usd",
            "recommended_sku",
            "subscription_id",
            "subscription_offer",
            "env_tag",
            "os_type",
            "license_type",
        ],
        resource_rows,
    )
    _write_csv(
        output_dir / "azure_reservations.csv",
        [
            "reservation_id",
            "reservation_name",
            "sku",
            "scope",
            "utilization_pct",
            "monthly_cost_usd",
            "expiry_date",
            "auto_renew",
            "applied_scope_subscription_ids",
        ],
        reservation_rows,
    )
    _write_csv(
        output_dir / "azure_log_workspaces.csv",
        [
            "workspace_id",
            "workspace_name",
            "daily_gb",
            "commitment_tier_gb",
            "recommended_tier",
            "est_savings_pct",
            "monthly_cost_usd",
        ],
        workspace_rows,
    )
    _write_csv(
        output_dir / "azure_benefit_recommendations.csv",
        [
            "recommendation_id",
            "scope",
            "scope_kind",
            "term",
            "lookback_period",
            "arm_sku_name",
            "cost_without_benefit_usd",
            "recommended_hourly_commit_usd",
            "net_savings_usd",
            "wastage_usd",
            "benefit_kind",
        ],
        benefit_rec_rows,
    )
    logger.info(
        "ARM collection complete: %d resources, %d reservations, %d workspaces, %d benefit recs",
        len(resource_rows),
        len(reservation_rows),
        len(workspace_rows),
        len(benefit_rec_rows),
    )
