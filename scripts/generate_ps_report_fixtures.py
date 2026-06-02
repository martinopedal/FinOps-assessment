#!/usr/bin/env python3
"""Generate the PowerShell report-conformance golden fixtures.

Phase-1c stands up conformance layers 4-5 for the JSON report contract
(see ``docs/plan.md`` §5a). This script produces two committed goldens
that the PowerShell Pester suite compares against:

``tests/fixtures/ps_conformance/demo-report-structural.canonical.json``
    The ``report-structural-v1`` canonical projection (see
    ``scripts/canonicalize_report.py``) of a **real** Python report built
    by the normal pipeline over the bundled demo tenant. The projection
    masks rule-dependent fields and finding contents, so this golden is
    an honest structural artefact both engines can match today, without
    pretending the PowerShell engine produces findings yet.

``tests/fixtures/ps_conformance/demo-personas.json``
    The persona assignments (``assign_personas``) over the demo tenant,
    canonicalised, so the ported PowerShell persona engine can be
    deep-compared field-for-field (conformance layer 2 for personas).

Both goldens are byte-stable: ``SOURCE_DATE_EPOCH=0`` pins the report
timestamp and the demo input is the committed ``src/finops_assess/demo``
directory (leaf name ``demo``), so the redacted ``run.input`` is the
stable ``"<redacted>/demo"`` on every OS.

Run ``python scripts/generate_ps_report_fixtures.py`` after any change
that affects the report envelope, persona engine, or demo data.
``tests/test_ps_report_fixtures.py`` re-runs this generator and fails on
any uncommitted drift.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from canonicalize_report import canonicalize  # noqa: E402

from finops_assess.catalog import load_catalog  # noqa: E402
from finops_assess.collectors import collect_from_directory  # noqa: E402
from finops_assess.engine import run_rules  # noqa: E402
from finops_assess.persona import assign_personas  # noqa: E402
from finops_assess.reporters.json_reporter import build_report  # noqa: E402
from finops_assess.rules import load_personas, load_rules  # noqa: E402

DEMO_DIR = _REPO_ROOT / "src" / "finops_assess" / "demo"
FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
STRUCTURAL_GOLDEN = FIXTURE_DIR / "demo-report-structural.canonical.json"
PERSONA_GOLDEN = FIXTURE_DIR / "demo-personas.json"
PROFILE = "report-structural-v1"


def _build_demo_report() -> dict:
    """Run the real Python pipeline over the demo tenant (epoch pinned)."""
    dataset = collect_from_directory(DEMO_DIR)
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    persona_assignments = assign_personas(dataset, personas)
    findings, summary = run_rules(
        rules=rules,
        catalog=catalog,
        personas=personas,
        persona_assignments=persona_assignments,
        dataset=dataset,
        redact_pii=True,
    )
    return build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=DEMO_DIR,
        redact_pii=True,
    )


def _persona_golden() -> dict:
    """Canonical persona-assignment map for the demo tenant."""
    dataset = collect_from_directory(DEMO_DIR)
    personas = load_personas()
    assignments = assign_personas(dataset, personas)
    return {
        principal: assignment.model_dump(mode="json")
        for principal, assignment in assignments.items()
    }


def regenerate() -> dict[Path, str]:
    """Return ``{path: contents}`` for every golden fixture."""
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        report = _build_demo_report()
        structural = canonicalize(report, PROFILE) + "\n"
        personas = (
            json.dumps(_persona_golden(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    return {STRUCTURAL_GOLDEN: structural, PERSONA_GOLDEN: personas}


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for path, contents in regenerate().items():
        path.write_text(contents, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
