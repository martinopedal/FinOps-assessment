# Maya History

## 2026-05-13 — v0.6.0 backlog: Two parallel stage-3 plans

**Issues:** #74 (reporter template overlay), #75 (squad routing + Scribe-after-Stage-4)  
**Mode:** Full §11 delivery loop (stage 1–3 plan by Maya)  
**Outcome:** Both plans merged (PR #97 bbf2a39, PR #96 7a9bf0e) after Noor APPROVE-WITH-CONDITIONS

### Issue #74 Plan (PR #97, stage-3)
- **Plan:** Reporter template overlay system design
- **Scope:** SandboxedEnvironment + FileSystemLoader + AST walker (rejects Include/Import/FromImport) + per-template SHA-256 manifest
- **Stage-3 gate:** Noor APPROVE-WITH-CONDITIONS (3 security conditions: AST walker scope, sandbox isolation, manifest validation)
- **Disposition:** All 3 conditions addressed in PR #101 impl by Diego (final SHA 59f96d1)
- **Follow-ups filed by Noor:** #102, #103 (architectural refinements, non-blocking)

### Issue #75 Plan (PR #96, stage-3)
- **Plan:** Squad routing rules + Scribe-after-Stage-4 pattern
- **Scope:** Updated `.squad/routing.md` (+40/-1); deferred-verdict pattern; rules 2 + 2a for Scribe post-stage-4 authority
- **Stage-3 gate:** Noor APPROVE-WITH-CONDITIONS (2 conditions: residual-risk section, self-application clarity)
- **Disposition:** Both conditions addressed in PR #100 impl by Yuki (final SHA 8bdf1b1)
- **PR readiness:** Yuki left #100 as draft — Diego noted in session: call `gh pr ready` before signaling done (procedure improvement)

**Session note:** Both plans were reviewed on the same day by Noor stage-4. Force-push collisions from parallel agent branches required surgical cleanup by coordinator. Future fan-outs should use `git worktrees` to avoid branch collision friction.
