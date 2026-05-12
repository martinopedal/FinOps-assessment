# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent m365-specialist initialized for the FinOps-assessment squad. See `.squad/agents/m365-specialist/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **2026-05-12** — Issue #29 (D.6: M365 SKU-mix collector surface review) now in backlog; label drift `squad:m365-specialist`→`squad:priya` is fixed. Stage-4 review flagged sovereign-cloud / tenant-id leakage as distinct from default PII redaction—keep that distinction sharp during implementation.

- **2026-05-12 (PR #40)** — M365 SKU-mix family-summary contract landed. Family-name enum choices (15 families): separated M365 E-tier progression (`m365_e1_tier`, `m365_e3_tier`, `m365_e5_tier`) from standalone Office 365 (`office365`); split Entra P1/P2, EMS E3/E5, Defender variants, Copilot variants, GSA. **PII boundary enforced**: aggregate-only model (`total_assigned`, `distinct_active_users`, `distinct_inactive_users`, `feature_usage_signals: dict[str, int]`) with `extra="forbid"` rejecting any `tenant_id`, `subscription_id`, or `user_id` fields. Tests explicitly assert tenant-id / user-id rejection. This preserves Noor's sovereign-cloud / GSA tenant-id-leakage catch—default PII redaction (user-level salted hashing) is insufficient; model is aggregate-only by construction. **What rules will need next**: Each of the five reserved rule IDs (`M365.SKU_MIX_FRAGMENTED`, `M365.ENTRA_P2_UNUSED`, `M365.SECURITY_ADDON_OVERLAP`, `M365.COPILOT_SKU_MIX_REVIEW`, `M365.GSA_UNUSED_OR_OVERLAP`) ships as its own §11 PR with rule YAML, tests, and collector wiring—data contract is now stable. **Family-to-SKU mapping logic deferred to collectors** (not in the data contract). Aaron Dinnage's M365 Maps (https://m365maps.com/) linked as reference; taxonomy is our own paraphrase (hard rule 3).
