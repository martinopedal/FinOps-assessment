# Maya — docs-voice SKILL decisions (issue #53, PR #55)

**By:** Maya (Lead), encoding scope decisions Martin set on issue #53.

**Status:** Posted to inbox for Scribe to promote into `.squad/decisions.md` on next wrap.

## Context

Issue #53 asked for a sweep of AI language and emojis across docs, and adoption of the news-fetcher voice profile as the docs tone. Martin made four binding scope choices before the work started. They are encoded as operational rules inside `.squad/skills/docs-voice/SKILL.md` (PR #55) and restated here so Scribe can lift them into `decisions.md` verbatim.

## Decisions

### 1. Emoji policy: pragmatic, keep role badges

Permitted across docs of record:

- ✅ and ❌ for binary status.
- Squad role badges (🏗️ ⚛️ 🔧 🧪 📋 🔄), because they are functional UI in routing tables and team rosters.
- Capability traffic-light glyphs (🟢 🟡 🔴) only inside `.squad/team.md`, `.squad/routing.md`, and the capability columns they feed. Outside those routing surfaces, strip them.

Strip every other emoji.

### 2. Em-dash policy: full sweep, except historical logs

Remove every em-dash and en-dash from docs of record. Replace with a comma, a period, or "and", per the news-fetcher rule. Skip `.squad/orchestration-log/` and `.squad/log/` because rewriting historical artifacts rewrites history.

### 3. AI-language scope: full news-fetcher blacklist

Apply the full news-fetcher blacklist (leverage, unlock, comprehensive, robust, seamless, holistic, cutting-edge, journey, delve, empower, streamline, furthermore, moreover, additionally, on the other hand, in conclusion, in today's world, it is worth noting, and the rest of the list inside the SKILL). The four confirmed hits found during audit are a starting point, not the whole scope. Replace abstract verbs and vague qualifiers with concrete nouns and specific verbs.

### 4. Voice profile location: skill only

The anonymized voice profile lives only at `.squad/skills/docs-voice/SKILL.md`. No duplicate at `docs/voice/`, no copy in `docs/style.md`. The SKILL is the canonical source, agents auto-read it through the normal skill-loading path.

## Handoff

Yuki performs the mechanical sweep next on the same branch (`squad/53-docs-voice-and-audit`), reading the SKILL as the spec.
