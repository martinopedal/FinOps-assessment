"""GitHub live collector — M6a.

Pulls GitHub Enterprise seat, Copilot, GHAS, and runner usage data from
the GitHub REST API and writes normalised CSV files for consumption by
``finops-assess run``.

Authentication
--------------
Supply a **read-only** GitHub token via the ``GITHUB_TOKEN`` environment
variable (recommended) or the *token* parameter.  For enterprise-level
endpoints the token must belong to an enterprise owner or an installed
GitHub App with the following permissions:

* ``Enterprise administration`` → Read  (for consumed-licenses and
  Copilot billing endpoints)
* ``Organization administration`` → Read  (for GHAS and Actions billing)
* ``Members`` → Read  (for org member enumeration)

No write permissions are requested or accepted.
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GH_BASE = "https://api.github.com"
_DEFAULT_PAGE_LIMIT = 200


def _require_requests() -> Any:
    try:
        import requests

        return requests
    except ImportError as exc:
        raise RuntimeError(
            "The [live] extra is required for the GitHub collector.  "
            "Install it with: pip install 'finops-assess[live]'"
        ) from exc


class _GitHubClient:
    """Minimal GitHub REST client with token auth and pagination."""

    def __init__(self, token: str, *, page_limit: int = _DEFAULT_PAGE_LIMIT) -> None:
        requests = _require_requests()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._page_limit = page_limit

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        _require_requests()
        resp = self._session.get(url, params=params, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def list_all(self, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Paginate using page/per_page query parameters."""
        results: list[dict[str, Any]] = []
        params = dict(params or {})
        params.setdefault("per_page", "100")
        page = 1
        while True:
            if self._page_limit and page > self._page_limit:
                logger.warning("Reached page_limit=%d; truncating.", self._page_limit)
                break
            params["page"] = str(page)
            body = self.get(url, params=params)
            if body is None:
                break
            if isinstance(body, list):
                batch = body
            elif isinstance(body, dict):
                # Some endpoints wrap results in a key
                batch = (
                    body.get("seats")
                    or body.get("users")
                    or body.get("runners")
                    or body.get("organizations")
                    or []
                )
            else:
                break
            if not batch:
                break
            results.extend(batch)
            if len(batch) < int(params.get("per_page", 100)):
                break
            page += 1
        return results


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------


def _collect_enterprise_seats(client: _GitHubClient, enterprise: str) -> list[dict[str, Any]]:
    """Return raw consumed-licence records for an enterprise."""
    url = f"{_GH_BASE}/enterprises/{enterprise}/consumed-licenses"
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Enterprise seat list failed for %s: %s", enterprise, exc)
        return []


def _collect_copilot_seats(client: _GitHubClient, enterprise: str) -> list[dict[str, Any]]:
    """Return Copilot Business/Enterprise seat records."""
    url = f"{_GH_BASE}/enterprises/{enterprise}/copilot/billing/seats"
    try:
        return client.list_all(url)
    except Exception as exc:
        logger.warning("Copilot seat list failed for %s: %s", enterprise, exc)
        return []


def _collect_ghas_org(client: _GitHubClient, org: str) -> dict[str, Any] | None:
    """Return GHAS billing summary for an org."""
    url = f"{_GH_BASE}/orgs/{org}/settings/billing/advanced-security"
    try:
        result: dict[str, Any] | None = client.get(url)
        return result
    except Exception as exc:
        logger.warning("GHAS billing unavailable for %s: %s", org, exc)
        return None


def _collect_actions_billing(client: _GitHubClient, org: str) -> dict[str, Any] | None:
    """Return Actions billing summary (runner minutes) for an org."""
    url = f"{_GH_BASE}/orgs/{org}/settings/billing/actions"
    try:
        result: dict[str, Any] | None = client.get(url)
        return result
    except Exception as exc:
        logger.debug("Actions billing unavailable for %s: %s", org, exc)
        return None


def _days_since_iso(dt_str: str | None) -> int | None:
    if not dt_str:
        return None
    import datetime

    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = datetime.datetime.now(tz=datetime.UTC) - dt
        return max(0, delta.days)
    except ValueError:
        return None


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


def collect_github(
    output_dir: Path,
    *,
    enterprise: str | None = None,
    orgs: list[str] | None = None,
    token: str | None = None,
    page_limit: int = _DEFAULT_PAGE_LIMIT,
) -> None:
    """Pull GitHub data and write normalised CSV files to *output_dir*.

    At least one of *enterprise* or *orgs* must be provided.

    *token* defaults to the ``GITHUB_TOKEN`` environment variable.

    Writes:
    * ``github_seats.csv``
    * ``github_orgs.csv``
    """
    resolved_token = token or os.environ.get("GITHUB_TOKEN")
    if not resolved_token:
        raise RuntimeError(
            "A GitHub token is required.  Set GITHUB_TOKEN or pass token= to collect_github()."
        )

    client = _GitHubClient(resolved_token, page_limit=page_limit)
    output_dir = Path(output_dir)

    seat_rows: list[dict[str, Any]] = []
    org_rows: list[dict[str, Any]] = []

    # ---- Enterprise seats (includes org members) ----------------------------
    if enterprise:
        logger.info("Collecting GitHub Enterprise seats for %s …", enterprise)
        for seat in _collect_enterprise_seats(client, enterprise):
            github_com = seat.get("github_com_user") or {}
            upn: str = github_com.get("login") or seat.get("login") or ""
            if not upn:
                continue
            last_active = github_com.get("updated_at") or github_com.get("created_at")
            seat_rows.append(
                {
                    "principal": upn,
                    "org": enterprise,
                    "seat_type": "enterprise",
                    "sku_id": "GH.ENTERPRISE",
                    "last_activity_days": _days_since_iso(last_active) if last_active else "",
                    "copilot_acceptances_30d": "",
                }
            )

    # ---- Copilot seats -------------------------------------------------------
    if enterprise:
        logger.info("Collecting GitHub Copilot seats for %s …", enterprise)
        for seat in _collect_copilot_seats(client, enterprise):
            assignee = seat.get("assignee") or {}
            upn = assignee.get("login") or ""
            if not upn:
                continue
            last_activity = seat.get("last_activity_at")
            last_activity_days = _days_since_iso(last_activity)

            # Determine Copilot tier from plan type
            plan_type = (seat.get("plan_type") or "").lower()
            sku_id = "GH.COPILOT_ENTERPRISE" if "enterprise" in plan_type else "GH.COPILOT_BUSINESS"
            seat_type = "copilot_enterprise" if "enterprise" in plan_type else "copilot_business"

            # acceptances_30d is not directly available from the REST API;
            # the Activity endpoint provides editor-level data but not totals.
            # We use the last_activity signal as a proxy: if the seat hasn't
            # had ANY activity in 30 days, set acceptances_30d = 0.
            copilot_acceptances: str = ""
            if last_activity_days is not None and last_activity_days >= 30:
                copilot_acceptances = "0"

            seat_rows.append(
                {
                    "principal": upn,
                    "org": enterprise,
                    "seat_type": seat_type,
                    "sku_id": sku_id,
                    "last_activity_days": ""
                    if last_activity_days is None
                    else str(last_activity_days),
                    "copilot_acceptances_30d": copilot_acceptances,
                }
            )

    # ---- GHAS + runner data per org -----------------------------------------
    all_orgs = list(orgs or [])
    # Also process orgs the enterprise belongs to, if provided separately
    for org in all_orgs:
        logger.info("Collecting org-level data for %s …", org)

        # GHAS
        ghas = _collect_ghas_org(client, org)
        actions = _collect_actions_billing(client, org)

        ghas_repo_count: int | None = None
        actively_scanned: int | None = None
        active_committers: int | None = None
        runner_minutes_used: int | None = None
        runner_minutes_included: int | None = None
        runner_tier: str | None = None

        if ghas:
            repos = ghas.get("repos") or []
            ghas_repo_count = len(repos)
            actively_scanned = sum(
                1
                for r in repos
                if any(
                    (a.get("results_count") or 0) > 0
                    for a in (r.get("advanced_security_committers_breakdown") or [])
                )
            )
            active_committers = ghas.get("total_advanced_security_committers") or 0

        if actions:
            runner_minutes_used = actions.get("total_minutes_used")
            runner_minutes_included = actions.get("included_minutes")
            # GitHub does not return the plan name in this endpoint; derive tier
            # from included_minutes: 0 = free (2k), 3k = team, 50k = enterprise, etc.
            if runner_minutes_included is not None:
                if runner_minutes_included >= 50000:
                    runner_tier = "enterprise"
                elif runner_minutes_included >= 3000:
                    runner_tier = "team"
                else:
                    runner_tier = "free"

        org_rows.append(
            {
                "org": org,
                "ghas_repo_count": "" if ghas_repo_count is None else str(ghas_repo_count),
                "actively_scanned_repos": "" if actively_scanned is None else str(actively_scanned),
                "active_committers": "" if active_committers is None else str(active_committers),
                "runner_tier": runner_tier or "",
                "runner_minutes_used": ""
                if runner_minutes_used is None
                else str(runner_minutes_used),
                "runner_minutes_included": ""
                if runner_minutes_included is None
                else str(runner_minutes_included),
            }
        )

    # Write CSVs --------------------------------------------------------------
    _write_csv(
        output_dir / "github_seats.csv",
        [
            "principal",
            "org",
            "seat_type",
            "sku_id",
            "last_activity_days",
            "copilot_acceptances_30d",
        ],
        seat_rows,
    )
    _write_csv(
        output_dir / "github_orgs.csv",
        [
            "org",
            "ghas_repo_count",
            "actively_scanned_repos",
            "active_committers",
            "runner_tier",
            "runner_minutes_used",
            "runner_minutes_included",
        ],
        org_rows,
    )
    logger.info(
        "GitHub collection complete: %d seats, %d orgs",
        len(seat_rows),
        len(org_rows),
    )
