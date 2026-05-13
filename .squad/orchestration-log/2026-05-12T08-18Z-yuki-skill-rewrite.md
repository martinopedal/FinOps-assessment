# 2026-05-12T08:18Z — Rewrite project-conventions SKILL.md

| Field | Value |
|-------|-------|
| **Agent routed** | Yuki (tester) |
| **Why chosen** | Issue #24 (chore(squad): rewrite project-conventions SKILL.md from copilot-instructions); router applies `squad:yuki` to documentation updates and pattern refinement |
| **Mode** | background |
| **Why this mode** | No hard data dependencies; SKILL.md is self-contained; authorized files are read-only (copilot-instructions.md, plan.md, pyproject.toml); file-under-rewrite scope is clear |
| **Files authorized to read** | `.github/copilot-instructions.md`, `docs/plan.md` §1, `pyproject.toml`, `.squad/skills/project-conventions/SKILL.md`, agent's own history + decisions.md + wisdom.md + now.md |
| **File(s) agent must produce** | `.squad/skills/project-conventions/SKILL.md` (rewritten, expected 77 insertions / 32 deletions); `.squad/agents/tester/history.md` (Learnings appended) |
| **Outcome** | ✅ Completed. PR #34 opened and squash-merged (commit on main). Validation gates passed (`finops-assess validate` OK, ruff/format/mypy clean, pytest 121 passed + 4 pre-existing live-collector failures unrelated to this PR + 3 weasyprint skips). Front-matter bumped to `confidence: high`, `source: codebase`. Scope respected: only the SKILL.md file was touched. |

---

## Notes

- **Issue closed:** #24
- **PR landed:** #34 (squash-merged to main)
- **Validation gates:** All green
- **Scope discipline:** Yuki respected the one-file boundary; no drift to other .squad/ files
