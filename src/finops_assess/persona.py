"""Persona engine — assigns each principal to exactly one persona.

Signal priority (highest first), per ``docs/plan.md`` §5:

1. Explicit override in ``samples/overrides.yaml``.
2. Job-title regex map.
3. Group-membership regex map.
4. Usage / type fallback (guests → ``guest``; shared mailboxes & ``svc-*`` →
   ``service_account``; default human user → ``information_worker``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from finops_assess.models import (
    NormalizedDataset,
    Persona,
    PersonaAssignment,
    UserRecord,
)


def _compile(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]


def _match_title(user: UserRecord, personas: list[Persona]) -> str | None:
    if not user.job_title:
        return None
    for persona in personas:
        for pattern in _compile(persona.title_patterns):
            if pattern.search(user.job_title):
                return persona.id
    return None


def _match_group(user: UserRecord, personas: list[Persona]) -> str | None:
    if not user.groups:
        return None
    for persona in personas:
        compiled = _compile(persona.group_patterns)
        for group in user.groups:
            for pattern in compiled:
                if pattern.search(group):
                    return persona.id
    return None


def _fallback(user: UserRecord, personas_by_id: dict[str, Persona]) -> str:
    if user.user_type == "guest" and "guest" in personas_by_id:
        return "guest"
    if user.user_type in {"service", "shared_mailbox"} and "service_account" in personas_by_id:
        return "service_account"
    if not user.account_enabled and "service_account" in personas_by_id:
        return "service_account"
    if "information_worker" in personas_by_id:
        return "information_worker"
    # Last-resort: first persona declared (deterministic).
    return next(iter(personas_by_id))


def assign_personas(
    dataset: NormalizedDataset,
    personas: list[Persona],
) -> dict[str, PersonaAssignment]:
    """Resolve a :class:`PersonaAssignment` for every user in ``dataset``."""
    if not personas:
        raise ValueError("at least one persona must be defined")

    personas_by_id = {p.id: p for p in personas}
    assignments: dict[str, PersonaAssignment] = {}

    for user in dataset.users:
        override = dataset.overrides.get(user.principal)
        if override:
            if override not in personas_by_id:
                raise ValueError(
                    f"override for {user.principal} references unknown persona '{override}'"
                )
            assignments[user.principal] = PersonaAssignment(
                principal=user.principal,
                persona_id=override,
                matched_by="override",
                confidence="high",
            )
            continue

        title_match = _match_title(user, personas)
        if title_match:
            assignments[user.principal] = PersonaAssignment(
                principal=user.principal,
                persona_id=title_match,
                matched_by="title",
                confidence="high",
            )
            continue

        group_match = _match_group(user, personas)
        if group_match:
            assignments[user.principal] = PersonaAssignment(
                principal=user.principal,
                persona_id=group_match,
                matched_by="group",
                confidence="medium",
            )
            continue

        assignments[user.principal] = PersonaAssignment(
            principal=user.principal,
            persona_id=_fallback(user, personas_by_id),
            matched_by="fallback",
            confidence="low",
        )

    return assignments
