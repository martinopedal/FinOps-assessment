#!/usr/bin/env python3
"""Generate PowerShell live-collector parity fixtures (graph + arm slices)."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from pytest import MonkeyPatch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from finops_assess.collectors.arm_collector import collect_arm  # noqa: E402
from finops_assess.collectors.graph_collector import collect_graph  # noqa: E402

FIXED_NOW = datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC)
FIXED_NOW_OVERRIDE = "2025-06-01"

_GRAPH_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "graph"
_GRAPH_INPUT_ROOT = _GRAPH_FIXTURE_ROOT / "_input"
_GRAPH_USERS_JSON = _GRAPH_INPUT_ROOT / "users.json"
_GRAPH_MAILBOX_CSV = _GRAPH_INPUT_ROOT / "mailbox_usage.csv"
_GRAPH_ACTIVE_CSV = _GRAPH_INPUT_ROOT / "active_users.csv"
_GRAPH_COPILOT_CSV = _GRAPH_INPUT_ROOT / "copilot_usage.csv"

_ARM_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "arm"
_ARM_INPUT_ROOT = _ARM_FIXTURE_ROOT / "_input"


class _FrozenDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz: datetime.tzinfo | None = None) -> datetime.datetime:
        if tz is None:
            return FIXED_NOW.replace(tzinfo=None)
        return FIXED_NOW.astimezone(tz)


def _frozen_days_since_iso(dt_str: str | None) -> int | None:
    if not dt_str:
        return None
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (FIXED_NOW - dt).days)


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


def _mock_credential() -> MagicMock:
    cred = MagicMock()
    tok = MagicMock()
    tok.token = "fixture-token"
    tok.expires_on = 9_999_999_999
    cred.get_token.return_value = tok
    return cred


def _read_graph_inputs() -> dict[str, Any]:
    return {
        "users": json.loads(_GRAPH_USERS_JSON.read_text(encoding="utf-8")),
        "mailbox": _GRAPH_MAILBOX_CSV.read_bytes(),
        "active": _GRAPH_ACTIVE_CSV.read_bytes(),
        "copilot": _GRAPH_COPILOT_CSV.read_bytes(),
    }


def _read_arm_inputs() -> dict[str, Any]:
    names = (
        "subscriptions",
        "vms",
        "disks",
        "public_ips",
        "reservations",
        "benefit_recommendations",
        "workspaces",
        "workspace_usages",
        "metrics-cpu",
        "metrics-mem",
        "metrics-net",
        "retail-prices",
    )
    payload: dict[str, Any] = {}
    for name in names:
        payload[name] = json.loads((_ARM_INPUT_ROOT / f"{name}.json").read_text(encoding="utf-8"))
    return payload


def _assert_patches_active() -> None:
    from finops_assess.collectors import (
        ado_collector,
        arm_collector,
        github_collector,
        graph_collector,
    )

    if graph_collector.datetime is not _FrozenDateTime:
        raise RuntimeError("graph collector datetime patch is not active")
    if not callable(arm_collector._now_utc) or arm_collector._now_utc() != FIXED_NOW:
        raise RuntimeError("arm collector _now_utc patch is not active")
    if ado_collector.datetime is not _FrozenDateTime:
        raise RuntimeError("ado collector datetime patch is not active")
    if github_collector._days_since_iso is not _frozen_days_since_iso:
        raise RuntimeError("github collector _days_since_iso patch is not active")


def _lf(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _regenerate_graph(scratch_dir: Path) -> dict[Path, str]:
    inputs = _read_graph_inputs()

    def _side_effect(url: str, **kwargs: Any) -> MagicMock:
        _ = kwargs
        lower = url.lower()
        if "users?" in lower:
            return _make_json_resp(inputs["users"])
        if "mailboxusagedetail" in lower:
            return _make_bytes_resp(inputs["mailbox"])
        if "activeuserdetail" in lower:
            return _make_bytes_resp(inputs["active"])
        if "copilot" in lower:
            return _make_bytes_resp(inputs["copilot"])
        return _make_json_resp({"value": []})

    with patch("requests.Session") as mock_session_cls:
        session = MagicMock()
        session.get.side_effect = _side_effect
        mock_session_cls.return_value = session
        collect_graph(scratch_dir, _credential=_mock_credential())

    return {
        _GRAPH_FIXTURE_ROOT / "users.csv": _lf(scratch_dir / "users.csv"),
        _GRAPH_FIXTURE_ROOT / "license_assignments.csv": _lf(
            scratch_dir / "license_assignments.csv"
        ),
        _GRAPH_FIXTURE_ROOT / "usage.csv": _lf(scratch_dir / "usage.csv"),
    }


def _regenerate_arm(scratch_dir: Path) -> dict[Path, str]:
    inputs = _read_arm_inputs()

    def _side_effect(url: str, **kwargs: Any) -> MagicMock:
        lower = url.lower()
        params = kwargs.get("params") or {}
        if "/subscriptions?" in lower and "providers" not in lower:
            return _make_json_resp(inputs["subscriptions"])
        if "virtualmachines" in lower and "metrics" not in lower:
            return _make_json_resp(inputs["vms"])
        if "/disks" in lower:
            return _make_json_resp(inputs["disks"])
        if "publicipaddresses" in lower:
            return _make_json_resp(inputs["public_ips"])
        if "microsoft.capacity/reservations" in lower:
            return _make_json_resp(inputs["reservations"])
        if "benefitrecommendations" in lower:
            return _make_json_resp(inputs["benefit_recommendations"])
        if "workspaces" in lower and "usages" not in lower:
            return _make_json_resp(inputs["workspaces"])
        if "usages" in lower:
            return _make_json_resp(inputs["workspace_usages"])
        if "providers/microsoft.insights/metrics" in lower:
            metric_names = str(params.get("metricnames", "")).lower()
            values: list[dict[str, Any]] = []
            if "percentage cpu" in metric_names:
                values.extend(inputs["metrics-cpu"].get("value", []))
            if "available memory bytes" in metric_names:
                values.extend(inputs["metrics-mem"].get("value", []))
            if "network" in metric_names:
                values.extend(inputs["metrics-net"].get("value", []))
            if not values:
                values = inputs["metrics-cpu"].get("value", [])
            return _make_json_resp({"value": values})
        if "prices.azure.com/api/retail/prices" in lower:
            return _make_json_resp(inputs["retail-prices"])
        return _make_json_resp({"value": []})

    with patch("requests.Session") as mock_session_cls:
        session = MagicMock()
        session.get.side_effect = _side_effect
        mock_session_cls.return_value = session
        collect_arm(
            scratch_dir,
            subscription_ids=None,
            collect_metrics=True,
            _credential=_mock_credential(),
        )

    return {
        _ARM_FIXTURE_ROOT / "azure_resources.csv": _lf(scratch_dir / "azure_resources.csv"),
        _ARM_FIXTURE_ROOT / "azure_reservations.csv": _lf(scratch_dir / "azure_reservations.csv"),
        _ARM_FIXTURE_ROOT / "azure_log_workspaces.csv": _lf(
            scratch_dir / "azure_log_workspaces.csv"
        ),
        _ARM_FIXTURE_ROOT / "azure_benefit_recommendations.csv": _lf(
            scratch_dir / "azure_benefit_recommendations.csv"
        ),
    }


def regenerate() -> dict[Path, str]:
    previous_now = os.environ.get("FINOPS_NOW_OVERRIDE")
    os.environ["FINOPS_NOW_OVERRIDE"] = FIXED_NOW_OVERRIDE

    monkeypatch = MonkeyPatch()
    graph_scratch = _REPO_ROOT / "scripts" / "_live_collector_fixture_tmp_graph"
    arm_scratch = _REPO_ROOT / "scripts" / "_live_collector_fixture_tmp_arm"
    try:
        monkeypatch.setattr(
            "finops_assess.collectors.graph_collector.datetime", _FrozenDateTime, raising=True
        )
        monkeypatch.setattr(
            "finops_assess.collectors.arm_collector._now_utc", lambda: FIXED_NOW, raising=True
        )
        monkeypatch.setattr(
            "finops_assess.collectors.ado_collector.datetime", _FrozenDateTime, raising=True
        )
        monkeypatch.setattr(
            "finops_assess.collectors.github_collector._days_since_iso",
            _frozen_days_since_iso,
            raising=True,
        )
        _assert_patches_active()

        graph_scratch.mkdir(parents=True, exist_ok=True)
        arm_scratch.mkdir(parents=True, exist_ok=True)

        expected: dict[Path, str] = {}
        expected.update(_regenerate_graph(graph_scratch))
        expected.update(_regenerate_arm(arm_scratch))
        return expected
    finally:
        monkeypatch.undo()
        if previous_now is None:
            os.environ.pop("FINOPS_NOW_OVERRIDE", None)
        else:
            os.environ["FINOPS_NOW_OVERRIDE"] = previous_now

        for scratch_dir, names in (
            (graph_scratch, ("users.csv", "license_assignments.csv", "usage.csv")),
            (
                arm_scratch,
                (
                    "azure_resources.csv",
                    "azure_reservations.csv",
                    "azure_log_workspaces.csv",
                    "azure_benefit_recommendations.csv",
                ),
            ),
        ):
            for name in names:
                p = scratch_dir / name
                if p.exists():
                    p.unlink()
            if scratch_dir.exists() and not any(scratch_dir.iterdir()):
                scratch_dir.rmdir()


def _check() -> int:
    expected = regenerate()
    stale: list[Path] = []
    for path, content in expected.items():
        if not path.exists() or path.read_bytes() != content.encode("utf-8"):
            stale.append(path)
    if stale:
        for path in stale:
            rel = path.relative_to(_REPO_ROOT)
            print(f"stale: {rel}; run python scripts/generate_ps_live_collector_fixtures.py")
        return 1
    print("ok: live collector graph+arm fixtures are up-to-date")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        return _check()

    _GRAPH_FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    _ARM_FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    for path, content in regenerate().items():
        path.write_text(content, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
