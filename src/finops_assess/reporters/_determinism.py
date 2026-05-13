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


def generated_at_iso() -> str:
    """Return the report timestamp as an ISO-8601 string, honouring ``SOURCE_DATE_EPOCH``.

    Defaults to ``datetime.now(UTC)`` so day-to-day runs continue to embed
    the wall-clock time.  When ``SOURCE_DATE_EPOCH`` is set, the timestamp
    is derived from that epoch, making output byte-deterministic across
    runs of the same input.

    Malformed or out-of-range epoch values (e.g. very large integers that
    overflow the OS ``gmtime`` syscall) are silently ignored and fall
    through to wall-clock time.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return datetime.now(UTC).isoformat(timespec="seconds")
