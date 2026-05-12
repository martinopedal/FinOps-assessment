---
updated_at: 2026-05-13T00:00:00.000Z
focus_area: PR #55 docs-voice SKILL shipped; deep-research scan in flight for FinOps/agentic/MCP gaps
active_issues: []
---

# What We're Focused On

**PR #55 docs-voice SKILL shipped (2026-05-12, squash-merged as 23da547).** Issue #53 closed. The SKILL at .squad/skills/docs-voice/SKILL.md is now the canonical voice contract for docs of record (including catalogue YAML summary and ecommendation_template fields). Yuki's mechanical sweep cleared 714 em-dashes, 3 AI-language hits, and 87 decorative emojis. Follow-up fix in 54177a corrected an dditionally-assigned miss in the source data/rules/m365.yaml that the post-merge sweep had only fixed in the generated docs/rules.md. Lesson promoted to decisions.md: catalogue YAML prose IS docs of record.

**Async-merge path validated end-to-end.** PR #55 was the first PR after #51 to ship without --admin and without the nforce_admins toggle dance. The sequence: Coordinator opens PR → squad label applied → Stage-4 Noor verdict comment posted → squad-approve.yml parses verdict → github-actions[bot] approval applied → all-green CI → gh pr merge --squash. The contract works.

**Inbox empty.** maya-docs-voice-skill.md merged into .squad/decisions.md and removed in the wrap PR.

**Active research (background).** Deep-research agent commissioned to map this tool against FinOps Foundation Framework + FOCUS spec, and to scope agentic + MCP-server extensions inside the read-only posture. Output is a prioritized backlog of 8-15 distinct additions, each with type / effort / posture-risk / §11 stage-3 plan one-liner. Coordinator will translate the report into GitHub issues (one per backlog item) and may implement the smallest mechanical wins directly.

**Next entry point:** the research report. Coordinator triages findings into issues, files them with squad + appropriate squad:{member} labels, and picks the smallest read-only wins (e.g., a new MCP-config skeleton, a new SKILL.md capturing FinOps Framework mapping, or a derived report view) to land in this session.