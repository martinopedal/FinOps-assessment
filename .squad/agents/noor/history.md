# Noor — Security & Adversarial Review History

**Role:** Senior security reviewer; stage-4 adversarial pass; Opus 4.7 model

## Core Context

Stage-4 role: Noor reviews stage-3 plans (produced by rule authors) and stage-5 implementations (produced by implementers). Verdict options:

- **APPROVE** — Plan/impl passes all hard invariants (7 gates: read-only scope, no secrets, no copyright redistribution, PII redaction on by default, catalogue-as-data, no hardcoded pricing, no cloud mutation).
- **REJECT (BLOCKING)** — Plan/impl violates hard invariants or introduces material security/design risk. Blocks stage-5 spawn (or forces revision).
- **REJECT (NIT)** — Non-blocking observations for implementer/author to consider.

## Recent Verdicts

### PR #95 (Diego stage-5 impl, issue #73 — PII salt mode)

**Status:** ✅ APPROVED  
**Date:** 2026-05-13  
**Invariants verified:** All 7/7 PASS

- ✅ Read-only scope upheld (no mutation, read-only CLI flags only)
- ✅ No secrets in repo (salt file/env var by operator; no hardcoded values)
- ✅ No copyright concern (original code, no third-party material)
- ✅ PII redaction on by default (per-run random salt; opt-in tenant-stable)
- ✅ Catalogue as data (engine.py salt parameter, not hardcoded rules)
- ✅ No hardcoded pricing (N/A for this feature)
- ✅ No cloud mutation (read-only; threat model correctly states operator responsibility for salt protection)

**Verdict:** APPROVE. Queued for merge (awaiting main CI, no blocking review).

---

## Session: 2026-05-13 — v0.6.0 backlog 4-PR fan-out batch (#74, #75, #81, #82)

**Context:** Coordinator drove 4 issues through §11 delivery loop in parallel. Noor stage-4 reviewed 6 PRs (2 plans + 4 implementations).

### PR #96 Stage-4 Review (Issue #75 plan, Maya)
- **Verdict:** APPROVE-WITH-CONDITIONS (2 conditions)
- **Conditions:** (1) Residual-risk section in plan, (2) Self-application clarity (Scribe's own routing authority)
- **Disposition:** Both conditions addressed in PR #100 impl by Yuki
- **Hard invariants:** All 7/7 PASS
- **Stage-5 spawn:** Approved for implementation

### PR #97 Stage-4 Review (Issue #74 plan, Maya)
- **Verdict:** APPROVE-WITH-CONDITIONS (3 conditions, all security-focused)
- **Conditions:** (1) AST walker scope (no side channels), (2) Sandbox isolation (FileSystemLoader bounds), (3) Manifest validation (SHA-256 not bypassable)
- **Disposition:** All 3 conditions verified in PR #101 impl by Diego (CodeQL gate passed)
- **Hard invariants:** All 7/7 PASS
- **Security summary:** Template overlay is security-sensitive; all three conditions were architectural constraints, not bugs
- **Stage-5 spawn:** Approved for implementation

### PR #98 Stage-4 Review (Issue #81 lightweight, Yuki)
- **Verdict:** APPROVE (unconditional)
- **Finding:** Mechanical CRLF→LF normalization. Large diff (93 files) is expected and correct. No semantic concerns.
- **Test delta:** Zero (all 624 tests pass post-normalization)
- **Hard invariants:** All 7/7 PASS
- **Summary:** Lightweight housekeeping task; straightforward review

### PR #99 Stage-4 Review Round 1 (Issue #82 impl, Yuki)
- **Verdict:** REJECT (1 BLOCKING item: ruff F401 unused-import in playbook module)
- **Hard invariants:** 6/7 PASS (ruff check failure)
- **Lockout activated:** Original author (Yuki) locked out per §11 protocol
- **Backup:** Diego provided 1-line F401 fix for round 2

### PR #99 Stage-4 Review Round 2 (Issue #82 revised impl, Diego)
- **Verdict:** APPROVE (after Diego F401 fix)
- **Finding:** Single-line change is clean. All gates pass. Round-2 review confirmed no regressions.
- **Hard invariants:** All 7/7 PASS
- **Note:** Lockout is not punishment — it's fresh-eyes validation. Diego's narrow fix unblocked the PR quickly.

### PR #100 Stage-4 Review (Issue #75 impl, Yuki)
- **Verdict:** APPROVE (with 2 non-blocking suggestions S1+S2)
- **Suggestions:** Kept as PR comments (scope too small for separate issues). Yuki may address in follow-up PRs if desired.
- **Hard invariants:** All 7/7 PASS
- **Finding:** Implementation matched plan correctly. No hard blockers.

### PR #101 Stage-4 Review (Issue #74 impl, Diego)
- **Verdict:** APPROVE (with 2 non-blocking suggestions S1+S2)
- **Suggestions:** Filed as separate issues #102, #103 (scope warrants dedicated PRs)
- **Hard invariants:** All 7/7 PASS
- **Security verification:** All 3 stage-3 plan conditions verified in code (AST walker proper, sandbox isolated, manifest validated)
- **CodeQL gate:** Passed
- **Finding:** Large implementation (1221/26 lines) is security-focused and thoroughly designed.

**Session summary:** 6 reviews, 4 APPROVE/APPROVE-WITH-CONDITIONS, 1 REJECT→APPROVE round-2 (lockout validated), 1 APPROVE (lightweight). All PRs eventually merged or ready. All conditions/findings addressed by implementers or filed as follow-ups. No design regressions.

---

