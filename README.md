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

```bash
python -m pip install -e ".[dev]"

# Validate the bundled catalogue, personas, and rules.
finops-assess validate
# or, equivalently:
python -m finops_assess.catalog validate
python -m finops_assess.rules   validate

# Run the test suite.
pytest
```

The collectors and rule engine arrive in M2; today's scaffold
exercises the data model and validation pipeline end-to-end.

## License

MIT — see [`LICENSE`](LICENSE).

## Credits

License feature taxonomy is informed by **Aaron Dinnage's M365 Maps**
([m365maps.com](https://m365maps.com/)). We link to and credit the source;
we do not redistribute the diagrams.
