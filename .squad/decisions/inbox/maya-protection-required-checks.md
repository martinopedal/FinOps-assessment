### 2026-05-12 — Required-checks summary job replaces "CI" context (issue #51)

**By:** Maya (Lead / FinOps PM)

**Decision:** Replace the brittle branch-protection contract `contexts: ["CI"]` with a single summary job that publishes the literal context `required-checks`. The job lives at the end of `.github/workflows/ci.yml`, `needs: [lint-and-test, catalog-validation]`, runs `if: always()`, and asserts every upstream `needs.*.result == 'success'` via `actions/github-script@v9` — failing the summary (and therefore the protection check) if any matrix shard or sibling job failed or was skipped.

**Why this matters:** Branch protection required the context name `CI`, but `name: CI` at the workflow level is *not* a published check context — only job names (and matrix expansions) are. So `gh api PUT .../merge` returned `HTTP 405 Required status check 'CI' is expected` on every squad PR (#46, #48, #50) even with all checks green. This was the last remaining trigger for the `enforce_admins` toggle-dance after #47/#48 made review-count async-friendly.

**Trade-offs considered:**
- **Option A — list every matrix context in protection** (`Lint, type-check, test (ubuntu-latest / py3.11)` × 6, plus `Validate YAML catalog & rules`): strongest correctness, but every matrix dimension change (add Python 3.13, drop macOS, etc.) silently breaks merge until protection is re-edited. Rejected on brittleness.
- **Option B — summary `required-checks` job** (chosen): one stable contract; matrix changes invisible to protection; cost is one extra runner-minute per PR. The `if: always()` + explicit `needs.*.result` check is the canonical GitHub Actions summary-job idiom and handles `failure`, `cancelled`, and `skipped` correctly (only `'success'` passes).
- **Option C — rename a job to `CI`**: cheapest but couples the protection contract to a generic, easy-to-rename job name and gives no aggregation guarantee. Rejected.
- **Option D — drop `required_status_checks` entirely**: lets red CI merge. Rejected outright.

**Operator handoff (Coordinator, post-merge):** After this PR merges to `main`, swap the protection contract:

```
gh api --method PATCH \
  repos/martinopedal/FinOps-assessment/branches/main/protection/required_status_checks \
  --raw-field 'contexts[]=required-checks' \
  --field 'strict=true'
```

Until that PATCH lands, this PR itself still requires one final `enforce_admins` toggle-dance to merge — it is the bootstrap cost, identical in shape to the #47/#48 cutover. All subsequent squad PRs become fully async-mergeable: open → squad label → Stage-4 Noor verdict comment → bot approval → all-green CI → `gh pr merge --squash` (no `--admin`, no toggle).

**Forward gotcha (binding on every future contributor):** Every new top-level job added to `.github/workflows/ci.yml` MUST be appended to the `required-checks` job's `needs:` list. Otherwise the summary will report success while the new job runs ungated by branch protection. The §11 Stage-4 reviewer is responsible for catching this on any PR that touches `ci.yml`.

**Related:** issue #47, #51; PRs #48 (auto-approve workflow), #50 (auto-approve inaugural test).
