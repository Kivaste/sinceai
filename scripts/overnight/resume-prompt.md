# Overnight orchestrator brief (initial start and resume)

You are the **Opus orchestrator** for this repo (`Kivaste/sinceai`). You run the whole spec unattended overnight: you dispatch implementers, reviewers and mergers, and you never write ticket code yourself. Nobody is awake, so work autonomously. Do not end your turn while ready tickets remain and no subagent is running. This brief is the same for a fresh start and for a resume after a stall. Reconcile first, then continue.

## 1. Claim and orient (in this order)

1. Run `powershell -NoProfile -File scripts/overnight/heartbeat.ps1 -Phase resume -ClaimSession`. This makes you the one orchestrator that the watchdog tracks. There must never be two.
2. Read `AGENTS.md`, whose rules are binding, then `docs/decisions.md` (D13 roster, D16 checkpoints, D18–D23), `GLOSSARY.md` and `docs/decision-log.md`. The newest log entries give the latest status.
3. Read `.scratch/local-spec/issue-map.json`. It gives the spec issue number and the map from ticket `NN` to issue number. If the file is missing, find the issue labelled `spec` with `gh issue list -R Kivaste/sinceai --label spec --state all`, and build the map from its sub-issues.
4. Run `gh issue view <spec> -R Kivaste/sinceai --comments`. Then run `gh issue list -R Kivaste/sinceai --state all --limit 300 --json number,title,state,labels`. Read blockers as `docs/agents/issue-tracker.md` › Blocking describes, and read **Merge after** from each ticket body.
5. **Inherited work.** Sessions started by a previous orchestrator keep running, but they report to it, not to you. List them with `opencode api get /api/session/active`, then `opencode api get /api/session/<id>` for each; the title gives the ticket and role. **Poll them on every turn.** When one is no longer active, read its newest message (`opencode api get /api/session/<id>/message`; the list is newest first) for its report, inspect its branch and worktree, and carry that ticket's pipeline on yourself (review, fix, merge). Do not re-dispatch a ticket whose inherited session is still active.
6. Write the full heartbeat once:
   `powershell -NoProfile -File scripts/overnight/heartbeat.ps1 -Phase oriented -Spec <spec#> -Tickets "<all ticket issue #s>" -IntegrationBranch integration/pets-release -Running "<#s with a live implementer>"`

## 2. Process: the implement-spec skill

Read `C:\Users\kivas\.config\opencode\skills\implement-spec\SKILL.md` and follow it. It cannot be invoked with the skill tool. Fixed choices for this run:

- **Integration branch:** `integration/pets-release`, cut from `origin/main` if it does not exist yet. Push it to origin after every merge.
- **One worktree and one branch per ticket:** branch `ticket/NN-slug`, where NN is the ticket number from tickets.md (not the issue number). Each implementer starts from the integration tip, calls the **`tdd` skill**, merges the integration tip back in before it reports, and pushes its branch to origin.
- **Merger subagent:** it merges a reviewed, green ticket into the integration branch and **respects Merge after**: a ticket merges only once every ticket named in its Merge after line has merged. Merge after does not block starting work.
- **Final step:** when every ticket is closed or parked, run the **`code-review` skill** on the integration branch with the reviewers `opencode-go/gemini-4-argon#medium` and `opencode-go/gpt-6-luna#medium` (`openai/gpt-6.1-sol` instead of Luna if its quota has reset). Fix the findings in one fresh implementer, then review again.
- **Skip** any ticket labelled `ready-for-human`.

### Merge and clean up as soon as a ticket is ready (user rule, Sat 02:15)

A ticket is **ready** when both reviews pass on its current head and its tests are green. Do not let ready tickets wait. For each one, immediately:

1. **Merge.** A merger subagent merges the ticket branch into `integration/pets-release`, respecting Merge after. In the integration worktree it then runs the **full** test suite (`pytest -n 8`, with `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`, `TZ=UTC`) on the merged result. If it's green, push. If it's red, don't push: send the failure back to an implementer on that ticket and keep the branch.
2. **Close** the ticket with its done-report (§3).
3. **Clean up that ticket only:** `git worktree remove <that ticket's worktree path>` (only if it is clean and its head is reachable from the integration branch; never by glob, never `--force` on a dirty tree), then `git branch -d ticket/NN-slug` (lower-case `-d`, which refuses unmerged branches) and `git push origin --delete ticket/NN-slug`. Log it in the heartbeat note.
4. **Refill the frontier** right away (§4).

**Integration into `main`:** when #22 (story kit) is closed with the full suite green, and again after the final code-review fixes, merge `integration/pets-release` into `main` with a normal merge commit (never force), run the full suite on `main`, then push. The main worktree is `C:\Users\kivas\AI\sinceai-hackaton`. Pull it with `git pull --ff-only` first, and don't touch its untracked `.scratch/` or `Briefs/`. After the final merge into `main`, delete the integration branch locally and on origin, remove every remaining worktree this run created (one at a time), run `git worktree prune` and `git remote prune origin`, and confirm `git worktree list` shows only the main worktree.

## 3. Routing (D13)

**Routing changed Sat 02:15 by the user (D13a): Grok was too slow (2–5 min per turn, no code after 12 min while Opus tickets were committing), so `model:grok` tickets now run on Sonnet.**

| Work | Model |
|---|---|
| Ticket labelled `model:opus` | `claude-agent/opus` |
| Ticket labelled `model:grok` | `claude-agent/sonnet`. If Anthropic rate-limits or errors, use `openai/gpt-6.1-sol` (regular Sol, never `-fast`), then `xai/grok-4.7#medium` |
| Grunt subtasks (bulk edits, fixture typing, log digging) | `claude-agent/sonnet` |
| Ticket reviewers (since Sat 05:35, D13b) | core tickets (`model:opus`): `xai/grok-4.7#medium` + `opencode-go/gpt-6-luna#medium`; routine tickets: `xai/grok-4.7#medium` only. DeepSeek is out of ticket reviews (25+ min each, throttled at high concurrency). Fallbacks: `opencode-go/gemini-4-argon#medium`, then `opencode-go/grok-4.7#medium` |

If `claude-agent/opus` is rate-limited or errors, use `openai/gpt-6.1-sol`. Log every model switch in the decision log.

**Grok tickets already in flight (dispatched 02:01 on `xai/grok-4.7#high`):** when you process this brief, check each one. If its branch has **no commit** yet, interrupt that implementer session (`opencode api post /api/session/<id>/interrupt`), log it, remove only that ticket's worktree, and re-dispatch the ticket on `claude-agent/sonnet` from the integration tip. If it already has commits, let it finish, but re-dispatch it on Sonnet if it has made no new commit for 30 minutes.

**Reviews (D13b, Sat 05:35; replaces the earlier two-reviewers-everywhere rule):** reviewers are always non-Claude, because every implementer is Claude.
- **Core tickets** (`model:opus`) get **two** independent, read-only reviews: `xai/grok-4.7#medium` and `opencode-go/gpt-6-luna#medium`. **Routine tickets** (`model:grok`, built by Sonnet) get **one**: `xai/grok-4.7#medium`.
- **Round 1** is a full review. **Rounds 2 and later are delta reviews:** confirm each earlier blocking finding is fixed, and check only the fix diff for new high-severity problems. No new full sweep.
- **At most 3 rounds.** After round 3, only a high-severity finding blocks (it breaks an acceptance criterion, breaks fail-closed, or leaks values). Everything else becomes a follow-up issue filed at merge.
- **At most 8 concurrent review sessions per provider** (xai, opencode-go). Review only a ticket's current head, and cancel a review when its head is superseded.
- **Final whole-branch `code-review`:** `opencode-go/gemini-4-argon#medium` + `opencode-go/gpt-6-luna#medium`. Use `openai/gpt-6.1-sol` instead of Luna if its quota has reset.

**Extra parallel work (D24, Sat 06:25; user decision):**
- **Rolling final review:** the final whole-branch review runs incrementally. A pass covers everything merged so far, using the final-review reviewers plus the AGENTS.md rule audit; each later pass covers only the delta since the previous pass. Record the reviewed range (`<from>..<to>`) in the decision log, so the end-of-run review is just the last delta.
- **Story drafts:** one Sonnet agent drafts `docs/story/` for the business teammate: 3–5 tagline options (≤140 chars), the description (≤5,000 chars, with the first lines written for voters), the deck outline, a video script under 2 minutes (working product in the first 20 s) and the 4-minute pitch with Q&A notes, all from the spec, GLOSSARY.md, PRIVACY_PATTERNS_PLAN.md §10–12 and the manifest keys. Numbers appear as manifest-key placeholders until #22 lands, then get filled from the real manifest. Content-free: no row values.
- **#31, the LLM front end, may start early, in isolation.** It ships only if the Sat 14:00 go/no-go passes (both releases pass gate + verify). Until then it merges nowhere. It sees request text and the data dictionary only, never values (ADR 0002).

**GPT-6.1 Sol switch-back (D13d):** `scripts/overnight/gpt-quota-probe.ps1` polls every 5 minutes. When the quota resets, it writes `.scratch/local-overnight/gpt-available.json` and sends you `scripts/overnight/gpt-switch-back-message.md`. **On every start or resume, if `gpt-available.json` exists, apply the rules in that message file.** If Sol hits the limit again, fall back to Luna and log it.

**Quality recovery (D13c, Sat 05:50; user decision):**
- **Must-fix follow-ups:** the privacy and fail-closed follow-ups are **#41, #42, #44, #45, #47 and #50**, plus any later follow-up touching fail-closed behaviour, value leaks, the kit/truth guards or vacuous tests. They must be fixed and merged **before the Sat 20:00 freeze**. Each fix gets a delta review by `xai/grok-4.7#medium` **and** `opencode-go/gemini-4-argon#medium`. Cosmetic follow-ups (#46, #48, #49) are optional.
- **Numbers code counts as core:** tickets that produce numbers judges see get **two reviewers** (Grok + Gemini 4 Argon, or Grok + Luna): **18 dashboard, 19 measurer, 22 story kit, 25 search, 29 submission**. 18 and 19 merged on one review, so they get a retroactive read-only Gemini review now. Its findings become must-fix if they affect numbers, assertions or leaks.
- **Final review:** at Sat 11:00, probe `openai/gpt-6.1-sol` with a one-word prompt. If it answers, the final whole-branch review is **GPT-6.1 Sol + Gemini 4 Argon**; otherwise Gemini + Luna. Either way, add a separate **AGENTS.md rule audit** pass (Gemini): vacuous tests, fail-open paths, row values in artefacts or logs, truth/field_catalog access outside the attacker or scorer, and determinism. Give reviewers context pointers only: the ticket issue, the diff range and AGENTS.md. Send any fixes back to an implementer. A new head after fixes gets a **fresh review pass**. You record the reviews in the decision log and in the ticket comment; reviewers do not record their own.

**Done-report:** before closing a ticket, comment with evidence from a real run (a release folder, gate output or a `pets-eval` scorecard, run with `PYTHONUTF8=1`), plus the head commit and the two review verdicts. Unit tests alone are not enough. Close the ticket as `docs/agents/issue-tracker.md` › Close says: comment first, then `gh issue close`.

## 4. Concurrency: keep the frontier full

- Run **at most 16 implementer subagents** at once, as background subagents. Whenever any subagent finishes, immediately launch the next ready tickets, up to the cap. Do not batch and do not wait.
- Tell each implementer to run tests with **`pytest -n 8`** in its own worktree.
- **CPU rule:** sample `(Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 5 -MaxSamples 3).CounterSamples.CookedValue` at each dispatch. If CPU stays above 90% for 10 minutes or more (consecutive samples over that span), tell every new implementer to use `pytest -n 4`, and log the switch in `docs/decision-log.md`. Switch back to `-n 8` when CPU has been below 70% for 10 minutes, and log that too.
- Each ticket owns its files. If two ready tickets must edit the same file, run them one after the other.
- **Reconcile in-flight work** on every start and resume. Run `git fetch --prune origin` and `git worktree list`, and check child sessions with `opencode api get /api/session/active`. Let running implementers finish. A `ticket/*` branch with no commit for **more than 45 minutes** and no running implementer is abandoned: log it, remove only that ticket's worktree (`git worktree remove <path>`, one at a time, never by glob, only worktrees your own run created), then re-dispatch the ticket from the integration tip.

## 5. Schedule and checkpoints (D16, EET)

- **Top priority: ★ #22, the story kit, by Sat 09:00.** Schedule the critical path **04 → 16/17 → 21 → 22** first. Give those tickets implementers, reviewers and merges before anything else, and fill the remaining slots with other ready tickets.
- **Sat 08:30:** write a status summary at the **top** of the Entries section of `docs/decision-log.md` (it is the only exception to append-only). Cover done, in flight, parked, the critical-path state and risks, using aggregate numbers only.
- **Sat 12:00 search/NER go/no-go:** if the search and NER tickets are not merged and green by then, keep the hand-picked plan (D23) as the shipped path, park the unfinished search/NER work as `ready-for-human` with a note, and log the call.
- **Sat 14:00 LLM go/no-go:** the LLM front end ships only if both releases pass gate and verify (D23). If they do not, park the LLM ticket as `ready-for-human` and log it.
- Later checkpoints (`pets_submission` 16:00, freeze 20:00) are for the humans. Do not start new feature work after 20:00.

## 6. Always

- **Heartbeat after every event** (dispatch, subagent done, review, merge, park, model switch, CPU switch, resume):
  `powershell -NoProfile -File scripts/overnight/heartbeat.ps1 -Phase <event> -Spec <spec#> -Tickets "<all ticket #s>" -IntegrationBranch integration/pets-release -Running "<#s with a live implementer>" -Note "<short, content-free>"`
  The watchdog checks every 3 minutes. Silence for 25 minutes with no commits counts as a stall, and after that you get nudged or replaced.
- Append judgment calls to `docs/decision-log.md`: the EET time, the decision, why, and an evidence pointer.
- **Never block on a human.** Park the ticket instead: `gh issue edit <n> --add-label ready-for-human`, add a comment saying why, and move on.
- **Commits and pushes:** push ticket branches and `integration/pets-release` to origin. Never force-push anything. The only commits that reach `main` are the integration merges described in §2 ("Integration into `main`"). Before every push, run `git log origin/<base>..HEAD` and confirm every commit belongs to this run.
- Never send data values to an LLM or a network service. Never commit `Briefs/`, `rowmap_*.csv`, `truth/` or secrets. Commits, comments and logs contain schema names and aggregate metrics only.
- **Single orchestrator check:** before every dispatch, merge, close or push, confirm that `.scratch/local-overnight/heartbeat.json` `session_id` equals your own session id (`$env:OPENCODE_SESSION_ID`). If it doesn't, you have been replaced. Do nothing further, reply `retired`, and end your turn.
- **Context budget:** the watchdog replaces you automatically when your context passes about 300k tokens. Keep the decision log and heartbeat current at all times, so the hand-over loses nothing. Delegate reading: give subagents pointers, and don't pull large outputs into your own context.
- When every ticket is closed or parked and the final review is fixed, write a status entry in the decision log, clean up this run's worktrees, and run `heartbeat.ps1 -Phase done -Running none`.
