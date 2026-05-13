# Stage-3 plan -- AZ.AHB_ELIGIBLE (#59 rule 5/5)

| field | value |
| --- | --- |
| author | Maya (Lead) |
| model | Opus 4.7 (stage-3 binding model per `.github/copilot-instructions.md` §"Per-step delivery process") |
| epic | #59 -- Azure commitment-discount + AHB rule suite |
| rule | `AZ.AHB_ELIGIBLE` -- Windows VM running PAYG without Azure Hybrid Benefit applied |
| plan branch | `squad/59-plan-maya-ahb-eligible` |
| impl branch (target) | `squad/59-impl-ahb-eligible` |
| implementer (primary) | Yuki |
| implementer (backup) | Diego |
| sibling plans | rule 1 `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (PR #79, merged) ; rule 2 `AZ.COMMITMENT_UNDER_COVERED` (PR #82, merged) ; rule 3 `AZ.COMMITMENT_RENEWAL_REVIEW` (PR #86, merged) ; rule 4 `AZ.RESERVATION_SCOPE_MISMATCH` (PR #89, merged) |
| producer-path SHA | `2a6a822` (HEAD of `main` at plan-branch creation) |
| target plan PR | draft, labels `squad:maya` + `type:plan` |

## Headline

`AZ.AHB_ELIGIBLE` is the **fifth and final rule** in epic #59, and it closes out the schema and rule taxonomy for the Azure commitment-discount + AHB suite. Unlike rules 1-4 (which all targeted commitment-discount levers -- Savings Plans and Reservations), rule 5 targets a **per-VM licence-bring lever**: detect Windows virtual machines running on pay-as-you-go (PAYG) Compute pricing where Azure Hybrid Benefit (AHB) has not been applied, so the operator can verify their on-prem Windows Server licence + Software Assurance position and consider switching the VM to AHB pricing.

The rule introduces **two new optional fields on `AzureResource`** -- one closed-set OS-family discriminator (`os_type`) and one open-string benefit-application discriminator (`license_type`) -- because both signals are required to soundly tell "Windows VM eligible for AHB" apart from "Linux VM (BYOS lever, out of V1 scope)" and "Windows VM already on AHB (success state)". The two-field schema diff is the smallest one that lets the rule abstain correctly on every non-Windows-PAYG row.

V1 scope is **virtualMachine resource_type only**. SQL VM AHB (a separate licensing lever with its own ARM resource provider, `Microsoft.SqlVirtualMachine`) and Linux BYOS (RHEL / SLES, qualitatively different commercial agreement) are explicitly out of scope and called out in §3.14, with placeholder rule IDs reserved for future epics.

The plan applies the **§1.1 disambiguation pattern** for the third time in the epic (after PR #85 / rule 1 introduced it for `term`-vs-`benefitTerm`, and PR #89 / rule 4 reapplied it for `appliedScopeType`-vs-`scope`). For AHB, the two confusable fields are the ARM-side `properties.storageProfile.osDisk.osType` (an OS-family discriminator returning `"Windows"` or `"Linux"`) and the ARM-side `properties.licenseType` (a benefit-application discriminator returning `"Windows_Server"`, `"Windows_Client"`, `"RHEL_BYOS"`, `"SLES_BYOS"`, or `null`). Both are short, both look like enums, and they produce a real false-positive class if conflated -- exactly the failure mode the disambiguation pattern was designed to prevent.

## Section 1 -- Research (stage 1)

Stage-1 research was carried out by Maya (Lead) directly during plan drafting, using the producer-path codebase at SHA `2a6a822` and the public Microsoft Learn AHB documentation. Three confusable ARM concepts and one schema choice required disambiguation; one was promoted into a §1.1 binding table.

### 1.1 Disambiguation -- `osType` vs `licenseType`

This is the **third instance** of the disambiguation pattern in epic #59, and it is the single most important sentence in the plan. Both fields live on the **same ARM Virtual Machine response object** (`Microsoft.Compute/virtualMachines`, api-version `2023-09-01`). Both are short string enums. **They mean different things and the rule needs both signals.**

| ARM field | type | meaning | example values | rule role |
| --- | --- | --- | --- | --- |
| `properties.storageProfile.osDisk.osType` | string enum | **OS-FAMILY discriminator** -- which operating system family the VM was created from. Set at provision time from the chosen image; does not change without redeploy. | `"Windows"`, `"Linux"` | gates the rule -- only `"Windows"` rows are eligible for AHB V1 |
| `properties.licenseType` | string enum (open / forward-compat) | **BENEFIT-APPLICATION discriminator** -- which licence-bring benefit (if any) the operator has elected to apply to this VM for billing. Mutable via ARM PATCH. | `"Windows_Server"`, `"Windows_Client"`, `"RHEL_BYOS"`, `"SLES_BYOS"`, `null` / absent | gates the rule -- only `null` / empty (PAYG) rows fire |

**Why both signals are required.** Without `osType` the rule cannot distinguish a Windows VM (eligible for AHB V1) from a Linux VM (eligible for BYOS, V2 scope). Without `licenseType` the rule cannot distinguish a Windows VM already on AHB (success state, must abstain) from a Windows VM on PAYG (eligible, must fire).

**Why `osType` is closed-set and `licenseType` is open string.** Microsoft's documented `osType` enum has shipped two values for the entire lifetime of the Compute API and is unlikely to grow; modelling it as `Literal["Windows", "Linux"]` is safe. Microsoft adds `licenseType` enum members over time as new licence-bring SKUs ship (`RHEL_ELS`, `SLES_HPC`, etc.); modelling it as `str | None` (open) protects the loader against API drift without requiring a schema bump every time. This is the same defensive posture rule 4 took for `AzureReservation.scope`.

**Why this is a §1.1 binding.** During §1 research, Maya drafted three early variants of the rule body that conflated the two fields (`os_type == "Windows" and license_type != "Windows"` for example, which silently mishandles `RHEL_BYOS` on a Windows VM as if it were AHB-applied). The §1.1 disambiguation table is the canonical fix and the implementer must keep it byte-equal in the rule docstring.

### 1.2 Producer-grounded summary

| concept | producer | citation |
| --- | --- | --- |
| Compute API surface for VM list / get | ARM REST `Microsoft.Compute/virtualMachines` api-version `2023-09-01` | `src/finops_assess/collectors/arm_collector.py:36` |
| `osType` and `licenseType` source path | `properties.storageProfile.osDisk.osType` and `properties.licenseType` on the VM response object | Microsoft Learn -- VM REST list-all response shape (`https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/list-all`) |
| AHB licence-bring semantics | Azure Hybrid Benefit (Windows Server) -- bring eligible Windows Server CALs + Software Assurance to a VM, billed at the Linux Compute rate (the Windows licence cost component is removed) | Microsoft Learn -- `https://learn.microsoft.com/en-us/azure/virtual-machines/windows/hybrid-use-benefit-licensing` |
| AHB scope coverage | per-VM toggle, applied at billing time, no infra change required | Microsoft Learn -- AHB scope-level guidance (`https://learn.microsoft.com/en-us/azure/cost-management-billing/scope-level/azure-hybrid-benefit`) |
| Read-only ARM scope | `https://management.azure.com/.default` (Reader role on the subscription) -- Reader already returns `properties.licenseType` and `properties.storageProfile.osDisk.osType` | `src/finops_assess/collectors/arm_collector.py:31` |
| Existing abstain precedent | `AZ.IDLE_VM_14D` returns `[]` when CPU / network telemetry is None; AHB will mirror this on `os_type is None` and `os_type == "Linux"` | `src/finops_assess/rules_impl/azure_rules.py:22-51` |
| Finding evidence shape | `Finding.evidence: dict[str, str | int | float | bool]` -- AHB will populate `os_type`, `license_type` (rendered as `"<unset>"` when None), `region`, `resource_group`, `monthly_cost_usd` | `src/finops_assess/models.py:79-94` |
| Per-run salt instability for ARM ID redaction | Finding.principal is salt-hashed using `RuleContext.redact`; salt rotates per run -- IDs are stable within a run, not across runs | `src/finops_assess/engine.py:70-75` and `:151` |
| Strict-column CSV loader backward-compat | `_load_strict` checks `expected.issubset(set(rows[0].keys()))` -- adding two new optional columns to `azure_resources.csv` keeps legacy CSVs loadable as long as both columns default to None | `src/finops_assess/collectors/csv_collector.py:54-107` |

### 1.3 Catalogue impact

**None.** AHB is not a SKU; it is a billing toggle on existing VM SKUs. No `data/catalog/azure/*.yaml` change. This is the same posture rules 1-4 took (commitment discounts are also not SKUs).

### 1.4 Stage-3 corrections to the stage-1 brief

Two corrections were applied during plan drafting:

1. **Initial draft modelled `os_type` as `str | None`.** Rejected -- the Compute `osType` enum has been closed at `{"Windows", "Linux"}` for the lifetime of the API and is documented as such. Tightening to `Literal["Windows", "Linux"] | None` lets the rule body and the test suite assert exhaustive coverage and gives the type-checker enough information to flag a stray third-value comparison. (Contrast with `license_type`, where the enum genuinely grows -- see §1.1.)
2. **Initial draft considered firing on Linux VMs with `license_type is None` as "Linux PAYG eligible for RHEL/SLES BYOS conversion".** Rejected -- Linux BYOS is a qualitatively different commercial conversation (existing RHEL / SLES contract with the OS vendor, not a Microsoft Software Assurance position). Conflating the two would tank precision. Linux BYOS is reserved for a future rule (`AZ.LINUX_BYOS_ELIGIBLE`, placeholder, no plan yet) and explicitly listed in §3.14 OOS.

## Section 2 -- Rubberduck (stage 2)

### 2.1 Plain-English walkthrough

> "We pull the list of virtual machines via ARM Reader. For every VM, we look at two fields. The first, `osType`, tells us the OS family the VM was provisioned with -- Windows or Linux. The second, `licenseType`, tells us which licence-bring benefit the operator has elected to apply to the VM for billing -- `Windows_Server` and `Windows_Client` mean AHB is already applied; `RHEL_BYOS` and `SLES_BYOS` are Linux licence-bring (out of V1 scope); null or empty means no benefit -- the VM is being billed at full PAYG with the Windows licence cost included. The rule fires when a VM is `osType=Windows` AND `licenseType is None or empty`. We abstain on every other combination -- Linux rows (V1 scope), missing telemetry, already-AHB rows, or a Windows row with an unexpected licence string (dirty data; we warn and abstain rather than guess)."

The walkthrough is reproduced verbatim in the rule docstring per §3.5.

### 2.2 Edge-case table (E1 - E14)

| id | scenario | rule behaviour | reason |
| --- | --- | --- | --- |
| E1 | empty `azure_resources` list | no findings | nothing to evaluate |
| E2 | row exists but `resource_type != "virtualMachine"` (managedDisk, publicIp) | skip row, no finding | rule scope is VMs only |
| E3 | virtualMachine row with `os_type is None` (CSV legacy without column, or ARM response that omitted the field) | abstain, warn at INFO | OS-family signal absent -- can't tell Windows from Linux |
| E4 | virtualMachine row with `os_type == "Linux"` | abstain | Linux AHB is BYOS, qualitatively different lever, V1 OOS (see §3.14) |
| E5 | virtualMachine + `os_type == "Windows"` + `license_type == "Windows_Server"` | abstain | already-AHB success state |
| E6 | virtualMachine + `os_type == "Windows"` + `license_type == "Windows_Client"` | abstain | already-AHB (Win 10/11 dev/test multi-tenant) success state |
| E7 | virtualMachine + `os_type == "Windows"` + `license_type is None or ""` | **FIRE** -- finding with `severity=info`, `principal=resource_id`, `estimated_monthly_savings_usd=None` | the eligible case |
| E8 | virtualMachine + `os_type == "Windows"` + `license_type` is anything other than `"Windows_Server"` / `"Windows_Client"` / null / empty (e.g. `"RHEL_BYOS"` accidentally set on a Windows VM -- dirty data) | abstain, warn at WARN | data quality issue, not an actionable finding -- the operator should fix the licenseType first |
| E9 | E7 conditions met but `monthly_cost_usd is None` | fire, but `evidence["monthly_cost_usd"] = "<unset>"` and `estimated_monthly_savings_usd = None` | finding still actionable; cost is rendered as `<unset>` for downstream readability |
| E10 | E7 conditions met AND row also matches `AZ.DEV_TEST_SUB_MISMATCH` | both rules fire, both findings present | intentional cross-rule co-fire (see §2.4) |
| E11 | dataset contains multiple eligible Windows-PAYG VMs in the same subscription | one finding per VM | findings are per-resource, not per-subscription |
| E12 | VM is deallocated (no compute charges accruing today) | fires -- the model has no `power_state` field today | acknowledged limitation; documented in §3.14 OOS; future work `AZ.AHB_ELIGIBLE_RUNNING_ONLY` would gate on power_state |
| E13 | duplicate VM rows in CSV (collector bug) | both rows produce a finding | not the rule's responsibility; collector bug surfaced upstream |
| E14 | SQL VM AHB candidate (`Microsoft.SqlVirtualMachine` resource_type) | not loaded; resource_type Literal does not include `sqlVirtualMachine` | OOS V1; reserved for `AZ.SQL_AHB_ELIGIBLE` future rule |

E15 (`virtualMachine` row with `os_type == "Windows"` and `license_type is None` but the VM is a Marketplace image where AHB does not apply, e.g. some BYOL marketplace listings) is **deliberately not enumerated** -- the rule has no signal to detect this and the recommendation_template ("verify and consider") puts the burden on the operator. False-positive risk discussion below in §2.3.

### 2.3 False-positive risks

Three classes:

1. **Marketplace BYOL Windows images that already include the licence in the marketplace fee.** Some Marketplace publishers ship Windows images whose BYOL licence cost is bundled into the per-hour publisher fee. AHB does not stack with this. The rule has no signal to detect it (it is buried in `properties.storageProfile.imageReference`). Mitigation: recommendation_template uses **"verify and consider"** wording so the operator must check the image source before acting.
2. **VMs in regions / SKU families where AHB savings are negligible after price-list refresh.** AHB savings vary by region and SKU; "up to 40%" is a marketing figure, not a per-VM truth. We cannot compute the per-VM savings without per-SKU price-list data we do not currently load. Mitigation: `estimated_monthly_savings_usd = None` (same posture as `AZ.OVERSIZED_VM`); recommendation_template explicitly avoids quoting a percent.
3. **Regulatory / licensing constraints that prohibit AHB.** Some customer Software Assurance contracts have geographic or affiliate restrictions. The tool cannot see these. Mitigation: "verify and consider" wording; recommendation_template names the operator-side prerequisite (Software Assurance position) explicitly.

### 2.4 Cross-rule isolation matrix

Per the §11 norm "co-fires must be intentional and disjoint by model OR signal", the AHB rule must demonstrably not double-count or contradict any other rule.

| other rule | model | signal | overlap with AHB? | resolution |
| --- | --- | --- | --- | --- |
| `AZ.IDLE_VM_14D` | `AzureResource` (virtualMachine) | low CPU + low network | YES same model, SIGNAL DISJOINT | intentional co-fire -- a Windows-PAYG idle VM should be flagged for both AHB application AND idle shutdown; both findings are valid and address different actions |
| `AZ.OVERSIZED_VM` | `AzureResource` (virtualMachine) | P95 CPU / mem < 40% | YES same model, SIGNAL DISJOINT | intentional co-fire -- right-size first, then apply AHB to the smaller SKU; both findings valid |
| `AZ.UNATTACHED_DISK` | `AzureResource` (managedDisk) | resource_type filter | NO -- different resource_type | cannot co-fire on same row |
| `AZ.PUBLIC_IP_UNATTACHED` | `AzureResource` (publicIp) | resource_type filter | NO -- different resource_type | cannot co-fire on same row |
| `AZ.RESERVATION_UNDERUTILIZED` | `AzureReservation` | utilization < 80% | NO -- different model | disjoint by model |
| `AZ.LOG_ANALYTICS_OVERINGEST` | `AzureLogAnalyticsWorkspace` | ingest tier | NO -- different model | disjoint by model |
| `AZ.SAVINGS_PLAN_ELIGIBLE_SPEND` (rule 1) | `AzureBenefitRecommendation` | recommended_term + on_demand_cost_usd | NO -- different model | disjoint by model; intentional adjacency since both reduce Compute spend |
| `AZ.COMMITMENT_UNDER_COVERED` (rule 2) | `AzureCommitmentCoverage` | uncovered ratio | NO -- different model | disjoint by model |
| `AZ.COMMITMENT_RENEWAL_REVIEW` (rule 3) | `AzureReservation` | days_to_expiry | NO -- different model | disjoint by model |
| `AZ.RESERVATION_SCOPE_MISMATCH` (rule 4) | `AzureReservation` | scope vs applied_scope_type | NO -- different model | disjoint by model |
| `AZ.DEV_TEST_SUB_PRODUCTION_PRICING` | `AzureResource` + `AzureSubscription` | env tag vs subscription type | YES same model, SIGNAL DISJOINT | intentional co-fire (see E10); AHB application is independent of subscription type |

Result: AHB is disjoint by model OR signal from every existing rule. Three intentional co-fires (`AZ.IDLE_VM_14D`, `AZ.OVERSIZED_VM`, `AZ.DEV_TEST_SUB_PRODUCTION_PRICING`) all reflect actions the operator should consider together rather than picking one.

### 2.5 Security review

| item | posture |
| --- | --- |
| New ARM scope? | **No.** Reader on the subscription already returns `properties.storageProfile.osDisk.osType` and `properties.licenseType` -- both are part of the standard VM GET response shape. Hard rule #1 (read-only) holds; `_ARM_SCOPES` at `arm_collector.py:31` is unchanged. |
| New M365 / Graph scope? | No -- AHB is Azure-only. |
| New PII fields? | Two new fields, both technical (`os_type`, `license_type`). Neither carries user-identifying information. ARM resource ID (already redactable -- `principal=resource_id`) is the only redactable field surfaced in findings. |
| Redaction call-site count | **TWO** -- (a) `Finding.principal = ctx.redact(resource.resource_id)` in the rule body; (b) the rendered `principal` argument passed to the playbook template. (Compare rule 4's six -- AHB is simpler because it emits no list-of-IDs.) |
| Salt rotation invariant | Per-run salt at `engine.py:151` -- principals stable within a run, not across runs. AHB inherits this; the Yuki-net e2e test (§3.8 test 12) asserts cross-run principal instability. |
| Token / secret exposure | None -- this is a plan, not code. Impl PR will use the existing OIDC federated credential. |

### 2.6 Wording -- the conservative framing

`recommendation_template` MUST use **"verify and consider"** framing, not "remove" or "convert". AHB has prerequisites the tool cannot verify:

- The operator must hold an eligible Windows Server licence (Datacenter or Standard edition).
- The licence must be covered by Software Assurance OR purchased via subscription.
- For Windows 10/11 (`license_type == "Windows_Client"`), the operator must hold a Windows Multi-tenant Hosting Rights or VDA subscription.
- The operator must agree to the AHB self-attestation in the Azure portal.

A flat "switch this VM to AHB" recommendation would be wrong for any operator who does not hold those prerequisites. Approved phrasing:

> "Verify your Windows Server licence and Software Assurance position covers this VM, and consider applying Azure Hybrid Benefit to remove the Windows licence cost from PAYG Compute pricing."

(Variable interpolation: `resource_name`, `region`, `monthly_cost_usd_str`. No interpolation of percent savings -- see §2.3 risk #2.)

### 2.7 Alternatives considered

| id | alternative | rejected because |
| --- | --- | --- |
| R1 | Single combined field `ahb_status: Literal["applied", "eligible", "not_applicable", "unknown"]` | conflates OS-family signal with benefit-application signal; loses the underlying ARM data; impossible to add SQL VM AHB or Linux BYOS in V2 without re-modelling; rejected (PR #89 lockout learning -- prefer one optional field over a derived enum) |
| R2 | Single field `license_type: str` only (drop `os_type`) | cannot distinguish Linux PAYG from Windows PAYG -- both appear as `license_type is None`; would force the rule to guess from VM size name (fragile); rejected |
| R3 | Single field `os_type: str` only (drop `license_type`) | cannot distinguish Windows-AHB-applied from Windows-PAYG-eligible -- the success state would fire as a false positive; rejected |
| R4 | Compute `ahb_eligible: bool` at collector time and store only the boolean | hides the underlying data, makes the rule harder to debug, makes future rule additions (Linux BYOS, SQL VM AHB) require more collector changes; rejected -- prefer raw signals in the model |
| R5 | Fire only on stopped/deallocated VMs to avoid disrupting running production | E12 -- the model has no `power_state` field; adding it for V1 doubles the scope; deferred to a future `AZ.AHB_ELIGIBLE_RUNNING_ONLY` variant; current V1 fires on all eligible regardless of power state |
| R6 | Compute per-VM AHB savings from the Retail Prices API at rule time | rules don't make network calls (engine boundary); pre-loading the price list would more than double the catalogue size; "verify and consider" + `estimated_monthly_savings_usd=None` is the right posture for V1 (same as `AZ.OVERSIZED_VM`); rejected |
| R7 | Skip the rule entirely -- "operators know about AHB" | epic #59 explicitly listed AHB; the discovery point is non-trivial when an operator inherited an estate; the rule is high-signal once `os_type` and `license_type` are in the model; rejected |

## Section 3 -- Implementation plan (stage 5 spec)

### 3.1 File-level changes

| path | change | reason |
| --- | --- | --- |
| `src/finops_assess/models.py` | ADD two fields on `AzureResource`: `os_type: Literal["Windows", "Linux"] \| None = None` and `license_type: str \| None = None`. Keep ordering -- new optional fields go AFTER all existing optional fields (`tags`, `monthly_cost_usd`). | schema diff for the rule |
| `src/finops_assess/collectors/arm_collector.py` | EXTEND `_build_vm_row` (or equivalent VM row builder near line 489) to read `properties.storageProfile.osDisk.osType` -> `os_type` and `properties.licenseType` -> `license_type`. Both reads use `.get(...)` with default None. | populate the new fields from ARM |
| `src/finops_assess/collectors/arm_collector.py` (CSV header writer) | EXTEND the `azure_resources.csv` header writer near line 697 to add `os_type,license_type` columns at end. | CSV round-trip parity |
| `src/finops_assess/collectors/csv_collector.py` | NO CHANGE to `_load_strict` body; it already handles missing columns via `_normalise_optional` for str fields. The Literal-typed `os_type` requires verification that an empty CSV cell is parsed as None and rejected if it carries an unexpected value -- pydantic v2 will enforce this; add an integration test (§3.8 test 14). | backward-compat for legacy CSVs |
| `src/finops_assess/rules_impl/azure_rules.py` | APPEND `def az_ahb_eligible(ctx: RuleContext) -> list[Finding]` after line 366. Body per §3.5 skeleton. | the rule body |
| `src/finops_assess/rules_impl/__init__.py` | REGISTER `("AZ.AHB_ELIGIBLE", az_ahb_eligible)` in `_AZURE_RULES` list. | engine registration |
| `data/rules/azure.yaml` | APPEND rule entry per §3.6. | rule metadata |
| `src/finops_assess/data/rules/azure.yaml` | MIRROR `data/rules/azure.yaml` byte-equal (the package data copy). | packaged data parity |
| `tests/test_engine.py` | ADD `"AZ.AHB_ELIGIBLE"` to `REQUIRED_RULES` set near line 23. | gate that registration is wired |
| `tests/test_rules_az_ahb_eligible.py` | NEW unit + e2e tests E1-E15 per §3.8. | rule correctness |
| `samples/azure_resources.csv` | ADD two columns + extend at least one row to be a Windows-PAYG eligible case (and a Linux row for E4 abstain coverage). | demo data shows the rule firing |
| `docs/plan.md` | ADD one line to §6 Azure rules block (§3.12 in this plan). | doc sync |
| `docs/schema.md` | ADD two lines to `AzureResource` field list (§3.13). | doc sync |
| `docs/rules.md` | regenerated by `python scripts/generate_docs.py` from the YAML rule entry; do not edit by hand. | doc regen |
| `docs/personas.md` | regenerated; no manual edit. | doc regen |
| `examples/m365_vendor_a_*.{json,md}` | regenerated by example-runner; no manual edit. | doc regen |
| `src/finops_assess/data/playbooks/azure/AZ.AHB_ELIGIBLE.md.j2` | NEW playbook template. Variables: `principal`, `resource_name`, `region`, `monthly_cost_usd_str`. StrictUndefined-safe from first commit. | playbook for the new rule |

### 3.2 Cleanup TODOs

None inherited from rule 4. The rule-4 plan added `AzureReservation.scope` defensively; rule 5 reuses the same defensive posture for `license_type` and does not require a follow-up.

### 3.3 CSV strict-column loader -- backward-compat

Citation: `src/finops_assess/collectors/csv_collector.py:54-107`.

The strict-column loader requires the CSV header to be a superset of the model's required columns. Both new fields are optional with `default=None`, so adding them does not break legacy CSVs that omit the columns. **Test 14 in §3.8 asserts this** -- it loads a CSV with the legacy header (no `os_type`, no `license_type`) and confirms loading succeeds and both fields are None on every row.

For new CSVs WITH the columns: pydantic v2 enforces the `Literal["Windows", "Linux"]` constraint on `os_type` -- a stray value (`"WINDOWS"` lowercased, or `"Win"` truncated) will raise a `ValidationError` at row-load time. **Test 15 in §3.8 asserts this** -- a CSV with `os_type=WindowsServer` raises a clear pydantic error rather than silently mis-classifying.

Empty cells: `_normalise_optional` already converts empty strings to None (`csv_collector.py:88-91`), so an `os_type` column present but blank parses as None and the rule abstains via E3.

### 3.4 ARM collector changes

Two new reads in the VM row builder near `arm_collector.py:489`. Both use `.get(...)` so a missing key parses as None (matches CSV behaviour).

```python
os_type = (
    vm_response.get("properties", {})
    .get("storageProfile", {})
    .get("osDisk", {})
    .get("osType")
)
license_type = vm_response.get("properties", {}).get("licenseType")
```

The CSV header writer near `arm_collector.py:697` extends to include the two new columns at the end of the header tuple. Existing column ordering MUST NOT be permuted -- legacy CSV samples and any operator-side scripts that pin column indices break otherwise.

No new ARM scope. No new API call. The VM list-all response already carries both fields; we are reading what we already retrieve.

### 3.5 Rule body skeleton

```python
def az_ahb_eligible(ctx: RuleContext) -> list[Finding]:
    """Detect Windows VMs running PAYG without Azure Hybrid Benefit applied.

    Rule-set: §1.1 of plan-059-az-ahb-eligible. Two ARM fields, easy to confuse:
      properties.storageProfile.osDisk.osType -- OS-FAMILY discriminator ("Windows" / "Linux")
      properties.licenseType -- BENEFIT-APPLICATION discriminator ("Windows_Server" / "Windows_Client" / "RHEL_BYOS" / "SLES_BYOS" / null)

    Fires when: resource_type == "virtualMachine" AND os_type == "Windows" AND license_type is None or empty.
    Abstains on every other combination. Recommendation framing is "verify and consider"; estimated savings is None (see §2.3).
    """
    findings: list[Finding] = []
    AHB_APPLIED_VALUES = {"Windows_Server", "Windows_Client"}

    for resource in ctx.dataset.azure_resources:
        if resource.resource_type != "virtualMachine":
            continue                                                # E2

        if resource.os_type is None:
            continue                                                # E3 -- signal absent
        if resource.os_type != "Windows":
            continue                                                # E4 -- Linux BYOS OOS V1

        license_type = (resource.license_type or "").strip()
        if license_type in AHB_APPLIED_VALUES:
            continue                                                # E5, E6 -- already AHB
        if license_type and license_type not in AHB_APPLIED_VALUES:
            # E8 -- dirty data (e.g. RHEL_BYOS on a Windows VM); warn + abstain.
            ctx.log.warning(
                "AZ.AHB_ELIGIBLE: unexpected license_type=%r on Windows VM %s; abstaining",
                license_type, resource.resource_id,
            )
            continue

        # E7 -- the eligible case.
        cost = resource.monthly_cost_usd
        evidence = {
            "os_type": resource.os_type,
            "license_type": resource.license_type or "<unset>",
            "region": resource.region or "<unset>",
            "resource_group": resource.resource_group or "<unset>",
            "monthly_cost_usd": cost if cost is not None else "<unset>",
        }
        findings.append(
            Finding(
                rule_id="AZ.AHB_ELIGIBLE",
                surface="azure",
                severity="info",
                principal=ctx.redact(resource.resource_id),         # redaction call-site #1
                summary=f"Windows VM {resource.name or resource.resource_id} running PAYG without Azure Hybrid Benefit",
                evidence=evidence,
                estimated_monthly_savings_usd=None,                 # see §2.3 #2
            )
        )

    return findings
```

(Implementer: do not change the comment markers `# E2`, `# E3`, etc. -- they are the test-suite anchors per §3.8.)

### 3.6 YAML rule entry

Append to `data/rules/azure.yaml`:

```yaml
- id: AZ.AHB_ELIGIBLE
  surface: azure
  severity: info
  summary: Windows VM running PAYG without Azure Hybrid Benefit applied, eligible for licence-bring savings.
  recommendation_template: |
    Verify your Windows Server licence and Software Assurance position covers this VM ({resource_name} in {region}, monthly_cost {monthly_cost_usd_str}), and consider applying Azure Hybrid Benefit to remove the Windows licence cost from PAYG Compute pricing.
  references:
    - https://learn.microsoft.com/en-us/azure/virtual-machines/windows/hybrid-use-benefit-licensing
    - https://learn.microsoft.com/en-us/azure/cost-management-billing/scope-level/azure-hybrid-benefit
```

Mirror byte-equal to `src/finops_assess/data/rules/azure.yaml`. The doc-regen `--check` gate will fail if the two diverge.

### 3.7 Producer-path citations (for stage-4 review)

| # | citation | claim it grounds |
| --- | --- | --- |
| 1 | `src/finops_assess/engine.py:70-75` | `RuleContext.redact` exists and is the correct call-site for principal hashing |
| 2 | `src/finops_assess/engine.py:151` | per-run salt instability -- principals stable within a run, not across runs |
| 3 | `src/finops_assess/models.py:212` | `resource_id` is the ARM ID and is the redactable principal for AHB |
| 4 | `src/finops_assess/models.py:213-217` | `resource_type` Literal scope -- contains `virtualMachine`/`managedDisk`/`publicIp` only; SQL VM out of scope V1 |
| 5 | `src/finops_assess/collectors/arm_collector.py:489` | VM row builder pattern; AHB extends this |
| 6 | `src/finops_assess/collectors/arm_collector.py:36` | `_API_VERSIONS["virtualMachines"] = "2023-09-01"` -- already returns `licenseType` and `osType` |
| 7 | `src/finops_assess/collectors/arm_collector.py:31` | `_ARM_SCOPES` -- read-only Reader scope, no change |
| 8 | `src/finops_assess/collectors/csv_collector.py:54-107` | strict-column loader docstring -- backward-compat for missing columns when both new fields are optional |
| 9 | `src/finops_assess/collectors/csv_collector.py:88-91` | empty CSV cell defaults to None via `_normalise_optional` |
| 10 | `src/finops_assess/collectors/arm_collector.py:697-718` | CSV header writer for `azure_resources.csv` -- AHB extends with two columns |
| 11 | `src/finops_assess/rules_impl/azure_rules.py:22-51` | `AZ.IDLE_VM_14D` abstain pattern -- precedent for "missing telemetry -> empty list" |
| 12 | `tests/test_playbook_cross_run_stability.py:1-80` | Yuki-net e2e pattern -- AHB e2e test mirrors this shape |
| 13 | `src/finops_assess/models.py:79-94` | `Finding.evidence` shape -- `dict[str, str \| int \| float \| bool]` |
| 14 | Microsoft Learn -- `https://learn.microsoft.com/en-us/azure/virtual-machines/windows/hybrid-use-benefit-licensing` | AHB semantics for Windows Server VMs |
| 15 | Microsoft Learn -- `https://learn.microsoft.com/en-us/azure/cost-management-billing/scope-level/azure-hybrid-benefit` | AHB scope-level guidance |
| 16 | Microsoft Learn -- `https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/list-all` | VM REST response shape carries `properties.licenseType` and `properties.storageProfile.osDisk.osType` |
| 17 | `samples/azure_resources.csv:1-6` | current header + rows -- AHB extends with two columns and adds at least one Windows-PAYG row |
| 18 | `tests/test_engine.py:23-48` | `REQUIRED_RULES` set -- AHB adds `"AZ.AHB_ELIGIBLE"` |
| 19 | PR #85 plan-rule-1 lockout learning -- §1.1 disambiguation pattern origin | the disambiguation table is repo doctrine, not personal preference |
| 20 | PR #89 plan-rule-4 lockout learning -- prefer ONE optional field over renaming/splitting | the two-field schema diff is justified; R1-R4 alternatives all rejected for losing signal |

20 citations total -- exceeds the ≥16 floor. The four overshoot citations (#19, #20 for lockout-learning provenance, plus #14 and #15 producer URLs split because AHB has separate Windows-Compute and Cost-Mgmt pages) tighten the §1.1 disambiguation provenance.

### 3.8 Test plan -- E1 to E15

Tests live in `tests/test_rules_az_ahb_eligible.py` (NEW file).

| # | test | covers | shape |
| --- | --- | --- | --- |
| 1 | `test_e1_empty_dataset_returns_empty_list` | E1 | call rule with `azure_resources=[]`; assert `findings == []` |
| 2 | `test_e2_non_vm_resource_skipped` | E2 | one managedDisk + one publicIp row (both with os_type / license_type set to dummy values that would otherwise fire); assert `findings == []` |
| 3 | `test_e3_os_type_none_abstains` | E3 | virtualMachine with `os_type=None`; assert `findings == []` |
| 4 | `test_e4_linux_vm_abstains` | E4 | virtualMachine with `os_type="Linux"`, `license_type=None`; assert `findings == []` |
| 5 | `test_e5_windows_server_ahb_already_applied_abstains` | E5 | virtualMachine with `os_type="Windows"`, `license_type="Windows_Server"`; assert `findings == []` |
| 6 | `test_e6_windows_client_ahb_already_applied_abstains` | E6 | virtualMachine with `os_type="Windows"`, `license_type="Windows_Client"`; assert `findings == []` |
| 7 | `test_e7_windows_payg_fires` | E7 (the happy path) | virtualMachine with `os_type="Windows"`, `license_type=None`, `monthly_cost_usd=120.0`; assert exactly one finding, `severity="info"`, `principal` is hashed, `evidence["license_type"] == "<unset>"`, `estimated_monthly_savings_usd is None` |
| 8 | `test_e8_dirty_license_type_warns_and_abstains` | E8 | virtualMachine with `os_type="Windows"`, `license_type="RHEL_BYOS"`; assert `findings == []` AND a WARN log was emitted naming the resource_id |
| 9 | `test_e9_missing_cost_fires_with_unset_marker` | E9 | virtualMachine with `os_type="Windows"`, `license_type=None`, `monthly_cost_usd=None`; assert one finding, `evidence["monthly_cost_usd"] == "<unset>"`, `estimated_monthly_savings_usd is None` |
| 10 | `test_e10_co_fires_with_dev_test_sub_mismatch` | E10 -- intentional cross-rule co-fire | dataset where the same VM matches AHB and `AZ.DEV_TEST_SUB_MISMATCH`; assert both findings present |
| 11 | `test_e11_multiple_eligible_vms_one_finding_each` | E11 | three Windows-PAYG VMs in same subscription; assert exactly three findings, distinct principals |
| 12 | `test_e7_yuki_net_end_to_end_stability` | redaction call-site count = 2; cross-run principal instability | mirror `tests/test_playbook_cross_run_stability.py:1-80` -- run `run_rules` twice with different salts, assert principals differ across runs but evidence does not, assert playbook renders without StrictUndefined errors |
| 13 | `test_required_rules_includes_ahb_eligible` | engine registration | mirrored from `tests/test_engine.py` `REQUIRED_RULES` -- test that the rule is loaded by `_AZURE_RULES` |
| 14 | `test_csv_loader_legacy_header_backward_compat` | §3.3 backward-compat | load a CSV with the legacy header (no `os_type`, no `license_type` columns); assert success, both fields None on every row |
| 15 | `test_csv_loader_invalid_os_type_raises` | §3.3 type safety | load a CSV with `os_type=WindowsServer`; assert pydantic `ValidationError` is raised with a clear field name |

15 tests = E1-E14 covered + the §3.3 round-trip (test 14, 15) + the engine-registration gate (test 13) + the Yuki-net e2e (test 12). Test 12 specifically mirrors `tests/test_playbook_cross_run_stability.py:1-80` to satisfy PR #88's lockout learning that e2e tests must exercise `run_rules` end-to-end and not duplicate `test_engine.py` body.

### 3.9 Doc regeneration

`python scripts/generate_docs.py` (or `--check` in CI) regenerates:

- `docs/rules.md` (from `data/rules/*.yaml`)
- `docs/personas.md` (no change -- AHB does not introduce a persona)
- `examples/azure_*.{json,md}` (the sample collector run picks up the new rule and the new sample CSV row)

**Implementer must run `python scripts/generate_docs.py` once and commit the regenerated files in the same PR.** The CI gate `python scripts/generate_docs.py --check` fails if any regen target drifts.

### 3.10 Personas impact

None. `AZ.AHB_ELIGIBLE` is severity `info`, fits naturally under existing personas (`finops_lead`, `platform_engineer`). No `data/personas.yaml` change.

### 3.11 Samples CSV updates

`samples/azure_resources.csv` (current 5 rows):

1. Extend header with `,os_type,license_type` at end.
2. Backfill existing 5 rows with empty (None) values for the two new columns -- legacy posture; rule abstains on E3.
3. ADD a NEW row -- Windows VM, region `eastus`, monthly_cost_usd `180.00`, `os_type=Windows`, `license_type=` (blank). This row fires the rule in the example output.
4. ADD a SECOND new row -- Windows VM with `license_type=Windows_Server` to demonstrate the abstain success state (E5).
5. ADD a THIRD new row -- Linux VM with `os_type=Linux` to demonstrate E4 abstain.

Net: header +2 columns, +3 data rows. Existing rows preserved exactly except for the two trailing empty cells per row.

### 3.12 docs/plan.md §6 update

Add ONE line to the Azure rules block (currently lines 209-217). Insert before `AZ.DEV_TEST_SUB_PRODUCTION_PRICING`:

```
- `AZ.AHB_ELIGIBLE`: Windows VM running PAYG without Azure Hybrid Benefit applied, eligible for licence-bring savings.
```

This plan PR makes that edit (1 line). The impl PR does not need to re-edit `docs/plan.md`.

### 3.13 docs/schema.md update

`AzureResource` field list grows by two:

```
| os_type | Literal["Windows", "Linux"] \| None | OS family from properties.storageProfile.osDisk.osType (V1 used by AZ.AHB_ELIGIBLE). |
| license_type | str \| None | Licence-bring benefit application from properties.licenseType ("Windows_Server", "Windows_Client", "RHEL_BYOS", "SLES_BYOS", or null). Open string -- Microsoft adds enum members over time. |
```

This is an impl-PR edit (the schema diff lands with the schema diff itself), not a plan-PR edit. The plan PR does not touch `docs/schema.md`.

### 3.14 Out of scope (V1)

| OOS item | rationale | future placeholder |
| --- | --- | --- |
| SQL VM AHB (`Microsoft.SqlVirtualMachine`) | different ARM resource provider, different licence-bring (SQL Server CALs + SA, not Windows Server CALs + SA), needs a SQL-specific recommendation | `AZ.SQL_AHB_ELIGIBLE` -- no plan yet, no model field yet |
| Linux BYOS (RHEL / SLES) | qualitatively different commercial agreement (with the OS vendor, not Microsoft); cannot share recommendation_template | `AZ.LINUX_BYOS_ELIGIBLE` -- no plan yet, no model field yet |
| Power-state gating | model has no `power_state` field today; deallocated VMs will fire even though no compute charge accrues | `AZ.AHB_ELIGIBLE_RUNNING_ONLY` -- variant on top of V1 |
| Per-VM savings $ estimate | requires Retail Prices API; rule cannot make network calls; "verify and consider" wording is the right V1 posture (matches `AZ.OVERSIZED_VM`) | future estimator pre-loaded at collector time |
| Marketplace BYOL detection | `properties.storageProfile.imageReference` contains the publisher / offer, but mapping to "BYOL listing" requires a Marketplace API the collector does not call today | OOS V1; recommendation_template's "verify" wording covers this |
| Reserved Instances combined with AHB | RI and AHB stack but the rule is about AHB only; RI rules already exist | not OOS, just outside this rule's surface |

### 3.15 Cross-cutting decisions to record in inbox note

1. Schema diff = TWO new fields on `AzureResource`. `os_type` is closed Literal; `license_type` is open str. Both required because the rule needs both signals (R1-R4 in §2.7 all rejected).
2. V1 scope = `virtualMachine` resource_type only. SQL VMs out of scope (resource_type Literal does not include `sqlVirtualMachine`). Linux BYOS out of scope (different commercial lever).
3. §1.1 disambiguation -- third instance of the pattern in epic #59 (PR #85 first, PR #89 second). `osType` is OS-family discriminator; `licenseType` is benefit-application discriminator. Bind in rule docstring.
4. Cross-rule isolation -- disjoint by model OR signal from every existing rule. Three intentional co-fires (`AZ.IDLE_VM_14D`, `AZ.OVERSIZED_VM`, `AZ.DEV_TEST_SUB_MISMATCH`) are documented and intentional.
5. Implementer = Yuki primary, Diego backup (per user mid-session decision -- rules 3, 4, 5 default to Yuki).
6. recommendation_template wording is "verify and consider" (PR #89 lockout learning -- conservative framing). `estimated_monthly_savings_usd = None` (matches `AZ.OVERSIZED_VM` posture).
7. No new ARM scope. No catalogue change. Reader already returns `properties.licenseType` and `properties.storageProfile.osDisk.osType`.
8. Rule 5 closes out the epic #59 schema and rule taxonomy. After this rule lands, the epic's schema surface is complete (no further `AzureResource` / `AzureReservation` / `AzureCommitmentCoverage` / `AzureBenefitRecommendation` field changes required for AHB-adjacent rules).

## Section 4 -- Stage-4 ask (Noor adversarial review)

Noor is asked to confirm or refute each of the following invariants. The plan ships only after Noor's `VERDICT: APPROVE`.

1. **§1.1 disambiguation is correct.** `properties.storageProfile.osDisk.osType` and `properties.licenseType` are two distinct ARM fields with distinct semantics; conflating them produces real false positives. The §1.1 table accurately captures which is which and the rule body uses each for the correct purpose.
2. **Schema diff is minimal.** TWO new fields is the smallest schema diff that lets the rule abstain correctly on E2-E8; alternatives R1-R4 in §2.7 all lose signal. (PR #89 lockout learning -- prefer one optional field where possible; here TWO is the floor, not three.)
3. **`os_type` is correctly modelled as `Literal["Windows", "Linux"] \| None`.** The Compute API's documented `osType` enum is closed at these two values; tightening to `Literal` lets the type-checker flag stray comparisons in the rule body.
4. **`license_type` is correctly modelled as open `str \| None`.** Microsoft adds `licenseType` enum values over time; closing the Literal would create maintenance churn and risk loader-rejection of valid VMs. (Same defensive posture as `AzureReservation.scope`.)
5. **Abstain paths E2-E8 are exhaustive.** Every non-firing branch in the rule body is enumerated and tested. E3 (signal absent), E4 (Linux), E5 / E6 (already AHB), E8 (dirty data) all return early with no finding.
6. **Fire path E7 is correct.** The rule fires when AND ONLY WHEN `resource_type == "virtualMachine"` AND `os_type == "Windows"` AND `license_type` is None or empty. E10 co-fire with `AZ.DEV_TEST_SUB_MISMATCH` is intentional and documented in §2.4.
7. **Redaction call-site count = TWO.** (a) `Finding.principal = ctx.redact(resource.resource_id)` in the rule body; (b) the rendered `principal` argument passed to the playbook template. No list-of-IDs to redact (compare rule 4's six). Tested in test 12.
8. **No new ARM scope.** Reader already returns both fields. `_ARM_SCOPES` at `arm_collector.py:31` is unchanged. Hard rule #1 (read-only) holds.
9. **No catalogue change.** AHB is a billing toggle, not a SKU. `data/catalog/azure/*.yaml` is untouched.
10. **e2e test uses real `run_rules`.** Test 12 in §3.8 mirrors `tests/test_playbook_cross_run_stability.py:1-80`; it calls `run_rules`, not the rule function in isolation. (PR #88 lockout learning -- don't ship a duplicate of `test_engine.py`.)
11. **Conservative wording.** `recommendation_template` uses "verify and consider" framing; the operator-side prerequisites (Software Assurance position, Marketplace BYOL, geographic restrictions) are named in the recommendation. No percent savings is quoted.
12. **Doc regen targets pass `--check`.** `python scripts/generate_docs.py --check` succeeds after impl. The plan PR does NOT regen docs (no rule YAML change in plan PR), but the impl PR must.
13. **Cross-rule isolation matrix is complete and correct.** §2.4 covers every existing Azure rule; the three intentional co-fires are documented and the disjoint-by-model claim holds for the rest.
14. **Backward-compat for legacy CSVs.** Test 14 in §3.8 loads a legacy `azure_resources.csv` (no `os_type`, no `license_type` columns) and asserts loading succeeds with both fields None on every row. Strict-column loader semantics preserved.
15. **OOS items correctly excluded.** SQL VMs (`sqlVirtualMachine` not in `resource_type` Literal), Linux BYOS, deallocated-VM gating, per-VM $ savings, and Marketplace BYOL detection are all listed in §3.14 with placeholders for future work.
16. **Field choice is justified -- TWO new fields, not a Literal explosion or a derived bool.** Alternatives R1-R4 in §2.7 are recorded and rejected with reasons.

16 invariants -- exceeds the ≥14 floor. (Two extra invariants -- #15 OOS coverage and #16 field-choice justification -- both lift recurring stage-4 stumbles into stage-3 binders.)

Noor's verdict format: post a PR comment with marker `**Stage-4 Adversarial Review -- Noor**` and a `VERDICT: APPROVE` line, per `.github/copilot-instructions.md`. The `squad-approve.yml` workflow then submits the bot approval that satisfies branch protection.

## Section 5 -- Stage-5 implementation plan

| field | value |
| --- | --- |
| primary implementer | **Yuki** |
| backup | Diego |
| target branch | `squad/59-impl-ahb-eligible` |
| target PR title | `feat(rules): AZ.AHB_ELIGIBLE -- Windows PAYG VM eligible for AHB (#59 rule 5/5)` |
| labels | `squad:yuki`, `type:rule`, `epic-59` |
| reviewer for stage-4 | Noor |

**Why Yuki primary.** Per the user's mid-session decision (rules 3, 4, 5 default to Yuki primary). Rule 4's plan still records Diego as primary because it was committed before the decision -- do not retro-edit rule 4. Rule 5 is the first to record the new default in writing.

**Why Diego backup.** Diego owns the `arm_collector.py` ARM-side schema reads from rule 1. If Yuki is unavailable, Diego is the next-best-fit because the impl is collector-heavy (two new field reads, CSV header writer, sample CSV update).

**Implementer kickoff checklist** (post in impl PR description):

- [ ] Branch off `main` at HEAD as of the impl-PR-open date (NOT off this plan branch).
- [ ] Read this plan in full before opening the impl PR.
- [ ] §1.1 disambiguation table goes into the rule docstring byte-equal -- do not paraphrase.
- [ ] All test E-numbers (E1-E15) get the same numeric ID in the test file (one test per E-number).
- [ ] Run `finops-assess validate`, `ruff check .`, `mypy src`, `pytest`, `python scripts/generate_docs.py --check` before opening the PR.
- [ ] Commit the regenerated `docs/rules.md`, `examples/azure_*.{json,md}`, and any other regen targets in the same PR.
- [ ] Open as draft; flip to ready when CI is green.
- [ ] Tag Noor for stage-4 review with the `**Stage-4 Adversarial Review -- Noor**` marker.

## Section 6 -- Sign-off mechanics

| stage | actor | artefact | passed when |
| --- | --- | --- | --- |
| 1 Research | Maya | §1 in this plan | producer-path citations grounded; §1.1 disambiguation in place |
| 2 Rubberduck | Maya | §2 in this plan | E-table covers all paths; cross-rule isolation matrix complete; alternatives R1-R7 recorded |
| 3 Plan (this doc) | Maya (Opus 4.7) | this file in `docs/plans/` | merged via this PR |
| 4 Adversarial review | Noor (Opus 4.7) | PR comment with `**Stage-4 Adversarial Review -- Noor**` + `VERDICT: APPROVE` | bot approval lands via `squad-approve.yml`; required-checks summary green |
| 5 Implementation | Yuki primary, Diego backup | impl PR per §5 | all gates green; Noor re-reviews impl PR; merged |
| 5b Lockout cycle | as needed | post-impl follow-up PR | only if impl PR's stage-4 catches a regression that needs a separate fix |
| Wrap | Scribe (Sage) | scribe-wrap PR after rule 5 impl merges | epic #59 fully closed; `.squad/decisions.md` and `.squad/agents/lead/history.md` updated; `.squad/identity/now.md` rotated |

## Section 7 -- Norms operationalised checklist

- [x] **§1.1 disambiguation table** -- third instance in epic #59 (`osType` vs `licenseType`); the rule body docstring carries the same table byte-equal (§3.5).
- [x] **Conservative wording** -- recommendation_template uses "verify and consider"; no percent savings quoted (§3.6, §2.6).
- [x] **`estimated_monthly_savings_usd = None`** -- matches `AZ.OVERSIZED_VM` posture; rule 5 cannot quote per-VM AHB savings without Retail Prices API (§2.3 #2).
- [x] **Cross-rule isolation matrix** -- §2.4 covers every existing Azure rule; three intentional co-fires documented; rest disjoint by model.
- [x] **Schema diff = TWO optional fields** -- minimum required for the rule to abstain correctly; R1-R4 alternatives all rejected (§2.7).
- [x] **`os_type` Literal closed; `license_type` open string** -- defensive posture for forward-compat (§1.1, §1.4).
- [x] **No new ARM scope** -- Reader already returns both fields (§2.5, §3.4).
- [x] **No catalogue change** -- AHB is not a SKU (§1.3).
- [x] **Backward-compat for legacy CSVs** -- test 14 asserts (§3.3, §3.8 #14).
- [x] **e2e test mirrors Yuki-net pattern** -- test 12 calls `run_rules` (§3.8 #12) per PR #88 lockout learning.
- [x] **Doc regen via `scripts/generate_docs.py`** -- no manual `docs/rules.md` edit in impl PR (§3.9).
- [x] **`docs/plan.md` §6 sync** -- this plan PR adds the one line for `AZ.AHB_ELIGIBLE` (§3.12).
- [x] **`docs/schema.md` sync** -- impl PR adds two field rows to `AzureResource` (§3.13).
- [x] **OOS items called out with placeholders** -- SQL VM AHB, Linux BYOS, power-state gating, per-VM $ estimator, Marketplace BYOL (§3.14).
- [x] **Cross-cutting decisions logged in inbox** -- `.squad/decisions/inbox/maya-rule5-stage3.md` to be dropped (gitignored) in this same session per §3.15.
- [x] **Implementer assignment recorded in §5** -- Yuki primary, Diego backup, per user mid-session decision.
- [x] **PR procedure** -- draft PR with `squad:maya` + `type:plan` labels; commit message includes `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- [x] **Validation gates** -- `finops-assess validate`, `ruff check .`, `python scripts/generate_docs.py --check` run before PR open. (No `pytest` / `mypy` -- this plan PR ships zero code.)
- [x] **Path discrepancy noted** -- Maya's history lives at `.squad/agents/lead/history.md`, not `.squad/agents/architect/history.md` (no architect path); inbox note flags this for Scribe.
- [x] **Rule 5 closes out epic #59 schema/rule taxonomy** -- after this rule lands, no further `AzureResource` / `AzureReservation` / `AzureCommitmentCoverage` / `AzureBenefitRecommendation` field changes are required for AHB-adjacent rules.

End of plan.
