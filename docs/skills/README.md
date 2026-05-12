# Local assessment skills and runbooks

This directory is the future home for local operator skill files and runbooks. The
current contents are an exploratory index only: they help reviewers agree on what
operators need before any executable workflow, schema, or collector change is
added.

## Read-only posture

Runbooks must preserve the same guarantees as the CLI: no remediation, no uploads,
no write scopes, no long-lived secrets, and PII redaction on by default. A runbook
may describe how an operator verifies a finding, but it must not script tenant
changes.

## Draft skill inventory

| Skill / runbook | Status | Intended scope |
|---|---|---|
| Prepare CSV inputs | exploratory | Explain normalized CSV files, required columns, and data-quality checks. |
| [Run assessment](run-assessment.md) | 🟢 runbook | Walk through `finops-assess validate`, `demo`, `run`, `collect`, and `triage`. |
| Interpret M365 SKU mix | exploratory | Review M365, Entra, Copilot, security, and GSA mix findings once shipped. |
| Interpret Azure commitments | exploratory | Review RI/Savings Plan coverage and utilization once shipped. |
| Use Copilot safely | exploratory | Explain optional local assistance with redacted data and default-off helper discovery. |
| Handoff to FinOps Hubs | exploratory | Describe operator-controlled file placement into an existing Hubs landing zone. |

## Runbook authoring rules

- Mark any unimplemented command, flag, rule, or collector as `(planned)`.
- Prefer verification checklists over imperative remediation steps.
- Link to public docs; do not copy pricing tables, diagrams, or customer-specific
  agreement terms.
- Keep examples synthetic and avoid tenant IDs, PATs, secrets, UPNs, or other PII.

## What this PR does NOT change

No runbook in this directory is packaged, executed by the CLI, or treated as a
shipped feature. Future runbooks should land with the feature they describe or be
clearly marked as draft.
