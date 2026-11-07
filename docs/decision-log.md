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

### Sat 03:05 — DeepSeek is the review bottleneck; superseded reviews cancelled; static-guard scope for 15

- **When:** Sat 03:05 EET
- **Decision:** (1) DeepSeek reviews take 25+ min each and ~20 ran at once, many for heads already superseded by fix rounds; interrupted the 11 superseded DeepSeek sessions so current-head reviews get capacity. Rule from now on: a review is dispatched only for a ticket's current head; the old-head review is cancelled when a fix lands. (2) Ticket 15's import guard was turning into an arms race with reviewers (aliases, constants, allowlisted files). Replaced with two simple fail-closed guards (static text rule + runtime import/audit-hook check); runtime-computed import names are a stated residual risk. (3) Ticket 12's implementer tuned rules from frequent kit tokens (seen in ≥10 conversations, no row values displayed): accepted once as aggregate-level; no further tuning from kit-derived tokens. (4) Ticket 08: some "not evaluated" scorecard results are benign for our releases (no released QI overlaps adversary knowledge; text table withheld) and are accepted only from an explicit reason-code allowlist and reported as not_applicable.
- **Why:** Keep the merge pipeline moving toward the Sat 09:00 story kit; avoid unbounded hardening of a validation-only guard.
- **Evidence:** session interrupt responses ×11; review verdicts in the ticket threads once closed.

### Sat 02:48 — review convergence rule; first merges

- **When:** Sat 02:48 EET
- **Decision:** (1) Review rounds were not converging (each GPT round finds a new edge case). From the next round on, a reviewer returns CHANGES REQUIRED only for high-severity defects that break an acceptance criterion, the fail-closed rule, or leak values; everything else is listed as non-blocking and filed as a follow-up issue at merge. (2) Merged 14 (`0008cdc`, 22 tests green) and 01 (`83efaa0`, 62 green); follow-ups #40 and #41 filed; ticket 20 (detector, #21) dispatched on Sonnet once 01 landed. (3) 02 now merges after 04, because the assertion→check binding is enforced by importing 04's map (no duplicated table, no "when importable" fallback).
- **Why:** Sat 09:00 story kit needs 04/06 → 16/17 → 21 → 22; endless rounds on non-critical edges put that at risk.
- **Evidence:** #15 and #2 done-reports; follow-up issues #40, #41.

### Sat 02:53 — model switch: GPT reviewer → xai/grok-4.7#medium

- **When:** Sat 02:53 EET
- **Decision:** `openai/gpt-6.1-sol` returned `subscription_sharing_usage_limit_exceeded`. New ticket reviews pair `opencode-go/deepseek-v4.1-flash` with `xai/grok-4.7#medium` (a third family, not Claude, so still independent of every implementer). GPT reviews already returned stay valid for their heads. Retry GPT for the final integration `/code-review` if the limit has reset.
- **Why:** Two-family review is mandatory; Grok is the roster's remaining non-Claude family.
- **Evidence:** 08 r5 GPT review session error.

### Sat 03:00–03:40 — merges 06, 07, 15; network outage; recorded deviations

- **When:** Sat 03:00–03:40 EET
- **Decision:** (1) Merged 06 (`6f58567`), 07 (`910a80a`) and 15 (`900dd8b`), each with the full suite green on the merged result (141 / 250 / 320 passed); follow-ups #42, #43, #44. (2) Accepted ticket 06's 5-field token message (adds scope kind to the spec's 4 fields): stricter domain separation, documented and pinned by test. (3) Rejected a DeepSeek "blocker" on 04 (files deleted vs integration) after a trial `git merge-tree`: the merge adds 43 files and deletes none; the branch was only behind. (4) A DNS outage killed 9 review sessions and 04's fix session; all re-dispatched after DNS recovered, 04 resumed in its own session. (5) Ticket 20's implementer self-reported briefly viewing part of a field-catalog-derived doc (the detect answer key) before realising; no answers hard-coded; its health macro-F1 is flagged optimistic and the other datasets treated as the held-out signal. Reviewers told not to open those files. (6) HEALTH-S1 hand plan misses k=5 per person (DeepSeek on 09); 09 is measuring per-person k with ticket 11's check and may add a deterministic local-suppression policy field for ticket 21 (D10 "suppression last").
- **Why:** Keep the critical path moving and record judgment calls.
- **Evidence:** #7, #8, #16 done-reports; `git merge-tree --write-tree` diff (A 43 / D 0).

### Sat 05:15 — time correction; 16/17/18/19 started before 02/04 merge

- **When:** Sat 05:15 EET
- **Decision:** (1) Correction: the DNS outage lasted ~2 h (about 03:00–05:10 EET); the previous entry's "03:00–03:40" range is wrong — the merges were ~03:00, the re-dispatch ~05:10. (2) With under 4 h to the Sat 09:00 story kit and 02/04 still in final review, started 16 (writer, Opus), 17 (verify, Opus), 18 (dashboard, Sonnet) and 19 (measurer, Sonnet) now, branched from 02's head (which contains 04) and, for 19, 08's head. They merge only after 02/04 (and 08) merge; implementers merge the final sibling heads before reporting. This bends "Blocked by" to "Merge after" for these four.
- **Why:** The critical path 04 → 16/17 → 21 → 22 cannot fit in the remaining time if 16/17 wait for two more review rounds on 02/04; both upstream APIs are stable and only final-round changes are pending.
- **Evidence:** heartbeat timestamp 03:12 UTC; worktrees `ticket/16-writer`, `17-verify`, `18-dashboard`, `19-measurer` based on 67ef441.

### Sat 05:22 — human instruction: six blocked tickets started early

- **When:** Sat 05:22 EET (applied 05:30)
- **Decision:** Per Kivaste (planning session): started 24 minimiser (Opus), 28 recipient keys (Sonnet), 27 determinism/offline tests (Sonnet; tests needing 21's `run` explicitly marked and listed), 30 README draft (Sonnet), 23 CS-S1 glue + fixture tests (Opus; real-kit e2e after 21), 22 part A story-kit script and numbers template keyed to manifest paths (Sonnet; part B blocked on 18/19/21). Blockers treated as Merge after only; each merges after its blockers close with the full suite green on the merged result. Implementer count ~12, under the cap; `pytest -n 8` (CPU 31–43%).
- **Why:** Machine headroom and time pressure; pinned contracts make parallel work safe.
- **Evidence:** worktrees `ticket/{24-minimiser,28-recipient-keys,27-determinism,30-readme,23-cs-s1,22-story-kit}` at 6675731.

### Sat 05:30 — k in the contract; hour-of-day rung; 08 identity-data check

- **When:** Sat 05:30 EET
- **Decision:** (1) The release contract carries the scenario's k target (`k`, from the policy) so recipient verify can re-run `producer.row-k` from the release alone; 10 emits it, 02's schema accepts it, 11 reads it. CS-S1 (no k target) handling is assigned to ticket 23. (2) Added rung `ts.hour_of_day` (ticket 07b, date-free `HH:00`): ticket 09 measured per-person k on the kit — with existing rungs the best HEALTH-S1 hand plan keeping all required tasks leaves 55% of persons below k=5, and suppression alone would remove 71% and break H-U4; hour-of-day gave ~4.5% below k with all tasks 1.0, within the policy's 10% suppression cap. (3) Ticket 08 decides "linkage expected" via pets-eval's own identity-data loader (in memory, yes/no only, never kept or exported) instead of building a truth/ path; recorded as a scoped exception to "only the attacker reads truth", because it is the kit evaluator's own loader used for the scorecard's coverage check.
- **Why:** Story-kit release must pass the producer k gate; recipient verify must be re-runnable; the boundary guard must hold on the merged tree.
- **Evidence:** 09's per-person k table (aggregate, ticket thread on merge); 07b scorecard H-U2…H-U8 all 1.0 with `arrival_ts` at `ts.hour_of_day`.

### Sat 05:35 — D13b lighter reviews applied; merges 03, 07b, 04, 20

- **When:** Sat 05:35–05:45 EET
- **Decision:** Applied D13b: core tickets reviewed by `xai/grok-4.7#medium` + `opencode-go/gpt-6-luna#medium`, routine tickets by Grok only; round 2+ are delta reviews; max 3 rounds, then only high-severity blocks; ≤ 8 concurrent reviews per provider. Interrupted all 16 in-flight DeepSeek reviews (including core ones; Luna dispatched as the second core reviewer instead, so no core ticket lost its second review). Routine tickets whose current head already had a Grok approval merged at once: 03 (`244e278`) and 07b (`c411162`). 04 merged (`6dcb187`) on Grok r4 + Luna delta (`a4144a2..2781778`, no findings) + earlier GPT r3 approval. 20 merged earlier (`d0b0386`). Follow-ups #45 (20) and #46 (03) filed. Decision for writer/verify: `bindings.inputs` binds every table of the scenario's dataset (withheld included) and `verify --full` requires exact equality.
- **Why:** Human instruction (planning session, Sat 05:35); DeepSeek reviews took 25+ min and were throttled; the critical path needs merges now.
- **Evidence:** #4, #5, #21 done-reports; Luna verdicts on 02/04/05/11/12 (APPROVE) and 16/17 (CHANGES, sent back).
