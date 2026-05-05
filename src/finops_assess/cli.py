"""finops-assess CLI entry point."""

from __future__ import annotations

import json
import logging
from pathlib import Path

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
from finops_assess.engine import run_rules
from finops_assess.persona import assign_personas
from finops_assess.reporters import write_json_report
from finops_assess.reporters.json_reporter import build_report
from finops_assess.rules import load_personas, load_rules


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
def run(input_dir: Path, output: Path | None, no_pii_redaction: bool, verbose: bool) -> None:
    """Run the rule engine over a directory of normalised CSVs."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

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
        redact_pii=not no_pii_redaction,
    )
    report = build_report(
        findings=findings,
        summary=summary,
        persona_assignments=persona_assignments,
        input_path=input_dir,
        redact_pii=not no_pii_redaction,
    )
    payload = write_json_report(report, output)
    if output is None:
        click.echo(payload)
    else:
        active = sum(1 for v in summary["rule_counts"].values() if v)
        click.echo(f"OK — wrote {len(findings)} findings across {active} rules to {output}")


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
