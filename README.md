# FinOps-assessment

A read-only assessment tool that audits licensing and cost across the
**Microsoft ecosystem**: Microsoft 365, Entra ID and EMS, Defender,
Purview, Power Platform, Azure, **GitHub**, and **Azure DevOps**. It
emits right-sizing and cost-saving recommendations. It never mutates
the systems it inspects.

Release history is in [`CHANGELOG.md`](CHANGELOG.md). Contributor
documentation is in [`docs/contributing.md`](docs/contributing.md).

## What you get

- Evidence-backed right-sizing findings across Microsoft 365, Azure, GitHub, and Azure DevOps.
- Multi-format outputs: executive HTML, canonical JSON, flat CSV, and optional PDF.
- Clear review queues for over-licensed, duplicate, idle, inactive, and over-provisioned spend.

See [`docs/user-guide.md`](docs/user-guide.md) for report previews, CLI visuals,
and worked examples of what the tool delivers.

## Quick start

The tool is a single Python package and a single CLI (`finops-assess`).
It runs identically on **Windows**, **macOS**, **Linux**, and inside
**GitHub Actions**, Azure DevOps Pipelines, or any container. There is
no OS-specific code path.

You only need Python 3.11 or newer. Pick the one-liner for your shell:

```bash
# Linux or macOS (bash, zsh)
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

```powershell
# Windows (PowerShell 5.1 or 7+)
py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

```bat
:: Windows (cmd.exe)
py -3.11 -m venv .venv && .venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

## Run

```bash
# Validate the bundled catalogue, personas, and rules.
finops-assess validate

# Run the synthetic-tenant demo end-to-end (writes JSON, HTML, and CSV reports).
finops-assess demo --output-dir ./demo-report

# Same demo, but also emit a PDF executive report (requires the [pdf] extra).
finops-assess demo --output-dir ./demo-report --pdf

# Run against your own normalised CSVs.
finops-assess run --input ./samples --output ./report.json --format both

# Emit a flat CSV of findings for pivoting in Excel or Sheets.
finops-assess run --input ./samples --format csv --csv-output ./findings.csv

# Build an advisory analyst triage pack from an existing JSON report.
finops-assess triage --input ./report.json --output-dir ./triage

# Run against your CSVs and emit JSON, HTML, CSV, and PDF together
# (the PDF step needs the optional [pdf] extra; see "PDF reports" below).
finops-assess run --input ./samples --output ./report.json --format all \
  --branding-name "Contoso" --branding-color "#0969da"
```

The data contract for `samples/` (CSV columns the collector expects)
is documented in [`docs/schema.md`](docs/schema.md). The full rule
reference is in [`docs/rules.md`](docs/rules.md).

## PDF reports (optional `[pdf]` extra)

The PDF executive report is rendered by [WeasyPrint](https://weasyprint.org/),
which has heavy native dependencies (Pango, cairo, GDK-pixbuf). It is
not installed by default. To enable it:

```bash
pip install 'finops-assess[pdf]'
```

Then install the platform-specific system libraries WeasyPrint needs.
See the [WeasyPrint installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
for your OS. PDF builds are deterministic: re-running against the same
JSON report produces a byte-identical PDF (`SOURCE_DATE_EPOCH` is
derived from the report's own `run.generated_at` timestamp).

PowerShell-native operators can use the wrapper script in `scripts/`
and keep the report flowing through a PowerShell pipeline:

```powershell
$report = ./scripts/Invoke-FinOpsAssess.ps1 -Demo -OutputDir ./out
$report.findings | Where-Object severity -eq 'high' | Format-Table
```

## Run inside a GitHub Actions workflow

Drop this into any repo's `.github/workflows/finops.yml`:

```yaml
jobs:
  finops-assess:
    runs-on: ubuntu-latest   # also valid: windows-latest, macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: finops-assess validate
      - run: finops-assess demo --output-dir ./demo-report
      - uses: actions/upload-artifact@v4
        with:
          name: finops-assess-demo-report
          path: demo-report/
```

For Azure DevOps Pipelines the equivalent is `UsePythonVersion@0`
followed by the same two `pip install` and `finops-assess` steps.

This repository ships the same demo job at
`.github/workflows/demo-report.yml`. Every push to `main` (and every
manual `workflow_dispatch`) publishes the rendered HTML and JSON
reports as the **`finops-assess-demo-report`** workflow artifact.

## Example reports and rule reference

In-repo artefacts that are auto-generated from the codebase on every
PR (`.github/workflows/docs.yml` fails the build on drift):

- [`docs/user-guide.md`](docs/user-guide.md): report previews, CLI visuals,
  and worked examples for interpreting over-licensed and idle-spend findings.
- [`docs/rules.md`](docs/rules.md): full reference for every rule
  shipped under `data/rules/`, annotated with whether each has a
  registered Python implementation.
- [`examples/demo-report.json`](examples/demo-report.json),
  [`examples/demo-report.html`](examples/demo-report.html),
  [`examples/demo-report.csv`](examples/demo-report.csv): the
  deterministic output of `finops-assess demo` against the bundled
  synthetic tenant. Rendered with `SOURCE_DATE_EPOCH=0` and a fixed
  redaction salt so the bytes are stable across CI runs.
- [`examples/demo-triage.json`](examples/demo-triage.json),
  [`examples/demo-triage.csv`](examples/demo-triage.csv): advisory triage
  artefacts derived from the demo JSON report.
- [`docs/roadmap/README.md`](docs/roadmap/README.md): exploratory frontier
  roadmap for FinOps Toolkit / FOCUS / Hubs alignment, pricing intelligence,
  commitments, SKU mix, practice-review outputs, and optional assist tooling.
- [`docs/skills/README.md`](docs/skills/README.md): draft local operator
  skills/runbook inventory; these are documentation guardrails, not executable
  automation.

## Contributing

Internal documentation (architecture, data contract, delivery process,
maintainer hardening) is collected in
[`docs/contributing.md`](docs/contributing.md). If you only want to
run the tool, you can ignore that file.

## License

MIT. See [`LICENSE`](LICENSE).

## Credits

License feature taxonomy is informed by **Aaron Dinnage's M365 Maps**
([m365maps.com](https://m365maps.com/)). We link to and credit the
source. We do not redistribute the diagrams.
