# Agentic FinOps with `finops-assess`

This page answers a question we hear from operators evaluating the tool: *"Is this a good base to build agentic FinOps on, like an agent that opens pull requests against our IaC repo when a finding is high-confidence?"*

The short answer is yes, and the architecture is clean *because* the tool stays read-only against the audited Microsoft tenant. This page explains the seam, what ships today, what is in flight, and the contract any agentic add-on must respect.

## What "agentic FinOps" means here

An agent that:

1. Reads the audit findings this tool produces.
2. Picks the high-confidence ones the operator has opted into.
3. Drafts a remediation in code (Terraform, Bicep, Policy-as-Code, ARM) against the operator's own IaC repository.
4. Opens a draft pull request with the finding ID, evidence hash, rule citation, and a verification checklist in the body.
5. Lets a human review and merge.
6. Lets the IaC pipeline apply the change against the audited cloud, on the operator's own approval cadence.

The agent never holds Microsoft tenant write credentials, never calls Microsoft Graph or Azure Resource Manager mutation endpoints against the audited tenant, and never auto-merges its own pull requests.

## Why `finops-assess` is a clean base

### 1. The read-only posture is a feature, not a workaround

`docs/plan.md` §1 and `.github/copilot-instructions.md` hard rule #1 require every collector to use `*.Read.All` or equivalent read scopes only. The CLI refuses to run if a credential carrying a write scope is detected. This is the architectural seam the agentic add-on builds across:

| Half | What it touches | Auth |
|---|---|---|
| **Audit half** (this tool) | Microsoft 365 / Azure / GitHub / ADO read endpoints | `*.Read.All` scopes via DefaultAzureCredential, GITHUB_TOKEN, AZURE_DEVOPS_PAT |
| **Agentic add-on** (the new layer) | Operator's own IaC repo + ticketing platform | Operator's own GitHub PAT scoped to one repo, never to the audited tenant |

The agent reads findings out of the audit half through the canonical JSON output (and through the MCP server once issue #60 ships). It never re-implements collector logic, never holds Microsoft tenant credentials, and never bypasses the audit-side scope guards.

### 2. The catalogue + rules architecture maps to remediation templates

Every rule in `data/rules/{surface}.yaml` already has an `id`, a `recommendation_template`, and structured `evidence`. Pair each rule with one or more remediation templates per IaC backend and the agent's job becomes mechanical:

```
finding (M365.UNUSED_LICENSE_30D, principal=hash:abc, sku=ENTERPRISEPACK)
  -> look up remediation template for backend=terraform
  -> render template with evidence values
  -> open draft PR against operator/infra-terraform with finding ID + evidence hash + rule citation in body
```

Templates live next to data, never embedded in Python (catalogue-is-data, hard rule #5).

### 3. Evidence-first design produces explainable PRs

Every finding carries a hash of the evidence row that triggered it. Every PR the agent opens cites that hash in the body, alongside the rule ID and a link to the rule definition. Reviewers can defend the change in code review without re-running the audit.

### 4. PII redaction by default keeps auto-opened PRs safe at scale

`Finding.principal` is a salted hash by default unless the operator explicitly opts in with `--no-pii-redaction`. PR bodies render the same hash, never the cleartext UPN. This matters because pull requests are public artefacts in many organisations and "agentic FinOps" leaks personnel data without redaction-by-default.

### 5. The §11 delivery loop is human-in-the-loop by design

`.github/copilot-instructions.md` documents a five-stage process for non-trivial work (research, rubberduck, plan, consensus, implement). Every PR the agent opens is one Stage-5 implementation against a Stage-3 plan that a human accepted. The agent never skips review. This is the same pattern the squad already uses for its own evolution; "agentic FinOps" is just the same loop applied to operator IaC instead of to this repo.

## What ships today

| Capability | Status | Evidence |
|---|---|---|
| Read-only collectors for M365 / Azure / GitHub / ADO | shipped | M4, M5, M6 milestones in `docs/plan.md` |
| Catalogue + persona + rule YAML model | shipped | 87 SKUs, 7 personas, 23 rules across four surfaces |
| Evidence-first finding output (JSON / HTML / CSV / PDF) | shipped | `src/finops_assess/reporters/` |
| PII redaction by default | shipped | Hard rule #4 in `.github/copilot-instructions.md` |
| §11 human-in-the-loop delivery loop | shipped | All 50+ merged PRs follow it |
| `finops-assess` CLI with subcommands | shipped | `validate`, `info`, `run`, `demo`, `catalog refresh`, `catalog coverage`, `collect` |

The audit half is feature-complete for the four covered surfaces. The agentic add-on is the next layer.

## What is in flight (the agentic backlog)

Tracked under epic [#57](https://github.com/martinopedal/FinOps-assessment/issues/57). The customer-priority subset for "agentic FinOps with PR opening":

| Order | Issue | What it adds |
|---|---|---|
| 1 | [#60](https://github.com/martinopedal/FinOps-assessment/issues/60) MCP server | Exposes findings via Model Context Protocol so any LLM agent (Claude, Copilot Workspace, GitHub Copilot Coding Agent, custom LangGraph) can drive the tool without shell-wrapping the CLI |
| 2 | [#61](https://github.com/martinopedal/FinOps-assessment/issues/61) Playbook reporter | Reformats findings as ServiceNow / Jira / GitHub Issues-ready JSONL payloads. Foundation for the PR drafter. |
| 3 | [#63](https://github.com/martinopedal/FinOps-assessment/issues/63) Remediation-PR drafter | Reads playbook output + per-rule remediation templates, opens draft PR against the operator's IaC repo via GitHub MCP write tools (write to operator's repo, not audited tenant) |
| 4 | [#5 in epic](https://github.com/martinopedal/FinOps-assessment/issues/57) Cross-surface principal join | "Principal X is flagged in M365 AND Azure" , agentic-surface table stakes |
| 5 | [#8 in epic](https://github.com/martinopedal/FinOps-assessment/issues/57) Counterfactual explainer | "Why did Alice get this finding when Bob did not?" , supports operator review of agent-opened PRs |
| 6 | [#10 in epic](https://github.com/martinopedal/FinOps-assessment/issues/57) Suppression-rule drafter | False-positive learning loop , operator marks an agent-opened PR as wrong, agent drafts a YAML suppression block for human review |

## The contract any agentic add-on must respect

The full contract is in [`.squad/skills/agentic-finops/SKILL.md`](../.squad/skills/agentic-finops/SKILL.md). The headlines:

1. **Never write to the audited tenant.** Ever. The agent's job is to draft what a human would do in code, not to take the action.
2. **PR drafts go to the operator's own IaC repo, not the audited tenant.** The target repository is operator-owned (`operator-corp/infra-terraform`, `operator-corp/policy-as-code`, etc.).
3. **Drafts only, never auto-merge.** The agent opens PRs in draft state by default. Operators are the merge gate.
4. **PR body schema is mandatory.** Every PR carries finding ID, rule ID with citation, evidence hash, estimated savings, verification checklist, salted-hash principal, "DO NOT MERGE without verifying X" header, and IaC backend.
5. **PII redaction at PR-render time.** Salted-hash principals only.
6. **Per-rule opt-in.** Each rule in `data/rules/` carries `allow_pr: false` default. Only opt-in rules generate PRs.
7. **Idempotency, rate limit, kill switch.** Deterministic dedup key per finding, max-PRs-per-rule-per-repo limit, operator-readable enabled flag.
8. **Drift handling.** If the IaC repo does not manage the resource a finding flags, the agent comments on the playbook output and skips opening a PR.

## What you should NOT do

- **Don't let the agent merge the IaC pull request.** It drafts; humans approve. The whole architectural advantage collapses if the agent merges its own PRs.
- **Don't let the agent write to the audited tenant.** Even "just remove this disabled-user license" is a hard no without going through the IaC layer the operator controls.
- **Don't bake remediation logic into the audit tool.** Templates live in YAML/Jinja under `data/remediation/{backend}/{rule_id}.j2`, never hard-coded in Python. This keeps the audit tool surface-agnostic and lets the operator add backends without forking the audit code.
- **Don't skip §11 stage-4 review on either the audit-tool changes OR the agent's PRs.** The same review rubric applies. Noor (or her runtime equivalent) is non-optional.

## What this means for evaluators

If you are evaluating `finops-assess` as the base for an agentic FinOps program, the question is not *"does the audit half do enough?"* (it covers the four Microsoft surfaces with 23 rules and is FOCUS-mappable per `docs/roadmap/focus-mapping.md`). The question is *"does the architectural seam fit our security posture?"* The answer is yes if your security team accepts:

- Audit credentials are read-only against the audited Microsoft tenant.
- Agent credentials are write-only against the operator's own IaC repo.
- Humans merge every IaC change.
- Findings carry full evidence so PR reviewers can defend the change.

If those four conditions are acceptable, this tool is a clean base. If your security team requires the agent to act unilaterally on the audited tenant, this tool is not the right base for that requirement; you would need a different architectural choice that this project explicitly rejects.

## Related documents

- `docs/plan.md` , source of truth for scope and milestones
- `docs/schema.md` , the finding and evidence schema the agentic add-on consumes
- `docs/rules.md` , the rule catalogue the agent maps to remediation templates
- `.squad/skills/agentic-finops/SKILL.md` , the binding contract for any agentic feature
- Epic [#57](https://github.com/martinopedal/FinOps-assessment/issues/57) , the full prioritised backlog
