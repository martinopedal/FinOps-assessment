"""Azure DevOps live collector — M6b.

Pulls ADO user entitlements and pipeline utilisation data from the Azure
DevOps REST API and writes normalised CSV files for consumption by
``finops-assess run``.

Authentication
--------------
Supply a **read-only** Personal Access Token (PAT) via the
``AZURE_DEVOPS_PAT`` environment variable (recommended) or the *pat*
parameter.  The PAT must have the following **read-only** scopes:

* ``Member Entitlement Management`` → Read  (user entitlements)
* ``Build`` → Read  (pipeline utilisation)
* ``Project and Team`` → Read  (project enumeration)

Alternatively, the collector accepts a bearer token (``AZURE_DEVOPS_TOKEN``)
from an Entra-backed service principal — pass *use_bearer=True* to enable
this path.  The service principal must have *Project Reader* or higher
at the organization level.

No write scopes are requested or accepted.
"""

from __future__ import annotations

import base64
import csv
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ADO_BASE = "https://dev.azure.com"
_VSAEX_BASE = "https://vsaex.dev.azure.com"
_DEFAULT_PAGE_LIMIT = 200

# ADO user access levels as returned by the entitlements API.
# We map these to our AdoSeat.seat_type Literal values.
_ACCESS_LEVEL_MAP = {
    "express": "basic",
    "advanced": "basic",
    "stakeholder": "stakeholder",
    "vssubscriber": "basic_plus_test",
    "eligible": "stakeholder",
    "none": "stakeholder",
    # Extended access
    "extendedmem": "basic_plus_test",
}


def _require_requests() -> Any:
    try:
        import requests

        return requests
    except ImportError as exc:
        raise RuntimeError(
            "The [live] extra is required for the ADO collector.  "
            "Install it with: pip install 'finops-assess[live]'"
        ) from exc


class _AdoClient:
    """Minimal Azure DevOps REST client."""

    def __init__(
        self,
        org: str,
        *,
        pat: str | None = None,
        bearer: str | None = None,
        page_limit: int = _DEFAULT_PAGE_LIMIT,
    ) -> None:
        requests = _require_requests()
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._org = org
        self._page_limit = page_limit

        if bearer:
            self._session.headers["Authorization"] = f"Bearer {bearer}"
        elif pat:
            token = base64.b64encode(f":{pat}".encode()).decode()
            self._session.headers["Authorization"] = f"Basic {token}"
        else:
            raise ValueError("Either pat or bearer must be provided.")

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        _require_requests()
        resp = self._session.get(url, params=params, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def list_all_entitlements(self) -> list[dict[str, Any]]:
        """Paginate /vsaex/_apis/userentitlements using continuationToken."""
        url = (
            f"{_VSAEX_BASE}/{self._org}/_apis/userentitlements"
            "?api-version=7.1&top=100&select=Projects,Extensions"
        )
        results: list[dict[str, Any]] = []
        page = 0
        while url:
            page += 1
            if self._page_limit and page > self._page_limit:
                logger.warning("Reached page_limit=%d; truncating.", self._page_limit)
                break
            body = self.get(url)
            if body is None:
                break
            results.extend(body.get("members") or [])
            # ADO uses X-MS-ContinuationToken in the response body
            token = (body.get("continuationToken") or "").strip()
            if token:
                url = (
                    f"{_VSAEX_BASE}/{self._org}/_apis/userentitlements"
                    f"?api-version=7.1&top=100&select=Projects,Extensions"
                    f"&continuationToken={token}"
                )
            else:
                break
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days_since_iso(dt_str: str | None) -> int | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = datetime.now(tz=UTC) - dt
        return max(0, delta.days)
    except ValueError:
        return None


def _collect_parallel_job_limits(client: _AdoClient) -> dict[str, Any]:
    """Return parallel-job resource limits for the organisation."""
    url = f"{_ADO_BASE}/{client._org}/_apis/distributedtask/resourcelimits?api-version=7.1"
    try:
        body = client.get(url)
        return body or {}
    except Exception as exc:
        logger.warning("Could not fetch resource limits for %s: %s", client._org, exc)
        return {}


def _collect_pipeline_runs_p95(client: _AdoClient) -> int | None:
    """Estimate P95 concurrent pipeline usage from the last 30 days.

    Queries all projects and their recent pipeline runs, then computes the
    P95 concurrent jobs by looking at overlapping run windows.

    Returns None when the data is unavailable or insufficient.
    """
    projects_url = f"{_ADO_BASE}/{client._org}/_apis/projects?api-version=7.1&$top=200"
    try:
        body = client.get(projects_url)
    except Exception as exc:
        logger.debug("Cannot list projects: %s", exc)
        return None

    projects = (body or {}).get("value") or []
    run_windows: list[tuple[datetime, datetime]] = []

    for project in projects:
        project_id = project.get("id") or ""
        if not project_id:
            continue
        runs_url = (
            f"{_ADO_BASE}/{client._org}/{project_id}/_apis/build/builds"
            "?api-version=7.1&$top=200&queryOrder=startTimeDescending"
            "&statusFilter=completed"
        )
        try:
            runs_body = client.get(runs_url)
        except Exception:
            continue
        for run in (runs_body or {}).get("value") or []:
            start_str = run.get("startTime")
            end_str = run.get("finishTime")
            if not start_str or not end_str:
                continue
            try:
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                run_windows.append((start, end))
            except ValueError:
                pass

    if not run_windows:
        return None

    # Count concurrent runs at each start-point to estimate P95.
    sorted_by_start = sorted(run_windows, key=lambda x: x[0])
    concurrencies: list[int] = []
    for i, (start, _) in enumerate(sorted_by_start):
        concurrent = sum(1 for s, e in sorted_by_start[: i + 1] if s <= start <= e)
        concurrencies.append(concurrent)

    concurrencies.sort()
    p95_idx = int(len(concurrencies) * 0.95)
    return concurrencies[min(p95_idx, len(concurrencies) - 1)]


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


def collect_ado(
    output_dir: Path,
    *,
    org: str,
    pat: str | None = None,
    bearer: str | None = None,
    use_bearer: bool = False,
    page_limit: int = _DEFAULT_PAGE_LIMIT,
) -> None:
    """Pull Azure DevOps data and write normalised CSV files to *output_dir*.

    *org* is the ADO organisation name (the segment in
    ``https://dev.azure.com/{org}``).

    Credentials:
    * *pat* — read-only Personal Access Token.  Defaults to the
      ``AZURE_DEVOPS_PAT`` environment variable.
    * *bearer* / *use_bearer* — Entra bearer token.  Defaults to the
      ``AZURE_DEVOPS_TOKEN`` environment variable when *use_bearer* is
      ``True``.

    Writes:
    * ``ado_seats.csv``
    * ``ado_orgs.csv``
    """
    resolved_pat = pat or os.environ.get("AZURE_DEVOPS_PAT")
    resolved_bearer: str | None = None
    if use_bearer or not resolved_pat:
        resolved_bearer = bearer or os.environ.get("AZURE_DEVOPS_TOKEN")

    if not resolved_pat and not resolved_bearer:
        raise RuntimeError(
            "An Azure DevOps credential is required.  Set AZURE_DEVOPS_PAT "
            "(preferred) or AZURE_DEVOPS_TOKEN, or pass pat=/bearer= to collect_ado()."
        )

    client = _AdoClient(
        org,
        pat=resolved_pat,
        bearer=resolved_bearer,
        page_limit=page_limit,
    )
    output_dir = Path(output_dir)

    logger.info("Collecting ADO user entitlements for %s …", org)
    entitlements = client.list_all_entitlements()

    seat_rows: list[dict[str, Any]] = []
    for member in entitlements:
        user = member.get("user") or {}
        principal: str = (
            user.get("mailAddress") or user.get("uniqueName") or user.get("displayName") or ""
        )
        if not principal:
            continue

        access_level = member.get("accessLevel") or {}
        # accessLevelName: "Express", "Advanced", "Stakeholder", "VSSubscriber", etc.
        level_name = (access_level.get("accessLevelName") or "").lower()
        seat_type = _ACCESS_LEVEL_MAP.get(level_name, "basic")

        # Derive SKU id from seat type
        sku_map = {
            "stakeholder": "ADO.STAKEHOLDER",
            "basic": "ADO.BASIC",
            "basic_plus_test": "ADO.BASIC_TEST",
        }
        sku_id = sku_map.get(seat_type, "ADO.BASIC")

        # Last access — ADO provides this in the entitlement
        last_access_str = member.get("lastAccessedDate") or access_level.get("lastAccessedDate")
        last_activity_days = _days_since_iso(last_access_str)

        # Extensions: check if Test Plans extension is present
        extensions = member.get("extensions") or []
        has_test_plans = any(
            "testplans" in (ext.get("id") or "").lower()
            or "test plans" in (ext.get("name") or "").lower()
            for ext in extensions
        )
        if has_test_plans and seat_type == "basic":
            seat_type = "basic_plus_test"
            sku_id = "ADO.BASIC_TEST"

        # Project activity: check if only boards/work items were accessed
        # (stakeholder-eligible proxy)
        projects = member.get("projectEntitlements") or []
        non_board_activity = any(
            (p.get("projectPermissions") or {}).get("hasRepoAccess")
            or (p.get("projectPermissions") or {}).get("hasBuildAccess")
            for p in projects
        )
        only_stakeholder_activity = bool(projects) and not non_board_activity

        seat_rows.append(
            {
                "principal": principal,
                "org": org,
                "seat_type": seat_type,
                "sku_id": sku_id,
                "last_activity_days": "" if last_activity_days is None else str(last_activity_days),
                "only_stakeholder_activity": str(only_stakeholder_activity).lower(),
                "last_test_plan_days": "",  # Not directly available from entitlements API
            }
        )

    # ---- Parallel-job limits ------------------------------------------------
    logger.info("Collecting ADO parallel-job limits for %s …", org)
    limits = _collect_parallel_job_limits(client)
    purchased = None
    if limits:
        # The resource limits endpoint returns a list; find Hosted Pipeline quota.
        items = limits if isinstance(limits, list) else limits.get("value") or [limits]
        for item in items:
            if isinstance(item, dict):
                hosted = item.get("parallelSmallJobsCount") or item.get("totalCount")
                if hosted is not None:
                    purchased = int(hosted)
                    break

    logger.info("Estimating P95 concurrent pipeline usage for %s …", org)
    p95_concurrent = _collect_pipeline_runs_p95(client)

    org_rows: list[dict[str, Any]] = [
        {
            "org": org,
            "purchased_parallel_jobs": "" if purchased is None else str(purchased),
            "p95_concurrent_jobs": "" if p95_concurrent is None else str(p95_concurrent),
        }
    ]

    # Write CSVs --------------------------------------------------------------
    _write_csv(
        output_dir / "ado_seats.csv",
        [
            "principal",
            "org",
            "seat_type",
            "sku_id",
            "last_activity_days",
            "only_stakeholder_activity",
            "last_test_plan_days",
        ],
        seat_rows,
    )
    _write_csv(
        output_dir / "ado_orgs.csv",
        ["org", "purchased_parallel_jobs", "p95_concurrent_jobs"],
        org_rows,
    )
    logger.info(
        "ADO collection complete: %d seats, org row written.",
        len(seat_rows),
    )
