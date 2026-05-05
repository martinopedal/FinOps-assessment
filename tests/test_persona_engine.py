"""Tests for the persona engine."""

from __future__ import annotations

import pytest

from finops_assess.models import NormalizedDataset, Persona, UserRecord
from finops_assess.persona import assign_personas

PERSONAS = [
    Persona(id="service_account", display_name="svc", title_patterns=["(?i)^svc[-_]"]),
    Persona(
        id="frontline_worker",
        display_name="frontline",
        required_features=["mailbox.2gb"],
        title_patterns=["(?i)warehouse|driver"],
    ),
    Persona(
        id="information_worker",
        display_name="iw",
        required_features=["mailbox.50gb", "office.desktop"],
        title_patterns=["(?i)analyst|manager"],
    ),
    Persona(id="guest", display_name="guest"),
]


def _ds(*users: UserRecord, **kwargs: object) -> NormalizedDataset:
    return NormalizedDataset(users=list(users), **kwargs)  # type: ignore[arg-type]


def test_override_wins_over_title() -> None:
    user = UserRecord(principal="a@x", job_title="Senior Manager")
    dataset = _ds(user, overrides={"a@x": "frontline_worker"})
    assn = assign_personas(dataset, PERSONAS)
    assert assn["a@x"].persona_id == "frontline_worker"
    assert assn["a@x"].matched_by == "override"


def test_title_regex_match() -> None:
    user = UserRecord(principal="b@x", job_title="Warehouse Operator")
    assn = assign_personas(_ds(user), PERSONAS)
    assert assn["b@x"].persona_id == "frontline_worker"
    assert assn["b@x"].matched_by == "title"


def test_guest_falls_back_to_guest_persona() -> None:
    user = UserRecord(principal="g@x", user_type="guest")
    assn = assign_personas(_ds(user), PERSONAS)
    assert assn["g@x"].persona_id == "guest"
    assert assn["g@x"].matched_by == "fallback"


def test_disabled_user_falls_back_to_service_account() -> None:
    user = UserRecord(principal="d@x", account_enabled=False)
    assn = assign_personas(_ds(user), PERSONAS)
    assert assn["d@x"].persona_id == "service_account"


def test_default_human_user_is_information_worker() -> None:
    user = UserRecord(principal="u@x", job_title="Designer")
    assn = assign_personas(_ds(user), PERSONAS)
    assert assn["u@x"].persona_id == "information_worker"
    assert assn["u@x"].matched_by == "fallback"


def test_unknown_override_is_rejected() -> None:
    user = UserRecord(principal="z@x")
    with pytest.raises(ValueError, match="unknown persona"):
        assign_personas(_ds(user, overrides={"z@x": "no-such"}), PERSONAS)
