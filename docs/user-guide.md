# What `finops-assess` gives you

`finops-assess` turns read-only Microsoft ecosystem inventory and usage data into
right-sizing findings with evidence. It is not just a how-to-use CLI: the output is
a review pack for license owners, FinOps analysts, and platform admins.

> Rule IDs and demo numbers on this page are quoted from the committed
> deterministic demo reports in [`examples/`](../examples/). If the demo data or
> rules change, update this guide alongside the regenerated examples.

## At a glance

A completed run gives you:

- an **executive HTML report** grouped by surface, severity, persona, current SKU,
  recommended SKU, savings, and evidence;
- a **canonical JSON report** for automation and long-term evidence storage;
- a **flat CSV export** for Excel, Sheets, Power BI, or chargeback workflows;
- an optional **PDF** rendered from the same report for sign-off packs.

![Preview of the synthetic demo HTML report with summary cards and sample findings.](images/report-preview.svg)

## The deterministic demo, end-to-end

The bundled demo uses a synthetic tenant and writes the same report shapes a real
CSV or live-collector run writes:

```console
$ finops-assess demo --output-dir ./demo-report
OK , demo run produced 34 findings across 23 rules.
  JSON: demo-report/demo-report.json
  HTML: demo-report/demo-report.html
  CSV:  demo-report/demo-report.csv
```

Committed examples are available without installing the package:

- [`examples/demo-report.html`](../examples/demo-report.html) , self-contained,
  print-friendly report preview.
- [`examples/demo-report.json`](../examples/demo-report.json) , full structured
  report with summary, findings, and evidence.
- [`examples/demo-report.csv`](../examples/demo-report.csv) , one row per finding
  for pivots and exports.

The sample input files under [`samples/`](../samples/) are synthetic illustrative
inputs using reserved `*.example` addresses. The committed report examples keep
PII redaction on, so principals appear as salted `sha256:...` identifiers.
`--no-pii-redaction` is an explicit operator opt-in.

## CLI visual

![Animated terminal transcript showing validate and demo commands.](images/cli-demo.svg)

The normal flow is intentionally small: validate the local catalogue and rules,
then run either the synthetic demo, normalized CSVs, or live read-only collectors.

```console
$ finops-assess validate
OK , catalog: 87 SKUs, personas: 7, rules: 23

$ finops-assess demo --output-dir ./demo-report
OK , demo run produced 34 findings across 23 rules.
  JSON: demo-report/demo-report.json
  HTML: demo-report/demo-report.html
  CSV:  demo-report/demo-report.csv
```

## Report pipeline

![Read-only pipeline from collectors to persona engine to rules engine to JSON, HTML, CSV, and PDF reports.](images/pipeline.svg)

The same normalized dataset powers every output format. Live collectors and CSV
inputs feed the persona engine, the rules engine emits evidence-backed findings,
and reporters shape those findings for different audiences.

## Worked examples: over-licensed and idle spend

`finops-assess` never mutates the systems it inspects. Treat every finding as a
read-only suggestion to verify before acting; compliance holds, eDiscovery
custodians, break-glass accounts, shared mailboxes, and service principals can
all be legitimate exceptions.

### Persona mismatch: E5 assigned to a frontline persona

Rule: `M365.OVER_LICENSED_VS_PERSONA`

The demo includes a principal classified as `frontline_worker` with `SPE_E5`.
The evidence says the persona only requires `intune.mam`, `mailbox.2gb`,
`office.web`, and `teams.basic`, while E5 supplies a much larger feature set.
The report recommends considering `SPE_F3`, with an estimated monthly savings of
`$49.00` for that assignment.

What this gives you: a conversation-ready exception list for license owners ,
not just "unused," but "current SKU exceeds the persona's required features."

### Unused premium capabilities: E5 features not exercised

Rule: `M365.E5_FEATURES_UNUSED`

The demo flags E5 users with no Defender for Office 365 P2, Purview DLP/IP, or
Entra P2 risk-policy activity in the 90-day window. The recommended review path
is to consider stepping down to E3 plus targeted add-ons when business context
confirms the premium controls are not needed.

What this gives you: a targeted review queue for the most expensive bundles,
with evidence about which premium signals were checked.

### Duplicate bundle: standalone SKU already included

Rule: `M365.DUPLICATE_BUNDLE`

The demo finds an account with `SPE_E3` and the standalone
`SHAREPOINTENTERPRISE` assignment, even though E3 already includes that
capability. The CSV export estimates `$10.00` monthly savings for the duplicate
assignment.

What this gives you: deterministic cleanup candidates for bundle overlap that
are easy to pivot by SKU, department, or tenant segment.

### Inactive developer-surface seats

Rules: `GH.COPILOT_INACTIVE_30D`, `ADO.STAKEHOLDER_ELIGIBLE`

The demo also covers non-M365 spend. It flags a GitHub Copilot Business seat
with zero accepted suggestions in 30 days (`$19.00` monthly savings in the CSV)
and an Azure DevOps Basic user whose only recent activity is reading boards and
commenting (`$6.00` monthly savings in the CSV).

What this gives you: one cross-surface view of Microsoft ecosystem SaaS spend,
not separate spreadsheets for M365, GitHub, and Azure DevOps.

### Azure idle and oversized resources

Rules: `AZ.IDLE_VM_14D`, `AZ.OVERSIZED_VM`, `AZ.UNATTACHED_DISK`,
`AZ.PUBLIC_IP_UNATTACHED`, `AZ.RESERVATION_UNDERUTILIZED`,
`AZ.LOG_ANALYTICS_OVERINGEST`, `AZ.DEV_TEST_SUB_MISMATCH`

The Azure rules turn resource metrics and cost signals into the same finding
shape as license issues. The demo includes idle compute, unattached resources,
reservation underutilization, Log Analytics over-ingest, and Dev/Test mismatch
examples.

What this gives you: infrastructure and seat recommendations in one report,
with consistent severity, confidence, savings, and evidence fields.

## Advisory triage pack

After a JSON report exists, generate a schema-versioned analyst queue:

```console
$ finops-assess triage --input demo-report/demo-report.json --output-dir ./triage
OK , wrote advisory triage JSON to triage/triage.json
OK , wrote advisory triage CSV to triage/triage.csv
Advisory triage items: 34
```

The triage pack preserves the source report's PII posture. If the report used
default redaction, principals remain salted hashes; if an operator explicitly
ran with `--no-pii-redaction`, triage passes that through and records
`pii_redaction: false`.

The command is template-based and makes no network calls by default. Teams
with GitHub Copilot can explicitly opt in to helper discovery:

```console
$ finops-assess triage --input report.json --enable-copilot-helper
```

This follows the azure-analyzer pattern: Copilot assistance is optional,
disabled by default, and must not be used to take remediation actions, request
write scopes, or de-redact principals. The current implementation records the
available helper mode (`sdk`, `cli`, or `unavailable`) while still emitting the
stable local JSON/CSV artefact. Analysts remain responsible for verification.

### Using triage artefacts with FinOps Hubs

The triage JSON/CSV files are intentionally file-based, so teams that already
operate FinOps Hubs can review them locally and then place approved artefacts in
their own Hubs landing zone or ingestion workflow. Useful correlation fields
include `finding_ref`, `rule_id`, `surface`, redacted `principal`,
`current_sku`, `recommended_sku`, `estimated_monthly_savings_usd`, and the
source report's run metadata.

This is an export/import design boundary, not a connector. `finops-assess` does
not upload to FinOps Hubs, deploy pipelines, mutate storage, or require Hubs to
run. Any future live connector should be tracked as a separate reviewed change
with explicit data-flow documentation.

## Playbook / ticket export

`finops-assess run --format playbook` emits a structured JSONL file — one line per
finding — designed to be loaded directly into ServiceNow, Jira, GitHub Issues, or any
ticket-creation pipeline. Each row is a self-contained playbook ticket with a stable
`ticket_key`, rich `description` / `remediation_steps` / `verification_checklist` /
`references` fields rendered from a per-rule Jinja2 template, and an `adapter_hints`
block that pre-populates common ticket fields (priority, category, assignment group).

```console
$ finops-assess run \
    --input ./samples \
    --format playbook \
    --playbook-output ./playbook-export.jsonl
Wrote 34 playbook tickets to playbook-export.jsonl
Manifest: playbook-export.jsonl.manifest.json
```

The output is two files:

- `<output>.jsonl` — one JSON object per line; each row validates against
  `src/finops_assess/schemas/playbook_row.schema.json`.
- `<output>.jsonl.manifest.json` — sidecar contract with SHA-256 of the JSONL,
  row count, PII handling mode, and `ticket_key_stability_by_surface`.
  **The manifest is the canonical readiness marker.** If it is absent or its
  `output_artifacts.jsonl_sha256` does not match the JSONL on disk, treat the
  JSONL as an orphan and do not consume it.

Both files honour `SOURCE_DATE_EPOCH` for byte-deterministic builds.

### Ticket key stability

- **Azure findings** have `stable` ticket keys. The principal is an ARM resource ID
  that does not change with the PII redaction salt, so the same finding always maps
  to the same ticket.
- **M365, GitHub, and ADO findings** with PII redaction on have `per_run` ticket keys.
  The principal is a salted hash that changes between runs with different salts. Use
  the `evidence_ref` field to correlate across runs.

### Orphan cleanup

Interrupted or failed writes can leave JSONL files on disk without a valid manifest.
Use `--cleanup-orphans` to remove them before a new run:

```console
$ finops-assess run \
    --input ./samples \
    --format playbook \
    --playbook-output ./playbook-export.jsonl \
    --cleanup-orphans
Cleaned up 1 orphaned JSONL file(s).
Wrote 34 playbook tickets to playbook-export.jsonl
```

### PII warning

When PII redaction is on (the default), the exporter logs a warning reminding
operators that ticket descriptions may contain de-anonymised evidence strings
(resource names, tenant IDs, subscription names). Use `--skip-warnings` to suppress
this warning in automated pipelines that have already acknowledged the posture.

### Committed example

- [`examples/playbook.jsonl`](../examples/playbook.jsonl) — 34 tickets from the
  synthetic demo tenant (LF-only, `SOURCE_DATE_EPOCH=0`).
- [`examples/playbook.jsonl.manifest.json`](../examples/playbook.jsonl.manifest.json)
  — matching sidecar manifest.

## Exporting findings to a FOCUS-aligned advisory CSV

`finops-assess` can project findings onto a CSV shaped like the FinOps Foundation
FOCUS 1.3 Cost-and-Usage spec, suitable for joining to your existing FOCUS-aligned
cost dataset. The output is **advisory**, not billed consumption — see
[`docs/focus-export.md`](focus-export.md) for the full warning banner before loading.

```console
$ finops-assess export focus-aligned \
    --input demo-report/demo-report.json \
    --output ./focus-aligned.csv
Wrote 7 advisory rows to focus-aligned.csv (manifest: focus-aligned.csv.manifest.json)
```

The output is two files: `<output>.csv` (the rows) and
`<output>.csv.manifest.json` (the sidecar contract). Both honour
`SOURCE_DATE_EPOCH` for byte-deterministic builds. Azure-only in v0.5.0;
M365/GitHub/ADO ship in v0.6.0 once the stable-principal-salt feature lands.

## Under-licensed cases: current boundary

The current v0.1 ruleset is cost-right-sizing focused. It detects
**over-licensed**, duplicate, idle, inactive, and over-provisioned cases; it does
not yet ship a `*.UNDER_LICENSED_*` rule family that asserts a user or workload
lacks required capabilities.

Today, use the persona evidence to review potential under-coverage manually:

- compare each assigned persona's required features against the current SKU
  evidence in `M365.OVER_LICENSED_VS_PERSONA` findings;
- inspect low-confidence persona assignments in JSON when job title, group, and
  usage signals disagree;
- treat missing activity signals as review prompts, not automatic removal
  instructions.

If under-licensed detection is added later, it should be tracked as a separate
schema/rule change with tests and conservative wording.

## Developed capabilities shipped today

The current rule reference lists **23 implemented rules** across four surfaces:

- **Microsoft 365** , unused licenses, persona over-licensing, duplicate bundles,
  disabled users with licenses, shared mailbox licensing, guest premium seats,
  inactive Copilot for M365, and E5 premium-feature inactivity.
- **Azure** , idle VMs, unattached disks, unattached public IPs, oversized VMs,
  underutilized reservations, Log Analytics over-ingest, and Dev/Test pricing
  mismatch.
- **GitHub** , inactive enterprise seats, inactive Copilot seats, over-provisioned
  GHAS, and runner tier mismatch.
- **Azure DevOps** , inactive Basic seats, Stakeholder-eligible users,
  over-provisioned parallel jobs, and unused Test Plans seats.

Cross-cutting capabilities include the persona engine, deterministic demo data,
JSON/HTML/CSV/PDF reporters, read-only live collectors, and PII redaction on by
default.

For the authoritative current list, use [`docs/rules.md`](rules.md).

## What it will not do

- It does **not** remediate, remove, downgrade, or mutate anything.
- It does **not** request write scopes or document write-scope credentials.
- It does **not** yet provide GitHub Copilot-assisted triage for customer
  findings beyond the opt-in local helper-discovery scaffold; today the triage
  pack is deterministic and template-based.
- It does **not** yet connect findings to FinOps Hubs. The triage JSON/CSV
  contract is stable for downstream file-based workflows, but no compatibility
  claim, upload path, or connector ships yet.
- It does **not** audit non-Microsoft SaaS, on-prem CALs, or perpetual licensing.
- It does **not** redistribute third-party diagrams or proprietary pricing tables.

## Pointers

- Data contract: [`docs/schema.md`](schema.md)
- Rule reference: [`docs/rules.md`](rules.md)
- Example HTML report: [`examples/demo-report.html`](../examples/demo-report.html)
- Contributor docs: [`docs/contributing.md`](contributing.md)
