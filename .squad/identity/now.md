---
updated_at: 2026-05-12T15:30:00.000Z
focus_area: Protection-fix shipped (#52) , toggle-dance era over; docs-voice scope (#53) awaits user decisions
active_issues: [53]
---

# What We're Focused On

**Protection-fix shipped (2026-05-12).** PR #52 merged via the LAST toggle-dance. Branch protection contract swapped from phantom `["CI"]` to the new `["required-checks"]` summary context published by `ci.yml`. Future squad PRs merge fully async: open → squad label → Stage-4 Noor verdict comment → bot approval → all-green CI → `gh pr merge --squash` (no `--admin`, no enforce_admins toggle).

**Standing directive promoted (2026-05-12).** Every coordinator turn that produces durable state writes it into the squad system (`.squad/` files via PR, or GitHub issues) BEFORE session end. Local-only scratch is not handoff-safe. See `decisions.md` for full text.

**Outstanding , Issue #53 (docs voice + audit).** Filed with full scope, anonymization strategy from `news-fetcher/src/drafts/voice_profile.md`, audit findings (4 AI-language hits, ~600 em-dash hits, squad-role-badge emoji policy decision, etc.), and 4 open scope decisions awaiting user input. Labels: `squad`, `squad:maya`. URL: https://github.com/martinopedal/FinOps-assessment/issues/53. Resume by reading the issue body end-to-end and using `ask_user` to resolve scope decisions before opening `squad/docs-voice-and-audit`.

**THIS wrap PR is the inaugural test of the new async path** (post-protection-swap). If it merges without `--admin`, the contract works.

**Next entry point:** Issue #53 once user resolves scope decisions, OR any new ask. Toggle-dance is no longer needed.

