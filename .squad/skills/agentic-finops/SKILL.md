---
name: "agentic-finops"
description: "Architecture contract for any feature that takes action OUTSIDE the tool's process boundary based on findings. The audit half stays read-only against the audited Microsoft tenant. Any agentic add-on writes only against the operator's own ticketing platform or IaC repo, never against the audited cloud. Applies to issue #16 (remediation-PR drafter), #11 (catalogue drift watcher when it files issues), #9 (playbook reporter when consumed by an agent), and any future agent-driven CLI subcommand."
domain: "architecture"
confidence: "high"
source: "earned"
---

## Context

This skill governs the architecture of any feature in this repo that takes action outside the tool's own process boundary based on a finding. Examples: opening a pull request against an operator's IaC repo to remediate a finding, filing a GitHub issue when catalogue prices drift, posting a Teams message with a daily finding digest. It does not govern the audit collectors (those are read-only by hard rule §1) and it does not govern derived reporters that emit local files (those are read-only output).

The contract exists because the customer ask "agentic FinOps , like opening PRs on findings" maps cleanly onto this tool only if a bright-line architectural seam is preserved: audit half read-only against the audited Microsoft tenant, agentic add-on write-side scoped to the operator's own systems, never the audited tenant.

Apply this skill when designing or implementing:

- `finops-assess remediate ...` and any future variant that drafts a PR
- a drift watcher that opens an issue when catalogue YAML diverges from a public price page
- a playbook publisher that writes JSONL into the operator's ticketing inbox
- an MCP server tool that takes any side-effect action

Do not apply this skill to:

- pure read-only collectors and reporters (those follow `docs/plan.md` §1 and the five hard rules already)
- internal agent-to-agent messaging within `.squad/`
- code that only writes local files inside the run directory

## The architectural seam

```
+----------------------------+        +----------------------------------+
| Audit half (this tool)     |        | Agentic add-on (the new layer)   |
|                            |        |                                  |
| Reads M365 / Azure /       |        | Reads findings JSON              |
| GitHub / ADO with          | ---->  | Reads operator's own IaC repo    |
| *.Read.All scopes only.    | finds  | Drafts PR against operator/infra |
|                            |        | Writes to operator ticketing     |
| Emits findings + evidence  |        | Never writes to audited tenant   |
+----------------------------+        +----------------------------------+
        read-only                            read-only on audited tenant,
                                             write-only on operator's own systems
```

The two halves communicate through the canonical findings JSON (and, once issue #60 ships, through the MCP server). The agentic add-on never re-implements collector logic, never holds Microsoft tenant credentials, and never calls Graph / ARM / GitHub-Enterprise / ADO write APIs against the audited tenant.

## Hard rules (binding on every PR that touches this surface)

### Rule 1. Never write to the audited tenant

The audited tenant is the Microsoft 365, Azure, GitHub Enterprise, or Azure DevOps environment that the audit half collected from. The agentic add-on may not call:

- Microsoft Graph write endpoints (anything not `*.Read.All`)
- Azure Resource Manager mutation operations (anything not GET / LIST)
- Azure Cost Management write operations
- GitHub Enterprise admin / billing / Copilot-seat write APIs against the audited org
- Azure DevOps user / license / project-collection mutation APIs against the audited org

Any PR template that would call these against the audited tenant is rejected at validation. The agent's job is to draft a description of the action a human would take in code, not to take the action.

### Rule 2. PR drafts go to the operator's own IaC repo, not the audited tenant

When the agentic add-on opens a pull request, the target repository is operator-owned. Examples:

- `operator-corp/infra-terraform` (the operator's Terraform repo for cloud resources)
- `operator-corp/policy-as-code` (the operator's Azure Policy or OPA repo)
- `operator-corp/m365-config` (the operator's Microsoft 365 baseline-as-code repo)

The target is never the audited tenant's GitHub Enterprise org if that org would read the PR as a change to its own configuration. Operator-owned and audited can be the same legal entity, but they must be different responsibility surfaces. If the target repo IS the audited tenant's repo, the PR must be in a branch the operator controls and the IaC pipeline must require human approval before apply.

### Rule 3. Drafts only, never auto-merge

The agent opens PRs in draft state by default. The PR description carries the finding ID, evidence hash, rule citation, and a "DO NOT MERGE without verifying X" checklist. The operator is the merge gate. The agent never calls `gh pr merge`, `gh pr ready` (without operator confirmation), or any equivalent.

### Rule 4. PR body schema is mandatory

Every PR opened by the agent carries a body that includes, at minimum:

| Field | Source | Required |
|---|---|---|
| Finding ID | `Finding.id` | yes |
| Rule ID + citation | `Finding.rule_id` + link to `data/rules/{surface}.yaml` | yes |
| Evidence hash | `sha256` of the evidence row that triggered the finding | yes |
| Estimated savings | `Finding.estimated_monthly_savings_usd` (if known) | yes |
| Verification checklist | per-rule checklist from the playbook template | yes |
| Salted-hash principal | the same hash the JSON reporter emitted (never the cleartext UPN) | yes |
| "DO NOT MERGE without verifying X" header | per-rule warning text | yes |
| IaC backend | `terraform` / `bicep` / `policy` / `arm` | yes |

A PR body that omits any required field fails the agent's local validation and is not opened.

### Rule 5. PII redaction at PR-render time

The PR body renders only salted-hash principals, never cleartext UPNs, email addresses, or display names. This is a separate redaction pass from the JSON reporter's redaction, run at the moment the PR body string is assembled. `--no-pii-redaction` is per-PR opt-in via an explicit flag; it is never a service-level default and never an environment variable.

### Rule 6. Per-rule opt-in (allow_pr default false)

Each rule in `data/rules/{surface}.yaml` carries an `allow_pr: false` default. Only rules where the operator has explicitly added `allow_pr: true` ever generate PRs. This prevents the agent from drafting PRs for findings the operator considers compliance-sensitive (shared mailboxes on legal hold, break-glass accounts, eDiscovery custodians, service accounts with intentional staleness).

### Rule 7. Idempotency

The agent computes a deterministic key per finding (typically `sha256(rule_id + principal_hash + resource_id)`) and refuses to open a second PR for the same key while a prior PR is still open or merged within the last 30 days. The deduplication store is operator-supplied (a small SQLite file or a tag on the existing PRs).

### Rule 8. Rate limit and kill switch

The agent enforces a configurable rate limit (default: max 5 open PRs per rule per repo) to prevent cascading wrong drafts. The operator config carries a kill switch (`enabled: false`) that the agent reads on every run; setting it to `false` immediately stops new PRs without redeployment.

### Rule 9. Drift handling

If the IaC repo does not manage the resource the finding flags (drift), the agent does not open a PR. It emits a finding-level comment on the most recent run's playbook output noting "no IaC owner found, drift suspected". The operator decides whether to onboard the resource into IaC before the agent retries.

## Validation gates (binding on every PR that touches this surface)

A PR that introduces or modifies the agentic add-on must pass:

1. `finops-assess validate` , catalogue, personas, rules schema unchanged.
2. The standard `ruff check`, `ruff format --check`, `mypy src`, `pytest`.
3. A new gate `tests/test_agentic_posture.py` , the test suite that:
   - Asserts no remediation template references a Microsoft tenant write API.
   - Asserts every new template renders a PR body that satisfies the Rule 4 schema.
   - Asserts every rule with `allow_pr: true` has at least one remediation template across the supported backends.
4. The standard §11 stage-4 Noor adversarial review, with explicit posture-check on the seven hard rules from this skill.

## Out-of-scope behaviours (red lines)

- Auto-merging the IaC PR. The agent drafts; humans approve.
- Writing to the audited tenant. Ever.
- Cross-repo PR drafts (the agent picks ONE target repo per invocation).
- Multi-resource bulk actions in a single PR (one PR per resource by default, configurable per rule).
- Publishing remediation templates that would call destructive operations (`terraform destroy`, `az resource delete`, `Remove-MgUser`) against the audited tenant. Even in IaC-as-code form. Even in a draft PR. The agent's job is to right-size, not to delete.
- Acting on findings where the persona file maps the principal to a `compliance_hold` or `legal_hold` flag. The agent skips these unconditionally.

## Why this skill exists

The customer ask of 2026-05-13 ("a customer asked for agentic finops, like opening PRs on findings if needed etc, is this a good base to build as part of, or based on this tool?") could only be answered "yes" because the tool's read-only-by-construction posture (`docs/plan.md` §1, `.github/copilot-instructions.md` hard rule #1) creates the architectural seam this skill formalises. Without the seam, "agentic FinOps" collapses into "the agent both observes and mutates the audited system", which is the failure mode every enterprise security review rejects.

This skill IS the contract that the future remediation-PR drafter (issue #63) must satisfy. Earlier features that already fit the seam in spirit (issue #61 playbook reporter, issue #60 MCP server) inherit the relevant subset (Rule 4 PR body schema for #61, Rule 5 PII redaction for #60).

## Citations

- Customer ask and Coordinator strategic answer: chat thread on 2026-05-13 (preserved in epic #57 body).
- `docs/plan.md` §1 hard rules and `docs/plan.md` §10 triage advisory boundary.
- `.github/copilot-instructions.md` five hard rules.
- `.squad/decisions.md` 2026-05-12 derived-views architectural primitive (sets the precedent for "feature reads canonical artefacts, never extends them").
- Issue #57 (epic), #60 (MCP server), #61 (playbook reporter), #63 (remediation-PR drafter, this skill's primary client).
- FinOps Foundation framework: https://www.finops.org/framework/ (the policy environment this seam respects).
