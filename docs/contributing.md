# Contributing

This document is for people who want to change `finops-assess` itself,
review pull requests, or operate the repository. **If you only want to
run the tool, you do not need anything below.** Start from the project
[README](../README.md).

Release history lives in [`CHANGELOG.md`](../CHANGELOG.md).

## Where to start

1. Read the [plan](plan.md). It is the source of truth for scope,
   architecture, the data contract, security posture, and the per-step
   delivery process.
2. Read [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
   for the rules that apply to every change.
3. Read the section on the [Squad team](#squad-team) below to see who
   owns which surface.

## Validation gates

Run before opening a pull request:

```bash
finops-assess validate
ruff check . && ruff format --check .
mypy src
pytest
python scripts/generate_docs.py --check
```

CI runs the same gates on Python 3.11 and 3.12 across `ubuntu-latest`,
`windows-latest`, and `macos-latest`. Do not merge red.

## Squad team

The repo runs on [Squad](https://github.com/bradygaster/squad)
(`@bradygaster/squad-cli`). Squad gives the project a repo-native team
of AI agents that pick up GitHub issues by label and follow the
five-stage delivery loop documented in the [plan](plan.md).

Full charters live under `.squad/agents/{name}/charter.md`.

| Member | Role | Issue label |
|--------|------|-------------|
| **Maya** | Lead and FinOps PM (triage, plan sign-off) | `squad:lead` |
| **Priya** | M365, Entra, EMS, Defender, Purview, Power Platform | `squad:m365-specialist` |
| **Diego** | Azure compute, storage, SQL, Cost Management | `squad:azure-specialist` |
| **Sam** | GitHub and Azure DevOps | `squad:devsurfaces-specialist` |
| **Noor** | Security and compliance reviewer (adversarial pass) | `squad:security-reviewer` |
| **Yuki** | Tester, quality, CI matrix | `squad:tester` |
| **Scribe** | Decisions and history log (auto, never routed) | (none) |
| **`@copilot`** | Async, well-defined work matching its green capability profile | `squad:copilot` |

How to delegate work:

1. Open an issue using `.github/ISSUE_TEMPLATE/squad-task.yml`. The
   template applies the `squad` label automatically.
2. The squad workflows (under `.github/workflows/squad-*.yml`) sync
   labels from `.squad/team.md` and notify members when their
   `squad:{member}` label is applied.
3. Maya triages within one working day, applying one `squad:{member}`
   label and a green / yellow / red fit comment for `@copilot`.
4. The named member picks the issue up and works through the
   delivery loop in [plan.md](plan.md).

To run the squad CLI locally (Node.js 20 or newer):

```bash
npm install -g @bradygaster/squad-cli
squad status        # show which member is active
squad triage        # scan the inbox and route untriaged issues
```

## Repository layout

```
docs/
  contributing.md          # this file
  plan.md                  # architecture, design, delivery loop
  rules.md                 # auto-generated rule reference (consumer-facing)
  schema.md                # data and report contract reference
src/finops_assess/         # Python package (models, catalog, rules, CLI)
  data/                    # packaged mirror of `data/` for non-editable installs
data/
  catalog/                 # SKU catalogue YAML
    m365/   azure/   github/   ado/
  personas.yaml            # persona model
  rules/                   # savings-rule definitions per surface
tests/                     # pytest loader, engine, and CLI smoke tests
.github/workflows/ci.yml   # lint, type-check, tests, YAML validation
.squad/                    # Squad multi-agent team (charters, routing)
.github/ISSUE_TEMPLATE/    # squad-task issue form
```

The repo-root `data/` tree is the authoring location. `src/finops_assess/data/`
is a byte-identical packaged mirror so `finops-assess validate`, `run`,
and `demo` work after a non-editable wheel install. Tests fail if the
two trees drift.

## Maintainer hardening checklist

Keep the following enabled on the repository:

- Branch protection on `main` requiring CI to pass and at least one review.
- Secret scanning with push protection.
- Dependabot for `pip` and `github-actions` ecosystems
  (`.github/dependabot.yml`).
- CodeQL on the Python package (run via the `parallel_validation` tool
  gate documented in `.github/copilot-instructions.md` and on a
  scheduled CI cadence).
- Required signed commits where supported by all contributors.

## Security-relevant files

| Path | Why it matters |
|------|----------------|
| `src/finops_assess/collectors/*.py` | Only place that holds credentials in memory. Any change is a yellow or red review per `.squad/team.md`. |
| `src/finops_assess/engine.py` (`RuleContext.redact`) | The single PII-redaction primitive. |
| `src/finops_assess/reporters/csv_reporter.py` | Sanitises CSV cells against formula injection. |
| `.github/workflows/*.yml` | Workflow permissions are scoped explicitly; new workflows must use the least permissions needed. |
| `data/` | No secrets, no copyrighted material. |
