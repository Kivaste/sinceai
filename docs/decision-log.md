# Decision log

Append-only log kept by the orchestrator during execution. Do not rewrite or delete earlier entries; add a new one at the bottom.

This is not the planning snapshot. Current decisions are in [decisions.md](decisions.md). Hard-to-reverse trade-offs also have an ADR in [adr/](adr/).

Each entry records:

- **When** — time in EET
- **Decision** — what was decided
- **Why** — the reason, in a sentence
- **Evidence** — pointer to the artefact (a file, a release folder, a `pets-eval` run)

## Entries

### Sat 00:15 — planning interview complete; see docs/decisions.md D6–D17

- **When:** Sat 00:15 EET
- **Decision:** Planning interview complete; see [docs/decisions.md](decisions.md) D6–D17.
- **Why:** Lock team, scope, stack, process and checkpoints before spec and tickets.
- **Evidence:** [docs/decisions.md](decisions.md) D6–D17; ADRs [0001](adr/0001-merge-pattern-engine-with-purpose-first-framing.md), [0002](adr/0002-llm-never-sees-data-values.md), [0003](adr/0003-row-maps-only-in-separate-private-repo.md).

### Sat 01:05 — spec reviewed by three model families; decisions D18–D23

- **When:** Sat 01:05 EET
- **Decision:** Spec draft reviewed independently by claude-agent/sonnet, openai/gpt-6.1-sol and opencode-go/deepseek-v4.1-flash (42 findings). User decided two-tier verify, per-label assertions, signed manifest, conditional turn_id, `age_band`, scope trims (D18–D23). Spec is being revised against all findings.
- **Why:** Reviews found contradictions between "verify re-derives everything" and fail-closed, overclaiming identifier assertions, and kit facts (CS-U1 retrains sklearn, CS-U5 keys on turn_id, CS-U4 string parsing) that would have broken parallel tickets.
- **Evidence:** `.scratch/local-spec/review-{sonnet,gpt,deepseek}.md` (local, not committed); [decisions.md](decisions.md) D18–D23.

### Sat 02:01 — overnight orchestrator started; 15 frontier tickets dispatched

- **When:** Sat 02:01 EET
- **Decision:** Fresh orchestrator start (no prior run). Cut `integration/pets-release` from `origin/main` (f23d60d). Dispatched implementers for all 15 unblocked tickets (01–15; issues #2–#16): opus tickets on `claude-agent/opus`, grok tickets on `xai/grok-4.7#high`, each in its own worktree. Pinned a shared package layout (`src/pets_release/<subpkg>/`, attacker as separate `pets_attacker`) in an out-of-repo conventions note so parallel tickets do not collide. Installed pytest-xdist, jsonschema, jinja2 and ruff into the shared venv up front to avoid concurrent pip runs. CPU at dispatch ~7%, so `pytest -n 8`.
- **Why:** All 15 are startable now (0 open blockers), under the 16 cap; critical path 04 → 16/17 → 21 → 22 needs 02/04/06/07/09/10/11/01/03 merged before 21.
- **Evidence:** `gh api repos/Kivaste/sinceai/issues/<n> --jq .issue_dependencies_summary.blocked_by` = 0 for #2–#16; `git worktree list`.

### Sat 02:15 — D13a applied: grok tickets moved to Sonnet; GPT + DeepSeek review everything

- **When:** Sat 02:15–02:30 EET
- **Decision:** Applied the user's D13a roster change. Of the 9 grok implementers dispatched at 02:01, 8 had no commit (01, 03, 07, 08, 09, 13, 14, 15): interrupted them via the session API and re-dispatched on `claude-agent/sonnet` from the new integration tip (01 first). Ticket 10 had one local commit, so it keeps running on grok and is re-dispatched only if silent for 30 min. Clean worktrees (07, 09, 13, 14) were removed and re-created; 01, 03, 08 and 15 had untracked partial files, so instead of `--force` removal their (commit-less) branches were fast-forwarded to the tip and the new implementer owns the leftovers. Merged `origin/main` (watchdog fix, D13a docs) into the integration branch (bc45db0). Reviews from now on are `openai/gpt-6.1-sol` + `opencode-go/deepseek-v4.1-flash`; the Sonnet review of 02 is superseded by a GPT review.
- **Why:** User instruction via the planning session (Grok 4.7 high too slow); Sonnet is the same family as Opus, so it cannot review Claude-written code.
- **Evidence:** [decisions.md](decisions.md) D13a; `git worktree list`; session interrupt responses `{"interrupted":true}` ×8.

### Sat 02:25 — pinned gate-check naming and registration across 02/04/05/11

- **When:** Sat 02:25 EET
- **Decision:** 04's `@register` API is the one registration path; check names follow 02's schema pattern (lower-case dot/kebab, semver versions); 04 exports the assertion → check-name map. Sent to 04 (with its GPT review fixes), 11 and 05.
- **Why:** GPT review of 04 found 11's checks would never be discovered (blocker) and 04's camelCase names fail 02's schema.
- **Evidence:** GPT review of 04 at a47edff (CHANGES REQUIRED: 1 blocker, 4 major); out-of-repo conventions note, section "Gate-check naming and registration".
