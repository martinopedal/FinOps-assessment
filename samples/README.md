# Synthetic FinOps assessment tenant

This directory is a **fully synthetic** Microsoft 365 + Azure tenant used by:

* the M2 unit tests (`tests/test_engine.py`, `tests/test_cli_run.py`)
* the `finops-assess run --input ./samples/` smoke command, which is the
  M2 milestone exit-criterion in `docs/plan.md` §2

No real principals, tenants, or resources are represented. All identifiers
use the IETF-reserved `*.example` domain (RFC 2606) and the
`/subscriptions/00000000/...` Azure subscription id.

## Files

| File | Shape | Notes |
|---|---|---|
| `users.csv` | `UserRecord` | Members, a guest, a shared mailbox, a disabled account, and a service principal. |
| `license_assignments.csv` | `LicenseAssignment` | Assignments designed to trigger every M365 rule. |
| `usage.csv` | `UsageSignal` | Per-principal activity signals (`exchange`, `teams`, `copilot`, `defender_o365`, `purview_dlp`, `entra_p2`, …). |
| `azure_resources.csv` | `AzureResource` | One idle VM, one oversized VM, one unattached disk, one orphan public IP. |
| `overrides.yaml` | `dict[str, str]` | Pin Alice to `frontline_worker` regardless of title regex. |

## Rule coverage matrix

The dataset is constructed so that running `finops-assess run --input ./samples/`
emits at least one finding for every rule shipped in M2:

* `M365.UNUSED_LICENSE_30D` — Dan's SPE_E3 (disabled, no recent activity).
* `M365.OVER_LICENSED_VS_PERSONA` — Alice (frontline) on E5; Isla (IW) on E5; Gloria (IW) on E3.
* `M365.DUPLICATE_BUNDLE` — Carol holds SPE_E3 *and* the included SHAREPOINTENTERPRISE.
* `M365.DISABLED_USER_LICENSED` — Dan (`accountEnabled=false`) still licensed.
* `M365.SHARED_MAILBOX_LICENSED` — Mailroom shared mailbox at 9.5 GB with EXCHANGESTANDARD.
* `M365.GUEST_PREMIUM_LICENSED` — Hugo (guest) carries SPE_E3.
* `M365.COPILOT_INACTIVE_60D` — Erin and Dan have Copilot but no `copilot` signal.
* `M365.E5_FEATURES_UNUSED` — Alice and Isla on E5 with no Defender / Purview / Entra-P2 activity.
* `AZ.IDLE_VM_14D` — `vm-idle` (avg CPU 2 %, net 8 KB/s).
* `AZ.UNATTACHED_DISK` — `disk-orphan` (unattached for 30 days).
* `AZ.PUBLIC_IP_UNATTACHED` — `pip-orphan` (not associated).
* `AZ.OVERSIZED_VM` — `vm-oversized` (P95 CPU 25 %, P95 mem 30 %).
