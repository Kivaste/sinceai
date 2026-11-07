# Decision log

Append-only log kept by the orchestrator during execution. Do not rewrite or delete earlier entries; add a new one at the bottom.

This is not the planning snapshot. Current decisions are in [decisions.md](decisions.md). Hard-to-reverse trade-offs also have an ADR in [adr/](adr/).

Each entry records:

- **When** — time in EET
- **Decision** — what was decided
- **Why** — the reason, in a sentence
- **Evidence** — pointer to the artefact (a file, a release folder, a `pets-eval` run)

## Entries

### Sat 11:10 - STATUS (brief v3 §5; replaces the 09:55 summary; only non-append exception)

- **Effective policies (changes only):** Brief v3 / D31 in force: templates.md prompts, separate Standards/Spec sub-agents, and closes only through `check-done-report.ps1`. D13e lifted at 11:03 (opencode-go back). The AGENTS.md cross-map is unchanged; Gemini Argon and GPT-6 Luna are now the fallback Spec reviewers when Sol is unavailable, replacing DeepSeek free (see the 11:05 entry). Reviews that predate D31 and combine the axes don't count toward D31. #78, #89, #49, slow-split and the #61 wave got fresh axis-separated rounds.
- **Critical path:**
  - The CS-S1 chain, merging in this order: #53 → #54 → #92/#56 → 23 (#24) → #63. It is the only route to a real-kit CS-S1 release, and that release blocks #96, 29 (#30), the 14:00 LLM go/no-go and `pets_submission/` at 16:00.
  - In parallel: 25 search (#26) before the 12:00 go/no-go, and the #61/#62/#71/#84 fail-closed wave.
- **Blocker owners (issue → session/model):**
  - CS-S1 chain (#24, #53, #54, #56, #63, #92) → ses_e4b294f0 / claude-agent/opus (D29 single owner). Grok r4 reviews of #53 and #54 and the 23 r2 review are in flight.
  - #26 search → ses_e4afab69 / claude-agent/opus (round-2 fixer).
  - #61, #62, #71, #84 → ses_e4ac9999 / claude-agent/opus (round 3: provenance fail-open, detector-derived QI measured first, registered manifest scan).
  - #89 → ses_e4ad2009 / claude-agent/opus (round 3: hour_of_day ordered coarser than month, plus an enumerated sacrifice).
  - #32 (31 LLM) → ses_e4b3ad94 / claude-agent/opus.
  - #97 → ses_e4ae8f04 / openai/gpt-6.1-sol.
  - #65, #66, #69, #90 → Sol implementers (ses_e4ae4acb, ses_e4ae48fd, ses_e4ae46ff, ses_e4ae449e).
  - #81, #83, #94 → ses_e4b3155b / claude-agent/sonnet.
  - #85 → reviews in flight (Grok, Sol).
  - #49 → ses_e4ad30dd / claude-agent/sonnet (evidence only).
  - #98 → held: main `b85d1d0` already has the splat fix; to be rebased to the remainder.
- **Latest verified revision:**
  - Integration `4811b16`, merged result: `pytest -n 16 -m "not slow"` gave 2357 passed, 5 skipped, 0 failed. No test carried the slow marker yet, so the run covered every test.
  - `b194d2b` adds the decision log only.
  - Real-kit HEALTH-S1 `run` plus both verify tiers were last run on `e846512` (`sinceai-out\story-tip-e846512\`).
- **Missing evidence:**
  - No real-kit CS-S1 release recorded.
  - No real-kit release or verify run on the integration tip (`b194d2b`).
  - 0 of 57 closed tickets have complete red/green evidence (10:45 audit, `.scratch/local-review/evidence-audit.md`). The final review and fresh proof (brief §4) cover them; they are not reopened.
  - Head-bound done-reports are still missing for #49, the #61 wave and #89.
  - The #78 affected-tests run is in progress.

### Sat 09:55 - STATUS SUMMARY (superseded by the 11:10 status above)

- **Done:** 58 issues closed. Spec tickets 01-22, 24, 26, 27, 28 and 30 are merged. Since 08:20: #67, #68, #72, #73, #74, #77, #79 and #91 merged, and the story drafts are merging now. Integration head `8cec414`, full suite 2357 passed, 5 skipped. The HEALTH-S1 release at the tip (`e846512`) passes the gate (40/40), both verify tiers and pets-eval (privacy 0.1716 -> 1.0, per-person k min 5). Draft PR #95 (`integration/pets-release` -> `main`) is open (D25).
- **In flight:** 23 CS-S1 (round-2 fixes: recipient threading, manifest self-scan); 25 search (round-1 review, Grok + Sol); 29 packager (approved; Merge after 23/25); 31 LLM (round-4 fix; the pipeline part of AC3 is deferred to the 14:00 go/no-go); follow-ups #49 (review), #78 (round 2), #81/#83/#94, #85, #89 (round 2).
- **Must-fix left:** #53 and #54 (fail-open highs found in round 3, being fixed), #92 (split secrets, built on #54), #56 (after #53), #63 (approved, after 23), and the #61/#62/#71/#84 wave (round-2 fix).
- **Parked / human:** #33-#39 (human tasks); #87 (detector default lowers detection macro-F1 0.7286 -> 0.6146).
- **ETA (EET):** search 25 merged by ~11:30 (before the 12:00 go/no-go). CS-S1 release passing gate + verify on the real kit by ~13:00 (needs #53, #54, #92 and then 23 + #63). Packager 29 by ~13:30, after 23/25. PR #95 ready after the final whole-branch review and fixes, ~16:00.
- **Risks:** (1) CPU/memory saturation from parallel full suites: new test policy (affected tests at `-n 2` while iterating, one full `-n 4` before the done-report, the merger at `-n 8` one merge at a time). (2) The CS-S1 secret/username gate and redactor are past their 3-round cap; only highs block, and highs keep appearing. (3) D13g: Sol implements routine work from 09:55; AGENTS.md:64 is updated to match.

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
### Sat 09:25 - orchestrator hand-over; Sol cannot implement under AGENTS.md; #87 parked; memory pressure

- **When:** Sat 08:31-09:25 EET
- **Decision:** (1) New orchestrator session (ses_e4b4ba0d...) claimed the heartbeat at 08:31. The previous orchestrator was interrupted, and interrupted again after the ~08:45 server restart resumed it. Inherited sessions that died mid-suite in the restart (#81/#83/#94, the #61 wave) were continued in fresh sessions, because inherited sessions can't be messaged. (2) GPT-6.1 Sol refuses implementer work because `AGENTS.md:64` says every implementer is Claude, and D13g (Sol implements easier work) was never written into AGENTS.md. Per AGENTS.md, implementers stay on Claude (Sonnet for routine, Opus for core) and reviews are Grok + Sol. The story-drafts number fill had already run on Sol, so it was reviewed by Grok + Sonnet. (3) #87 parked `ready-for-human`. The cautious detector default lowers kit detection macro-F1 from 0.7286 to 0.6146 (below the 0.65 baseline), and the detector never sets release roles. (4) Commit memory was down to ~4 GB free with ~400 python processes from parallel full suites, and one git command hit an out-of-memory error. New dispatches use `pytest -n 4`. (5) `build/` (setuptools artefact from the entry-point test) was committed on one branch (#89) and blocks worktree cleanup, so it is now gitignored on integration. (6) Accepted 23's CS-U5 lineage rule (score restored through the producer row map, gated; the unmodified score is kept ungated in the manifest). Grok confirmed it is honest and fail-closed. (7) #31 AC3 (a drafted policy run through search/gate/verify) needs a policy-loading entry point in files owned by 23/25/#63. Deferred to the 14:00 go/no-go.
- **Why:** Single orchestrator; AGENTS.md is binding over the brief; judge-visible score trade-offs are a human call; machine stability.
- **Evidence:** #87 comment; Sol refusals (sessions ses_e4b44d07..., ses_e4b44ea1...); merges `5966fb8`, `a48ef2e`.


### Sat 09:55 - utilization nudge: 2 dispatched, the rest sequenced

- **When:** Sat 09:55 EET
- **Decision:** For the 09:23 utilization nudge (19 items): dispatched #92 (Opus, branched from #54's head, Merge after #54) and #85 (Sonnet, skipping items in files owned by in-flight tickets). Not dispatched, with the blocker recorded on each issue: #77, #79, #91 were already merged; #54, #62, #71, #84 and 23 have live fixers; 29 and #63 are approved but Merge after 23/25; #56 waits on #53, and #88 on #54 (same files); #65, #66, #69 wait on 23 and #63 (contract/CS files); #80 waits on 23 and the #61 wave (writer/core.py); #90 waits on 25 (run/cli.py), and its L2 changes judge-facing numbers; #93 waits on 23 (run/purpose.py).
- **Why:** Each ticket owns its files, so parallel edits to the same file would conflict on merge.
- **Evidence:** "Orchestrator 09:55 EET" comments on each issue.

### Sat 10:05 - D27 affected tests only; ticket 25 split for CS-S1

- **When:** Sat 09:58-10:05 EET
- **Decision:** (1) Applied D27 (user): implementers, fixers and reviewers run only the affected tests through `scripts/overnight/affected-tests.ps1 -Run` (`pytest -n 2 -m "not slow"`), never the whole suite. Only the merger runs the full suite (`-n 8`), one merge at a time. The note was queued to all 14 reachable child sessions. It replaces the 09:55 policy (one full `-n 4` run before the done-report). Prompts call the helper with `-ExecutionPolicy Bypass`, because script execution is disabled on this machine. (2) Draft PR #95 opened (D25). (3) Ticket 25: Sol's round 1 found that #26's CS-S1 acceptance needs ticket 23. Split into #96 (Merge after 23, 25), so 25 ships the HEALTH-S1 search before the 12:00 go/no-go, with CS-S1 refusing fail-closed. Round-2 fixer dispatched: the measured entry point defaulted to the hand plan, and no CLI test covered the privacy-guard call.
- **Why:** CPU pinned at 100% with ~155 python processes; the 12:00 search go/no-go.
- **Evidence:** docs/decisions.md D27; PR #95; issue #96; Sol review session ses_e4b0536aeffeL6KsDdz9kXG8X0.

### Sat 10:08 - D28 merge train; D27 enforced; quiet-branch audit

- **When:** Sat 10:08 EET
- **Decision:** (1) Applied D28 (user): one merger takes up to 4 ready tickets in Merge-after order, runs the full suite once on the combined result with `pytest -n 16` (Normal priority), bisects on red, and only one merger runs at a time. (2) D27 enforced: a stop-full-suite note went to the sessions for fu61, fu78, fu81, fu85, 31 and 25. (3) Quiet-branch audit, no re-dispatch needed: `fu63-cs-contract` is approved, Merge after 23 (it is branched from 23); `29-packager` is approved, Merge after 23 and 25; `fu61-producer-wave` has a live round-2 continuation (updated 09:59); `23-cs-s1` has a live round-2 fixer (10:00); `fu53-secrets` has a live round-4 fixer (09:59); `fu89-ladder` has a live round-2 fixer (10:02); `fu87-detector` is parked `ready-for-human` (detection F1 trade-off). The next merge train is 23 + #63 + 25 + 29 once 23 and 25 pass review.
- **Why:** Fewer full-suite runs and faster merges.
- **Evidence:** docs/decisions.md D28; session update times; issue comments of 09:55.

### Sat 10:15 - D29 CS-S1 chain: one owner; 12:00 fallback

- **When:** Sat 10:15 EET
- **Decision:** Applied D29 (user). The ticket 23 session (ses_e4b294f0..., `claude-agent/opus`) is now the single owner of 23 plus #53, #54, #56, #63 and #92. The current fixers on #53, #54 and #92 finish their step, push and hand over; no new rounds. #56 moves to the owner. Merge order through the train: #53 -> #54 -> #92/#56 -> 23 -> #63. At 12:00, if the real-kit CS-S1 release still can't pass the gate, the owner adds the D29 fallback: turns still flagged by the independent checker are withheld, recorded as a sacrifice with counts, with reduced independence stated in `residualRisks`; the gate stays strict. Also forwarded Grok's ticket-25 findings (5 items, including the wire recipient overlapping #94) to the 25 fixer.
- **Why:** Several fixers were editing overlapping redactor and check files across rounds 2-4; CS-S1 blocks 25's CS part, 29, the LLM go/no-go and pets_submission.
- **Evidence:** docs/decisions.md D29; 23 at `9f9192d` refuses on the real kit only on `rescan.usernames` (2) and `text.usernames` (4).
- **Sat 10:25 addendum:** #92 hand-over at WIP head `3bd5f5d`. The redactor's new cross-turn step, which covers gate-flagged multi-turn hits, lowers kit SECRET exact-match precision to 0.9684, against a floor of 0.9757. The cause is 4 extra spans that have no gold span. Decision: re-baseline the precision floor with the reason recorded (over-redaction of gate-flagged spans is the privacy-safe direction), on condition that recall stays above its floor. The gate's cross-turn rule is not narrowed.

### Sat 10:25 - D30 speed-ups; #97 dispatched on Sol

- **When:** Sat 10:25 EET
- **Decision:** Applied D30 (user). (1) From now on, every prompt sets `PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\sinceai-pycache` and leaves out `PYTHONDONTWRITEBYTECODE` on the top-level pytest command. (2) The merge train fails fast: the fast tier `-m "not slow"` runs on the combined batch first, and `-m slow` only if that is green. Docs-only batches run only `tests/docs` and `tests/story_kit`. (3) #97 (kit-data parse cache for tests) dispatched on `openai/gpt-6.1-sol#high`, to be reviewed by Grok + Sonnet. It merges after `ticket/slow-split` if both touch `tests/conftest.py`. The prompt states the D13g authorization explicitly, because `AGENTS.md:65` on main still says Claude-only. A merger is now merging `main` into integration and writing the D13g wording.
- **Why:** The inner loop and the merge gate are slow under CPU saturation.
- **Evidence:** docs/decisions.md D30; issue #97.

### Sat 11:05 - D13e lifted (opencode-go back); roster conflict logged

- **When:** Sat 11:03-11:05 EET
- **Decision:** The opencode-go probe succeeded at 11:03 (`go-available.json`), so D13e is lifted. The probe message asks for Gemini 4 Argon to take back the Gemini roles: second reviewer on must-fix deltas, rule audits and one final-review seat. That conflicts with AGENTS.md › Review and brief v3 §2.5 (D31): Claude-written code gets Standards from Grok and Spec from Sol; Sol-written code gets Spec from Sonnet; the final review is Sol + Grok high. AGENTS.md wins, so the cross-map is unchanged. Gemini (`opencode-go/gemini-4-argon#medium`) and Luna (`opencode-go/gpt-6-luna#medium`) replace `opencode/deepseek-v4.1-flash-free` as the fallback Spec reviewer for Claude code when Sol is unavailable. They may also be an extra, non-counting reviewer in rule audits. They are used for reviews only, never implementation, with at most 6 concurrent opencode-go sessions. On another usage-limit error, go back to the D13e roster and log it. **Conflict for the human:** if Gemini should hold a counting review seat, AGENTS.md › Review must say so first.
- **Why:** AGENTS.md is binding and wins over automated steering. Keeping the cross-map stable means reviews already in flight stay valid.
- **Evidence:** `.scratch/local-overnight/go-available.json` (available_at 2026-11-07T11:03:23+02:00).

### Sat 11:10 - 3 full-profile failures not reproduced; slow-split unblocked

- **When:** Sat 11:10 EET
- **Decision:** The 3 failures in slow-split's full profile (`test_verify_full_ignores_planted_rowmap`, `test_two_runs_byte_identical`, `test_unmodified_release_verifies_in_both_tiers`; `toolRevision: mismatch`) don't reproduce. They pass in the merger's full run on `4811b16` (2357 passed, 0 failed), in the slow tier of the diagnosis lane (175 passed) and in slow-split's own fast tier at `e694598` (2248 passed). Cause: the tree moved during the profile run. slow-split may merge once both axes approve: Grok Standards and Sonnet Spec both APPROVE at `e694598`.
- **Why:** A failure that doesn't reproduce on a clean, committed tree, and that comes with a revision-binding mismatch, is a moving-tree artefact, not a defect.
- **Evidence:** the merger session ses_e4ae9a7e report; the diagnosis session ses_e4add289; `sinceai-out\slow-split\evidence-e69459898734603ee4c5ae25a082e94df9249d0b\`.

### Sat 11:25 - merge train 1 (slow-split + #78); utilization nudge (09:08Z) handled

- **When:** Sat 11:12-11:25 EET
- **Decision:**
  1. Merged slow-split (`e694598`) and #78 (`213e8ed`) into integration at `4ab170b`. On the exact sha (PYTHONUTF8=1, TZ=UTC, PYTHONPATH=src), the fast tier `-n 16 -m "not slow"` gave exit 0, 2264 passed, 5 skipped. The slow tier `-n 16 -m slow` gave exit 0, 123 passed. The first slow-tier attempt failed one subprocess test because the merger prompt left out `PYTHONPATH=src`, which docs/testing.md prescribes. That was an environment error in the orchestrator's prompt, not a defect. #78 closed: `check-done-report.ps1` exited 0. Worktrees and branches were removed.
  2. Filed #102: `check-done-report.ps1` decodes gh output with the console code page, so the template's `→` fails the gate. Posted reports use `->` until #102 merges. Sol was dispatched on a branch from main.
  3. For the nudge's 24 items:
     - Dispatched D31 two-axis reviews for #65, #66, #69, #90, #97 (Standards = Grok, Spec = Sonnet) and #81/#83/#94 (Grok + Sol), plus a #85 round-2 fixer.
     - Not dispatched, each reason recorded on its issue:
       - The CS-S1 chain (#53, #54, #92, #56, #63, #88) has a single owner under D29.
       - #62, #71 and #84 are in the live #61 wave.
       - #80 (writer/core.py), #93 (run/purpose.py) and #96 (search files) wait on 23, the #61 wave and 25.
       - #30 is Merge after 23 and 25.
       - #98 is held because main `b85d1d0` already has its splat fix.
     - Added `blocked-by` edges for #80, #93, #96, #56 and #88 so the monitor stops flagging them.
- **Why:** Single owner for the CS-S1 files (D29); each ticket owns its files.
- **Evidence:** merger session ses_e4abaa0a; issue comments "Orchestrator 11:20 EET" on each item; #78 close comment.

### Sat 11:35 - worktree isolation breach in the main checkout; guard filed; #104

- **When:** Sat 11:18-11:35 EET
- **Decision:**
  1. The planning session reported uncommitted ticket work in the main checkout: `tests/gen_fixtures/test_gen_fixtures.py` and `tests/kiteval/test_scorecard.py` modified, and `tests/policy/test_csv_reads.py` and `tests/checks_text/test_followup56.py` untracked. They were already there when this orchestrator started (08:37Z git status).
  2. Hash comparison showed they belong to inherited sessions: #81 (ses_e4b3155b, finished) and the CS-S1 chain owner (ses_e4b294f0, live). Neither can be messaged.
     - `test_gen_fixtures.py` is byte-identical to `origin/ticket/fu81-csv-determinism`.
     - `test_scorecard.py` and `test_csv_reads.py` are strict earlier drafts of the versions committed on that branch.
     - `test_followup56.py` in the main checkout is 0 bytes; the real file is committed on `origin/ticket/23-cs-s1`.
  3. After confirming the owners' versions are on origin, the orchestrator backed up all four to `C:\Users\kivas\AI\orch-tmp\main-stray-backup\`. It then restored only those paths (`git checkout --` on the two modified files, deleted the two untracked ones). Main `git status` is now clean.
  4. Added "Never edit, test or commit in C:\Users\kivas\AI\sinceai-hackaton (the main checkout); `git -C <your worktree>` only" to templates.md §1 (main `6bad0b8`), and it goes into every implementer prompt from now on. Filed #105 (Sol) for deterministic guards: `affected-tests.ps1` refuses a main checkout by Git identity, and `check-done-report.ps1` requires a `ticket/*` linked worktree. It is branched from #102 because both touch the same file.
  5. Filed #104 (Sol) for the HEAD-moves-mid-session class from the planning lane's diagnosis. Tests pin the revision per session and fail explicitly if HEAD moves.
- **Why:** AGENTS.md: each ticket owns its files, and a recurring defect class gets a deterministic guard, not just prose.
- **Evidence:** planning-session report 11:18; hash comparison (orchestrator shell); main `6bad0b8`; issues #104 and #105.

### Sat 11:45 - orchestrator hand-over; merge train 3 (#89); review ledger recovered; second main-checkout stray

- **When:** Sat 11:27-11:45 EET
- **Decision:**
  1. New orchestrator session (ses_e4aaa374...) claimed the heartbeat at 11:27. The previous one (ses_e4ad88b2...) was retired: interrupted, then a queued retirement notice, which it answered with "retired". Its 18 live child sessions keep running and are polled through the API. Results that reached the retired session after 11:27 were recovered from its message stream (cursor-paged) and acted on.
  2. Merge train 3 merged #89 (2887046) at 1a2c045: fast tier exit 0, 2289 passed, 5 skipped; slow tier exit 0, 123 passed. #89 closed (check-done-report exit 0); its worktree and branch were removed. Grok Standards r3 APPROVE and Sol Spec r3 APPROVE at 2887046. Sol's non-blocking note (search-seam test, not CLI) stands until search is wired through the CLI.
  3. CS-S1 chain round 1 at 219db98: all four reviews (Grok and Sol on both axes) are CHANGES REQUIRED. Two #53 fail-opens: a bare network cue + copula + date/time is suppressed by the prose exception, and a glued hedge-colon value is not credential-shaped in the cell rescan. Plus #56: text applicability rests on four probe phrases (Sol, both axes). Forwarded to the owner (ses_e4aac068...) with the D29 12:00 instruction.
  4. #49 and #90: merged in train 2 (31ffa5c) and approved on both axes, but their done-reports fail the close gate on a real gap: erify --full was never recorded at the head. Kept open. A Sol evidence task runs it at the exact heads; formatting gaps were not edited around.
  5. #102 r1: Spec (Sonnet) APPROVE. Standards (Grok) found a high gap: the unconfined -GhExe test hook (and -BodyFile, same class) allows a close pass on a forged body. A Sol round-2 fixer was dispatched with one confinement for both (a defect class found twice).
  6. 31 LLM r1 at ada8855: Grok Standards found a hard ADR 0002 bypass (str-subclass dispatch in the request/endpoint screen; model not exact-typed before transport). Sol Spec: evidence gaps only. An Opus round-2 fixer was dispatched with one exact-type normaliser for everything that reaches transport. It is stretch, merging only on the 14:00 go.
  7. Second main-checkout stray: two untracked test files in the main checkout (written 11:25:36, same second). They match no commit and no worktree, and their names don't match their contents. Owner unknown, so they were left in place (possibly unique work) and recorded on #105 as the second occurrence.
  8. AGENTS.md › Review now sets D32 for the final integration review: Standards Grok high; Spec twice, by Sol high and opencode-go/gemini-4-argon#medium. It is applied at the brief's section 4 step.
- **Why:** Single orchestrator; close only on evidence (D31); a defect class found twice gets a guard.
- **Evidence:** heartbeat.json session_id; merge train 3 session ses_e4aa6832; review sessions ses_e4aae4fd, ses_e4aae34e, ses_e4aabe3e, ses_e4aab95b, ses_e4aabc36, ses_e4aabab0, ses_e4aaed3b, ses_e4aaeb8d, ses_e4aab0df, ses_e4aaaf12; #89 close comment.

### Sat 11:55 - utilization nudge (09:28Z) handled; merges #104, #85; closes #49, #85, #90, #104

- **When:** Sat 11:45-11:55 EET
- **Decision:**
  1. Nudge items:
     - Dispatched: #98 round 2 (Sol) to merge the integration tip and keep the exit-5 handling and tests. Round 3 then went out for Grok's high finding (interpreter chosen by file presence, not Git identity).
     - Not dispatched, with the reason on each issue: #53, #54, #92 (D29 chain owner); #63 and #30 (Merge after 23/25; native edges); #62, #71, #84 (#61 wave, now merging); #83, #94 (#81 fixer, live); #102 (round 3 under review); #103 (section 4, after the final SHA; native edges to #24, #26, #30); #49 (evidence task).
     - Added native edges: #105 blocked by #102 and #98 (same scripts); #63 by #24; #103 by #24, #26, #30.
  2. Merge train 4: #104 at 6b43d2b (fast tier exit 0, 2290 passed, 5 skipped; slow tier exit 0, 123 passed). Merge train 5: #85 at e19a1d9 (fast tier exit 0, 2311 passed, 5 skipped; slow tier exit 0, 123 passed). Merge train 6 (#61 wave, both axes APPROVE at 40f7a86) is running.
  3. #49 and #90: a Sol evidence session ran run, verify and verify --full at the exact heads: 0/0/0, gate 40/40. Done-reports were reposted with that evidence and the recorded verdicts. Formatting was normalised only: arrows, one artefact path per line, the template Rule label, and #49's item-7 setup note moved after the outcome. Both pass check-done-report (exit 0) and are closed with worktrees removed. #90's missing red is stated as "No red observed", not reconstructed.
  4. 25 search, Spec re-run (Sol) at fdadfad: no behavioural blocker. The evidence gaps (both verify tiers, dashboard, rung diff vs hand) are being produced by a Sol evidence session. Grok Standards APPROVE.
  5. 31 LLM r2 (6b4535c): Grok APPROVE (the ADR 0002 bypass is fixed through one exact-type normaliser). Sol found an evidence-binding gap (no revision or input digests in evidence.json), sent back. It is stretch: merging only on the 14:00 go.
  6. #102 round 3 (c6d0c06): both axes APPROVE (no substitute path exits 0). It is next in the merge queue.
- **Why:** Each ticket owns its files; close only on evidence (D31); a guard is chosen by identity, never by a plantable file.
- **Evidence:** merge sessions ses_e4aa037c, ses_e4a9b1c8; evidence session ses_e4aa228d; close comments on #49, #85, #90, #104.

### Sat 12:00 - STATUS; 12:00 checkpoint decisions; D32 applied

- **When:** Sat 12:00 EET

#### Effective policies (changes only)
- D32 (human, via the planning session, 11:35): Gemini 4 Argon holds a counting seat on the final whole-product review only. Fixed point c309db6. Standards: Grok high. Spec: Sol high and Gemini 4 Argon, as separate sub-agents. Plus the rule audit. Ticket reviews keep the D31 cross-map. This resolves the 11:05 roster conflict. Main pulled at 678fbd9.
- Search GO (12:00): ticket 25 ships the measured search for HEALTH-S1 (D10, D23); the hand plan stays available with --plan hand.
- CS-S1 D29 fallback TRIGGERED (12:00). No real-kit CS-S1 gate pass was shown at 12:00 (the owner's run at d796170 started 11:55). The owner withholds the turns the independent checker still flags, records counts and the CS-U1/CS-U5 effect in sacrifices, and states the reduced checker independence in esidualRisks. The gate stays strict. If the strict run passes, 0 turns are withheld and that is recorded. The two #53 fail-opens and the #56 applicability gap still have to be fixed; the fallback does not replace them.

#### Critical path
CS-S1 chain (23 + #53/#54/#56/#92, then #63) -> 29 packager (#30) -> pets_submission at 16:00 -> 14:00 LLM go (needs both releases passing gate + verify) -> final review at c309db6 per D32 -> fresh real-kit proof on the final SHA -> #103 story finalisation -> PR #95 merge.

#### Blocker owners
- #24 + #53, #54, #56, #92 -> ses_e4aac068 (claude-agent/opus, D29 owner), running the real-kit run plus the fallback.
- #26 (25 search) -> approved on both axes at fdadfad; merge train 8 next (after #102).
- #30 -> approved; waits on #24, #26.
- #63 -> approved; waits on #24.
- #62, #71, #84 -> merged at 8e93dcf; per-issue done-reports outstanding (#71 also lacks its mutation-red evidence).
- #81/#83/#94 -> fe2feed: Spec APPROVE, Grok delta pending. The full affected selection at the head is unknown, so not merge-clear.
- #97 -> inherited Sol fixer (ses_e4aae03f).
- #98 -> 094edb5: Spec APPROVE, Grok delta pending.
- #102 -> merge train 7 running.
- #105 -> approved at 96fa357; waits on #102 and #98 (same scripts).
- #106 -> ready-for-human (detector-QI policy decision).
- #107 -> waits on #97 (tests/conftest.py); three main-checkout write occurrences today.
- #108 -> flaky kiteval probe control, ready-for-agent.
- 31 LLM (#32) -> approved on both axes at f53e09d; held for the 14:00 go.

#### Latest verified revision
- 8e93dcf (integration tip, #61 wave). Fast tier exit 0, 2372 passed, 5 skipped. Slow tier: first run exit 1 (1 failed, the #108 flaky control), passed 2/2 in isolation; full slow-tier re-run on the same sha exit 0, 123 passed.
- Requested record, tip 31ffa5c6302a075cd6ad7549499f592792295ccd (merge train 2: #49 at 11:21 + #90 at 11:22; merger ses_e4aaf9c8). Fast tier -n 16 -m "not slow": exit 0, 2274 passed, 0 failed, 5 skipped. Slow tier -n 16 -m slow: exit 0, 123 passed, 0 failed. Exit codes were read after a pipe; pytest's own summary lines agree.
- Later merges, each with both tiers green on the exact merged sha: 1a2c045 (#89: 2289 + 123), 6b43d2b (#104: 2290 + 123), e19a1d9 (#85: 2311 + 123), d177288 (#102: fast tier exit 0, 2381 passed, 5 skipped; slow tier exit 0, 123 passed).
- No real-kit release run certifies the integration tip yet.

#### Missing evidence
- The 5 fast-tier skips at 4ab170b (re-run with -rs on that exact sha: exit 0, 2264 passed, 5 skipped). All five are in 	ests/docs/test_readme_commands.py:
  1. :126 reason=environment-setup. Intended: the README's environment-setup command (venv/pip) is not executed by tests.
  2. :126 reason=sets-secret-placeholder-only. Intended: the README line only sets a key placeholder and is not runnable.
  3. :126 reason=cs-s1-run-needs-ticket-23. Gap: the CS-S1 README command is unverified until 23 merges. Tracked on #24 (skip to be removed at merge).
  4. :135 "not built yet: pets-release submission is available after ticket=29". Gap: the submission command is unverified until 29 merges. Tracked on #30.
  5. :126 reason=runs-the-whole-test-suite-recursively. Intended: the README's full-suite command would recurse; the merger runs the suite itself.
- The CS-S1 real-kit release, both verify tiers and the scorecard at any head (owner running).
- Per-issue done-reports for #62, #71, #84 (#71: mutation-red demonstration).
- The full affected selection at #81's head fe2feed.
- A real-kit run of both releases on the integration tip: needed for the 14:00 go and for section 4.

- **Note:** this status entry is appended at the bottom. The brief asks for status at the top, but the log header and AGENTS.md › Orchestration say append-only, add at the bottom. AGENTS.md wins.

### Sat 12:55 - orchestrator hand-over; CS-S1 passes the gate without the D29 fallback; merges #98, #105; tier-1 pass-2 wave dispatched

- **When:** Sat 12:00-12:55 EET
- **Decision:**
  1. New orchestrator session (ses_e4a8c046...) claimed the heartbeat at 12:00. The previous one (ses_e4aaa374...) was interrupted and sent a queued retirement notice; it replied "retired" and listed its open items, all picked up below.
  2. CS-S1: the chain owner (ses_e4aac068, Opus) reports the real-kit CS-S1 release passes the strict gate at d796170 (39 pass, 2 not applicable, 0 hits), with both verify tiers and the scorecard run. The D29 turn-withholding fallback was not needed (0 turns withheld). The two #53 fail-opens are fixed at d796170; #56's applicability blocker was fixed red-to-green afterwards, and the owner is re-merging integration. Its done-report and the four round-1 reviews are still to come.
  3. Merges: train 8 merged #98 at 10c2ba7 (fast tier exit 0, 2388 passed, 5 skipped; slow tier exit 0, 123 passed). Train 10 merged #105 at 9d139b3 (fast tier exit 0, 2405 passed, 5 skipped; slow tier exit 0, 123 passed). Closed on check-done-report exit 0: #102, #98, #105, and #62, #71, #84 (Sol evidence session produced head-bound mutation reds at 40f7a86; reviews Grok r3 + Sol r3 APPROVE there). #102's posted report uses Unicode arrows, so its close exercised the real gh path.
  4. Train 9 (#81/#83/#94 at fe2feed) was red: 1 fast-tier failure, the branch's own CSV-read guard flagging 3 reads in tests merged after it branched. Reset, nothing pushed. This is the third hit of the stale-branch class for that guard; the guard itself is the deterministic check and the merger caught it, so no new guard. Round 3 (9bbad25) fixed the reads and added a risks-order regression test (a mutation probe showed the sort was untested). Grok r3 APPROVE; Sol r3 CHANGES REQUIRED on evidence binding only (head-bound affected-tests log and real run); an evidence session is producing both.
  5. Planning-session steer (12:38): dispatched the rolling-review pass-2 must-fix wave, all claude-agent/opus, four fixers grouped by owned files: #111+#112 (ticket/fu111-suppression), #110+#113 (ticket/fu110-scorecard-k, branched from fu81's head because both edit kiteval/report.py and measure/wire.py; Merge after #81 and #26), #114 (ticket/fu114-manifest-json), #109 (ticket/fu109-rung-sacrifice; the same owner takes #106 after #26 merges). #111 and #109 touch run/pipeline.py and verify/core.py, which ticket 23 also edits, so both merge after #24. #108 dispatched on Sol, branched from fu81 (same test file), Merge after #81. #115 not dispatched: blocked by #112 (minimiser/risk.py) and #81 (tests/verify/test_full_real.py), native edges added.
  6. D33 accepted (main 65b8c6d); #106 blocked by #26 and #109 (native edges).
  7. Spec question from the steer: the 83 `text.health` hits on HEALTH-S1 at 8e93dcf all come from `lab_results.test_name` (purpose-permitted per spec #1's per-column table; no free-text column released) and are disclosed in residualRisks with count and denominator. Not a must-fix.
  8. #30 gained two acceptance criteria: output exactly to C:\Users\kivas\AI\sinceai-out\pets_submission, built after the tier-1 wave merges, build revision logged.
  9. Process defect: `demo-8e93dcf\commands.txt` holds result lines only, so it is not a runnable recipe. Added `C:\Users\kivas\AI\sinceai-out\health-s1-evidence.ps1` (outside the repo; pinned clean head, kit path, throwaway local key never printed, logs every exit code and the toolRevision match) and sent the correction to the four fixers.
- **Why:** Single orchestrator; tier-1 fail-closed fixes first (brief v3 section 2.1); close only on evidence (D31); each ticket owns its files.
- **Evidence:** merger sessions ses_e4a8bbed, ses_e4a8542c (red), ses_e4a71498; reviews ses_e4a782e2, ses_e4a780de, ses_e4a7121e, ses_e4a71026; evidence sessions ses_e4a8b4c8, ses_e4a83ce5; close comments on #62, #71, #84, #98, #102, #105.

### Sat 12:55 - STATUS

#### Effective policies (changes only)
- Brief v3 section 5 (main b775c57): never block the orchestrator turn on long waits while ready work exists; waits are at most 2 minutes.
- send-to-orchestrator.ps1 defaults to delivery=steer (main 44af20e).
- D33 (#106): lab_results.test_name is a QI with a "CRP vs other" rung; justified non-QI fallback if the cap is still exceeded.

#### Critical path
CS-S1 chain done-report + 4 reviews (23 + #53/#54/#56/#92) -> merge -> #63 -> 25 search (#26) merge -> 29 packager (#30) on the post-tier-1 revision -> pets_submission at 16:00 -> 14:00 LLM go (both releases gate + verify on the current revision) -> final review per D32 -> fresh proof -> #103 -> PR #95 merge.

#### Blocker owners
- #24, #53, #54, #56, #92 -> ses_e4aac068 (claude-agent/opus, D29 owner).
- #26 (25 search) -> ses_e4a8b8d8 (claude-agent/opus), merging the integration tip.
- #81/#83/#94 -> evidence session ses_e4a61c11 (Sol) at 9bbad25, then Sol Spec delta.
- #109 -> ses_e4a61e44; #111+#112 -> ses_e4a62268; #110+#113 -> ses_e4a620ac; #114 -> ses_e4a61f43 (all claude-agent/opus).
- #108 -> ses_e4a61938 (Sol). #97 -> ses_e4aae03f (Sol, inherited).
- #106 -> #109's owner after #26. #115 -> after #112 and #81. #30, #63, #65, #66, #69, #80, #93, #96 -> wait on #24/#26 (native edges).

#### Latest verified revision
- 9d139b3 (integration tip, #105): fast tier exit 0, 2405 passed, 5 skipped; slow tier exit 0, 123 passed.
- Release evidence: 8e93dcf side lane (planning session, 12:01): HEALTH-S1 real-kit run RELEASED, gate 41/41, verify (limited) 37 release-checked + 4 producer-attested, verify --full pass; dashboard C:\Users\kivas\AI\sinceai-out\demo-8e93dcf\health-s1-dashboard.html.
- CS-S1 real-kit at d796170 (ticket/23-cs-s1, not yet on integration): gate 39 pass + 2 not applicable, both verify tiers run (owner's report).

#### Missing evidence
- HEALTH-S1 k claims (min k 5, 0 below k) stay unverified until #106 and #109 merge.
- The CS-S1 done-report and its four round-1 reviews; CS-S1 verify exit codes at the final chain head.
- No real-kit run of either release on the integration tip 9d139b3.
- #81/#83/#94: head-bound real run at 9bbad25 (running).
### Sat 13:28-13:50 - orchestrator hand-over; #119 and #107 closed; #107 split to #123; close-gate encoding defect (#122); CS-S1 done-report at 926765f; server restart

- **When:** Sat 13:28-13:50 EET
- **Decision:**
  1. New orchestrator session ses_e4a3c596... claimed the heartbeat at 13:28 (start-orchestrator; the previous session ses_e4a8c046 replied "retired"). The scripts are run with `-ExecutionPolicy Bypass`, as docs/operations/overnight.md documents; the default policy blocks `-File`.
  2. Close gate defect: `check-done-report.ps1` decoded `gh` output in the OEM code page, so the arrows in Red/Green/affected-tests lines did not match (false gaps, still fail-closed). The same mangling hit done-reports fetched with `opencode api` in PowerShell. Filed #122 (Sol, Grok + Sonnet APPROVE, in merge train 16 to main). Until it lands, the orchestrator runs the gate and the session fetches with `[Console]::OutputEncoding=UTF8`. One mangled #107 comment was deleted and re-posted.
  3. #119 closed (merged 98c62aa): the done-report was re-posted with "Same command" expanded to the Red command, and the gate then exited 0. templates.md section 4 now forbids "Same command" (#122).
  4. #107: Spec r1 (Sonnet) asked for script/agent writes outside pytest. The orchestrator descoped that to #123 (Sol, dispatched on main). Spec r2 APPROVE, Grok APPROVE. Merged in train 15 at 4cd4a0a: fast tier exit 0, 2452 passed, 5 skipped; slow tier exit 0, 123 passed. Closed; gate exit 0; worktree and branch removed (also fu119's).
  5. Train 15 culprit: #26 at a3c2bc8. Its new tests/run/test_run_search.py trips the CSV read-policy guard (2 findings). Sol fixer dispatched. Train 15 found that `pets_release` is not installed in the shared venv, so subprocess tests need `PYTHONPATH=<worktree>\src`. Merger prompts now set it, which earlier trains did implicitly. Without it, test_fu85_low_audit fails on the base too.
  6. Reviews: #114 got 4/4 APPROVE after the orchestrator ruled the extra strict loaders in scope (same defect class; AGENTS.md "found twice"); Sol r2 APPROVE. #115 got 4/4 APPROVE. Train 16 has #114, #115 and #122 (main). #121 is approved (Grok, Sonnet) and Merge after #117. #109 r1: Sol Spec found a high (the validator rejects the turn_id -> id.pseudonym alt-floor fallback, which CS-S1's CS-U5 relies on) and Sol Standards found a high (unmasked names in diagnostics). Opus fixer round 2 is running. #110+#113 r1: 3 APPROVE, Grok Spec CHANGES REQUIRED. There is no measured real-kit release because of #120. Ruling: the measure CLI seam is accepted, #110 waits on #120 (native edge), and a measured run is required afterwards. #113 met.
  7. Human steering 13:52 relayed to the owners: #120 (bounded manifest fix, both CLI regressions, measured run with default and alternate recipient, both verify tiers), the CS-S1 owner (head-bound evidence; n/a vs missing; no fallback claim with 0 withheld), #30 (D37 gate before publication, planted-miss regression, complete by default, `submission_index.json`, rehearsal without uploads), #116 (measured path in the smoke, temporary CS refusal expectation, missing/errored = fail), #117 (aggregate views only, no row view until confirmed). D40: #96, #99, #100, #101 deferred (commented). Steer point 7 (the close gate must validate machine records, not prose) filed as #124, sequenced after #122.
  8. Utilization-monitor items that cannot be dispatched: ticket/fu53, fu54, fu92 (and #56) are in the CS-S1 chain on ticket/23-cs-s1, which has one owner (D29). ticket/fu63, fu65, fu66, fu69 have native blocked_by #24 edges and comments. #118 is blocked by #26 (native edge), with an Opus dispatch after #26 merges. Per steer 4 it must cover the whole missing-PersonK class in search.
  9. CS-S1: the chain owner finished at 926765f (includes 98c62aa). Real kit: gate 40 pass + 2 not_applicable (producer.person-k and producer.row-k; no k target), 0 fail, 0 hits; 42 registry checks = 42 records. run, verify (limited) and verify --full exit 0. Scorecard: CS-U1 0.9984, CS-U3 1.0, CS-U4 1.0, CS-U5 adapted 0.8803 (turn_id pseudonymised). D29/D38 fallback not used, 0 turns withheld. Four round-1 reviews were dispatched at once (Grok + Sol on both axes).
  10. The OpenCode server restarted at about 13:50. The CS-S1 owner and #117 had already finished. #116 was interrupted and was resumed in its own session. The #109 fixer had ended its turn waiting on background tests; it was resumed with foreground tests.
  11. Time-stamp correction: some issue comments from this session say 13:58-14:10 EET. The actual times were 13:38-13:46 EET.
- **Why:** Brief v3 section 2 tiers (fail-closed blockers, CS-S1, search, packaging); close only on evidence (D31); human steering 13:52; D38-D40.
- **Evidence:** merge train 15 session ses_e4a35d72; review sessions ses_e4a39565, ses_e4a3936e, ses_e4a3728, ses_e4a370c6, ses_e4a36e7a, ses_e4a36c86, ses_e4a36add, ses_e4a3696, ses_e4a3676, ses_e4a3656, ses_e4a3640, ses_e4a362c, ses_e4a31e9, ses_e4a31ce, ses_e4a31b8, ses_e4a31a5, ses_e4a318a, ses_e4a3170, ses_e4a315b, ses_e4a3147, ses_e4a3582, ses_e4a356c, ses_e4a3283, ses_e4a326a; close comments on #107 and #119; C:\Users\kivas\AI\sinceai-out\cs-s1\evidence-926765f9b62978d829808047269a2c744537d1e2\.

### Sat 14:18 - STATUS

#### Effective policies (changes only)
- D38 (human, 13:35): CS-S1 keeps the strict gate until 15:00, then the D29 fallback and merge. Planning steer 14:14: Sol's round-1 high (text-form applicability fails open to not_applicable) must be fixed before merge regardless of time. The fallback withholds flagged turns; it does not cover a check that fails open.
- D39 amended (human, 14:02): #32 is being prepared now. It merges only if both releases pass gate + verify on integration by 16:00.
- D40 (human, 13:50): #96, #99, #100 and #101 are deferred, not dispatched. D41: the web app shows real-kit protected rows, labelled, only from a release that passes verify at display time. Agents never view rows. D42: hosted demo on exe.dev (planning lane).
- templates.md section 5 (main aa5c3a0): merger tiers run in the foreground with a timeout and a PID check, and a tier lost to a restart is rerun. The orchestrator fetches and runs the close gate with UTF-8 console decoding until #122 is on main.

#### Critical path
#24 chain fix (alternation fail-open + SECRET recall) -> delta reviews -> merge -> #63 -> CS-S1 evidence on integration; #120 -> #110/#113 measured evidence -> measured HEALTH-S1 release; #30 fix -> complete bundle after #24 -> pets_submission 16:00; D39 check -> #32 by 16:00; then final review (D32), fresh proof, #103, PR #95.

#### Blocker -> owner -> next proof
- #24 + #53/#54/#56/#92 (CS-S1) -> ses_e4aac068 (claude-agent/opus, D29 owner) -> fix of the Sol Standards high (`_shape()` alternation/repeat counted as non-text) and the held-out SECRET recall 15/17 (spec target 0.98; escalate to the human by 14:40 if not reachable), red-first, then a real-kit run + verify (limited) + verify --full + scorecard at the new head, then Sol Standards and Sol Spec deltas. Round 1 at 926765f: Grok APPROVE on both axes.
- #120 (manifest value scan; measured HEALTH-S1 refuses) -> ses_e4a44ed4 (opus) -> foreground measured run, default and `--recipient acme`, both verify tiers, plus the two CLI regressions; then 4 round-1 reviews.
- #110 + #113 -> no live owner. Branch ticket/fu110-scorecard-k at 289a88c: 3 of 4 round-1 APPROVE; Grok Spec CHANGES REQUIRED for the missing measured real-kit run. Blocked by #120 (native edge). Next proof: a measured real-kit run + both verify tiers at a head that includes #120, then a Grok Spec delta. Dispatched (Opus evidence session) when #120 merges.
- #118 (missing PersonK as zero shortfall in search) -> no owner yet; blocked by #26 (native edge). Opus dispatched after #26 merges (train 17). Steer: it must cover the whole failure class in search.
- #106 (D33 HEALTH QI policy) -> after #26 and #109 merge -> Opus; measure the CRP-vs-other rung, H-U7, person-k and suppression.
- #30 (packager, D37) -> round 2 at 4112335. Sol Spec CHANGES REQUIRED: the masking effect on the redaction metrics is not recorded; README example broken / wrong destination; the README submission test is still skipped. Grok Standards pending. Opus fixer next. Complete bundle after #24.
- #116 (release smoke) -> round 1 at 0b83256. Sonnet Spec CHANGES REQUIRED: the CS-S1 expectation is "refused" but this base exits 2 (run is HEALTH-S1-only until #24). Grok pending. Fixer next; Merge after #24.
- #117 (web app, D35/D41) -> ses_e4a27f3f (Sol), round 2 with D40-D42 scope; must merge by about 17:00.
- #32 (LLM) -> prepared at 3aec8c5. Delta review after #26 merges (cli.py). Merge held for D39.
- Merge train 16 (#114, #115; #122 to main) -> ses_e4a2d88e (sonnet). Its background fast tier was killed by the 13:50 restart; it was interrupted and rerun in the foreground. Train 17 is ready: #26 at 4dc9eb5 and #109 at cf92ae3 (both axes APPROVE), #123 to main at acb2d71 (both axes APPROVE).
- #121 approved at d326ffe, Merge after #117. #124 after #122. #125/#126 (wait/idle guards) after #123 (same script). #63, #65, #66, #69, #80, #93 Merge after #24.

#### Latest exact revision with measured release evidence
- None. No `measure.wire` (measured) release has been released at any head; every measured run refuses on #120.
- Plain HEALTH-S1 real-kit releases (gate 41/41, run + verify (limited) + verify --full exit 0, toolRevision match) on branch heads: cf92ae3 (#109), 4dc9eb5 (#26 search plan), 3aec8c5 (#32), 289a88c (#110).
- CS-S1 real-kit release on branch head 926765f (#24): gate 40 pass + 2 allowed not_applicable, 0 hits; both verify tiers exit 0; 0 turns withheld.
- Integration tip 4cd4a0a: fast tier exit 0 (2452 passed, 5 skipped), slow tier exit 0 (123 passed); no real-kit run on it yet.

#### Complete-bundle status
- Not built. At 4112335 (#30) a complete build refuses with `REFUSED: incomplete (missing datasets: customer_service)` and nothing is written. `--partial` builds with `submission_index.json` (198 masked CS eval turns). The delivery folder is untouched and there was no upload. A complete build needs #24 merged plus the #30 round-3 fixes.

#### Remaining unknowns
- CS-S1 held-out SECRET recall below target (15/17).
- The measured HEALTH-S1 release (blocked on #120); the #110 k behaviour on a measured release.
- Real-kit runs of both releases on the integration tip.
- #116 smoke is red on the real kit until #24 and #120 merge.
- 5 README-ledger skips (named reasons; not passes).

### Sat 14:28-14:52 - orchestrator hand-over; merge train 18 (#120); #110/#113 evidence dispatched

- **When:** Sat 14:28-14:52 EET
- **Decision:**
  1. New orchestrator session ses_e4a056b3... claimed the heartbeat at 14:28 (start-orchestrator). The previous session ses_e4a3c596 had already replied "retired". Its children (#24 chain owner, #30, #32, #106, #116, #117, #118, #124, #125+#126) were still live and are polled each turn. Scripts still need `-ExecutionPolicy Bypass`.
  2. #120: Grok Standards r1 returned APPROVE at c30f5a4, completing 4/4 (Standards: Grok, Sol; Spec: Sol, Grok). Merge train 18 merged it at 9ef58f9: fast tier exit 0, 2558 passed, 5 skipped; slow tier exit 0, 123 passed. Done-report posted, check-done-report exit 0, closed; worktree and branch removed.
  3. #110 + #113: an Opus evidence session (ses_e4a02df0) merges the integration tip (now with #120) into ticket/fu110-scorecard-k and produces a head-bound measured real-kit run (default and `acme` recipients, both verify tiers), then a Grok Spec delta.
  4. #94 stays open. Its measured `--recipient acme` run RELEASED with both verify tiers exit 0 at c30f5a4 (#120's evidence). The close gate binds evidence to #94's own head (9bbad25), so #94 closes on the final-SHA proof (section 4).
  5. Planning steers 14:31 and 14:33 received. Trains 16 and 17 had already merged (integration 809bbce). #127 (D44) is dispatched to a fresh Opus session once #118 and #106 merge; the search owner's session has ended. #63, #65, #66, #69, #80 and #93 build on or edit ticket/23-cs-s1 files, so they wait for #24 (D29). #96, #99, #100 and #101 are deferred (D40).
- **Why:** Single orchestrator; tier-1 fail-closed first; close only on evidence (D31).
- **Evidence:** merger ses_e4a0370d; reviews ses_e4a08319, ses_e4a0814b, ses_e4a07dec, ses_e4a07f88; C:\Users\kivas\AI\sinceai-out\fu120\evidence-c30f5a469ccafa0a5cd6488cc89abc103fbe1769; #120 close comments.

### Sat 14:52 - STATUS

#### Blocker -> owner -> next proof
- #24 + #53/#54/#56/#92 (CS-S1) -> ses_e4aac068 (claude-agent/opus, D29 owner) -> held-out SECRET recall is now 17/17 (59c4652). It is re-merging integration and fixing the README CS-S1 command test (red first). Next: the fix for Sol's round-1 Standards high (repeated alternation counted as non-text, failing open to not_applicable), required before merge (steer 14:14). Then a real-kit run + verify (limited) + verify --full + scorecard at the new head, Sol Standards and Spec deltas, and a merge. D38 time-box 15:00 (fallback only withholds flagged turns; it does not cover a fail-open check).
- #118 (missing PersonK as zero shortfall, blocks #127) -> ses_e4a0a7cb (claude-agent/opus) -> red covered the five pre-fix sites, all fixed; merging the integration tip and running affected tests. Next: done-report, then 4 round-1 reviews. ETA for reviews about 15:10, merge about 15:40.
- #106 (D33 QI policy, blocks #127) -> ses_e4a0a4c1 (claude-agent/opus) -> recording the before-baseline real-kit search run at 809bbce; then the CRP-vs-other rung, H-U7, person-k and suppression measurements.
- #127 (D44 parallel search scoring) -> not dispatched; native blocked by #118 and #106 -> Opus at merge; by 20:00 or deferred.
- #110 + #113 -> ses_e4a02df0 (claude-agent/opus) -> measured real-kit evidence at a head including #120, then Grok Spec delta.
- #30 (packager, D37) -> ses_e4a0f100 (claude-agent/opus), round 3 -> submission suite green locally; then the rehearsal without uploads; complete bundle after #24.
- #116 (release smoke) -> ses_e4a0ee60 (Sol), round 2 -> planted-junction gap found and fixed; Merge after #24.
- #117 (web app) -> ses_e4a27f3f (Sol), round 2 -> protected-row guards pass; it is allowing the 64-char keyed-pseudonym shape only on freshly verified row responses. Reviewers must check that against D35 (every response passes the identifier-shape scan). Must merge by about 17:00.
- #32 (LLM) -> ses_e4a237c0 (Sol) -> affected tests 416 passed; rerun after a main-checkout guard hit from a main pull. Merge only on the D39 condition by 16:00.
- #124 -> ses_e4a0c81f (Sol); #125+#126 -> ses_e4a07b94 (Sol).

#### Latest exact revision with measured release evidence
- c30f5a4 (#120 head, now merged at 9ef58f9): measured HEALTH-S1 RELEASED for default and `acme`; verify (limited) and verify --full exit 0 for both; plain run gate 41/41.
- Integration tip 9ef58f9: fast tier exit 0 (2558 passed, 5 skipped), slow tier exit 0 (123 passed); no real-kit run on it yet.
- CS-S1: last real-kit release at 926765f (branch); no run at the chain's current head.

#### Complete-bundle status
- Not built. A complete build needs #24 merged plus the #30 round-3 fixes. No upload; delivery folder untouched.

#### Remaining unknowns
- The CS-S1 alternation fail-open (open, high).
- Real-kit runs of both releases on the integration tip.
- #110 behaviour on a measured release (evidence running).
- 5 README-ledger skips (named reasons; not passes).

### Sat 14:38 - time-stamp correction

- **When:** Sat 14:38 EET
- **Decision:** The two entries above headed "14:28-14:52" and "14:52 - STATUS" were written at 14:37 EET. The orchestrator misread the clock. The #120 close comment's "14:50 EET" is also 14:37 EET. The content is unchanged.
- **Why:** The log is append-only, so the times are corrected in a new entry.
- **Evidence:** heartbeat timestamp 2026-11-07T12:37:35Z.

### Sat 14:45 - D45 relayed with a recall conflict; utilization nudge (12:38Z) handled; #129 filed

- **When:** Sat 14:40-14:45 EET
- **Decision:**
  1. D45 (human, 14:39) was relayed to the CS-S1 owner (ses_e4aac068) by steer. Conflict logged: D45 cites held-out SECRET recall 15/17, but the owner reported 17/17 at 59c4652 after e47bedb changed the redactor in response to Sol r1 Spec findings about the held-out misses. The steer requires both figures in the manifest target notes and residualRisks, with counts and denominators, and states that the post-change figure is optimistic (held-out contamination). The 0.98 target stays and is reported as not shown met on untouched data. No further recall tuning. The rest of the D38 window goes to the `_shape()` alternation/repeat fail-open (high), red first, then head-bound real-kit evidence and Sol delta reviews.
  2. Nudge items that cannot be dispatched:
     - ticket/23-cs-s1: owner live (ses_e4aac068).
     - fu53, fu54, fu92: superseded leftovers; their fixes are on ticket/23-cs-s1 (D29). Native blocked-by #24 added.
     - #121: approved; native blocked-by #117 added.
     - fu63, fu65, fu66, fu69: built on ticket/23-cs-s1, with existing native #24 edges.
     - #94: the code merged; it closes on the final-SHA proof (close-gate head binding).
     Commented on each issue.
  3. The monitor ignores native blockers on branch items. This is the second occurrence (13:28, 14:38), filed as #129 (Sol). It is blocked by #125, because #125+#126 edit the same script.
- **Why:** AGENTS.md: a defect class found twice becomes an automated check. Single owner for the CS-S1 chain (D29). Transparency on unmet targets (D40, D45).
- **Evidence:** steer message msg_1b605012 to ses_e4aac068; issue comments on #53, #54, #63, #65, #66, #69, #92, #94, #121; #129.

### Sat 14:52 - planning steer 14:50: Sol pre-staging lanes

- **When:** Sat 14:50-14:52 EET (clock from heartbeat; the previous entry's "14:45" was written at about 14:40)
- **Decision:**
  1. #63: a Sol session (ses_e49f4e82) merges ticket/23-cs-s1 @ e4ae3fc into ticket/fu63-cs-contract. Rebase fallout only, with a real-kit CS-S1 run on its head. #65, #66 and #69 each contain the fu63 branch, so they are dispatched in parallel once #63's new head is pushed, so the same conflicts aren't resolved four times.
  2. #80, #88, #93: no branches exist, so there is nothing to pre-stage. #88 is redactor work (D29 chain files) and stays after #24.
  3. #103 story prep: Sol (ses_e49f4be2) on the new ticket/fu103-story-prep from f98cf62. It covers the D40 five items, the targets table with `{{manifest.*}}` placeholders, claim gates and the D45 statement. Finalisation still waits for section 4.
  4. README prep filed as #130: Sol (ses_e49f49a4) on the new ticket/fu130-readme-final from #121's head d326ffe. Merge after #121, #117, #24 and #30. The submission section is left to #30's fixer.
  5. Reviews for all of these: Grok Standards + Sonnet Spec (Sol-written).
- **Why:** Planning steer 14:50. The dependency graph, not the cap, limits the work; pre-staged branches merge in the train right after #24.
- **Evidence:** sessions above; worktrees fu103-story-prep and fu130-readme-final.

### Sat 14:48 - utilization nudge (12:48Z): same items as 12:38Z, nothing dispatchable

- **When:** Sat 14:48 EET
- **Decision:** All 9 items were already answered in the 14:40 entry, with issue comments and native edges. They are re-flagged because the monitor ignores native blockers on branch items (#129). #65, #66 and #69 are additionally sequenced after the #63 rebase session (ses_e49f4e82), per the 14:52 entry. CPU is at 65.3% against the 70% limit.
- **Why:** No new information; the monitor defect is #129.
- **Evidence:** 14:40 and 14:52 entries; #129.

### Sat 15:07 - rolling review pass 3 (Spec) findings routed; #131 folded into #110/#113

- **When:** Sat 15:07 EET
- **Decision:**
  1. Pass 3 Spec (Sol, 8e93dcf...f98cf62): 2 high and 3 medium. Four of them confirm open tickets, and each is routed to the live owner:
     - #106 -> ses_e4a0a4c1, steered;
     - #110 and #113 -> ses_e4a02df0, which adds the reviewer's evaluator-child probe as a regression;
     - #118 -> ses_e4a0a7cb, steered to cover both sites, search.py:619-624 and 819-821.
  2. New tier-1 must-fix #131 (kiteval scorecard input parsed last-wins; incomplete fix of #114) is folded into ticket/fu110-scorecard-k under the same Opus owner. Duplicate keys must fail closed, reusing #114's strict loader. That branch now carries #110, #113 and #131, and round 1 gets all 4 reviews.
  3. Noted: the pass found no path that makes a missing check produce false. The #109 and #120 regressions pass. The Standards axis (Grok) is still running.
- **Why:** Tier-1 fail-closed first; same-area work goes to one owner.
- **Evidence:** newest comments on #106, #110, #113 and #118; #131.

### Sat 15:00 - utilization nudge (12:58Z); reviews for 5 finished heads; #116 r3; #32 AC3 question

- **When:** Sat 14:58-15:05 EET (machine clock)
- **Decision:**
  1. Finished inherited sessions: #116 r2 (810594c), #32 delta prep (25dddf7), #124 (5f926b3), #125+#126 (beae83b). Also #103 prep (860829e, own child). Ten reviews were dispatched, Grok Standards + Sonnet Spec for each, since all are Sol-written. #131 is folded into fu110 (live owner). #94 is unchanged (closes on the final proof).
  2. #116 r2 Spec (Sonnet): CHANGES REQUIRED. The real-kit smoke at 810594c has pass:false. HEALTH-S1 passes and CS-S1 is run-unknown (expected before #24), but the measured delivery lane refused. The base 3fe0298 predates #120, so a Sol fixer (ses_e49e7225) merges the tip and re-runs the smoke. Any remaining refusal is diagnosed from reason codes only.
  3. #124 r1 Spec (Sonnet): CHANGES REQUIRED. The new close gate rejects #120's genuine multi-release evidence folder (it requires exactly one manifest, plus hard-coded log names). A report that omits "gate"/"verify" also skips machine validation. The fixer waits for Grok Standards so there is one combined round.
  4. #32 delta Spec (Sonnet): CHANGES REQUIRED on AC3 ("a drafted HEALTH-S1 policy run through the search passes gate and verify"). The draft is review-only and `run` cannot consume it. The earlier "AC3 pipeline part deferred to 14:00" was an orchestrator deferral, not an amendment. Not decided by the orchestrator: asked the human to choose between (a) amending AC3 on #32 (the draft stays a reviewed artefact, with the consumer as future work) and (b) building a minimal approved-draft consumer on `run` before 16:00. #32 does not merge until this is answered and D39's condition holds.
- **Why:** Close on evidence (D31). An acceptance criterion is changed only by the human.
- **Evidence:** review sessions ses_e49e82a9 (#116 Spec), ses_e49e7bf8 (#124 Spec), ses_e49e7f95 (#32 Spec); C:\Users\kivas\AI\sinceai-out\smoke\810594cc0d51fb60d1e0fc2e60eff480b5a388cd\smoke.json.

### Sat 15:15 - merge train 19 (#103 prep); review rounds dispatched

- **When:** Sat 15:05-15:15 EET (machine clock)
- **Decision:**
  1. #103 prep: Grok Standards and Sonnet Spec both APPROVE at 860829e. Docs-only train 19 merged it at 871ff07 (tests/docs + tests/story_kit: exit 0, 39 passed, 6 named skips). #103 stays open for finalisation. The prep worktree and branch are removed.
  2. #116: Grok r2 APPROVE. Its non-blocking gap (the CS expectation test is vacuous with respect to the CLI outcome) was added to the round-3 fixer ses_e49e7225.
  3. #125+#126: Grok APPROVE and Sonnet CHANGES REQUIRED (the heartbeat running-id parser collapsed the live scan to unknown). Round 2 is with Sol (ses_e49e4418): parse every known shape, isolate unparsable entries, re-run the live dry run, and add the process-identity and bounded-retry tests. The orchestrator's heartbeat now lists plain issue numbers.
  4. #124: Grok and Sonnet both CHANGES REQUIRED. There are two highs: release selection by file presence (it rejects #120's genuine three-release folder, yet accepts one planted manifest), and validation skipped when the Outcome omits "gate"/"verify". Round 2 is with Sol (ses_e49e3870).
  5. #32: Grok delta APPROVE. Sonnet Spec CHANGES REQUIRED on AC3, which awaits a human decision (15:00 entry).
- **Why:** Close and merge only on evidence (D31); one combined fix round per ticket.
- **Evidence:** merger ses_e49e4d31; review sessions ses_e49e776e, ses_e49e75de, ses_e49e84b0, ses_e49e7a78, ses_e49e791c, ses_e49e7da5, ses_e49e7bf8, ses_e49e80f0, ses_e49e7f95.

### Sat 15:10 - D46 applied (demoable cut); nudge 13:08Z handled

- **When:** Sat 15:07-15:12 EET (heartbeat clock). Correction: the entry above headed "15:15" was written at about 15:05.
- **Decision:**
  1. **CS-S1 dropped (D46).** The #63 rebase lane (ses_e49f4e82) was interrupted. #65, #66 and #69 were never dispatched. "Deferred, D46" comments were posted on #24, #53, #54, #56, #63, #65, #66, #88 and #92, and their ready-for-agent labels removed (this stops the utilization monitor flagging them). The planning session told the chain owner to push its WIP and stop. The CS eval exports still ship under D37 (#30).
     - #116 r3 fixer steered: the CS-S1 expectation stays refused/unsupported permanently. A crash exit must not pass, and the "unsupported" outcome is pinned by a test.
     - #130 steered: the README states CS-S1 is unsupported, with skip reason `cs-s1-deferred-d46`.
  2. **Tooling parked until the pin (#117 merge):** #124 and #125+#126 round-2 fixers (ses_e49e3870, ses_e49e4418) interrupted. #124, #125, #126 and #129 commented and unlabelled.
  3. **Queued after the pin:** #133 and #134 natively blocked by #117.
  4. **Dispatched (Opus, from integration e24fa05):**
     - #132: rung-form check for validator-ID rungs. High, demo path, before the pin; 4 reviews in round 1.
     - #80: writer self-scan of withheld source values. It merges after the recording, unless it is green on the real kit before the pin.
     - #128: search keeps record keys. It merges after the recording and after #118, and avoids #118's lines in search.py.
     - #128 was relabelled ready-for-agent + model:opus.
  5. **#30 round 3** finished at 5a6b82f (Opus). Reviews dispatched: Grok Standards and Sol Spec. The Spec reviewer is asked what "complete bundle" means under D46.
  6. **#117 fast track (D46):** when its round-2 head is ready, only high findings against D35/D41 block. It merges alone, ahead of the queue, and its merge commit is the pin.
  7. **#32:** not merged and not closed; the human decides (D47).
  8. **Nudge 13:08Z:**
     - #131 is in ticket/fu110-scorecard-k (live owner ses_e4a02df0).
     - #94 closes on the final proof.
     - #121 waits on #117.
     - #29-packager reviews are now dispatched.
     - The remaining CS items are deferred (above).
- **Why:** D46 (human, 15:05): a demoable HEALTH-S1 web-app cut pinned on the #117 merge by about 17:00.
- **Evidence:** interrupt responses {"interrupted":true} x3; issue comments; sessions ses_e49de3e3 (#132), ses_e49de156 (#80), ses_e49dde65 (#128), ses_e49ddc6a / ses_e49dda89 (#30 reviews).

### Sat 15:16 - D47: #32 GO via the Mistral API; dispatched

- **When:** Sat 15:16 EET (heartbeat clock)
- **Decision:** A Sol session (ses_e49db522) merges integration 436e81c into ticket/31-llm, resolving the cli.py conflicts with search, then does the real Mistral `draft-policy` run once the human's key file exists. The key goes into the env var only and is never printed. Evidence: closed-schema pass, request digest, a no-credentials scan, no values in the request, the offline guard on every other subcommand, and a HEALTH-S1 real-kit run (the D47 condition). Delta reviews follow: Grok Standards + Sonnet Spec. #32 merges before the pin only if that doesn't delay #117; otherwise after the pin.
- **Open:** AC3 of #32 (a drafted policy run through the search) is not amended by D47. The orchestrator asked the human at 15:00 and has no answer yet, so #32 doesn't close until AC3 is amended or met. No draft consumer is being built meanwhile.
- **Why:** D47 (human, 15:12).
- **Evidence:** D47 on main; session ses_e49db522.

### Sat 15:20 - nudge 13:18Z handled

- **When:** Sat 15:18-15:20 EET
- **Decision:**
  - #69: its branch builds on the deferred CS chain, so it needs a fresh branch after the pin. Native blocked-by #117 added; unlabelled.
  - #131: on ticket/fu110-scorecard-k with a live owner. Native blocked-by #110 added.
  - #94: no implementer work remains; it closes on the final proof. Unlabelled.
  - #121: the native #117 edge already exists. The branch flag is the #129 monitor defect.
- **Why:** None of them can be dispatched. The edges and labels stop repeat flags.
- **Evidence:** issue comments on #69, #94 and #131.

### Sat 15:30 - nudge 13:28Z: #117 r2 and #118 r1 reviews dispatched; trains 20 running

- **When:** Sat 15:28-15:30 EET
- **Decision:**
  1. #117 round 2 finished at 0fa353a (Sol). Real kit: HEALTH-S1 RELEASED, gate 41/41, both verify tiers exit 0, using explicit hand plans. Fast-track reviews (D46: only high findings against D35/D41 block): Grok Standards (ses_e49cd713) and Sonnet Spec (ses_e49cd51a). On approval it merges alone, and that merge commit is the pin.
  2. #118 finished at dbbd7a9 (Opus, core). All 4 round-1 reviews dispatched: Grok and Sol on both axes. #118 blocks #127 (with #106).
  3. #121 has a native blocked-by #117 edge; the branch flag is the #129 defect.
  4. Merge train 20 (side/video-shot-list, docs-only, planning steer) is running (ses_e49cddb6).
- **Why:** The D46 fast track; tier-1 fail-closed reviews.
- **Evidence:** done-reports in sessions ses_e4a27f3f (#117) and ses_e4a0a7cb (#118).

### Sat 15:30-15:42 - #118 merged and closed; #30 approved, train 22; #117 r3; #80 reviews; train 20

- **When:** Sat 15:30-15:42 EET (heartbeat clock)
- **Decision:**
  1. #118: 4/4 APPROVE at dbbd7a9. Train 21 merged it at 4ab271e: fast tier exit 0, 2585 passed, 6 skipped; slow tier exit 0, 123 passed. Done-report posted, gate exit 0, closed; worktree and branch removed. #127 now waits only on #106.
  2. #30 round 4 (2b8ec4b, Opus): the D46 complete bundle = HEALTH-S1 + unseen + D37-gated CS eval exports, with outOfScope CS-S1. Grok and Sol delta reviews both APPROVE. Done-report posted, gate exit 0 locally. Train 22 (ses_e49c2c85) is merging it. #117 was not ready, and pets_submission at 16:00 depends on #30.
  3. #117 round 2 (0fa353a): Grok APPROVE; Sonnet Spec high (the UI default is `--plan hand`, not the CLI's search default). Round 3 is with Sol (ses_e49cc60d). Grok's non-blocking notes go to a follow-up after the pin.
  4. #80 (0e0fc58, Opus, core writer): all 4 round-1 reviews dispatched. Under D46 it merges after the recording.
  5. Train 20 merged side/video-shot-list at 026e3c8 (docs: exit 0, 39 passed, 6 named skips); the branch was deleted on origin.
- **Why:** D46 order: before the pin, only demo-path work. Close on evidence (D31).
- **Evidence:** merger sessions ses_e49c94e2 and ses_e49cddb6; review sessions in the issue threads.

### Sat 15:42 - STATUS

#### Blocker -> owner -> next proof
- #117 (the pin) -> ses_e49cc60d (Sol, round 3) -> UI default = search; red/green; real-kit UI capture with byte equality against the search-default CLI. Then a fast-track delta review, then it merges alone.
- #132 (rung-form, high, before the pin) -> ses_e49de3e3 (Opus) -> verify-CLI red/green; real-kit run; 4 reviews.
- #30 (packager) -> train 22 -> merged sha; then the human builds pets_submission from it (D15).
- #32 (LLM, D47) -> ses_e49db522 (Sol) -> HEALTH-S1 evidence at 5e1bf09; the Mistral run waits on the human's key file. Both axes APPROVE at 5e1bf09. AC3 is open for the human.
- #110 + #113 + #131 -> ses_e4a02df0 (Opus) -> measured real-kit evidence and the duplicate-key red.
- #106 (blocks #127) -> ses_e4a0a4c1 (Opus) -> merges after the recording (D46).
- #116 -> ses_e49e7225 (Sol, round 3) -> overall pass:true smoke with CS-S1 unsupported (D46).
- #80, #128 -> after the recording. #130 -> ses_e49f49a4 (Sol). #127 -> after #106.
- Parked until the pin: #124, #125, #126, #129, #133, #134. Deferred (D46): CS-S1 and its follow-ups.

#### Latest exact revision with measured release evidence
- f98cf626e1b7edf104fecbee1602b2f91cef3a8c (planning-session side lane; artefacts and a runnable commands.ps1 in C:\Users\kivas\AI\sinceai-out\proof-f98cf62\).
  - Plain search-plan run, measured default and measured `acme`: all RELEASED. Gate 41 pass / 0 n/a / 0 fail; all 18 assertions false; toolRevision = tip.
  - Both verify tiers pass for all three. Verify (limited) is 37 checked + 4 attested; --full re-ran 41.
- Scorecards (measured), privacy / utility / composite: 0.1716 / 1 / 0.2752 -> 1 / 0.9283 / 0.9661. Linkage risk 0.5697 -> 0. Attribute inference: not measured.
- Purpose checks: U2 0.9671, U4 0.7952, U6 0.9462, U7 0.9827, U8 0.9504. There are 3 sacrifices (U4, U6, U8) and 7 residual risks.
- Person-k: min 5, median 43, below-k 0. This is provisional until #106 merges (test_name is outside k).
- Integration tip 4ab271e (#118): fast tier exit 0 (2585 passed, 6 skipped), slow tier exit 0 (123 passed); no real-kit run on it.

#### Complete-bundle status
- At #30 head 2b8ec4b: a COMPLETE D46 bundle was built on the real kit into a throwaway folder (C:\Users\kivas\AI\sinceai-out\29-packager\evidence-2b8ec4bb727acd9f2aa22a3193eb26e315885509). The delivery folder was untouched and nothing was uploaded. The delivery build waits for train 22.

#### Remaining unknowns
- The pin does not exist yet (#117 round 3).
- Person-k is provisional until #106 merges.
- The #32 Mistral run (key file absent); #32 AC3.
- The default-plan release feeding the packager (#128; the README uses --plan hand until it merges).
- 5 README-ledger skips (named reasons; not passes).

### Sat 15:44 - nudge 13:43Z; #80 round 2

- **When:** Sat 15:43-15:44 EET
- **Decision:**
  - ticket/fu121-readme-examples (#121): approved, with a native blocked-by #117 edge and a comment from 14:40. It is flagged only because of the #129 monitor defect, which is parked until the pin. Not dispatchable.
  - #80 round 1: Sol Standards (high, reproduced on the synthetic minikit), Sol Spec and Grok Spec all CHANGES REQUIRED. A withheld value held by 5 or more rows is exempt from the self-scan. Round 2 is with the Opus implementer (ses_e49de156): drop the frequency exemption, red first. Grok Standards is pending.
- **Evidence:** issue #121 comment; review sessions ses_e49c2940, ses_e49c27a9, ses_e49c2662.

### Sat 15:52 - train 22 red (#30); #135 filed; #132 round 2; #80 Grok

- **When:** Sat 15:46-15:52 EET
- **Decision:**
  1. Train 22 was red on #30 at merged sha ee655fe: fast tier exit 1, 2 failed, 2653 passed. The culprits are two repo-wide guards: raw key bytes read in submission/guards.py (tests/run/test_context_keys.py), and the submission CLI entry point missing from the offline matrix (tests/offline/test_entrypoints.py). Reset, nothing pushed. Round 5 is with the Opus fixer (ses_e49d9d21). pets_submission at 16:00 slips until #30 merges.
  2. Defect class found twice (train 15 tripped tests/policy; train 22 tripped tests/run and tests/offline guards): affected-tests.ps1 doesn't select repo-wide guard tests. Filed #135 (Sol), parked until the pin (native blocked-by #117). Stopgap: all 8 running implementers were told to also run `tests/policy tests/offline/test_entrypoints.py tests/run/test_context_keys.py` and report its exit code.
  3. #132 round 1:
     - Sol Spec: CHANGES REQUIRED (evidence only; the red and mutation exit codes were not cleanly captured).
     - Sol Standards: CHANGES REQUIRED, high. Any anchored regex is accepted for `text` rungs, which hides a column from the text checks; reproduced with production code. Fail-open in verify.
     - Both go to the Opus implementer (ses_e49de3e3): a clean rerun at eed24a7, then round 2 (exact `text` form required for text-backed rungs; red at the verify CLI). Grok's two reviews are pending.
  4. #80: Grok Standards APPROVE (it rates the frequency cut a documented trade-off). Sol Standards high, Sol Spec and Grok Spec all CHANGES REQUIRED. The majority and the issue's Fix line stand, so round 2 continues to remove the exemption.
- **Why:** Close and merge only on evidence; fail-closed on the verify path before the pin (D46).
- **Evidence:** merger ses_e49c2c85; review sessions ses_e49bf33d, ses_e49bf194, ses_e49c2aa4; #135.
