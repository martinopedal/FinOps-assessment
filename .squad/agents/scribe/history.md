# Project Context

- **Project:** FinOps-assessment
- **Created:** 2026-05-04

## Core Context

Agent Scribe initialized and ready for work.

## Recent Updates

 Team initialized on 2026-05-04

## Learnings

- **2026-05-13 (post PR #55 merge)**  ,  Wrapped docs-voice SKILL ship + follow-up fix (PR #55 squash-merged as `23da547`). Promoted Maya's 4-decision scope set from `.squad/decisions/inbox/maya-docs-voice-skill.md` into `.squad/decisions.md` as wave "2026-05-13 , Docs-voice SKILL adopted" (entry covers emoji policy, em-dash policy, AI-language scope, voice-profile location, AND the operational consequence that catalogue YAML prose fields are docs of record). Appended two Maya learnings to `.squad/agents/lead/history.md`: the docs-voice SKILL ship narrative (including the post-CI YAML-vs-generated-doc fix in commit `f54177a` and the lesson about catalogue prose), and the PowerShell unicode round-trip workaround (use `[System.IO.File]::WriteAllText` with `UTF8Encoding($false)`, never `Out-File -Encoding utf8`). Deleted the inbox file via `git rm -f` (it was force-added in commit `1af794c` because `.squad/decisions/inbox/` is gitignored). Updated `.squad/identity/now.md` to post-PR-#55 state. Inbox empty.

- **2026-05-12 (18:52Z)**  ,  Wrapped follow-up batch (PRs #46, #48). Promoted Coordinator's 2026-05-12T10:51Z local-spawn-preference directive to `decisions.md` (top of file, newest first); created decision entry for PR #48 auto-approve workflow (inbox file was deleted by Coordinator, so synthesized from task description). Updated `now.md` with current state snapshot (2026-05-12, follow-up batch complete, auto-approve workflow shipped, 24 orphan branches flagged). Wrote orchestration log (yuki-44, noor-pr46, maya-47, noor-pr48, scribe-followup runs). Wrote session log. Deleted inbox file. Inbox now empty. Key pattern: when inbox files are missing, Scribe infers decision structure from PR descriptions and merged commit messages.
- **2026-05-12**  ,  Merged Maya stage-3 (gap analysis) + Noor stage-4 (verdict & amendments) inbox files into `.squad/decisions.md` (3 entries). Inbox pattern: sub-agents return verbatim final wording (banner text, wisdom rewordings, issue templates); Coordinator copy-pastes into committed files, then Scribe deletes inbox copies. Committed file (decisions.md, wisdom.md, etc.) becomes canonical source. 9 backlog issues filed (#24–#32), PR #33 opened, inbox files deleted.

