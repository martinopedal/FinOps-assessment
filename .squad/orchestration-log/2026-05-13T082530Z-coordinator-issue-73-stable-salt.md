# Orchestration Log Entry

### 2026-05-13 08:25:30 UTC — Coordinator action: File issue #73 (stable-salt feature, follow-up from #61)

| Field | Value |
|-------|-------|
| **Action** | File follow-up issue #73: "Engine: tenant-stable PII salt mode for cross-run ticket_key stability (M365/GitHub/ADO)" |
| **Trigger** | Maya stage-3 plan D2 resolution (Option B-honest) deferred stable-salt engine feature to a separate issue; Coordinator filed it immediately to unblock stage-5 #61 work |
| **Issue labels** | type:feature, release:v0.6.0, squad, priority:p1 |
| **Dependency** | Unblocks #61 stage-5 implementation; #73 itself is a v0.6.0 milestone (not blocking v0.5.0 merge) |
| **Scope** | Add `--stable-principal-salt` CLI flag + `stable_salt_mode` parameter to `run_rules()` + documentation of stable-salt contract in docs/security.md |
| **Owner assignment** | TBD by Coordinator (squad:core-platform per routing.md, likely Diego or Azure Specialist) |
| **Rationale** | D2 in #61 stage-3 plan locks the "honest stability declaration" posture: manifest per-surface stability field tells operators what is stable (Azure) vs. per-run (M365/GitHub/ADO). This is correct for v0.5.0, but #16 (FinOps roadmap) and #63 (remediation-PR drafter) require stable ticket keys across runs for all surfaces. The stable-salt engine feature is prerequisite for #74 (runtime overlay) and multi-surface parity in v0.6.0. |

---

## Cross-reference

- Parent issue: #61 (playbook reporter, v0.5.0)
- Stage-3 plan reference: `.squad/decisions.md` D2, §1 "Locked architectural response"
- Related: #74 (runtime template overlay), #16 (FinOps roadmap), #63 (remediation-PR drafter)
