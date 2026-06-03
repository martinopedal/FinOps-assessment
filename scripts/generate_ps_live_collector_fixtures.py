#!/usr/bin/env python3
"""Generate PowerShell live-collector parity fixtures (Phase 6b graph slice)."""

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

from finops_assess.collectors.graph_collector import collect_graph  # noqa: E402

FIXED_NOW = datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC)
FIXED_NOW_OVERRIDE = "2025-06-01"

_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "live_collectors" / "graph"
_INPUT_ROOT = _FIXTURE_ROOT / "_input"
_USERS_JSON = _INPUT_ROOT / "users.json"
_MAILBOX_CSV = _INPUT_ROOT / "mailbox_usage.csv"
_ACTIVE_CSV = _INPUT_ROOT / "active_users.csv"
_COPILOT_CSV = _INPUT_ROOT / "copilot_usage.csv"

_USERS_OUT = _FIXTURE_ROOT / "users.csv"
_ASSIGNMENTS_OUT = _FIXTURE_ROOT / "license_assignments.csv"
_USAGE_OUT = _FIXTURE_ROOT / "usage.csv"


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


def _read_inputs() -> dict[str, Any]:
    return {
        "users": json.loads(_USERS_JSON.read_text(encoding="utf-8")),
        "mailbox": _MAILBOX_CSV.read_bytes(),
        "active": _ACTIVE_CSV.read_bytes(),
        "copilot": _COPILOT_CSV.read_bytes(),
    }


def _mock_credential() -> MagicMock:
    cred = MagicMock()
    tok = MagicMock()
    tok.token = "fixture-token"
    tok.expires_on = 9_999_999_999
    cred.get_token.return_value = tok
    return cred


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


def regenerate() -> dict[Path, str]:
    inputs = _read_inputs()
    previous_now = os.environ.get("FINOPS_NOW_OVERRIDE")
    os.environ["FINOPS_NOW_OVERRIDE"] = FIXED_NOW_OVERRIDE

    monkeypatch = MonkeyPatch()
    scratch_dir = _REPO_ROOT / "scripts" / "_live_collector_fixture_tmp"
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

        scratch_dir.mkdir(parents=True, exist_ok=True)

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

        def _lf(path: Path) -> str:
            return path.read_text(encoding="utf-8").replace("\r\n", "\n")

        return {
            _USERS_OUT: _lf(scratch_dir / "users.csv"),
            _ASSIGNMENTS_OUT: _lf(scratch_dir / "license_assignments.csv"),
            _USAGE_OUT: _lf(scratch_dir / "usage.csv"),
        }
    finally:
        monkeypatch.undo()
        if previous_now is None:
            os.environ.pop("FINOPS_NOW_OVERRIDE", None)
        else:
            os.environ["FINOPS_NOW_OVERRIDE"] = previous_now
        for name in ("users.csv", "license_assignments.csv", "usage.csv"):
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
    print("ok: live collector graph fixtures are up-to-date")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        return _check()

    _FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    for path, content in regenerate().items():
        path.write_text(content, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
