---
name: "project-conventions"
description: "Core conventions and patterns for this codebase"
domain: "project-conventions"
confidence: "high"
source: "codebase"
---

## Core Identity

FinOps Assessment is a **read-only** auditing tool for the Microsoft ecosystem (M365, Entra, Defender, Purview, Power Platform, Azure, GitHub, Azure DevOps). It ingests licensing, identity, usage, and cost signals to emit right-sizing and savings *recommendations* , never mutations. Every rule output must be advisory, citing the exact evidence (evidence hash + path) that produced it.

## Hard Rules (Non-Negotiable)

### Read-Only Posture by Construction

- Never request or accept write, `*.ReadWrite.*`, or admin scopes. All collectors (Microsoft Graph, ARM, GitHub, Azure DevOps) use read-only scopes only.
- CLI must refuse to run if a credential carries a write scope is detected.
- PII redaction is **on by default**: any user-identifying field in a report must be salted-hashed unless operator explicitly passes `--no-pii-redaction`.
- No OIDC-only federated auth in live mode; never commit long-lived tokens, PATs, client secrets, or tenant IDs to source.

### Catalogue as Data, Not Code

- SKUs, features, list prices, and bundle relationships live in versioned YAML under `data/catalog/`. Rules reference catalogue entries by `id`, never hard-coded SKU strings.
- New SKUs: add to `data/catalog/<surface>/*.yaml` with required fields `id`, `display_name`, `family`, `cloud`. Use `source_url` (public, non-copyrighted page only) to cite origin.
- Bundle composition via `includes:` (child SKU IDs) and `successor_of:` (upgrade-path predecessors).

### No Third-Party Copyright Redistribution

- Aaron Dinnage's M365 Maps diagrams, Microsoft pricing pages, etc. may be **linked and credited**, never copied into the repo.
- Feature taxonomy derived from external sources is our own paraphrase , maintain that separation.

## Python Toolchain

### Language & Cross-Platform Guarantee

- **Python ≥ 3.11**. CI exercises every push on `{ubuntu-latest, windows-latest, macos-latest} × {3.11, 3.12}` matrix.
- **Never introduce OS-specific code paths**, paths built with `os.sep`/`\\`, or shell-only invocations. Use `pathlib.Path`, `subprocess` with list-form `args`, and `importlib.resources` for bundled data.
- Do not introduce a second runtime (PowerShell, Node, Go) unless `docs/plan.md` is updated to justify it.

### Code Quality Gates

- **ruff**: line length 100, target `py311`. Rules: `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`, `RUF` (ignore `E501`).
- **mypy**: `--strict` over `src/`. New code must pass.
- **pydantic v2**: models with `extra="forbid"`. Add new fields to `src/finops_assess/models.py` before adding them to YAML.
- **pytest**: Every new loader, rule, or collector ships with a unit test. `tests/test_loaders.py` must remain green.

### Style Nits

- Imports ordered by ruff (`I` rule).
- Prefer `pathlib.Path` over `os.path`.
- Prefer `importlib.resources.files()` for packaged data over `__file__`-relative paths.
- Docstrings on every public symbol; one-line summary + optional body.
- **No `print()` in library code**: use `click.echo` in CLI, `logging` elsewhere.

## Where Things Live

```
data/
  catalog/{m365,azure,github,ado}/*.yaml   # SKU definitions
  personas.yaml                             # persona definitions
  rules/{m365,azure,github,ado}.yaml        # rule YAML
src/finops_assess/
  cli.py                                    # Click CLI entry point
  models.py                                 # pydantic models (extra="forbid")
  catalog.py                                # catalog loader + validator
  rules.py                                  # rules loader + validator + engine
  collectors/                               # Graph, ARM, GitHub, ADO, CSV adapters
  reporters/                                # JSON, HTML, PDF, CSV reporters
tests/
  test_loaders.py                           # golden-file tests for loaders + rules
```

## Data Model Conventions

### Rules

- **ID format**: `SURFACE.SHORT_NAME` (screaming-snake-case, e.g., `M365.UNUSED_LICENSE_30D`).
- **Recommendation wording**: phrase as *"consider"* or *"verify and then…"* rather than absolute action, because signals (activity counts) have legitimate exceptions (compliance holds, eDiscovery custodians, break-glass accounts).
- When adding a rule, reference its ID in `docs/plan.md` §6 , keep plan and YAML in sync.

### Personas

- Persona-driven sizing: the right-size question is never "is this user over-licensed?" in the abstract; it's "given this user's *persona*, are they on the cheapest SKU that still covers the features they actually use?"

## Validation Gates

All four gates must pass before opening a PR:

```bash
finops-assess validate          # catalog + personas + rules schema
ruff check . && ruff format --check .
mypy src
pytest
```

CI runs the same gates on Python 3.11 and 3.12. Don't merge red.

## Evidence-First Architecture

Every finding links back to raw rows / API responses via a **hash + path inside the evidence bundle**, so an admin can defend the call. Offline-first by default: CSV/JSON ingest path is the entry point; live collectors (Graph, ARM, Cost Management, GitHub, ADO) are thin adapters producing the same normalized schema.
