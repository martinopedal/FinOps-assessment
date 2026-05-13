# Orchestration Log Entry

### 2026-05-13 08:25:45 UTC — Coordinator action: File issue #74 (runtime template overlay, follow-up from #61)

| Field | Value |
|-------|-------|
| **Action** | File follow-up issue #74: "Reporters: operator-supplied template overlay with sandbox + manifest provenance" |
| **Trigger** | Maya stage-3 plan OQ-3 resolution (no runtime overlay in v0.5.0) deferred operator custom-template support to a separate issue; Coordinator filed it immediately |
| **Issue labels** | type:feature, release:v0.6.0, squad, priority:p2 |
| **Dependency** | Optional after #61; enables v0.6.0 multi-surface playbook customization and #16 FinOps roadmap operator self-service |
| **Scope** | Add `--playbook-overlay-dir <path>` CLI flag + sandbox-safe template loader (detect supply-chain risk, escape attempts) + manifest field `template_overlay_strategy` (none/overlay/allowed_paths) |
| **Owner assignment** | TBD by Coordinator (squad:core-platform per routing.md) |
| **Rationale** | OQ-3 in #61 stage-3 plan locks "repo-controlled templates only" for v0.5.0 due to sandbox-escape and supply-chain risk. Sonnet flagged this as a future user request (Noor prediction #2). A v0.6.0 feature with explicit overlay strategy declaration (manifest-level) and path sandbox constraints (e.g., `~/.finops-assess/playbooks/{surface}/*.j2` only) unblocks operator customization without weakening the security posture. |

---

## Cross-reference

- Parent issue: #61 (playbook reporter, v0.5.0)
- Stage-3 plan reference: `.squad/decisions.md` OQ-3, Noor prediction #2
- Related: #73 (stable-salt), #16 (FinOps roadmap)
