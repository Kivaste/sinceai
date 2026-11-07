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

### Sat 02:40 — 07's rung IDs canonical; 14's held-out split at turn level

- **When:** Sat 02:40 EET
- **Decision:** (1) Ticket 07's rung IDs and contract-form table are the single source; 09 (which invented its own IDs against a stub) is re-aligning before review, and 10/24 use the same. (2) Accepted ticket 14's deviation: the spec's conversation-level template hold-out yields 0 held-out conversations on the kit (every conversation shares a skeleton with another), so the default hold-out is per turn by skeleton hash (zero skeleton overlap by construction); the strict conversation mode stays available and its count is reported. Reviewers were told to judge leakage disclosure.
- **Why:** Two parallel tickets produced incompatible plan vocabularies; a hold-out set of size 0 measures nothing.
- **Evidence:** 14 harness run on the kit train split: 18.6% of turns held out, 0 skeleton overlap, 84 fully held-out conversations under the strict rule (aggregate report outside the repo).

### Sat 02:50 — incident: one kit row entered an implementer's model context

- **When:** Sat 02:50 EET
- **Decision:** Ticket 05's implementer (claude-agent/opus) printed the first line of a kit gold-span file to learn its format, so one turn's values entered that model's context. Nothing was written to a file, commit or message. Recorded as a breach of the AGENTS.md "never send data values to any LLM" rule; added an explicit "never display rows; inspect keys/counts only" rule to the shared implementer conventions and to reviewer prompts.
- **Why:** Self-reported by the implementer; the rule can't be undone, only prevented from recurring.
- **Evidence:** 05 done-report (content-free); conventions note section "Never look at row values".

### Sat 02:50 — text-check assertions and HEALTH-S1 text checks

- **When:** Sat 02:50 EET
- **Decision:** (1) Per-label export assertions stay bound to the `rescan.*` cell checks (02's one-check-per-assertion rule); `text.*` checks gate (refuse on hit) and appear in gate records but do not back assertions. (2) A release with no text column (HEALTH-S1) gives text checks denominator 0, which 04's runner records as error and refuses. Fix: a runner-level `not_applicable` status, allowed only when the contract declares no column of the check's unit, never backing an assertion. Done as a follow-up on 04's files after 04 merges and before 05 merges, so 04's review/merge on the critical path isn't restarted.
- **Why:** Keep 04 → 16/17 → 21 moving; without (2) every HEALTH-S1 release refuses once 05 lands.
- **Evidence:** 05 done-report parked items 1–2.
