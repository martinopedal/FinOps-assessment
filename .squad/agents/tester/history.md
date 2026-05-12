# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent tester initialized for the FinOps-assessment squad. See `.squad/agents/tester/charter.md` for role, boundaries, and voice.

## Recent Updates

📌 Squad team expanded on 2026-05-04 to cover the M0–M7 roadmap (M365, Azure, GitHub/ADO surfaces + security review + test ownership).

## Learnings

- **2026-05-12** — Issues #24 (D.1: SKILL rewrite—project-conventions docs-to-code sync), #32 (D.9: first runbook—automated triage & reporting) now in backlog. Review test coverage for incoming D.4–D.8 collector PRs as they land; these spikes are gated on stage-4 falsification criteria per the pilot frame.
- **2026-05-12** — Issue #24 completed (PR #34): `.squad/skills/project-conventions/SKILL.md` rewritten from placeholder template by paraphrasing copilot-instructions.md (hard rules 1–5, tech stack, validation gates) and docs/plan.md §1 (guiding principles, catalogue/package model). Agents now read authoritative convention guidance at session start instead of template noise. All validation gates passed (finops-assess validate ✓, ruff ✓, mypy ✓, pytest 121/125 ✓).
- **2026-05-13** — Issue #32 (D.9: first runbook—"Run assessment") completed. Runbook format chosen: Markdown with H1 title, Purpose one-liner, Prerequisites checklist, numbered step-by-step (keyed to actual shipped CLI commands only), (planned) section for unshipped features explicitly marked with the literal `(planned)` suffix (not italics), read-only posture statement (5 check/cross bullets), and See Also links. Updated `docs/skills/README.md` index to link and mark row as 🟢 (runbook ready). Convention for multi-skill PRs (one runbook per PR per issue) now established. Validation gates baseline: 87/7/23 maintained. Hard rules preserved: read-only in runbook steps (no write/admin scopes), no secrets/PII (only synthetic examples), no vendor doc copying (paraphrase + link), PII redaction guidance included. Planned to reuse format for converting remaining 5 exploratory rows to runbooks later.
- **2026-05-13** — Lockout-revision on PR #42 (issue #28: Diego's commitment-coverage data model). Noor's review surfaced two findings: (1) scope violation — six §11 stage scratch files (`pr-body.md`, `stage-1..5-*.md`) committed to repo root, removed in commit `9c6869e`; (2) test coverage gap in `test_commitment_language_guardrail()` — only checked two class docstrings, missed `AzureCommitmentDataset`, all Field descriptions, and all Literal enum values. Expanded test to iterate every commitment model, extract all surfaces (docstrings via `__doc__`, Field descriptions via `model_fields[name].description`, Literal values via `typing.get_origin`/`get_args` recursive unwrap), and check prohibited-verb regex (`\bpurchase\b`, `\bbuy\b`, `\bexchange\b`, `\bmodify\b`) against concatenated corpus. Failure messages now name model + surface for fast diagnosis. Pattern reusable for future pricing.py contracts (issue #30 will likely need this same guardrail). Expanded test caught NO existing offenders — Diego's models already adhered to read-only posture. All validation gates passed (ruff ✓, mypy ✓, pytest 167/167 ✓, finops-assess validate ✓). Posted revision summary to PR #42; awaiting Noor's re-review per protocol.

