# SKILL: Branch-protection summary checks (with post-merge PATCH handoff)

**When to use:** A repository's `main` (or release) branch protection requires a status check context that does not exist, or that is brittle because it names a matrix-instance or workflow-level identifier. Symptom: `gh api PUT .../merge` returns `HTTP 405 Required status check '<name>' is expected` even when the PR's CI is fully green. Result is admins forced into a `DELETE enforce_admins → admin-merge → POST enforce_admins` toggle-dance on every merge.

## The pattern

1. **Add a single summary job** to the workflow whose contexts protection should gate on. Put it last:
   ```yaml
   required-checks:
     name: required-checks            # explicit; this string IS the published context
     runs-on: ubuntu-latest
     needs: [job-a, job-b, ...]       # every other top-level job in the workflow
     if: always()                     # publish failure context, not 'skipped'
     steps:
       - name: Assert all required jobs succeeded
         uses: actions/github-script@v9
         with:
           script: |
             const needs = ${{ toJSON(needs) }};
             const failed = Object.entries(needs)
               .filter(([, job]) => job.result !== 'success')
               .map(([name, job]) => `${name}=${job.result}`);
             if (failed.length > 0) {
               core.setFailed(`Required upstream jobs did not all succeed: ${failed.join(', ')}`);
             } else {
               core.info('All required upstream jobs succeeded.');
             }
   ```
   - `if: always()` matters: without it, the summary is `skipped` when an upstream job fails, and a `skipped` check does not satisfy protection , but it also doesn't *fail* it, so the PR sits forever.
   - Filter on `result !== 'success'` (not `=== 'failure'`) so `cancelled` and `skipped` also fail the contract.
   - Use kebab-case for the job `name:` , branch-protection contexts shouldn't carry spaces if you can avoid it.

2. **Operator handoff (post-merge, by a different agent than the PR author):** after the PR merges, swap the protection contract:
   ```bash
   gh api --method PATCH \
     repos/<owner>/<repo>/branches/main/protection/required_status_checks \
     --raw-field 'contexts[]=required-checks' \
     --field 'strict=true'
   ```
   This must be a separate step *after* merge because branch-protection is repo-state, not branch-state , the PR cannot modify the rule that gates its own merge.

3. **Bootstrap cost:** the PR introducing the summary job itself still needs one final `enforce_admins` toggle-dance to merge, because protection still requires the *old* (broken) context until the PATCH lands. Document this in the PR body so the operator isn't surprised.

## Forward gotcha (binding on all future contributors)

**Every new top-level job added to the workflow MUST be appended to the summary's `needs:` list.** Otherwise the summary publishes success while the new job runs ungated by protection. Reviewers of any PR that touches the workflow file own this check.

## Why this beats the alternatives

| Option | Verdict | Reason |
|---|---|---|
| List every matrix context in protection | ❌ brittle | Every matrix dimension change (add Python 3.13, drop macOS) silently breaks merge. |
| Rename a job to match the existing context | ❌ couples | Protection contract becomes a generic, easy-to-rename job name with no aggregation guarantee. |
| Drop `required_status_checks` entirely | ❌ unsafe | Lets red CI merge. |
| **Summary job (this skill)** | ✅ stable | One contract; matrix-invariant; cost is one extra runner-minute per PR. |

## Pitfall: workflow-level `name:` is not a check context

A common cause of this bug is assuming `name: CI` at the workflow root publishes a `CI` check. It does not , only **job** names (with matrix expansion) are published as check contexts. Branch-protection that references the workflow name will never be satisfied.

## Provenance

- FinOps-assessment issue #51 / PR #52 (2026-05-12). The bug surfaced after #47/#48 made the review-count rule async-friendly via `squad-approve.yml`; the broken `"CI"` context was the last remaining trigger for the toggle-dance. After this skill's pattern landed, all subsequent squad PRs became fully async-mergeable.
