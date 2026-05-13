---
name: "docs-voice"
description: "Write project documentation in a direct, human voice. Strip AI tells, ban em-dashes, and keep emojis to a small functional set. Applies to all docs of record (README, docs/, .github/agents/, .squad/templates/, .squad/decisions.md, .squad/skills/*/SKILL.md, agent histories, copilot-instructions.md). Does not apply to historical artifacts under .squad/orchestration-log/ and .squad/log/."
domain: "documentation"
confidence: "medium"
source: "earned"
---

## Context

This skill governs how the squad writes prose. It applies whenever an agent edits or creates a document of record in this repo. It does not govern code comments inside `.py`, `.yml`, or `.sh` files (that is a separate code-style concern), and it does not govern README badge conventions.

Apply this skill to:

- `README.md`
- everything under `docs/`
- everything under `.github/agents/` and `.github/copilot-instructions.md`
- `.squad/templates/`
- `.squad/decisions.md` and files under `.squad/decisions/inbox/`
- `.squad/skills/*/SKILL.md`
- per-agent `history.md`, `charter.md`, `skills.md`, and identity files
- PR descriptions and issue bodies authored by squad members

Do not apply this skill to:

- `.squad/orchestration-log/` and `.squad/log/`. Those are historical artifacts, leave them alone.
- inline code comments. Use the language's normal style there.
- third-party content quoted verbatim with attribution.

## Patterns

### 1. Open with the point

State the position or the fact in the first sentence. Skip warm-up phrases like "In today's world", "As we all know", or "I'm excited to share". Give the conclusion before the reasoning.

### 2. Use concrete nouns

Name the file, the function, the rule ID, the YAML key, the workflow. Abstract sentences read as filler. If a paragraph could be pasted into any other repo without editing, rewrite it.

### 3. Imperative or third-person, not first-person personal

Docs are written, not spoken. Prefer "the loader rejects unknown keys" over "I think the loader should reject unknown keys". For instructions, use the imperative: "run `pytest` before opening a PR", not "you might want to consider running `pytest`".

### 4. Short paragraphs, varied length

Two or three sentences per paragraph is the default. Mix in a one-line statement when a point lands harder alone. Do not stack four paragraphs of the same shape.

### 5. Active voice, concrete verbs

Use `update`, `replace`, `drop`, `add`, `reject`, `enforce`. Avoid `leverage`, `enable`, `facilitate`, `utilise`, `drive`.

### 6. Closers state, do not invite

Docs do not ask "what do you think?" End on a fact, a rule, or a pointer to the next file. Leave open invitations for issue threads and PR conversations.

## Operational rules (binding for this repo)

These four rules encode the scope decisions Martin made on issue #53. Yuki applies them mechanically in the next sweep.

### Rule A. Emoji policy: pragmatic, keep role badges

Permitted emojis across all docs of record:

- `✅` and `❌` for binary status.
- The squad role badges, because they are functional UI in routing tables and team rosters: `🏗️` `⚛️` `🔧` `🧪` `📋` `🔄`.
- The capability traffic-light glyphs where they are load-bearing labels in routing (`🟢` `🟡` `🔴` inside `.squad/team.md`, `.squad/routing.md`, and the capability columns they feed). Outside those routing surfaces, strip them.

Strip every other emoji on sight. Common offenders to remove: `` `` `` `` `` `` `` `` `` `` `` `` `` `` `` `` `` ``.

### Rule B. Em-dash policy: full sweep, except historical logs

Remove every em-dash and en-dash from docs of record. Replace with a comma, a period, or the word "and", picking whichever fits the sentence:

- list-style aside, use a comma. Example: "the loader rejects unknown keys, including typos".
- two independent clauses, use a period. Example: "the loader rejects unknown keys. Typos fail loudly."
- joining two parallel ideas, use "and". Example: "the loader validates keys and surfaces typos".

Skip the sweep for files under `.squad/orchestration-log/` and `.squad/log/`. Those are dated artifacts, rewriting them rewrites history.

Hyphens (`-`) inside compound words (`read-only`, `single-duck`, `frontier-model`) are unaffected.

### Rule C. AI-language blacklist

Reject these words and phrases in any doc of record. The list is not exhaustive, the test is "does it sound like a model wrote it":

- abstract verbs: `leverage`, `unlock`, `unleash`, `harness`, `empower`, `elevate`, `streamline`, `embark`, `navigate` (when used about a system, not a UI), `delve`, `dive into`, `deep dive`.
- vague qualifiers: `comprehensive`, `robust`, `cutting-edge`, `seamless`, `holistic`, `paradigm`, `lightweight` (when used as a vague compliment), `game-changer`, `next-generation`.
- transition tells: `furthermore`, `moreover`, `additionally`, `on the other hand`, `in conclusion`, `to sum up`, `in fact`, `it is worth noting`, `it should be noted`, `aforementioned`, `hereinafter`, `notwithstanding`, `nonetheless`.
- framing tells: "In today's world", "In today's landscape", "Let's explore", "Let's dive in", three-point bulleted intros, hedging openers ("It is important to note that").
- career or product romance: `journey` (for a process or a roadmap), "at the end of the day", "it goes without saying".
- AI-tell sign-offs: "feel free to connect", "if you found this helpful", "drop a comment".

Replace with the concrete word. `comprehensive testing` becomes `tests cover X, Y, Z`. `leverage Pydantic` becomes `use Pydantic`. `robust validation` becomes `validation that rejects unknown keys and fails on type drift`. If the abstract word is doing real work, the sentence is hiding what it actually means.

### Rule D. Voice profile location: skill only

This SKILL is the only canonical location for the docs voice. Do not duplicate it under `docs/voice/`, `docs/style.md`, or anywhere else. Agents read this file at session start through the normal skill-loading path. If a future agent wants to extend the voice rules, edit this file in a tracked PR, do not fork it.

## Examples

### Before and after, abstract verb

Before:

> The loader leverages Pydantic to provide robust validation across the catalogue.

After:

> The loader uses Pydantic v2 with `extra="forbid"`. Unknown keys fail at parse time.

### Before and after, em-dash sweep

Before (with an em-dash joining two clauses):

> The duck pass is mandatory for code PRs, post draft PRs are exempt.

After (period and a fresh sentence):

> The duck pass is mandatory for code PRs. Post draft PRs are exempt.

### Before and after, transition tell

Before:

> Furthermore, the validator hard-fails at publish time. Moreover, soft warnings surface during drafting.

After:

> The validator hard-fails at publish time. Soft warnings surface during drafting.

### Before and after, hedging opener

Before:

> It is important to note that the cloud agent cannot self-merge.

After:

> The cloud agent cannot self-merge.

### Before and after, emoji strip

Before:

>  New rule:  never push secrets to the repo.  Use OIDC instead.

After:

> New rule: never push secrets to the repo. Use OIDC instead.

### Before and after, role-badge keep

Keep:

> | Member | Role |
> |---|---|
> | Maya | 📋 Lead |
> | Diego | 🏗️ Architect |

The badges are functional UI in the team roster, so they stay.

## Anti-patterns

- rewriting historical logs under `.squad/orchestration-log/` or `.squad/log/`. Those files capture what happened on a given date. Editing them for voice destroys the record.
- stripping `🟢` `🟡` `🔴` from `.squad/routing.md` capability columns. Those glyphs are load-bearing labels, removing them breaks the routing table contract.
- replacing every em-dash with a comma reflexively. Pick the punctuation that fits the sentence. Two independent clauses want a period, not a comma splice.
- adding a CTA to a docs page. Docs are not posts. No "what do you think?" closers.
- swapping one banned abstract verb for another (`leverage` to `utilise`, `robust` to `comprehensive`). The fix is a concrete noun or verb, not a synonym from the same family.
- writing a "voice section" in another file. This SKILL is the source. Other docs reference it by path, they do not restate it.
- treating this skill as a hard lint. The blacklist is a guide for human and agent judgement. A word on the list can appear in a quoted source, an issue title from outside the squad, or a code identifier. Sweep prose, not quotes or code.
