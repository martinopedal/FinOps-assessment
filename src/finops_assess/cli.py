"""finops-assess CLI entry point."""

from __future__ import annotations

import json
import logging
import os
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
    find_orphaned_jsonl,
    write_csv_report,
    write_focus_aligned_export,
    write_html_report,
    write_json_report,
    write_pdf_report,
    write_playbook_export,
    write_triage_csv,
    write_triage_json,
)
from finops_assess.reporters.json_reporter import build_report
from finops_assess.rules import load_personas, load_rules
from finops_assess.triage import CopilotHelperMode, build_triage, resolve_copilot_helper

logger = logging.getLogger(__name__)


def _resolve_pii_salt(
    pii_salt_file: Path | None,
    no_pii_redaction: bool,
) -> tuple[str | None, str]:
    """Resolve the PII salt and return (salt_or_none, mode_label).

    Returns (None, "per_run") when no stable salt is configured.
    Returns (salt_string, "tenant_stable") when a salt is found.
    Raises click.BadParameter on validation failure.
    """
    if no_pii_redaction:
        if pii_salt_file is not None:
            logger.warning("--pii-salt-file is ignored because --no-pii-redaction is set")
        return None, "disabled"

    # 1. Explicit file flag (highest precedence)
    if pii_salt_file is not None:
        if not pii_salt_file.exists():
            raise click.BadParameter(
                f"Salt file not found: {pii_salt_file}",
                param_hint="--pii-salt-file",
            )
        if pii_salt_file.stat().st_size == 0:
            raise click.BadParameter(
                "Salt file is empty (no entropy)",
                param_hint="--pii-salt-file",
            )
        if pii_salt_file.stat().st_size > 1024 * 1024:
            raise click.BadParameter(
                f"Salt file too large: {pii_salt_file.stat().st_size} bytes (max 1 MiB)",
                param_hint="--pii-salt-file",
            )
        salt = pii_salt_file.read_text(encoding="utf-8").strip()
        if not salt:
            raise click.BadParameter(
                "Salt file contains only whitespace",
                param_hint="--pii-salt-file",
            )
        # Warn if entropy is low (< 32 hex chars = 128 bits)
        if len(salt) < 32:
            logger.warning(
                f"Salt has low entropy ({len(salt)} chars < 32); "
                "consider regenerating with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        # Unix-only advisory: warn if world-readable
        if hasattr(os, "stat") and pii_salt_file.stat().st_mode & 0o004:
            logger.warning(
                f"Salt file {pii_salt_file} is world-readable; "
                "consider restricting to owner-only (chmod 600)"
            )
        logger.info(f"PII salt mode: tenant_stable (source: file {pii_salt_file})")
        return salt, "tenant_stable"

    # 2. Environment variable
    env_salt = os.environ.get("FINOPS_PII_SALT", "").strip()
    if env_salt:
        if len(env_salt) < 32:
            logger.warning(
                f"Salt from FINOPS_PII_SALT has low entropy ({len(env_salt)} chars < 32); "
                "consider regenerating with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        logger.info("PII salt mode: tenant_stable (source: env FINOPS_PII_SALT)")
        return env_salt, "tenant_stable"

    # 3. Default: per-run rotation
    logger.info("PII salt mode: per_run")
    return None, "per_run"


def _execute_assessment(
    *,
    input_dir: Path,
    redact_pii: bool,
    salt: str | None = None,
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
        salt=salt,
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
    type=click.Choice(["json", "html", "csv", "pdf", "playbook", "both", "all"]),
    default="json",
    show_default=True,
    help="Report format(s) to emit. 'both' emits json+html (back-compat); "
    "'all' emits json+html+csv+pdf — the pdf step requires the optional "
    "'pdf' extra (pip install 'finops-assess[pdf]'). 'playbook' emits a "
    "JSONL ticket-playbook file alongside a sidecar manifest.json.",
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
    "--playbook-output",
    "playbook_output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the playbook JSONL (only used when --format is playbook). "
    "A sidecar <path>.manifest.json is written in the same directory. "
    "Defaults to --output with the suffix replaced by .jsonl when --format=playbook.",
)
@click.option(
    "--cleanup-orphans",
    is_flag=True,
    default=False,
    help="Pre-flight: scan the playbook output directory for .jsonl files that lack a "
    "matching manifest (or whose manifest sha256 does not match). Remove orphaned "
    "files before writing the new export. Default off.",
)
@click.option(
    "--skip-warnings",
    is_flag=True,
    default=False,
    help="Suppress advisory warnings emitted to stderr (e.g. per-run ticket_key stability "
    "warning for M365/GitHub/ADO findings when PII redaction is on).",
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
    "--pii-salt-file",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to a file containing the PII salt (high-entropy secret, ≥32 hex chars recommended). "
        "When set, principal hashes are stable across runs for the same tenant. "
        "Overrides FINOPS_PII_SALT env var. Ignored if --no-pii-redaction is set."
    ),
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
    playbook_output: Path | None,
    cleanup_orphans: bool,
    skip_warnings: bool,
    branding_name: str | None,
    branding_color: str | None,
    branding_logo: Path | None,
    branding_page_size: str | None,
    no_pii_redaction: bool,
    pii_salt_file: Path | None,
    verbose: bool,
) -> None:
    """Run the rule engine over a directory of normalised CSVs."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    salt, _salt_mode = _resolve_pii_salt(pii_salt_file, no_pii_redaction)
    redact_pii = not no_pii_redaction
    report, rule_counts = _execute_assessment(
        input_dir=input_dir,
        redact_pii=redact_pii,
        salt=salt,
    )
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

    if fmt == "playbook":
        resolved_playbook = playbook_output
        if resolved_playbook is None and output is not None:
            resolved_playbook = output.with_suffix(".jsonl")
        if resolved_playbook is None:
            raise click.UsageError(
                "--playbook-output (or --output) is required for playbook format."
            )
        if cleanup_orphans:
            orphans = find_orphaned_jsonl(resolved_playbook.parent)
            for orphan in orphans:
                click.echo(f"Removing orphaned JSONL (no matching manifest): {orphan}", err=True)
                orphan.unlink()
        jsonl_path, manifest_path = write_playbook_export(
            report, resolved_playbook, skip_warnings=skip_warnings
        )
        wrote_any_file = True
        click.echo(
            f"OK — wrote {findings_count} playbook rows to {jsonl_path}\n"
            f"     manifest: {manifest_path}"
        )

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
@click.option(
    "--pii-salt-file",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to a file containing the PII salt (high-entropy secret, ≥32 hex chars recommended). "
        "When set, principal hashes are stable across runs for the same tenant. "
        "Overrides FINOPS_PII_SALT env var. Ignored if --no-pii-redaction is set."
    ),
)
def demo(
    output_dir: Path, include_pdf: bool, no_pii_redaction: bool, pii_salt_file: Path | None
) -> None:
    """Run the assessment against the bundled synthetic tenant.

    Produces ``demo-report.json``, ``demo-report.html``, and
    ``demo-report.csv`` in ``--output-dir``, and (with ``--pdf``)
    ``demo-report.pdf`` as well. The synthetic tenant is shipped inside
    the package so this works after ``pip install`` without a checkout
    — see ``finops_assess.demo``.
    """
    salt, _salt_mode = _resolve_pii_salt(pii_salt_file, no_pii_redaction)
    redact_pii = not no_pii_redaction
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="finops-demo-") as tmp:
        demo_input = materialise_demo_data(Path(tmp))
        report, rule_counts = _execute_assessment(
            input_dir=demo_input,
            redact_pii=redact_pii,
            salt=salt,
        )

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


@main.group()
def export() -> None:
    """Export findings to interoperability formats (advisory, not billing)."""


@export.command("focus-aligned")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Canonical findings JSON from `finops-assess run`.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Destination CSV path; manifest written alongside.",
)
def export_focus_aligned(input_path: Path, output_path: Path) -> None:
    """Emit a FOCUS-aligned advisory CSV from a finops-assess findings report.

    This export is NOT a FOCUS 1.3 conformant Cost-and-Usage dataset. Rows
    describe corrective recommendations, not billed consumption. Cost columns
    (BilledCost, ContractedCost, EffectiveCost, ListCost) are intentionally
    empty; advisory savings are surfaced in EstimatedMonthlySavingsUsd. See
    the sidecar manifest.json and docs/focus-export.md before loading.
    """
    try:
        raw = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        click.echo(f"ERROR: could not read {input_path}: {exc}", err=True)
        raise click.exceptions.Exit(1) from exc

    try:
        report: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        click.echo(
            f"ERROR: {input_path} is not valid JSON: {exc}",
            err=True,
        )
        raise click.exceptions.Exit(1) from exc

    if "findings" not in report:
        click.echo(
            f"ERROR: {input_path} does not look like a finops-assess report (no 'findings' key).",
            err=True,
        )
        raise click.exceptions.Exit(1) from None

    csv_path, manifest_path = write_focus_aligned_export(report, output_path)

    # Log skipped non-Azure findings.
    findings: list[dict[str, Any]] = report.get("findings", [])
    n_m365 = sum(1 for f in findings if f.get("surface") == "m365")
    n_github = sum(1 for f in findings if f.get("surface") == "github")
    n_ado = sum(1 for f in findings if f.get("surface") == "ado")
    n_skipped = n_m365 + n_github + n_ado
    if n_skipped:
        click.echo(
            f"Skipped {n_skipped} non-Azure findings "
            f"(m365={n_m365}, github={n_github}, ado={n_ado})"
        )

    n_rows = sum(1 for f in findings if f.get("surface") == "azure")
    click.echo(f"Wrote {n_rows} advisory rows to {csv_path} (manifest: {manifest_path})")


if __name__ == "__main__":  # pragma: no cover
    main()
