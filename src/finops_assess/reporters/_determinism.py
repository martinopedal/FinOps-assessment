"""Shared determinism helpers for all reporters.

Centralises the ``SOURCE_DATE_EPOCH`` timestamp logic so every output
format (JSON, HTML, CSV, FOCUS-aligned advisory CSV, future PDF/SARIF)
calls the same code path instead of re-implementing it.

Usage::

    from finops_assess.reporters._determinism import generated_at_iso
    ts = generated_at_iso()

The function honours the ``SOURCE_DATE_EPOCH`` environment variable
(the `reproducible-builds.org <https://reproducible-builds.org/>`_
convention): when set, the timestamp is derived from that epoch instead
of the wall-clock, making output byte-deterministic across runs of the
same input. This is what ``scripts/generate_docs.py`` relies on to
produce committed ``examples/`` artefacts.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime


def now_utc() -> datetime:
    """Return "now" as a timezone-aware UTC ``datetime``, honouring ``SOURCE_DATE_EPOCH``.

    Defaults to ``datetime.now(UTC)`` so day-to-day runs continue to use the
    wall-clock time.  When ``SOURCE_DATE_EPOCH`` is set, the value is derived
    from that epoch, making any timestamp-derived output (report ``generated_at``,
    FOCUS ``BillingPeriod`` fallback, …) byte-deterministic across runs.

    Every reporter that needs a "current time" fallback must call this helper
    rather than ``datetime.now`` directly; otherwise the committed
    ``examples/`` artefacts silently rebase to the wall-clock month and the
    docs-freshness gate time-bombs on the next calendar rollover.

    Malformed or out-of-range epoch values (e.g. very large integers that
    overflow the OS ``gmtime`` syscall) are silently ignored and fall
    through to wall-clock time.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=UTC)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return datetime.now(UTC)


def generated_at_iso() -> str:
    """Return the report timestamp as an ISO-8601 string, honouring ``SOURCE_DATE_EPOCH``.

    Thin wrapper around :func:`now_utc`; see that function for the
    determinism contract.
    """
    return now_utc().isoformat(timespec="seconds")
