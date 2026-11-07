# Decision log

Append-only log kept by the orchestrator during execution. Do not rewrite or delete earlier entries; add a new one at the bottom.

This is not the planning snapshot. Current decisions are in [decisions.md](decisions.md). Hard-to-reverse trade-offs also have an ADR in [adr/](adr/).

Each entry records:

- **When** — time in EET
- **Decision** — what was decided
- **Why** — the reason, in a sentence
- **Evidence** — pointer to the artefact (a file, a release folder, a `pets-eval` run)

## Entries

### Sat 08:20 - STATUS SUMMARY (D16 08:30 checkpoint; only non-append exception)

- **Done:** 50 issues closed. All spec tickets 01-22, 24, 26, 27, 28 and 30 are merged. **Story kit (22) merged `15b2a42` at ~07:50 and integration merged into `main` (`f8665e2`, full suite 2230 passed).** The HEALTH-S1 real-kit release passes the gate (40/40), both verify tiers and pets-eval (composite 0.9695, privacy 1.0, utility 0.9352). Must-fixes merged since 06:00: #52, #55, #57, #58, #59, #60, #64, #70, #75, #76, #82, plus #48.
- **In flight:** 23 CS-S1 (fixture release green; real-kit gate still refuses on the secret/username checks, owned by #53 r3 and #54 r3, and on #92 split secrets); 25 search (HEALTH-S1 search release passes; re-merging 24's final head); 29 packager (approved; Merge after 23/25); 31 LLM (side lane, 14:00 gate); must-fix wave #61/#62/#84/#71 (in review), #63 (approved; merges after 23), #56 (after #53), #92 (after #54); follow-ups #67/#68 (review), #72-#74, #77/#79.
- **Parked / human:** #33-#39 (human tasks).
- **Critical path:** CS-S1 (23) is now the critical path, with 25 and 29 merging after it. Search go/no-go is at 12:00: 25 is green for HEALTH-S1 and its CS-S1 part depends on 23.
- **Risks:** (1) Reviewer capacity: `opencode-go` (Gemini, Luna) and the opencode free tier (DeepSeek, GLM) are over quota; Sol is back since 08:06 after an auth expiry; only Grok + Sol remain. (2) CS-S1 gate secrets/usernames: the gate and redactor rules are converging, but both are in their 3rd and final review round. (3) The open rule-audit follow-ups (#65, #66, #69, #78, #80, #81, #83, #85, #87-#91, #93, #94) run only on spare capacity unless they touch fail-closed or leak behaviour.

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

### Sat 05:50 — D13c quality recovery applied; merges up to 16 and 22 part A

- **When:** Sat 05:50–06:00 EET
- **Decision:** (1) Applied D13c (human instruction): must-fix follow-ups #41, #42, #44, #45, #47, #50 before the 20:00 freeze, each delta-reviewed by `xai/grok-4.7#medium` **and** `opencode-go/gemini-4-argon#medium`; numbers tickets 18, 19, 22, 25, 29 get two reviewers. #44 was pulled from the merge queue (Grok-approved, not yet Gemini) — the merger had merged it locally and reset before pushing, so nothing landed. #41 had already merged on Grok alone, so it gets a retroactive Gemini delta review; same for 18, 19 and 22 part A. Gemini dispatched on #41, #42, #44, #45, #47, 18, 19, 22A; #50 fix dispatched (Sonnet). (2) Merged since 05:35: 05 `b148908`, 11 `b48ec2d`, 08 `6422758`, 09 `4c69eb1`, 02 `9914409`, 18 `65e4e37`, 19 `4da22de`, 10 `c26c9ed`, 12 `e1222fd`, 13 `5fae780`, #40 `abf7ad9`, #41 `f23ece7`, 17 `5caec51`, 16 `afd62da`, 22 part A `5f17654` — each with the full suite green on the merged result (last: 1862 passed, 3 skipped). All blockers of ticket 21 are merged. (3) 17's first merge attempt failed 3 tests once 11's producer checks were registered; fixed in tests only, re-reviewed, merged. (4) Follow-ups filed: #47 (05/11), #48 (08/09), #49 (18/19), #50 (12/13/17 incl. 13's lexicon encoding damage and the 02 fixture's unregistered check claim). (5) Ticket 08's leftover worktree has an uncommitted edit to another ticket's file (`redaction_eval/__init__.py`) from an unknown session — left in place, not force-removed; flagged for a human.
- **Why:** Human instruction (planning session); the critical path 21 → 22 now has every dependency merged.
- **Evidence:** issue done-reports #2–#21 (closed); `git log --merges origin/integration/pets-release`.

### Sat 06:20 — D13d: GPT-6.1 Sol back; ticket 21 merged; CS-S1 gate blockers; H-U4 sacrifice accepted

- **When:** Sat 06:00–06:20 EET
- **Decision:** (1) D13d: the GPT-6.1 Sol quota reset (probe script). Core tickets and numbers code (18, 19, 22, 25, 29) now get `xai/grok-4.7#medium` + `openai/gpt-6.1-sol#high`; final whole-branch review is Sol + `opencode-go/gemini-4-argon#medium` plus an AGENTS.md rule audit; ≤ 4 concurrent Sol sessions; on a usage-limit error fall back to Luna and log it. Dispatched: Sol on must-fix #52 (with Grok), and retroactive Sol reviews of 05, 11 and 02's final delta (their second review was Luna-only). 24's Luna review was already running and finishes as is. (2) Ticket 21 merged (`5ddf33c`) on Grok + Luna approvals: real-kit HEALTH-S1 release passes the gate (40/40), both verify tiers, suppression 0.0994 ≤ 0.10, per-person k min 5, byte-identical runs; #43 merged on top (`93d61a6`) with no run test broken. Must-fix #41, #42, #44, #45, #47, #50, #51 merged (each Grok + Gemini). (3) Ticket 23's real-kit dry run: the CS-S1 gate refuses on `rescan.secrets` false positives (cued everyday words) and redactor misses — filed must-fix #53 and #54 (fixes dispatched); #55 (verify status mismatch) dispatched. The kit's `turn_id` is in exact conversation order, so 23 pseudonymises it (fallback plan). (4) Accepted ticket 24's search waiving H-U4 at 0.795 after local suppression: H-U4 is a policy-enumerated sacrifice (floor 0.6 via `municipality`), it passed fully before suppression and its via column is coarser than its floor; errors and non-enumerated checks are never waived. Consequence: the hand plan's post-suppression scores must be measured (22 part B) — the story kit shows the suppressed release's scores, never pre-suppression ones. (5) #49 is covered by #51 + #52 (no separate fixer). (6) The server restarted at ~06:00; dead sessions (24's evidence run, the #50 fixer) were resumed in their own sessions.
- **Why:** Human instructions (D13d probe; planning-session notes); critical path 21 → 22 part B.
- **Evidence:** #22 done-report; ticket 24 summary (aggregate, outside the repo); issues #52–#55.

### Sat 06:25 - orchestrator hand-over; 25 and 29 started early

- **When:** Sat 06:25 EET
- **Decision:** (1) New orchestrator session claimed the heartbeat (watchdog fresh start). The previous orchestrator was still mid-turn, so it was interrupted to keep a single orchestrator; its child sessions (22B, 23, 28, #48, #53, #54, #55 implementers; reviews of 24, 26, 27, 30, #52; Sol retro reviews of 02, 05, 11) keep running and are polled by the new orchestrator. (2) Started 25 search (Opus, branched from the integration tip plus `ticket/24-minimiser`) and 29 submission packager (Sonnet) with blockers 23/24/25 treated as Merge after, as done for 16-19 and 22-30. 31 LLM front end held until the CS-S1 release is closer (14:00 gate).
- **Why:** Single-orchestrator rule; search must be merged and green before the 12:00 go/no-go.
- **Evidence:** heartbeat session id; sessions ses_e4bc63baeffeeZDM3tV2LSuEtI (25), ses_e4bc62164ffeTrHVrIiB0DgHAV (29).

### Sat 06:55 - merges 26, 27, 30, #55, #48; #52 weighting rule; opencode-go quota out

- **When:** Sat 06:30-06:55 EET
- **Decision:** (1) Merged 26 `7c8ecdb`, 27 `8451969`, 30 `297356b`, #55 `7afa590`, #48 `06a0d79`, each with the full suite green on the merged result (last: 2062 passed, 8 skipped); issues closed, worktrees and branches removed. (2) Sol retro reviews: 02 delta APPROVE; 05 and 11 CHANGES (4 + 3 high), filed as must-fix #56 (text checks; merges after #53, same files) and #57 (producer checks; fix in review). (3) #52: `k_below_5_share` becomes row-weighted, with the max exported as `k_below_5_worst_table`. The real HEALTH-S1 after-scorecard has a released table with no k rate, so the share is weighted over the tables the scorecard scores for k, with the weighted table list recorded and fail-closed checks kept. Story kit 22B waits on this to rebuild. (4) Model switch: `opencode-go` returned "Go usage limit exceeded" (Luna on 24, Gemini on #57). Second reviewers move to `openai/gpt-6.1-sol#high` (non-Claude, non-Grok; at most 4 concurrent). Gemini's earlier #53/#54 verdicts stand. (5) 25 search: the HEALTH-S1 search release passes gate, both verify tiers and pets-eval (composite 0.9661 vs hand 0.9695); it is re-merging 24's fix before review. CS-S1 search waits on 23.
- **Why:** Clear the merge queue; judge-facing numbers must match their labels; keep two-family reviews when a provider is out.
- **Evidence:** issues #27, #28, #31, #48, #55 done-reports; review sessions ses_e4b9cbd15ffeDcjBDL4D9o1WHh and ses_e4b9c7341ffesDN6Q1tRgDa7dE (error); #56, #57.

### Sat 07:10 - Sol auth expired; DeepSeek free as second reviewer; must-fix wave dispatched; CS-S1 decisions

- **When:** Sat 07:05-07:10 EET
- **Decision:** (1) `openai/gpt-6.1-sol` now fails with "authentication token is expired" (probe confirmed), and `opencode-go` is over its quota. D13f (human, 07:20 per AGENTS.md) asks for Grok + Sol on every ticket. Until Sol is re-authenticated (#86, ready-for-human), the second reviewer is `opencode/deepseek-v4.1-flash-free` (a non-Claude, non-Grok family that answered the probe). Reviews already returned stand. (2) Must-fix wave from final-review and rule-audit pass 1, dispatched as six implementers grouped by owned files: #59+#60+#58 (verify/run), #61+#62+#84+#71 (producer/context/writer; branched from #57, merges after it), #63 (CS contract), #64+#82 (kiteval/offline guard), #75 (attacker), #70 (detect test). #56 waits on #53 (same files). (3) CS-S1 real-kit gate blockers: the `ipAddresses` assertion stays strict; the CS-S1 release (not the eval redaction file, which follows the gold convention) also redacts private IPs. The redactor's HEALTH coverage is aligned to the gate's own lexicon (redactor matches its independent checker; no kit-derived words). A missing `healthInTextRequired` must fail closed (added to #56). (4) Ticket 23 was continued in a fresh session, because inherited sessions can't be messaged.
- **Why:** Keep two-family review while two providers are down; clear the fail-open findings before the freeze; make the CS-S1 release pass without weakening an assertion.
- **Evidence:** probe sessions ses_e4b9b9571ffe8yYDuBvWr5C0qi (Sol, error) and ses_e4b9b922effebMm9j3PKLh68rm (DeepSeek free, ok); issues #56, #58-#64, #70, #71, #75, #82, #84, #86.

### Sat 08:05 - story kit merged; ticket 24 merged; merges #52, #70, #75/#76, 28

- **When:** Sat 07:15-08:05 EET
- **Decision:** (1) Ticket 22 (story kit, #23) merged `15b2a42` on Grok + DeepSeek approvals (round 3), full suite green on the merged result (2192 passed, 8 skipped). The real-kit HEALTH-S1 release passes both verify tiers, and the story kit is in the out folder. Integration → main merge dispatched (§2 checkpoint). (2) Ticket 24 minimiser merged `faa726c` (round 3, Grok + DeepSeek). Its worktree is kept because 25 builds on it. (3) Merged #52 `d902df0`, #70 `6f6bae6`, #75/#76 `6559731`, 28 `dee7d18`. Follow-up #91 filed. (4) #64/#82 approved, but the merge failed (an import conflict and the new `measure.wire` entry point is not offline-guarded); sent back. #61 wave: Grok found two high fail-open paths in the manifest value scan (unscanned count fields; `bindings`/`signature` skipped wholesale); sent back. (5) #63 approved by both reviewers. It merges after 23, because its branch carries 23's commits. Stitching surfaces 95 split-secret hits in CS-S1, filed as must-fix #92 (redactor, after #54). (6) 29 packager approved by both reviewers; it waits on 23/25 (Merge after).
- **Why:** Story kit checkpoint; clear the merge queue.
- **Evidence:** #23, #25, #29, #52, #70, #75, #76 done-reports; `git log --merges origin/integration/pets-release`.
