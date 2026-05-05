"""Microsoft Graph live collector — M4.

Pulls users, license assignments, service-plan usage signals, and sign-in
inactivity from Microsoft Graph v1.0 and writes normalised CSV files that
the ``finops-assess run`` command can consume directly.

Authentication
--------------
Uses :class:`azure.identity.DefaultAzureCredential`, which tries the
following credential chain in order (no long-lived secrets in the repo):

1. ``AZURE_FEDERATED_TOKEN_FILE`` + ``AZURE_CLIENT_ID`` + ``AZURE_TENANT_ID``
   (OIDC / workload-identity in GitHub Actions).
2. ``AZURE_CLIENT_ID`` + ``AZURE_TENANT_ID`` + ``AZURE_CLIENT_SECRET``
   (service principal with client secret — for local / non-OIDC environments).
3. Azure CLI credentials (``az login`` — for developer workstations).

Required **read-only** Graph API delegated / application permissions:

* ``User.Read.All``
* ``AuditLog.Read.All``   (for ``signInActivity`` property on users)
* ``Reports.Read.All``    (for ``getMailboxUsageDetail``,
  ``getOffice365ActiveUserDetail``, ``getMicrosoft365CopilotUsageDetail``)
* ``Organization.Read.All``

These are app-only (application) permissions so the collector can run
headlessly. No write scopes are requested or accepted.
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]

# Maximum number of pages fetched per resource to guard against runaway
# pagination in very large tenants.  Raise via ``page_limit`` parameter if
# your tenant exceeds this; 0 = unlimited.
_DEFAULT_PAGE_LIMIT = 200


def _require_deps() -> tuple[Any, Any]:
    """Import optional live-mode deps and raise a friendly error if absent."""
    try:
        import requests
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential, requests
    except ImportError as exc:
        raise RuntimeError(
            "The [live] extra is required for the Graph collector.  "
            "Install it with: pip install 'finops-assess[live]'"
        ) from exc


class _GraphClient:
    """Minimal Microsoft Graph REST client with bearer-token auth."""

    def __init__(self, credential: Any, *, page_limit: int = _DEFAULT_PAGE_LIMIT) -> None:
        _, requests = _require_deps()
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._credential = credential
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._page_limit = page_limit

    def _get_token(self) -> str:
        """Return a fresh bearer token, refreshing if within 60 s of expiry."""
        now = time.monotonic()
        if self._token is None or now >= self._token_expiry - 60:
            tok = self._credential.get_token(*_GRAPH_SCOPES)
            self._token = tok.token
            self._token_expiry = now + tok.expires_on - time.time()
        assert self._token is not None
        return self._token

    def get(self, url: str, **kwargs: Any) -> Any:
        """HTTP GET returning parsed JSON.  Raises on 4xx/5xx."""
        _require_deps()
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        headers.update(kwargs.pop("extra_headers", {}))
        resp = self._session.get(url, headers=headers, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_bytes(self, url: str) -> bytes:
        """HTTP GET returning raw bytes (used for CSV report downloads)."""
        _require_deps()
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        resp = self._session.get(url, headers=headers, timeout=120)
        resp.raise_for_status()
        return bytes(resp.content)

    def list_all(self, url: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Paginate a Graph collection, following ``@odata.nextLink`` pointers."""
        results: list[dict[str, Any]] = []
        page = 0
        while url:
            page += 1
            if self._page_limit and page > self._page_limit:
                logger.warning(
                    "Reached page_limit=%d fetching %s; truncating.", self._page_limit, url
                )
                break
            body = self.get(url, **kwargs)
            results.extend(body.get("value", []))
            url = body.get("@odata.nextLink", "")
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days_since(dt_str: str | None) -> int | None:
    """Convert an ISO-8601 datetime string to days-ago, or None if blank/null."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = datetime.now(tz=UTC) - dt
        return max(0, delta.days)
    except ValueError:
        logger.debug("Cannot parse datetime '%s'", dt_str)
        return None


def _parse_csv_report(raw: bytes) -> list[dict[str, str]]:
    """Parse a UTF-8(-BOM) CSV byte-blob from a Graph reports API."""
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


# ---------------------------------------------------------------------------
# Data collection steps
# ---------------------------------------------------------------------------


def _collect_users(client: _GraphClient) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (raw_users, upn_map) from /v1.0/users.

    Fetches id, userPrincipalName, displayName, userType, accountEnabled,
    jobTitle, department, assignedLicenses, signInActivity.
    ``upn_map`` is keyed by lower-cased UPN for fast mailbox-report merging.
    """
    select = (
        "id,userPrincipalName,displayName,userType,accountEnabled,"
        "jobTitle,department,assignedLicenses,signInActivity"
    )
    url = f"{_GRAPH_BASE}/users?$select={select}&$top=999&$count=true"
    users = client.list_all(
        url,
        extra_headers={"ConsistencyLevel": "eventual"},
    )
    upn_map = {
        u.get("userPrincipalName", "").lower(): u for u in users if u.get("userPrincipalName")
    }
    return users, upn_map


def _collect_mailbox_usage(client: _GraphClient) -> dict[str, float]:
    """Return {upn_lower: mailbox_size_gb} from the mailbox-usage report."""
    url = f"{_GRAPH_BASE}/reports/getMailboxUsageDetail(period='D30')"
    try:
        raw = client.get_bytes(url)
    except Exception as exc:
        logger.warning("getMailboxUsageDetail failed (%s); skipping mailbox sizes.", exc)
        return {}
    sizes: dict[str, float] = {}
    for row in _parse_csv_report(raw):
        upn = (row.get("User Principal Name") or "").lower().strip()
        quota_str = row.get("Storage Used (Byte)") or row.get("Used (Byte)") or ""
        if upn and quota_str.strip():
            with contextlib.suppress(ValueError):
                sizes[upn] = round(int(quota_str.strip()) / 1_073_741_824, 3)  # bytes to GB
    return sizes


def _collect_active_users(client: _GraphClient) -> dict[str, set[str]]:
    """Return {upn_lower: {active_service_keys}} from the Office 365 active-user report.

    Column names from getOffice365ActiveUserDetail vary slightly between
    tenants; we match by lowercase contains-check so the mapping is robust.
    """
    url = f"{_GRAPH_BASE}/reports/getOffice365ActiveUserDetail(period='D30')"
    try:
        raw = client.get_bytes(url)
    except Exception as exc:
        logger.warning("getOffice365ActiveUserDetail failed (%s); skipping activity signals.", exc)
        return {}

    # Normalise header names so we can do fuzzy column matching.
    rows = _parse_csv_report(raw)
    if not rows:
        return {}
    active: dict[str, set[str]] = {}
    for row in rows:
        low_row = {k.lower(): v for k, v in row.items()}
        upn = (low_row.get("user principal name") or "").lower().strip()
        if not upn:
            continue
        signals: set[str] = set()
        for col, val in low_row.items():
            v = (val or "").strip().lower()
            if v not in ("yes", "true", "1"):
                continue
            if "exchange" in col:
                signals.add("exchange")
            elif "sharepoint" in col:
                signals.add("sharepoint")
            elif "teams" in col:
                signals.add("teams")
            elif "yammer" in col:
                signals.add("yammer")
            elif "skype" in col:
                signals.add("skype")
        active[upn] = signals
    return active


def _collect_copilot_usage(client: _GraphClient) -> dict[str, bool]:
    """Return {upn_lower: has_any_copilot_activity_30d}.

    Uses the getMicrosoft365CopilotUsageSummary report endpoint.
    Returns {} if the tenant does not have Copilot licences.
    """
    url = f"{_GRAPH_BASE}/reports/getMicrosoft365CopilotUsageSummary(period='D30')"
    try:
        raw = client.get_bytes(url)
        rows = _parse_csv_report(raw)
    except Exception:
        # Endpoint not available for this tenant / licence tier — that's fine.
        return {}
    active: dict[str, bool] = {}
    for row in rows:
        low = {k.lower(): v for k, v in row.items()}
        upn = (low.get("user principal name") or "").lower().strip()
        if not upn:
            continue
        # Any non-zero activity column counts as "active".
        active_flag = any(
            (v or "0").strip() not in ("0", "", "false", "no")
            for k, v in low.items()
            if any(x in k for x in ("active", "used", "activity")) and "user" not in k
        )
        active[upn] = active_flag
    return active


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


def collect_graph(
    output_dir: Path,
    *,
    tenant_id: str | None = None,
    page_limit: int = _DEFAULT_PAGE_LIMIT,
    _credential: Any = None,
) -> None:
    """Pull Microsoft Graph data and write normalised CSV files to *output_dir*.

    Credentials are resolved automatically via
    :class:`azure.identity.DefaultAzureCredential` using the ambient
    environment (OIDC workload identity in GitHub Actions, CLI credentials
    for developer workstations, etc.).  Pass *tenant_id* to override the
    ``AZURE_TENANT_ID`` environment variable.

    The private *_credential* parameter is for testing only — pass a mock
    credential to avoid real API calls in unit tests.

    Writes:
    * ``users.csv``
    * ``license_assignments.csv``
    * ``usage.csv``
    """
    if _credential is None:
        DefaultAzureCredential, _ = _require_deps()
        kwargs: dict[str, Any] = {}
        if tenant_id:
            kwargs["additionally_allowed_tenants"] = [tenant_id]
        _credential = DefaultAzureCredential(**kwargs)
    client = _GraphClient(_credential, page_limit=page_limit)

    output_dir = Path(output_dir)

    logger.info("Collecting users from Microsoft Graph …")
    raw_users, _ = _collect_users(client)

    logger.info("Collecting mailbox usage …")
    mailbox_sizes = _collect_mailbox_usage(client)

    logger.info("Collecting Office 365 active-user detail …")
    active_services = _collect_active_users(client)

    logger.info("Collecting Copilot usage …")
    copilot_active = _collect_copilot_usage(client)

    # Build output rows -------------------------------------------------------
    user_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []

    for u in raw_users:
        upn: str = u.get("userPrincipalName") or ""
        upn_lower = upn.lower()
        display_name: str = u.get("displayName") or ""
        user_type_raw: str = (u.get("userType") or "member").lower()

        # Map Graph userType to our Literal
        if user_type_raw == "guest":
            user_type = "guest"
        elif user_type_raw == "member":
            user_type = "member"
        else:
            user_type = "service"

        # Graph doesn't distinguish shared mailboxes in userType — infer from
        # the mailbox-usage report's "Recipient Type" column when available.
        # For now we use the approximation that shared mailboxes often have
        # no sign-in activity at all and very small mailbox sizes.
        # The live Graph collector can be enhanced later with EWS/EXO checks.

        account_enabled: bool = bool(u.get("accountEnabled", True))
        sign_in_activity = u.get("signInActivity") or {}
        last_sign_in_dt: str | None = sign_in_activity.get("lastSignInDateTime")
        last_sign_in_days = _days_since(last_sign_in_dt)

        mailbox_gb = mailbox_sizes.get(upn_lower)

        user_rows.append(
            {
                "principal": upn,
                "display_name": display_name,
                "user_type": user_type,
                "account_enabled": str(account_enabled).lower(),
                "job_title": u.get("jobTitle") or "",
                "department": u.get("department") or "",
                "mailbox_size_gb": "" if mailbox_gb is None else str(mailbox_gb),
                "last_sign_in_days": "" if last_sign_in_days is None else str(last_sign_in_days),
            }
        )

        # License assignments
        for lic in u.get("assignedLicenses") or []:
            sku_id: str = (lic.get("skuId") or "").upper()
            if sku_id:
                assignment_rows.append({"principal": upn, "sku_id": sku_id})

        # Usage signals from activity report
        services = active_services.get(upn_lower, set())
        service_signal_map = {
            "exchange": "exchange",
            "sharepoint": "sharepoint",
            "teams": "teams",
        }
        for svc_key, signal in service_signal_map.items():
            if svc_key in services:
                usage_rows.append(
                    {
                        "principal": upn,
                        "signal": signal,
                        "last_activity_days": "0",  # active within the report window
                    }
                )
            elif last_sign_in_days is not None:
                # No signal in the 30-day window — use last sign-in as a proxy
                usage_rows.append(
                    {
                        "principal": upn,
                        "signal": signal,
                        "last_activity_days": str(last_sign_in_days),
                    }
                )

        # Copilot signal
        copilot_active_flag = copilot_active.get(upn_lower)
        if copilot_active_flag is not None:
            usage_rows.append(
                {
                    "principal": upn,
                    "signal": "copilot",
                    "last_activity_days": "0" if copilot_active_flag else "61",
                }
            )

    # Write CSVs --------------------------------------------------------------
    _write_csv(
        output_dir / "users.csv",
        [
            "principal",
            "display_name",
            "user_type",
            "account_enabled",
            "job_title",
            "department",
            "mailbox_size_gb",
            "last_sign_in_days",
        ],
        user_rows,
    )
    _write_csv(
        output_dir / "license_assignments.csv",
        ["principal", "sku_id"],
        assignment_rows,
    )
    _write_csv(
        output_dir / "usage.csv",
        ["principal", "signal", "last_activity_days"],
        usage_rows,
    )
    logger.info(
        "Graph collection complete: %d users, %d assignments, %d signals",
        len(user_rows),
        len(assignment_rows),
        len(usage_rows),
    )
