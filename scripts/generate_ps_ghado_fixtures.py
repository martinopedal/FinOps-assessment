#!/usr/bin/env python3
"""Generate the PowerShell GitHub + ADO rule-slice conformance goldens (Phase 4).

Phase 4 ports the four ``GH.*`` and four ``ADO.*`` rules and the flat-CSV
reporter to the native PowerShell engine (see ``docs/plan.md`` §6/§7). This
script emits four committed goldens the PowerShell Pester suite compares
against, byte-for-byte, via the shared canonicaliser / CSV reporter:

``tests/fixtures/ps_conformance/demo-report-github.canonical.json``
    The ``report-github-v1`` canonical projection of a **real** Python report
    built by the normal pipeline over the bundled demo tenant.

``tests/fixtures/ps_conformance/demo-report-github.csv``
    The flat CSV (``finops_assess.reporters.csv_reporter``) over the same
    GitHub findings, in the same canonical sort order.

``tests/fixtures/ps_conformance/demo-report-ado.canonical.json``
    The ``report-ado-v1`` canonical projection of the same Python report.

``tests/fixtures/ps_conformance/demo-report-ado.csv``
    The flat CSV over the ADO findings.

Determinism: ``SOURCE_DATE_EPOCH=0`` pins the report timestamp; the demo
input is the committed ``src/finops_assess/demo`` directory; and a **fixed
salt** (:data:`FIXED_SALT`) makes ``salt_mode`` ``tenant_stable`` and the
salted-hash of every principal reproducible across engines.

Run ``python scripts/generate_ps_ghado_fixtures.py`` after any change that
affects the GitHub/ADO rules, the CSV reporter, the canonicaliser, or the
demo data. ``tests/test_ps_ghado_fixtures.py`` re-runs this generator and
fails on any uncommitted drift.
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
GH_JSON_GOLDEN = FIXTURE_DIR / "demo-report-github.canonical.json"
GH_CSV_GOLDEN = FIXTURE_DIR / "demo-report-github.csv"
ADO_JSON_GOLDEN = FIXTURE_DIR / "demo-report-ado.canonical.json"
ADO_CSV_GOLDEN = FIXTURE_DIR / "demo-report-ado.csv"

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


def _surface_csv(report: dict, prefix: str) -> str:
    """Render the flat CSV over the findings of a surface from ``report``.

    Findings are kept in **natural report order** (rule order, then each
    rule's input-iteration order) rather than sorted: the PowerShell rule
    engine mirrors the Python engine's iteration order exactly, so the CSV
    byte-compare doubles as an emission-order drift check (which the sorted
    JSON canonical compare deliberately cannot catch).
    """
    surface_findings = [
        f for f in report.get("findings", []) if str(f.get("rule_id", "")).startswith(prefix)
    ]
    csv_report = {"findings": surface_findings}
    with tempfile.TemporaryDirectory() as tmp:
        out = write_csv_report(csv_report, Path(tmp) / "surface.csv")
        return out.read_text(encoding="utf-8")


def regenerate() -> dict[Path, str]:
    """Return ``{path: contents}`` for every GitHub + ADO golden fixture."""
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        report = _build_demo_report()
        gh_canonical = canonicalize(report, "report-github-v1") + "\n"
        gh_csv = _surface_csv(report, "GH.")
        ado_canonical = canonicalize(report, "report-ado-v1") + "\n"
        ado_csv = _surface_csv(report, "ADO.")
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    return {
        GH_JSON_GOLDEN: gh_canonical,
        GH_CSV_GOLDEN: gh_csv,
        ADO_JSON_GOLDEN: ado_canonical,
        ADO_CSV_GOLDEN: ado_csv,
    }


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for path, contents in regenerate().items():
        path.write_text(contents, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
