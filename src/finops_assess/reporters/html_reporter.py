"""Self-contained HTML reporter (Jinja2 + vendored CSS, no remote assets).

Consumes the canonical report dictionary produced by
:func:`finops_assess.reporters.json_reporter.build_report`, so it
inherits PII redaction and any other normalisation already applied
upstream — the HTML reporter never sees raw :class:`Finding` objects.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FunctionLoader, select_autoescape

# Severity ordering: highest impact first in the rendered tables.
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

# Surface tabs — order is deliberate (M365 → Azure → GitHub → ADO).
_SURFACE_LABELS: list[tuple[str, str]] = [
    ("m365", "Microsoft 365"),
    ("azure", "Azure"),
    ("github", "GitHub"),
    ("ado", "Azure DevOps"),
]

_TEMPLATE_NAME = "report.html.j2"


def _load_template_source(name: str) -> str | None:
    """Load a template by name from the packaged ``templates/`` resource dir."""
    if name != _TEMPLATE_NAME:
        return None
    template_root = resources.files("finops_assess.reporters") / "templates"
    return (template_root / name).read_text(encoding="utf-8")


def _make_env() -> Environment:
    return Environment(
        loader=FunctionLoader(_load_template_source),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def _group_by_surface(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        grouped.setdefault(f["surface"], []).append(f)
    for _surface, items in grouped.items():
        items.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 99), f["rule_id"]))
    return grouped


def build_html_report(report: dict[str, Any]) -> str:
    """Render the JSON-shaped ``report`` dictionary as a self-contained HTML document."""
    findings: list[dict[str, Any]] = list(report.get("findings", []))
    summary: dict[str, Any] = dict(report.get("summary", {}))
    run: dict[str, Any] = dict(report.get("run", {}))

    rule_counts: dict[str, int] = summary.get("rule_counts", {}) or {}
    rules_fired_count = sum(1 for v in rule_counts.values() if v)
    total_estimated_savings = sum(
        float(f.get("estimated_monthly_savings_usd") or 0.0) for f in findings
    )

    env = _make_env()
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(
        run=run,
        summary=summary,
        findings=findings,
        findings_by_surface=_group_by_surface(findings),
        rules_fired_count=rules_fired_count,
        total_estimated_savings=total_estimated_savings,
        surface_labels=_SURFACE_LABELS,
    )


def write_html_report(report: dict[str, Any], output: Path | None) -> str:
    """Render ``report`` to HTML; write to ``output`` if given, else return string."""
    payload = build_html_report(report)
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    return payload
