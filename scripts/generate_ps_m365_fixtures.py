#!/usr/bin/env python3
"""Generate the PowerShell M365 rule-slice conformance goldens (Phase 2).

Phase 2 ports the eight ``M365.*`` rules and the flat-CSV reporter to the
native PowerShell engine (see ``docs/plan.md`` §6/§7). This script emits
two committed goldens the PowerShell Pester suite compares against,
byte-for-byte, via the shared canonicaliser / CSV reporter:

``tests/fixtures/ps_conformance/demo-report-m365.canonical.json``
    The ``report-m365-v1`` canonical projection (see
    ``scripts/canonicalize_report.py``) of a **real** Python report built
    by the normal pipeline over the bundled demo tenant. The projection
    keeps the full contents of every ``M365.*`` finding (sorted by a
    deterministic key) plus the M365 ``rule_counts``, and self-validates
    that all eight M365 rules are exercised.

``tests/fixtures/ps_conformance/demo-report-m365.csv``
    The flat CSV (``finops_assess.reporters.csv_reporter``) over the same
    M365 findings, in the same canonical sort order, so the hand-rolled
    PowerShell CSV writer can be compared byte-for-byte.

Determinism: ``SOURCE_DATE_EPOCH=0`` pins the report timestamp; the demo
input is the committed ``src/finops_assess/demo`` directory (leaf name
``demo``) so the redacted ``run.input`` is stable; and a **fixed salt**
(:data:`FIXED_SALT`) makes ``salt_mode`` ``tenant_stable`` and the
salted-hash of every principal reproducible across engines (SHA-256 of
``"{salt}:{principal}"`` is portable), which is what lets the *contents*
of redacted findings byte-match.

Run ``python scripts/generate_ps_m365_fixtures.py`` after any change that
affects the M365 rules, the CSV reporter, the canonicaliser, or the demo
data. ``tests/test_ps_m365_fixtures.py`` re-runs this generator and fails
on any uncommitted drift.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from canonicalize_report import canonicalize  # noqa: E402

from finops_assess.catalog import load_catalog  # noqa: E402
from finops_assess.collectors import collect_from_directory  # noqa: E402
from finops_assess.engine import run_rules  # noqa: E402
from finops_assess.persona import assign_personas  # noqa: E402
from finops_assess.reporters.csv_reporter import write_csv_report  # noqa: E402
from finops_assess.reporters.json_reporter import build_report  # noqa: E402
from finops_assess.rules import load_personas, load_rules  # noqa: E402

DEMO_DIR = _REPO_ROOT / "src" / "finops_assess" / "demo"
FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "ps_conformance"
M365_GOLDEN = FIXTURE_DIR / "demo-report-m365.canonical.json"
CSV_GOLDEN = FIXTURE_DIR / "demo-report-m365.csv"
PROFILE = "report-m365-v1"

#: Fixed salt shared by the golden generator and the PowerShell Pester
#: conformance test. Using a fixed salt (rather than the per-run random
#: default) makes ``salt_mode`` ``tenant_stable`` and the salted hash of
#: every principal reproducible, so redacted finding contents byte-match
#: across engines. This salt is a *test* value only; it never ships.
FIXED_SALT = "conformance-fixed-salt-v1"


def _build_demo_report() -> dict:
    """Run the real Python pipeline over the demo tenant (epoch + salt pinned)."""
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
        salt=FIXED_SALT,
    )
    return build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=DEMO_DIR,
        redact_pii=True,
    )


def _m365_csv(report: dict) -> str:
    """Render the flat CSV over the M365 findings of ``report``.

    Findings are kept in **natural report order** (rule order, then each
    rule's input-iteration order) rather than sorted: the PowerShell rule
    engine mirrors the Python engine's iteration order exactly, so the CSV
    byte-compare doubles as an emission-order drift check (which the sorted
    JSON canonical compare deliberately cannot catch).
    """
    m365 = [f for f in report.get("findings", []) if str(f.get("rule_id", "")).startswith("M365.")]
    csv_report = {"findings": m365}
    with tempfile.TemporaryDirectory() as tmp:
        out = write_csv_report(csv_report, Path(tmp) / "m365.csv")
        return out.read_text(encoding="utf-8")


def regenerate() -> dict[Path, str]:
    """Return ``{path: contents}`` for every M365 golden fixture."""
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        report = _build_demo_report()
        canonical = canonicalize(report, PROFILE) + "\n"
        csv_text = _m365_csv(report)
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    return {M365_GOLDEN: canonical, CSV_GOLDEN: csv_text}


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for path, contents in regenerate().items():
        path.write_text(contents, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
