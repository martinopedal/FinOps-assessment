"""Unit tests for the live collectors (M4-M6).

All HTTP calls are intercepted with :mod:`unittest.mock` so no real
credentials or network connectivity are required.  Each test verifies that
the collector:

1. Makes the expected HTTP requests.
2. Writes well-formed CSV files that the CSV collector can read back.
3. Produces the correct ``NormalizedDataset`` rows when re-ingested.
"""

from __future__ import annotations

import pytest

# Skip all tests if requests is not installed (requires [live] extras)
pytest.importorskip(
    "requests", reason="Live collectors require [live] extras: pip install -e .[live]"
)

import csv
import io
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from finops_assess.collectors.csv_collector import collect_from_directory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode()


def _mock_credential() -> MagicMock:
    cred = MagicMock()
    tok = MagicMock()
    tok.token = "fake-token"
    tok.expires_on = 9_999_999_999
    cred.get_token.return_value = tok
    return cred


def _make_json_resp(payload: Any, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _make_bytes_resp(payload: bytes, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.side_effect = ValueError("not json")
    resp.content = payload
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Graph collector (M4)
# ---------------------------------------------------------------------------


class TestGraphCollector:
    """Tests for :mod:`finops_assess.collectors.graph_collector`."""

    def test_collect_graph_writes_csvs(self, tmp_path: Path) -> None:
        from finops_assess.collectors.graph_collector import collect_graph

        cred = _mock_credential()

        users_resp = {
            "value": [
                {
                    "userPrincipalName": "alice@contoso.test",
                    "displayName": "Alice",
                    "userType": "Member",
                    "accountEnabled": True,
                    "jobTitle": "Engineer",
                    "department": "Engineering",
                    "assignedLicenses": [{"skuId": "6fd2c87f-b296-42f0-b197-1e91e994b900"}],
                    "signInActivity": {"lastSignInDateTime": "2023-01-01T00:00:00Z"},
                }
            ]
        }

        mailbox_csv = _csv_bytes(
            ["User Principal Name", "Storage Used (Byte)"],
            [["alice@contoso.test", "1073741824"]],
        )

        active_csv = _csv_bytes(
            ["User Principal Name", "Exchange", "SharePoint", "Teams"],
            [["alice@contoso.test", "Yes", "Yes", "No"]],
        )

        copilot_csv = _csv_bytes(
            ["User Principal Name", "Copilot Active"],
            [["alice@contoso.test", "1"]],
        )

        def _side_effect(url: str, **kwargs: Any) -> MagicMock:
            if "users" in url.lower():
                return _make_json_resp(users_resp)
            if "mailboxusagedetail" in url.lower() or "MailboxUsageDetail" in url:
                return _make_bytes_resp(mailbox_csv)
            if "activeuserdetail" in url.lower() or "ActiveUserDetail" in url:
                return _make_bytes_resp(active_csv)
            if "copilot" in url.lower():
                return _make_bytes_resp(copilot_csv)
            return _make_json_resp({"value": []})

        with patch("requests.Session") as mock_session_cls:
            session = MagicMock()
            session.get.side_effect = _side_effect
            mock_session_cls.return_value = session
            collect_graph(tmp_path, _credential=cred)

        assert (tmp_path / "users.csv").exists()
        assert (tmp_path / "license_assignments.csv").exists()
        assert (tmp_path / "usage.csv").exists()

        dataset = collect_from_directory(tmp_path)
        assert len(dataset.users) == 1
        assert dataset.users[0].principal == "alice@contoso.test"
        assert dataset.users[0].mailbox_size_gb == pytest.approx(1.0, abs=0.01)
        assert len(dataset.assignments) == 1
        assert len(dataset.usage) > 0


# ---------------------------------------------------------------------------
# ARM collector (M5)
# ---------------------------------------------------------------------------


class TestArmCollector:
    """Tests for :mod:`finops_assess.collectors.arm_collector`."""

    def test_collect_arm_writes_csvs(self, tmp_path: Path) -> None:
        from finops_assess.collectors.arm_collector import collect_arm

        cred = _mock_credential()

        vm_id = (
            "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
        )
        disk_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk1"
        pip_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip1"
        ws_id = (
            "/subscriptions/sub-1/resourceGroups/rg/providers/"
            "Microsoft.OperationalInsights/workspaces/ws1"
        )

        def _side_effect(url: str, **kwargs: Any) -> MagicMock:
            url_lower = url.lower()
            if "virtualmachines" in url_lower and "metrics" not in url_lower:
                return _make_json_resp(
                    {
                        "value": [
                            {
                                "id": vm_id,
                                "location": "eastus",
                                "properties": {"hardwareProfile": {"vmSize": "Standard_D4s_v5"}},
                                "tags": {"env": "prod"},
                            }
                        ]
                    }
                )
            if "/disks" in url_lower:
                return _make_json_resp(
                    {
                        "value": [
                            {
                                "id": disk_id,
                                "location": "eastus",
                                "sku": {"name": "Premium_LRS"},
                                "properties": {
                                    "diskState": "Unattached",
                                    "timeCreated": "2024-01-01T00:00:00Z",
                                },
                            }
                        ]
                    }
                )
            if "publicipaddresses" in url_lower:
                return _make_json_resp(
                    {
                        "value": [
                            {
                                "id": pip_id,
                                "location": "eastus",
                                "sku": {"name": "Standard"},
                                "properties": {},
                            }
                        ]
                    }
                )
            if "workspaces" in url_lower and "usages" not in url_lower:
                return _make_json_resp(
                    {
                        "value": [
                            {
                                "id": ws_id,
                                "name": "ws1",
                                "properties": {"sku": {"name": "PerGB2018"}},
                            }
                        ]
                    }
                )
            if "usages" in url_lower:
                return _make_json_resp(
                    {
                        "value": [
                            {
                                "name": {"value": "DataIngestion"},
                                "currentValue": 122880,
                            }
                        ]
                    }
                )
            return _make_json_resp({"value": []})

        with patch("requests.Session") as mock_session_cls:
            session = MagicMock()
            session.get.side_effect = _side_effect
            mock_session_cls.return_value = session
            collect_arm(
                tmp_path,
                subscription_ids=["sub-1"],
                collect_metrics=False,
                _credential=cred,
            )

        assert (tmp_path / "azure_resources.csv").exists()
        assert (tmp_path / "azure_reservations.csv").exists()
        assert (tmp_path / "azure_log_workspaces.csv").exists()

        dataset = collect_from_directory(tmp_path)
        resource_ids = {r.resource_id for r in dataset.azure_resources}
        assert vm_id in resource_ids
        assert disk_id in resource_ids
        assert pip_id in resource_ids
        vm_row = next(r for r in dataset.azure_resources if r.resource_id == vm_id)
        assert vm_row.env_tag == "prod"


# ---------------------------------------------------------------------------
# GitHub collector (M6a)
# ---------------------------------------------------------------------------


class TestGitHubCollector:
    """Tests for :mod:`finops_assess.collectors.github_collector`."""

    def test_collect_github_writes_csvs(self, tmp_path: Path) -> None:
        from finops_assess.collectors.github_collector import collect_github

        def _side_effect(url: str, **kwargs: Any) -> MagicMock:
            if "consumed-licenses" in url:
                return _make_json_resp(
                    [
                        {
                            "github_com_user": {
                                "login": "alice",
                                "updated_at": "2023-01-01T00:00:00Z",
                            }
                        }
                    ]
                )
            if "copilot/billing/seats" in url:
                return _make_json_resp(
                    {
                        "seats": [
                            {
                                "assignee": {"login": "alice"},
                                "last_activity_at": "2023-01-01T00:00:00Z",
                                "plan_type": "business",
                            }
                        ]
                    }
                )
            if "advanced-security" in url:
                return _make_json_resp(
                    {
                        "total_advanced_security_committers": 5,
                        "repos": [
                            {"advanced_security_committers_breakdown": [{"results_count": 3}]},
                        ],
                    }
                )
            if "billing/actions" in url:
                return _make_json_resp({"total_minutes_used": 12000, "included_minutes": 50000})
            return _make_json_resp([])

        with patch("requests.Session") as mock_session_cls:
            session = MagicMock()
            session.get.side_effect = _side_effect
            mock_session_cls.return_value = session
            collect_github(
                tmp_path,
                enterprise="contoso",
                orgs=["contoso"],
                token="fake-token",
            )

        assert (tmp_path / "github_seats.csv").exists()
        assert (tmp_path / "github_orgs.csv").exists()

        dataset = collect_from_directory(tmp_path)
        assert len(dataset.github_seats) >= 1
        assert len(dataset.github_orgs) == 1
        org = dataset.github_orgs[0]
        assert org.runner_minutes_used == 12000
        assert org.runner_tier == "enterprise"

    def test_collect_github_raises_without_token(self, tmp_path: Path) -> None:
        from finops_assess.collectors.github_collector import collect_github

        # Temporarily remove GITHUB_TOKEN from the environment.
        old_token = os.environ.pop("GITHUB_TOKEN", None)
        try:
            with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
                collect_github(tmp_path, enterprise="contoso")
        finally:
            if old_token is not None:
                os.environ["GITHUB_TOKEN"] = old_token


# ---------------------------------------------------------------------------
# ADO collector (M6b)
# ---------------------------------------------------------------------------


class TestAdoCollector:
    """Tests for :mod:`finops_assess.collectors.ado_collector`."""

    def test_collect_ado_writes_csvs(self, tmp_path: Path) -> None:
        from finops_assess.collectors.ado_collector import collect_ado

        def _side_effect(url: str, **kwargs: Any) -> MagicMock:
            if "userentitlements" in url:
                return _make_json_resp(
                    {
                        "members": [
                            {
                                "user": {
                                    "mailAddress": "alice@contoso.test",
                                    "displayName": "Alice",
                                },
                                "accessLevel": {
                                    "accessLevelName": "Advanced",
                                    "lastAccessedDate": "2023-01-01T00:00:00Z",
                                },
                                "extensions": [],
                                "projectEntitlements": [],
                            },
                            {
                                "user": {
                                    "mailAddress": "bob@contoso.test",
                                    "displayName": "Bob",
                                },
                                "accessLevel": {
                                    "accessLevelName": "Stakeholder",
                                    "lastAccessedDate": "2024-01-01T00:00:00Z",
                                },
                                "extensions": [],
                                "projectEntitlements": [],
                            },
                        ],
                        "continuationToken": "",
                    }
                )
            if "resourcelimits" in url:
                return _make_json_resp([{"parallelSmallJobsCount": 10}])
            if "_apis/projects" in url:
                return _make_json_resp({"value": []})
            return _make_json_resp({"value": []})

        with patch("requests.Session") as mock_session_cls:
            session = MagicMock()
            session.get.side_effect = _side_effect
            mock_session_cls.return_value = session
            collect_ado(tmp_path, org="contoso", pat="fake-pat")

        assert (tmp_path / "ado_seats.csv").exists()
        assert (tmp_path / "ado_orgs.csv").exists()

        dataset = collect_from_directory(tmp_path)
        assert len(dataset.ado_seats) == 2
        alice = next(s for s in dataset.ado_seats if "alice" in s.principal)
        assert alice.seat_type == "basic"
        bob = next(s for s in dataset.ado_seats if "bob" in s.principal)
        assert bob.seat_type == "stakeholder"

        assert len(dataset.ado_orgs) == 1
        assert dataset.ado_orgs[0].purchased_parallel_jobs == 10

    def test_collect_ado_raises_without_credential(self, tmp_path: Path) -> None:
        from finops_assess.collectors.ado_collector import collect_ado

        old_pat = os.environ.pop("AZURE_DEVOPS_PAT", None)
        old_token = os.environ.pop("AZURE_DEVOPS_TOKEN", None)
        try:
            with pytest.raises(RuntimeError, match="AZURE_DEVOPS_PAT"):
                collect_ado(tmp_path, org="contoso")
        finally:
            if old_pat is not None:
                os.environ["AZURE_DEVOPS_PAT"] = old_pat
            if old_token is not None:
                os.environ["AZURE_DEVOPS_TOKEN"] = old_token
