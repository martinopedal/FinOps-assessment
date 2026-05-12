# Operator runbook: Run assessment

**Purpose:** Walk an operator through the steps to execute a FinOps assessment 
against their tenant data or the bundled synthetic demo.

## Prerequisites

- **Python 3.11 or newer** installed and in your `PATH`
- **`finops-assess` package installed** (see [Quick start in README](../../README.md#quick-start))
- **Catalog and rules validated** (one-time check: `finops-assess validate`)
- For **CSV input mode**: normalised CSV files in a single directory (see 
  [Data schema reference](../schema.md) for column requirements and the 
  `samples/` directory for structure)
- For **PDF output**: optional `[pdf]` extra installed (`pip install 'finops-assess[pdf]'`)

## Step-by-step: assessment flow

### 1. Validate the catalogue and rules (optional but recommended)

Before your first assessment, verify that the bundled catalogue, personas, and 
rules are valid on your system:

```bash
finops-assess validate
```

Expected output:
```
OK — catalog: 87 SKUs, personas: 7, rules: 23
```

**Why:** This is a smoke test that the package is correctly installed and no 
local catalogue drift exists.

### 2. Choose your data source

Pick one of the following entry points:

#### 2a. Demo mode (synthetic tenant, no credentials)

To run a quick end-to-end test against the bundled synthetic tenant:

```bash
finops-assess demo --output-dir ./demo-report
```

This produces:
- `demo-report/demo-report.json` — canonical structured report
- `demo-report/demo-report.html` — executive summary and findings
- `demo-report/demo-report.csv` — flat findings table

**With PDF (requires `pip install 'finops-assess[pdf]'`):**

```bash
finops-assess demo --output-dir ./demo-report --pdf
```

#### 2b. CSV input mode (bring your own data)

Prepare a directory with normalised CSV files:
- `users.csv` — principals (users, service principals, shared mailboxes)
- `license_assignments.csv` — SKU assignments per principal
- `usage.csv` — activity/signal data (sign-in dates, feature usage)
- `azure_resources.csv` — Azure resource inventory
- `overrides.yaml` (optional) — persona overrides or exclusions

See [`docs/schema.md`](../schema.md) for exact column definitions. The 
`samples/` directory in the repo shows synthetic examples.

Then run the assessment:

```bash
finops-assess run --input ./path/to/csv/dir --output ./report.json --format both
```

This produces:
- `report.json` — canonical report
- `report.html` — executive summary

**Emit all formats (JSON, HTML, CSV, PDF):**

```bash
finops-assess run --input ./samples \
  --output ./report.json \
  --format all \
  --branding-name "Your Org" \
  --branding-color "#0969da"
```

### 3. Review findings

1. **HTML report** — open `demo-report.html` or `report.html` in a browser 
   for an interactive review grouped by severity, persona, and surface 
   (M365 · Azure · GitHub · ADO).
2. **JSON report** — use for automation, alerting, or long-term storage.
3. **CSV export** — pivot in Excel or Sheets, e.g. filter by severity or 
   surface.

### 4. (Optional) Build an advisory triage pack

After generating a JSON report, convert it into a triage pack for analyst 
review:

```bash
finops-assess triage --input ./report.json --output-dir ./triage
```

This produces:
- `triage.json` — structured advisory pack
- `triage.csv` — flat triage table

**With GitHub Copilot helper (optional, requires `gh` CLI and Copilot access):**

```bash
finops-assess triage --input ./report.json \
  --output-dir ./triage \
  --enable-copilot-helper
```

**Note:** The helper runs locally and does not upload data off your machine 
without explicit flag.

### 5. Use PII redaction (default; override with caution)

By default, all user-identifying fields (UPNs, email addresses, principals) 
are replaced with salted SHA256 hashes in the report:

```bash
finops-assess demo --output-dir ./report
```

To opt out and emit unredacted principal names:

```bash
finops-assess demo --output-dir ./report --no-pii-redaction
```

**Guidance:** Only use `--no-pii-redaction` in isolated environments with 
access controls (e.g. internal FinOps analyst shared drives, not public CI 
logs).

## Planned features (not yet shipped)

The following commands and options are **under development** and will ship 
in future releases:

- **Live collectors** `(planned)` — Replace CSV input with direct API 
  collection from Microsoft 365, Azure, GitHub, and Azure DevOps using 
  federated identity (OIDC) or service principal credentials.
- **Incremental runs** `(planned)` — Compare assessments across time to track 
  progress on recommendations.
- **Custom rule definitions** `(planned)` — Allow operators to author 
  additional rules or modify severity/recommendation text without editing 
  the codebase.
- **Integration with FinOps Hubs** `(planned)` — Automated handoff of 
  findings to a Hubs landing zone.
- **Concurrent collector execution** `(planned)` — Speed up live collection 
  by parallelising API requests across surfaces.

## Read-only posture

This tool **never modifies** the systems or data it inspects:

- ✅ Reads user inventory, assignments, and usage signals
- ✅ Reads SKU catalogue and pricing data
- ✅ Emits findings and recommendations
- ❌ Does **not** change licence assignments
- ❌ Does **not** modify Azure resources
- ❌ Does **not** write to tenant configuration
- ❌ Does **not** upload data beyond your control

Every finding is advisory. Before acting on a recommendation, verify the 
exception case (compliance holds, eDiscovery custodians, break-glass 
accounts, multi-tenant shared resources) applies in your environment.

## See also

- [README: Quick start](../../README.md#quick-start) — installation 
  steps
- [User guide](../user-guide.md) — report interpretation and worked 
  examples
- [Data schema](../schema.md) — CSV column reference and report model
- [Rules reference](../rules.md) — every rule ID and recommendation template
- [Plan & Architecture](../plan.md) — internal design and roadmap
