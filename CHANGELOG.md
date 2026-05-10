# Changelog

All notable changes to `finops-assess` are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project follows semantic versioning once it reaches a tagged
release.

## Unreleased

### Added

- User-facing guide (`docs/user-guide.md`) showing what the tool delivers,
  with report previews, CLI visuals, worked over-licensed examples drawn from
  the deterministic demo report, and an explicit note on current under-licensed
  scope.
- `finops-assess triage`, an advisory subcommand that reads an existing
  read-only JSON report and emits stable triage JSON/CSV artefacts while
  preserving source PII redaction. GitHub Copilot SDK/CLI helper discovery is
  explicit opt-in and gracefully skips when unavailable.
- Future-plan docs for GitHub Copilot-assisted triage and optional FinOps Hubs
  linkage, plus contributor guidance requiring docs updates with every PR.
- A read-only FinOps Hubs export/import design boundary that keeps Hubs
  optional, file-based, and operator controlled until a separate connector is
  reviewed.
- Exploratory frontier roadmap docs for FinOps Toolkit / FOCUS / Hubs alignment,
  Azure pricing intelligence, agreement discounts, commitments, SKU-mix reviews,
  data-collection frontiers, practice-review outputs, optional Copilot / Azure
  MCP assistance, and draft local operator skills.
- Exploratory FOCUS 1.2 correlation mapping (`docs/roadmap/focus-mapping.md`)
  documenting how today's `Finding` and `run` fields line up with FOCUS columns
  for operator-side correlation against an existing FinOps Toolkit / Hubs
  dataset. Docs-only; no exporter, schema, or collector changes.

## Shipped milestones

These items track the original delivery roadmap. Each is shipped on
`main` and is the cumulative state of the tool before the first
tagged release.

| ID | Deliverable | PR |
|----|-------------|----|
| M0 | Repo scaffold and the original plan | #1 |
| M1 | License catalogue YAML (87 SKUs) | #2 |
| M2 | CSV collector, persona engine, and the first 23 savings rules | #3 |
| M3 | HTML and JSON report, demo workflow, PowerShell wrapper | #4 |
| M4 | Microsoft Graph live collector with OIDC federated auth | #9 |
| M5 | Azure Cost Management collector | #9 |
| M6 | GitHub and Azure DevOps collectors | #9 |
| M7 | PDF executive report (WeasyPrint, deterministic build) | #7 |
| Bonus | Flat-CSV findings reporter for Excel pivots | #10 |

All milestones are `✅` shipped.
