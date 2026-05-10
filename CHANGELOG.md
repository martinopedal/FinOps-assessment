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
