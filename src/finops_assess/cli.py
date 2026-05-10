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
    write_csv_report,
    write_html_report,
    write_json_report,
    write_pdf_report,
    write_triage_csv,
    write_triage_json,
)
from finops_assess.reporters.json_reporter import build_report
from finops_assess.rules import load_personas, load_rules
from finops_assess.triage import CopilotHelperMode, build_triage, resolve_copilot_helper


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


def _write_pdf_or_friendly_error(
    report: dict[str, Any],
    output: Path,
    branding: Branding,
) -> None:
    """Wrap ``write_pdf_report`` so the missing-extra error is clean.

    Without this, an operator who installed the base package but not
    ``finops-assess[pdf]`` would see a Python traceback on stderr;
    Click renders :class:`click.ClickException` as a single tidy line
    prefixed with ``Error:`` and exits with status 1.
    """
    try:
        write_pdf_report(report, output, branding=branding)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


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
    "input_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=True,
    help="Existing finops-assess JSON report to convert into advisory triage artefacts.",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("./triage-output"),
    show_default=True,
    help="Directory to write triage.json and/or triage.csv.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "csv", "both"]),
    default="both",
    show_default=True,
    help="Triage artefact format(s) to emit.",
)
@click.option(
    "--enable-copilot-helper",
    is_flag=True,
    default=False,
    help="Opt in to GitHub Copilot helper discovery. No data is sent unless this flag is used.",
)
@click.option(
    "--copilot-helper",
    type=click.Choice(["auto", "sdk", "cli"]),
    default="auto",
    show_default=True,
    help="Preferred GitHub Copilot helper when --enable-copilot-helper is set.",
)
def triage(
    input_path: Path,
    output_dir: Path,
    fmt: str,
    enable_copilot_helper: bool,
    copilot_helper: str,
) -> None:
    """Emit a read-only advisory triage pack from an existing report."""
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    run = payload.get("run") or {}
    if run.get("tool") != "finops-assess" or run.get("mode") != "read-only":
        raise click.ClickException("Input must be a finops-assess read-only JSON report.")

    helper_mode: CopilotHelperMode = "disabled"
    if enable_copilot_helper:
        helper_mode = resolve_copilot_helper(copilot_helper)  # type: ignore[arg-type]
        if helper_mode == "unavailable":
            click.echo(
                "Warning: GitHub Copilot helper was requested but no supported SDK or gh CLI "
                "helper was detected; emitting template-based triage only."
            )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    triage_report = build_triage(payload, source_path=input_path, copilot_helper=helper_mode)

    if fmt in ("json", "both"):
        json_path = output_dir / "triage.json"
        write_triage_json(triage_report, json_path)
        click.echo(f"OK — wrote advisory triage JSON to {json_path}")
    if fmt in ("csv", "both"):
        csv_path = output_dir / "triage.csv"
        write_triage_csv(triage_report, csv_path)
        click.echo(f"OK — wrote advisory triage CSV to {csv_path}")
    click.echo(f"Advisory triage items: {len(triage_report.items)}")


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
    type=click.Choice(["json", "html", "csv", "pdf", "both", "all"]),
    default="json",
    show_default=True,
    help="Report format(s) to emit. 'both' emits json+html (back-compat); "
    "'all' emits json+html+csv+pdf — the pdf step requires the optional "
    "'pdf' extra (pip install 'finops-assess[pdf]').",
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
    "--csv-output",
    "csv_output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the flat CSV findings report (only used when --format is csv or all). "
    "Defaults to --output with the suffix replaced by .csv when --format=all.",
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
    csv_output: Path | None,
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

    if fmt in ("csv", "all"):
        resolved_csv = csv_output
        if resolved_csv is None and output is not None and fmt == "all":
            resolved_csv = output.with_suffix(".csv")
        if resolved_csv is None:
            raise click.UsageError(
                "--csv-output (or --output, when --format=all) is required for CSV output."
            )
        write_csv_report(report, resolved_csv)
        wrote_any_file = True
        click.echo(f"OK — wrote CSV report to {resolved_csv}")

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
        _write_pdf_or_friendly_error(report, resolved_pdf, branding)
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
    help="Directory to write demo-report.json, demo-report.html, and "
    "demo-report.csv into (and demo-report.pdf when --pdf is passed).",
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

    Produces ``demo-report.json``, ``demo-report.html``, and
    ``demo-report.csv`` in ``--output-dir``, and (with ``--pdf``)
    ``demo-report.pdf`` as well. The synthetic tenant is shipped inside
    the package so this works after ``pip install`` without a checkout
    — see ``finops_assess.demo``.
    """
    redact_pii = not no_pii_redaction
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="finops-demo-") as tmp:
        demo_input = materialise_demo_data(Path(tmp))
        report, rule_counts = _execute_assessment(input_dir=demo_input, redact_pii=redact_pii)

    json_path = output_dir / "demo-report.json"
    html_path = output_dir / "demo-report.html"
    csv_path = output_dir / "demo-report.csv"
    write_json_report(report, json_path)
    write_html_report(report, html_path)
    write_csv_report(report, csv_path)

    pdf_line = ""
    if include_pdf:
        pdf_path = output_dir / "demo-report.pdf"
        _write_pdf_or_friendly_error(report, pdf_path, Branding())
        pdf_line = f"\n  PDF:  {pdf_path}"

    findings_count = len(report["findings"])
    active = sum(1 for v in rule_counts.values() if v)
    click.echo(
        f"OK — demo run produced {findings_count} findings across {active} rules.\n"
        f"  JSON: {json_path}\n"
        f"  HTML: {html_path}\n"
        f"  CSV:  {csv_path}"
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
        try:
            path = write_autogen(coverage)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
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


@main.command()
@click.option(
    "--surface",
    "surfaces",
    type=click.Choice(["m365", "azure", "github", "ado"]),
    multiple=True,
    default=["m365", "azure", "github", "ado"],
    show_default=True,
    help="Surface(s) to collect.  Repeat to select multiple.  Defaults to all four.",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("./collected-data"),
    show_default=True,
    help="Directory to write normalised CSV files into.  Passed directly to "
    "'finops-assess run --input' afterwards.",
)
@click.option(
    "--tenant-id",
    default=None,
    envvar="AZURE_TENANT_ID",
    help="Azure Entra tenant ID (M365 + Azure).  Falls back to AZURE_TENANT_ID.",
)
@click.option(
    "--subscription-ids",
    "subscription_ids",
    default=None,
    help="Comma-separated Azure subscription IDs to scan (Azure only).  "
    "Omit to scan all subscriptions the credential can read.",
)
@click.option(
    "--github-enterprise",
    "github_enterprise",
    default=None,
    envvar="GITHUB_ENTERPRISE",
    help="GitHub Enterprise slug.  Falls back to GITHUB_ENTERPRISE.",
)
@click.option(
    "--github-orgs",
    "github_orgs",
    default=None,
    help="Comma-separated GitHub organisation names (for GHAS + runner data).",
)
@click.option(
    "--ado-org",
    "ado_org",
    default=None,
    envvar="AZURE_DEVOPS_ORG",
    help="Azure DevOps organisation name.  Falls back to AZURE_DEVOPS_ORG.",
)
@click.option(
    "--no-metrics",
    "skip_metrics",
    is_flag=True,
    default=False,
    help="Skip Azure Monitor metrics calls (useful when Reader role is present "
    "but Monitoring Reader is not).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose (INFO-level) logging.",
)
def collect(
    surfaces: tuple[str, ...],
    output_dir: Path,
    tenant_id: str | None,
    subscription_ids: str | None,
    github_enterprise: str | None,
    github_orgs: str | None,
    ado_org: str | None,
    skip_metrics: bool,
    verbose: bool,
) -> None:
    """Pull live data from Microsoft / GitHub / ADO APIs into normalised CSVs.

    Writes CSV files to --output-dir; the directory can then be passed
    directly to finops-assess run --input <output-dir>.

    Requires the [live] optional extra:
    pip install 'finops-assess[live]'

    Authentication uses environment variables - see the collector modules for
    full details.

    \b
    M365 / Azure:  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (or
                   AZURE_FEDERATED_TOKEN_FILE for OIDC workload identity)
    GitHub:        GITHUB_TOKEN
    Azure DevOps:  AZURE_DEVOPS_PAT (or AZURE_DEVOPS_TOKEN for Entra auth)
    """
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    unique_surfaces = list(dict.fromkeys(surfaces))  # dedup while preserving order

    for surface in unique_surfaces:
        if surface == "m365":
            try:
                from finops_assess.collectors.graph_collector import collect_graph
            except ImportError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo("Collecting Microsoft 365 data via Graph API ...")
            try:
                collect_graph(output_dir, tenant_id=tenant_id)
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(f"  -> CSVs written to {output_dir}")

        elif surface == "azure":
            try:
                from finops_assess.collectors.arm_collector import collect_arm
            except ImportError as exc:
                raise click.ClickException(str(exc)) from exc
            sub_ids: list[str] | None = None
            if subscription_ids:
                sub_ids = [s.strip() for s in subscription_ids.split(",") if s.strip()]
            click.echo("Collecting Azure resource data via ARM API ...")
            try:
                collect_arm(output_dir, subscription_ids=sub_ids, collect_metrics=not skip_metrics)
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(f"  -> CSVs written to {output_dir}")

        elif surface == "github":
            try:
                from finops_assess.collectors.github_collector import collect_github
            except ImportError as exc:
                raise click.ClickException(str(exc)) from exc
            if not github_enterprise and not github_orgs:
                raise click.UsageError(
                    "At least one of --github-enterprise or --github-orgs is required "
                    "when collecting the github surface."
                )
            orgs_list: list[str] | None = None
            if github_orgs:
                orgs_list = [o.strip() for o in github_orgs.split(",") if o.strip()]
            click.echo("Collecting GitHub data via REST API ...")
            try:
                collect_github(
                    output_dir,
                    enterprise=github_enterprise,
                    orgs=orgs_list,
                )
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(f"  -> CSVs written to {output_dir}")

        elif surface == "ado":
            try:
                from finops_assess.collectors.ado_collector import collect_ado
            except ImportError as exc:
                raise click.ClickException(str(exc)) from exc
            if not ado_org:
                raise click.UsageError(
                    "--ado-org (or AZURE_DEVOPS_ORG env var) is required "
                    "when collecting the ado surface."
                )
            click.echo("Collecting Azure DevOps data via REST API ...")
            try:
                collect_ado(output_dir, org=ado_org)
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(f"  -> CSVs written to {output_dir}")

    click.echo(
        f"\nCollection complete.  Run the assessment with:\n"
        f"  finops-assess run --input {output_dir} --output report.json --format all"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
