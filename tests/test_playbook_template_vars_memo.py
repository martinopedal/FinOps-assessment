"""Memoisation test for ``extract_template_vars`` (Noor PR #78 AMENDMENT #1).

The static AST walk in ``extract_template_vars`` is memoised per
``(rule_id, template_source)``.  Without memoisation the parse runs
once per finding (10K Azure findings * ~5ms parse = ~50s of avoidable
wall-clock).
"""

from __future__ import annotations

from typing import Any

from finops_assess.reporters import playbook


def _finding(rule_id: str = "AZ.IDLE_VM_14D") -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "surface": "azure",
        "severity": "high",
        "principal": "/subscriptions/test/VM/test-vm",
        "current_sku": "Standard_D4s_v3",
        "recommended_sku": "Standard_D2s_v3",
        "estimated_monthly_savings_usd": 85.0,
        "recommendation": "Idle VM.",
        "evidence_ref": None,
        "confidence": "high",
        "evidence": {"avg_cpu_pct": 2.1, "avg_net_kbps": 15.5},
    }


def test_extract_template_vars_runs_once_per_unique_rule(monkeypatch: Any) -> None:
    """Render N findings for the same rule_id; the underlying parser must run once."""
    # Reset the memo between test runs (cache is process-global).
    playbook._template_vars_cached.cache_clear()

    call_count = {"n": 0}
    real_extract = playbook.extract_template_vars

    def counting(source: str) -> list[str]:
        call_count["n"] += 1
        return real_extract(source)

    monkeypatch.setattr(playbook, "extract_template_vars", counting)

    # Render the same finding ten times.
    for _ in range(10):
        playbook.render_row(_finding())

    assert call_count["n"] == 1, (
        f"extract_template_vars must run once for 10 renders of the same rule; "
        f"ran {call_count['n']} times"
    )


def test_extract_template_vars_memo_keyed_per_rule(monkeypatch: Any) -> None:
    """Distinct rule_ids must each parse once; the memo key includes rule_id."""
    playbook._template_vars_cached.cache_clear()

    call_count = {"n": 0}
    real_extract = playbook.extract_template_vars

    def counting(source: str) -> list[str]:
        call_count["n"] += 1
        return real_extract(source)

    monkeypatch.setattr(playbook, "extract_template_vars", counting)

    rule_ids = [
        "AZ.IDLE_VM_14D",
        "AZ.UNATTACHED_DISK",
        "AZ.PUBLIC_IP_UNATTACHED",
    ]
    for rid in rule_ids * 3:
        playbook.render_row(_finding(rid))

    assert call_count["n"] == len(rule_ids), (
        f"extract_template_vars must run once per unique rule_id; "
        f"saw {call_count['n']} calls for {len(rule_ids)} unique rules"
    )
