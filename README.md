# FinOps-assessment

A read-only assessment tool that audits licensing and cost across the
**Microsoft ecosystem** — Microsoft 365, Entra ID / EMS, Defender, Purview,
Power Platform, Azure, **GitHub**, and **Azure DevOps** — and emits
right-sizing and cost-saving recommendations.

> 🚧 Scaffolding in progress. The comprehensive plan, license catalogue
> (seeded from [Aaron Dinnage's M365 Maps](https://m365maps.com/)),
> persona model, and savings-rule engine are being authored in the
> first PR. See `docs/plan.md` once that PR lands.

## Status

| Milestone | State |
|---|---|
| M0 — Repo scaffold + comprehensive plan | ✅ shipped (PR #1) |
| M1 — License catalogue YAML (87 SKUs) | ✅ shipped (PR #2) |
| M2 — CSV collector + persona engine + core savings rules (12) | ✅ shipped (PR #3) |
| M3 — HTML/JSON report + demo workflow + PowerShell wrapper | **this PR** |
| M4 — Microsoft Graph live collector (OIDC) | pending |
| M5 — Azure Cost Management collector | pending |
| M6 — GitHub + Azure DevOps collectors | pending |
| M7 — PDF executive report | pending |

## Repository layout

```
docs/plan.md              # comprehensive plan (M365 + Azure + GitHub + ADO)
src/finops_assess/        # Python package (models, catalog, rules, CLI)
data/
  catalog/                # SKU catalogue YAML (~50 entries, M0)
    m365/   azure/   github/   ado/
  personas.yaml           # persona model
  rules/                  # savings-rule skeletons per surface
tests/                    # pytest loader + CLI smoke tests
.github/workflows/ci.yml  # lint + type-check + tests + YAML validation
.squad/                   # Squad multi-agent team (charters, routing, decisions)
.github/ISSUE_TEMPLATE/   # roadmap-milestone & squad-task issue forms
```

## Squad — multi-agent delivery

This repo runs on [Squad](https://github.com/bradygaster/squad)
(`@bradygaster/squad-cli`). Squad gives us a repo-native team of AI
agents that pick up GitHub issues by label and follow the §11
five-stage delivery loop documented in `docs/plan.md`.

The team (full charters under `.squad/agents/{name}/charter.md`):

| Member | Role | Issue label |
|--------|------|-------------|
| **Maya** | Lead / FinOps PM (triage, plan sign-off) | `squad:lead` |
| **Priya** | M365 / Entra / EMS / Defender / Purview / Power Platform | `squad:m365-specialist` |
| **Diego** | Azure compute / storage / SQL / Cost Management | `squad:azure-specialist` |
| **Sam** | GitHub & Azure DevOps | `squad:devsurfaces-specialist` |
| **Noor** | Security & compliance reviewer (adversarial pass) | `squad:security-reviewer` |
| **Yuki** | Tester / quality / CI matrix | `squad:tester` |
| **Scribe** | Decisions & history log | (auto, never routed) |
| **`@copilot`** | Async, well-defined work matching its 🟢 capability profile | `squad:copilot` |

How to delegate work:

1. Open an issue using `.github/ISSUE_TEMPLATE/milestone.yml` (for an
   M1–M7 roadmap item) or `squad-task.yml` (for a smaller task).
   Both apply the `squad` label automatically.
2. The squad workflows (under `.github/workflows/squad-*.yml`) sync
   labels from `.squad/team.md` and notify members when their
   `squad:{member}` label is applied.
3. **Maya** triages within one working day, applying one
   `squad:{member}` label, the right `milestone:Mx` label, and a
   🟢/🟡/🔴 fit comment for `@copilot`.
4. The named member picks the issue up and works through stages 1–5
   of the delivery loop in `docs/plan.md` §11.

To run the squad CLI locally (Node.js ≥ 20):

```bash
npm install -g @bradygaster/squad-cli
squad status        # show which member is active
squad triage        # scan the inbox and route untriaged issues
```

## Quick start

The tool is a single Python package and a single CLI (`finops-assess`).
It runs identically on **Windows**, **macOS**, **Linux**, and inside
**GitHub Actions** / Azure DevOps Pipelines / any container — there is
no OS-specific code path. CI exercises every push on the full
`{ubuntu-latest, windows-latest, macos-latest} × {3.11, 3.12}` matrix
to keep it that way.

### Install (any OS)

You only need Python ≥ 3.11. Pick the one-liner for your shell:

```bash
# Linux / macOS (bash, zsh)
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

### Run

```bash
# Validate the bundled catalogue, personas, and rules.
finops-assess validate
# or, equivalently:
python -m finops_assess.catalog validate
python -m finops_assess.rules   validate

# Run the synthetic-tenant demo end-to-end (writes JSON + HTML reports).
finops-assess demo --output-dir ./demo-report

# Run against your own normalised CSVs.
finops-assess run --input ./samples --output ./report.json --format both

# Run the test suite.
pytest
```

PowerShell-native operators can use the wrapper script in `scripts/` and
keep the report flowing through a PowerShell pipeline:

```powershell
$report = ./scripts/Invoke-FinOpsAssess.ps1 -Demo -OutputDir ./out
$report.findings | Where-Object severity -eq 'high' | Format-Table
```

### Run inside a GitHub Actions workflow

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
followed by the same two `pip install` / `finops-assess` steps — no
extra agent capabilities required.

This repository ships the same demo job at
`.github/workflows/demo-report.yml`; every push to `main` (and every
manual `workflow_dispatch`) publishes the rendered HTML + JSON reports
as the **`finops-assess-demo-report`** workflow artifact.

## License

MIT — see [`LICENSE`](LICENSE).

## Credits

License feature taxonomy is informed by **Aaron Dinnage's M365 Maps**
([m365maps.com](https://m365maps.com/)). We link to and credit the source;
we do not redistribute the diagrams.
