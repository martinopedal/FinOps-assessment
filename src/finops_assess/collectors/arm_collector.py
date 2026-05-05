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

    # ---- Reservations (tenant-level) ----------------------------------------
    for res in _collect_reservations(client):
        rid = res.get("id") or ""
        props = res.get("properties") or {}
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
    logger.info(
        "ARM collection complete: %d resources, %d reservations, %d workspaces",
        len(resource_rows),
        len(reservation_rows),
        len(workspace_rows),
    )
