# Copilot instructions for `martinopedal/FinOps-assessment`

These instructions apply to every Copilot-assisted change in this repo
(coding agent, chat, and PR review). Keep them short, concrete, and
**aligned with `docs/plan.md`** — that document is the source of truth
for scope, milestones, and the data contract.

## What this project is

A **read-only** FinOps assessment tool that audits licensing, identity,
usage, and cost across the **Microsoft ecosystem**: Microsoft 365
(incl. Entra/EMS/Defender/Purview/Power Platform), Azure, **GitHub**,
and **Azure DevOps**. It emits right-sizing and savings findings with
evidence — it never mutates the systems it inspects.

## Hard rules (non-negotiable)

1. **Read-only by construction.**
   - Never request, accept, or document a write/`*.ReadWrite.*`/admin
     scope. Microsoft Graph, ARM, GitHub, and Azure DevOps collectors
     must use read-only scopes only.
   - The CLI must refuse to run if a credential carrying a write scope
     is detected (see `docs/plan.md` §9).
2. **No secrets in the repo.** Live-mode auth is **OIDC federated
   credentials** in GitHub Actions; never add long-lived tokens, PATs,
   client secrets, or tenant IDs to source. Use `${{ secrets.* }}` or
   federated identity exclusively.
3. **No redistribution of third-party copyrighted material.** Aaron
   Dinnage's M365 Maps diagrams, Microsoft pricing pages, etc. may be
   **linked and credited** but never copied into the repo. The feature
   taxonomy we derive from them is our own paraphrase.
4. **PII redaction on by default.** Any user-identifying field in a
   report must be salted-hashed unless the operator opts in with
   `--no-pii-redaction`.
5. **Catalogue is data, not code.** SKUs, features, prices, and bundle
   relationships live in versioned YAML under `data/catalog/`. Rules
   reference catalogue entries by `id`. Do not hard-code SKU strings
   in Python.

## Tech stack & conventions

- **Language: Python ≥ 3.11.** Cross-platform (Linux/macOS/Windows),
  rich SDK coverage for Graph/Azure/GitHub/ADO, and the same engine can
  run locally, in CI, and in containers. CI exercises every push on
  the full `{ubuntu-latest, windows-latest, macos-latest} × {3.11,
  3.12}` matrix — **never introduce OS-specific code paths, paths
  built with `os.sep`/`\\`, or shell-only invocations that wouldn't
  work in `cmd.exe` and `pwsh` and `bash`**. Use `pathlib.Path`,
  `subprocess` with a list-form `args`, and `importlib.resources` for
  bundled data. Do not introduce a second runtime (PowerShell, Node,
  Go) unless `docs/plan.md` is updated to justify it.
- **Type-checked**: `mypy --strict` over `src/`. New code must pass.
- **Linted/formatted**: `ruff check` and `ruff format` (line length
  100, target `py311`). New code must pass both.
- **Schema-first**: pydantic v2 models with `extra="forbid"`. Add new
  fields to `src/finops_assess/models.py` before adding them to YAML.
- **Tests**: `pytest`. Every new loader, rule, or collector ships with
  a unit test. Loader/rule changes must keep `tests/test_loaders.py`
  green.
- **CLI**: Click; subcommands live in `src/finops_assess/cli.py`.

## Repository layout (authoritative)

```
docs/plan.md              # plan + architecture + milestones
src/finops_assess/
  models.py               # pydantic models (extra="forbid")
  catalog.py              # catalog YAML loader + validator
  rules.py                # persona + rule YAML loader + validator
  cli.py                  # `finops-assess` entry point
data/
  catalog/{m365,azure,github,ado}/*.yaml
  personas.yaml
  rules/{m365,azure,github,ado}.yaml
tests/
.github/workflows/ci.yml  # ruff + mypy + pytest + YAML validation
```

When the package is **installed** (not editable), data files must
still be discoverable. Prefer `importlib.resources` over filesystem
path arithmetic when reading bundled YAML.

## Adding or changing data

- **New SKU**: add to the right `data/catalog/<surface>/*.yaml`. Required
  fields: `id`, `display_name`, `family`, `cloud`. Provide
  `list_price_usd_month` only if you have a citation; otherwise leave
  `null`. Always set `source_url` to a public, non-copyrighted page.
- **Bundle composition**: use `includes:` for child SKU IDs and
  `successor_of:` for upgrade-path predecessors. Successor IDs must
  refer to other catalog entries (loader enforces this).
- **Feature tags**: re-use the existing controlled vocabulary
  (`mailbox.*`, `office.*`, `teams.*`, `intune.*`, `entra.*`,
  `defender.*`, `purview.*`, `power.*`, `copilot.*`, `vm.*`, `disk.*`,
  `sql.*`, `logs.*`, `network.*`, `github.*`, `ado.*`, `ghas.*`).
  Coin a new tag only when nothing existing fits, and document it in
  the PR description.
- **New rule**: add a YAML entry to `data/rules/<surface>.yaml` with
  `id`, `surface`, `severity`, `summary`, `recommendation_template`.
  Rule IDs follow `SURFACE.SHORT_NAME`, screaming-snake-case (e.g.,
  `M365.UNUSED_LICENSE_30D`). When you add a rule, also reference its
  ID in `docs/plan.md` §6 — keep the plan and the YAML in sync.
- **Recommendation wording must be conservative.** A rule's
  `recommendation_template` should phrase the action as *"consider"*
  or *"verify and then…"* rather than an absolute "remove", because
  signals like activity counts can have legitimate exceptions
  (compliance holds on shared mailboxes, eDiscovery custodians,
  break-glass accounts, etc.).

## Validation gates (run before opening a PR)

```bash
finops-assess validate          # catalog + personas + rules schema
ruff check . && ruff format --check .
mypy src
pytest
```

CI runs the same gates on Python 3.11 and 3.12. Don't merge red.

## Out of scope (don't add without an issue)

- Mutation / remediation paths.
- Non-Microsoft SaaS audits (AWS, GCP, Workday, etc.).
- On-prem CAL / perpetual-licensing reconciliation.
- Bundling third-party diagrams or proprietary pricing tables.

## Style nits

- Imports ordered by `ruff` (`I` rule).
- Prefer `pathlib.Path` over `os.path`.
- Prefer `importlib.resources.files()` for packaged data over
  `__file__`-relative paths.
- Docstrings on every public symbol; one-line summary + optional body.
- No `print()` in library code — use `click.echo` in CLI, `logging`
  elsewhere.

## Per-step delivery process (multi-agent)

Every milestone — and every non-trivial sub-task within one — is
delivered through the five-stage loop documented in `docs/plan.md`
§11. Copilot agents working on this repo **must** follow it:

1. **Research** (`explore` agent, parallel-safe; Haiku). Produce a short
   brief: relevant API surfaces, SKU IDs, prior-art links, public
   docs, identified unknowns. Read-only — no edits.
2. **Rubberduck** (`general-purpose`; Sonnet). Plain-English walkthrough
   of the proposed approach against the brief: what could go wrong,
   edge cases, false-positive risks, security implications, alternatives
   considered.
3. **Plan** (`general-purpose`; **Opus 4.7 — always**). Concrete
   checklist of file-level changes (paths, schemas, rule IDs), tests to
   add, and acceptance criteria — small enough to fit in one PR. Posted
   into the PR description **before** any edits. Plan owns the most
   consequential reasoning of the loop; we never trade capability for
   cost here. If Opus 4.7 is unavailable, **block** stage 3 rather than
   downgrade.
4. **Consensus**. Human reviewer signs off on the plan; an adversarial
   `general-purpose` pass (**Opus 4.7**) steelmans the case against
   shipping it. Disagreements are resolved by amending the plan, not by
   silently overriding it. "No objections within X" never counts as
   consensus for security-relevant or schema-changing work.
5. **Implement** (`general-purpose`, Sonnet by default; Opus 4.7 if the
   plan calls for it; `task` Haiku for narrow mechanical edits).
   Code/data/doc changes + tests + a `parallel_validation` gate (code
   review + CodeQL) before opening the PR.

Stages 1–3 produce artefacts that live in the PR description (or in
`docs/decisions/` for cross-PR decisions) so future contributors can
reconstruct *why* a choice was made, not just *what* changed.

When an agent fails or hits a dead end, the next agent must restate
the brief from stage 1 in its own words before proceeding — this
catches misunderstandings early and prevents single-agent tunnel
vision. Agents are stateless across invocations; the PR is the shared
memory.

## Squad orchestration

This repo is initialised with [Squad](https://github.com/bradygaster/squad)
(`@bradygaster/squad-cli`). Squad provides repo-native, multi-agent
orchestration via labelled GitHub issues **and pull requests**, all
running on cloud agents (GitHub Actions). The five-stage delivery loop
above maps onto squad members; the squad workflows route work on the
relevant `squad:{member}` label event.

The cloud-agent surface:

- `squad-triage.yml` — fires on `issues: labeled` with the `squad`
  label; Lead triages and applies one `squad:{member}` label.
- `squad-issue-assign.yml` — fires on `issues: labeled` with any
  `squad:{member}` label; posts routing acknowledgment + (if
  `squad:copilot` and a PAT is configured) auto-assigns `@copilot`.
- `squad-pr-route.yml` — fires on `pull_request_target: labeled`;
  mirrors the issue-assign behaviour for PRs so labelling a PR with
  `squad:{member}` posts the same routing acknowledgment.
- `sync-squad-labels.yml` — fires on push when `.squad/team.md`
  changes; ensures every `squad:{member}` label exists in the repo.

When picking up an issue **or PR review** autonomously as `@copilot`:

1. Read `.squad/team.md` for the team roster and your capability
   profile (🟢 / 🟡 / 🔴).
2. Read `.squad/routing.md` for routing rules.
3. If the issue carries a `squad:{member}` label, read that member's
   charter at `.squad/agents/{member}/charter.md` and work in that
   member's voice and within their boundaries.
4. Use the squad branch convention `squad/{issue-number}-{slug}`.
5. Reference the issue in the PR (`Closes #N`) and, if the task was
   flagged 🟡, add the standard "needs review" banner to the PR body.
6. If you make a decision other members should know, drop a note at
   `.squad/decisions/inbox/copilot-{slug}.md`; the Scribe will merge
   it into `.squad/decisions.md`.

🔴 (not-suitable) issues — security-sensitive work, schema changes,
catalogue-pricing edits, and anything that would relax the read-only
posture — must not be picked up autonomously. Comment on the issue
asking the Lead to reassign to a human squad member.
