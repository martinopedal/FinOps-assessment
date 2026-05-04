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
| M0 — Repo scaffold + comprehensive plan | **this PR** |
| M1 — License catalogue YAML (~50 SKUs) | pending |
| M2 — CSV collector + persona engine + core savings rules | pending |
| M3 — HTML/JSON report + demo workflow | pending |
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

# Run the test suite.
pytest
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
```

For Azure DevOps Pipelines the equivalent is `UsePythonVersion@0`
followed by the same two `pip install` / `finops-assess` steps — no
extra agent capabilities required.

The collectors and rule engine arrive in M2; today's scaffold
exercises the data model and validation pipeline end-to-end.

## License

MIT — see [`LICENSE`](LICENSE).

## Credits

License feature taxonomy is informed by **Aaron Dinnage's M365 Maps**
([m365maps.com](https://m365maps.com/)). We link to and credit the source;
we do not redistribute the diagrams.
