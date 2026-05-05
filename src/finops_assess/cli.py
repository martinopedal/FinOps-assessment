"""finops-assess CLI entry point."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import click

from finops_assess import __version__
from finops_assess.catalog import load_catalog
from finops_assess.catalog_refresh import (
    DEFAULT_SOURCE_URL,
    compute_coverage,
    fetch_and_parse,
    write_autogen,
)
from finops_assess.collectors import collect_from_directory
from finops_assess.demo import materialise_demo_data
from finops_assess.engine import run_rules
from finops_assess.persona import assign_personas
from finops_assess.reporters import (
    Branding,
    write_html_report,
    write_json_report,
    write_pdf_report,
)
from finops_assess.reporters.json_reporter import build_report
from finops_assess.rules import load_personas, load_rules


def _execute_assessment(
    *,
    input_dir: Path,
    redact_pii: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Run the collector → engine → report pipeline against ``input_dir``.

    Returns the report dict and the per-rule count summary so the caller
    can format CLI output without re-deriving anything.
    """
    dataset = collect_from_directory(input_dir)
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
        redact_pii=redact_pii,
    )
    report = build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=input_dir,
        redact_pii=redact_pii,
    )
    rule_counts: dict[str, int] = summary["rule_counts"]
    return report, rule_counts


@click.group()
@click.version_option(__version__, prog_name="finops-assess")
def main() -> None:
    """Read-only FinOps assessment for the Microsoft ecosystem."""


@main.command()
def validate() -> None:
    """Validate the on-disk catalog, personas, and rules."""
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    click.echo(f"OK — catalog: {len(catalog)} SKUs, personas: {len(personas)}, rules: {len(rules)}")


@main.command()
def info() -> None:
    """Print version + scope summary."""
    click.echo(f"finops-assess {__version__}")
    click.echo("Surfaces: M365 · Azure · GitHub · Azure DevOps")
    click.echo("Mode: read-only")


@main.command()
@click.option(
    "--input",
    "input_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Directory containing normalised CSV files (users.csv, license_assignments.csv, "
    "usage.csv, azure_resources.csv) and an optional overrides.yaml.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the JSON report; if omitted, prints to stdout.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "html", "pdf", "both", "all"]),
    default="json",
    show_default=True,
    help="Report format(s) to emit. 'both' emits json+html (back-compat); "
    "'all' emits json+html+pdf.",
)
@click.option(
    "--html-output",
    "html_output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the HTML report (only used when --format is html, both, or all). "
    "Defaults to --output with the suffix replaced by .html when --format is both or all.",
)
@click.option(
    "--pdf-output",
    "pdf_output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the PDF report (only used when --format is pdf or all). "
    "Defaults to --output with the suffix replaced by .pdf when --format=all. "
    "Requires the optional 'pdf' extra (pip install 'finops-assess[pdf]').",
)
@click.option(
    "--branding-name",
    default=None,
    help="Organisation name to print on the PDF cover page.",
)
@click.option(
    "--branding-color",
    default=None,
    help="Accent colour for the PDF cover page as a #RRGGBB hex literal.",
)
@click.option(
    "--branding-logo",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a PNG/JPEG/GIF logo (≤1 MiB) to embed on the PDF cover page.",
)
@click.option(
    "--branding-page-size",
    type=click.Choice(["Letter", "A4", "Legal", "A3", "A5"]),
    default=None,
    help="Paper size for the PDF report. Defaults to Letter.",
)
@click.option(
    "--no-pii-redaction",
    is_flag=True,
    default=False,
    help="Disable salted hashing of principals in the report (opt-in; default is on).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose (INFO-level) logging.",
)
def run(
    input_dir: Path,
    output: Path | None,
    fmt: str,
    html_output: Path | None,
    pdf_output: Path | None,
    branding_name: str | None,
    branding_color: str | None,
    branding_logo: Path | None,
    branding_page_size: str | None,
    no_pii_redaction: bool,
    verbose: bool,
) -> None:
    """Run the rule engine over a directory of normalised CSVs."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    redact_pii = not no_pii_redaction
    report, rule_counts = _execute_assessment(input_dir=input_dir, redact_pii=redact_pii)
    findings_count = len(report["findings"])
    active = sum(1 for v in rule_counts.values() if v)

    wrote_any_file = False
    if fmt in ("json", "both", "all"):
        json_payload = write_json_report(report, output)
        if output is not None:
            wrote_any_file = True
            click.echo(f"OK — wrote {findings_count} findings across {active} rules to {output}")
        elif fmt == "json":
            click.echo(json_payload)

    if fmt in ("html", "both", "all"):
        resolved_html = html_output
        if resolved_html is None and output is not None and fmt in ("both", "all"):
            resolved_html = output.with_suffix(".html")
        if resolved_html is None:
            raise click.UsageError(
                "--html-output (or --output, when --format is both or all) "
                "is required for HTML output."
            )
        write_html_report(report, resolved_html)
        wrote_any_file = True
        click.echo(f"OK — wrote HTML report to {resolved_html}")

    if fmt in ("pdf", "all"):
        resolved_pdf = pdf_output
        if resolved_pdf is None and output is not None and fmt == "all":
            resolved_pdf = output.with_suffix(".pdf")
        if resolved_pdf is None:
            raise click.UsageError(
                "--pdf-output (or --output, when --format=all) is required for PDF output."
            )
        branding = Branding.from_options(
            name=branding_name,
            accent_color=branding_color,
            page_size=branding_page_size,
            logo_path=branding_logo,
        )
        write_pdf_report(report, resolved_pdf, branding=branding)
        wrote_any_file = True
        click.echo(f"OK — wrote PDF report to {resolved_pdf}")

    if not wrote_any_file and fmt == "json" and output is None:
        # Already echoed JSON to stdout above; nothing else to do.
        return


@main.command()
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("./demo-report"),
    show_default=True,
    help="Directory to write demo-report.json and demo-report.html into.",
)
@click.option(
    "--pdf",
    "include_pdf",
    is_flag=True,
    default=False,
    help="Also emit demo-report.pdf. Requires the optional 'pdf' extra "
    "(pip install 'finops-assess[pdf]').",
)
@click.option(
    "--no-pii-redaction",
    is_flag=True,
    default=False,
    help="Disable salted hashing of principals in the report (opt-in; default is on).",
)
def demo(output_dir: Path, include_pdf: bool, no_pii_redaction: bool) -> None:
    """Run the assessment against the bundled synthetic tenant.

    Produces ``demo-report.json`` and ``demo-report.html`` in ``--output-dir``,
    and (with ``--pdf``) ``demo-report.pdf`` as well. The synthetic tenant
    is shipped inside the package so this works after ``pip install``
    without a checkout — see ``finops_assess.demo``.
    """
    redact_pii = not no_pii_redaction
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="finops-demo-") as tmp:
        demo_input = materialise_demo_data(Path(tmp))
        report, rule_counts = _execute_assessment(input_dir=demo_input, redact_pii=redact_pii)

    json_path = output_dir / "demo-report.json"
    html_path = output_dir / "demo-report.html"
    write_json_report(report, json_path)
    write_html_report(report, html_path)

    pdf_line = ""
    if include_pdf:
        pdf_path = output_dir / "demo-report.pdf"
        write_pdf_report(report, pdf_path, branding=Branding())
        pdf_line = f"\n  PDF:  {pdf_path}"

    findings_count = len(report["findings"])
    active = sum(1 for v in rule_counts.values() if v)
    click.echo(
        f"OK — demo run produced {findings_count} findings across {active} rules.\n"
        f"  JSON: {json_path}\n"
        f"  HTML: {html_path}"
        f"{pdf_line}"
    )


@main.group()
def catalog() -> None:
    """Catalogue maintenance commands (auto-fetch from official sources)."""


@catalog.command("refresh")
@click.option(
    "--source",
    default=DEFAULT_SOURCE_URL,
    show_default=False,
    help="HTTP(S) URL or local path to the Microsoft 'Product names and service plan "
    "identifiers for licensing' CSV. Defaults to the stable download.microsoft.com URL.",
)
@click.option(
    "--write/--report-only",
    default=False,
    help="Write missing SKU stubs to data/catalog/m365/_autogen_unmapped.yaml "
    "(default: report only).",
)
def catalog_refresh(source: str, write: bool) -> None:
    """Fetch the official Microsoft SKU catalogue and report (or write) gaps."""
    click.echo(f"Fetching upstream catalogue from {source} …")
    upstream = fetch_and_parse(source)
    coverage = compute_coverage(upstream, source_url=source)
    click.echo(
        f"Upstream SKUs: {coverage.upstream_count}; "
        f"catalogued M365 SKUs: {coverage.catalog_count}; "
        f"coverage: {coverage.coverage_pct}%"
    )
    if coverage.missing:
        click.echo(f"Missing from catalogue ({len(coverage.missing)}):")
        for sku in coverage.missing[:25]:
            click.echo(f"  - {sku.string_id}\t{sku.display_name}")
        if len(coverage.missing) > 25:
            click.echo(f"  … and {len(coverage.missing) - 25} more")
    else:
        click.echo("No upstream gaps. ✓")
    if coverage.extra_local_ids:
        click.echo(
            f"Catalogue contains {len(coverage.extra_local_ids)} M365 ids not present "
            "in the upstream CSV (legacy or non-user SKUs); not removed."
        )
    if write and coverage.missing:
        path = write_autogen(coverage)
        if path is not None:
            click.echo(f"Wrote stubs for {len(coverage.missing)} SKUs to {path}")


@catalog.command("coverage")
@click.option("--source", default=DEFAULT_SOURCE_URL)
@click.option(
    "--fail-on-gap/--no-fail-on-gap",
    default=True,
    help="Exit non-zero when upstream has SKUs we don't model (default: on).",
)
def catalog_coverage(source: str, fail_on_gap: bool) -> None:
    """Print a JSON coverage diff vs. the upstream catalogue."""
    upstream = fetch_and_parse(source)
    coverage = compute_coverage(upstream, source_url=source)
    payload = {
        "source": source,
        "upstream_count": coverage.upstream_count,
        "catalog_count": coverage.catalog_count,
        "coverage_pct": coverage.coverage_pct,
        "missing": [{"id": s.string_id, "display_name": s.display_name} for s in coverage.missing],
        "extra_local_ids": coverage.extra_local_ids,
    }
    click.echo(json.dumps(payload, indent=2))
    if fail_on_gap and coverage.missing:
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
