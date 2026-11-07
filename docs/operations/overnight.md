# Overnight run: keeping the orchestrator from stalling

An unattended OpenCode orchestrator (`claude-agent/opus`) runs `/implement-spec`. It launches background implementer subagents (one worktree and one `ticket/*` branch per ticket), merges them into an integration branch, and repeats while there are ready tickets. A scheduled **watchdog** checks liveness every 3 minutes and wakes up, or replaces, the orchestrator when it stalls. The thresholds below are wall-clock minutes, independent of that cadence, and the 20-minute cooldown caps interventions at one per 20 minutes.

Files live in `scripts/overnight/`. State is in `.scratch/local-overnight/`, which is gitignored.

| File | Role |
|---|---|
| `heartbeat.ps1` | The orchestrator runs it after every event. It writes `heartbeat.json`: timestamp, phase, running tickets, spec, ticket list, integration branch, last merged commit and orchestrator session id. The write is atomic. |
| `watchdog.ps1` | The liveness check and its recovery actions. `-DryRun` reports what it would do without doing it. Every check is logged to `watchdog.log`. |
| `resume-prompt.md` | The complete orchestrator brief, used for the **initial** start and for every resume. It covers claiming the session, reading the steering files and `.scratch/local-spec/issue-map.json`, following the implement-spec skill (`integration/pets-release`, one `ticket/NN-slug` worktree per ticket, `tdd`, the merger respecting Merge after, the final `code-review`), label routing (`model:opus` / `model:grok`) with fallbacks, two cross-family reviews, done-report evidence, at most 16 implementers with `pytest -n 8` (dropping to `-n 4` when CPU stays above 90% for 10 minutes), the D16 checkpoints (★ #22 by Sat 09:00 via 04→16/17→21→22, the 08:30 status, the 12:00 and 14:00 go/no-go), heartbeats, parking and push rules. |
| `start-orchestrator.ps1` | Creates a fresh OpenCode session through the API (`claude-agent/opus`, directory set to the repo root), queues `resume-prompt.md` as its first prompt, and records the id in `heartbeat.json` and `watchdog-state.json`. It refuses if a tracked orchestrator is running, was updated within 25 minutes, or holds a live lock; `-Force` interrupts and replaces it. `-DryRun` runs only read-only probes. |
| `install-watchdog.ps1` / `uninstall-watchdog.ps1` | Register or unregister the scheduled task `sinceai-overnight-watchdog`. |
| `test-watchdog.ps1` | A self-test with no Pester: 16 cases in `%TEMP%`. They include the 3-minute cadence cooldown and the parameter defaults. |

## OpenCode facts (verified on v2.2.5, 2026-11-07)

- **Continue a session non-interactively:** `opencode run --session <id> "<msg>"`. The model kept the earlier turns: it was asked which word it had replied with before, and answered correctly. `--continue/-c` continues the last session. `-m provider/model#variant` sets the model, `--agent` the agent, `--file` attaches a file, `--format json` streams JSON events that include the `sessionID`, and `--title` names the session. `run` wraps a message that contains spaces in literal quotes. This is cosmetic.
- **HTTP API, which the watchdog prefers:** `opencode api <METHOD> <path> [--data JSON] [--param k=v]`. It handles discovery and authentication for the background service and starts the service if none is healthy. A direct HTTP call without auth returns 401. The spec is at `opencode api get /openapi.json`.
  - Send a message, which runs server-side and needs no client attached: `POST /api/session/{id}/prompt` with `{"text": "...", "delivery": "queue"}`. `queue` waits for the current turn to finish; `steer` injects the message into the running turn. **Verified:** the session woke up and replied.
  - Create a session: `POST /api/session` with `{"title", "agent": "build", "model": {"providerID", "id", "variant"}, "location": {"directory"}}`. **Verified.**
  - Status:
    - `GET /api/session/active` returns `{data: {ses_…: {type: "running"}}}` for running drains, and leaves idle sessions out.
    - `GET /api/session/{id}` has `time.updated`, `time.busy`, `time.idle`, `outcome` (`succeeded`, `failed` or `interrupted`) and `parentID`.
    - `GET /api/session?parentID={id}` lists child sessions, i.e. the subagents.
    - `GET /api/session/{id}/message` returns messages, newest first.
  - Control: `POST /api/session/{id}/interrupt` with `{}` (verified), `POST /api/session/{id}/model` with `{"model": {...}}`, and `POST /api/session/{id}/compact`.
- **Current session id:** the `OPENCODE_SESSION_ID` environment variable is set in the agent's shell. `heartbeat.ps1` records it.
- **Windows PowerShell 5.1 quirk:** it mangles embedded `"` in arguments to native programs, so `opencode api … --data '{"a":"b c"}'` fails. The watchdog therefore starts `opencode.exe` through `System.Diagnostics.Process`, with MSVC-style argument quoting.

## How the watchdog decides

Signals:

- **(a)** heartbeat age.
- **(b)** age of the newest commit on `ticket/*` and the integration branch, local and `origin`. It runs `git fetch --prune` first.
- **(c)** open, closed and parked (`ready-for-human`) tickets, read with `gh`. If `heartbeat.json` lists tickets, it counts those; otherwise it counts issues labelled `ready-for-agent`.
- **(d)** OpenCode activity: whether the orchestrator session and its children are active, their newest `time.updated`, and the last outcome.

Rules, where the first match wins:

1. gh failed, so the counts are unknown → **no action**, exit 2. It does not act on unknown state.
2. No open agent tickets → **done**: one log line and a quiet exit.
3. A live `orchestrator.lock` process, and not hung → **alive-lock**.
4. Activity fresh (any signal younger than 25 minutes) and the session not idle-stuck → **alive**. This also resets escalation.
5. Intervened less than 20 minutes ago → **cooldown**.
6. Otherwise, if the orchestrator session is idle with no active child and the heartbeat is at least 10 minutes old (fast path), or if the heartbeat, commits and OpenCode activity are all at least 25 minutes old (or the heartbeat and commits are at least 90 minutes old), it escalates:
   - Steps 0–2: **nudge** the same session through the prompt API, with `queue` delivery. If the last outcome was `failed`, it first switches the session to `openai/gpt-6.1-sol`. If the session is running but hung (90 minutes or more), it interrupts it first.
   - Step 3 and later, or no usable session: **new-session**. It interrupts the old session, creates a new one through the API with `claude-agent/opus#high` and the full `resume-prompt.md`, and tracks the new id. If the last outcome was `failed`, step 4 and later use `openai/gpt-6.1-sol`.
   - API unreachable: **start-process**, i.e. a detached `opencode run --file resume-prompt.md`, with `orchestrator.lock` holding the PID and start time. The lock is stale when that PID is dead or has been reused. A fallback process that has hung for 90 minutes is killed and restarted.

Thresholds are parameters: `-StaleMinutes 25 -IdleMinutes 10 -HungMinutes 90 -CooldownMinutes 20`. The resume prompt treats a ticket branch with no commit for **more than 45 minutes**, and no running implementer, as abandoned.

**Concurrency and idempotence:** a named mutex per state directory means a second watchdog exits with `action=skip`. All state is written atomically. Only one orchestrator session id is tracked. A new orchestrator claims it with `heartbeat.ps1 -ClaimSession`, and a heartbeat from any other session cannot overwrite it.

## Install, uninstall and test

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-watchdog.ps1      # expect "16 cases, 0 failed"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/start-orchestrator.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/start-orchestrator.ps1 # prints the session id
opencode --session <id>                                                                       # attach the TUI (run in the repo root)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/watchdog.ps1 -DryRun   # real signals, no action
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/install-watchdog.ps1   # every 3 min for 16 h, hidden
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/uninstall-watchdog.ps1
```

Start the orchestrator first, then install the watchdog. The session runs on the background service, so closing the TUI does not stop it.

The task runs as the current user, **only while that user is logged on**, so it stores no password. A locked screen is fine. Instances do not overlap: the task uses IgnoreNew and the watchdog holds a mutex. Each run has a 2-minute limit at the 3-minute cadence (cadence minus 1, at least 2 and at most 9).

**Keep the machine awake.** The scripts never change power settings. Do this yourself, plugged in to AC:

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE   # note the current AC value
powercfg /change standby-timeout-ac 0                  # never sleep on AC
powercfg /change hibernate-timeout-ac 0
# morning: restore, e.g.
powercfg /change standby-timeout-ac 30
```

Also set lid close on AC to "Do nothing", or keep the lid open, and pause Windows Update for a day.

## Morning check

```powershell
Get-Content .scratch/local-overnight/watchdog.log -Tail 30     # one line per check: action=..., signals
Get-Content .scratch/local-overnight/heartbeat.json
Get-ScheduledTaskInfo sinceai-overnight-watchdog              # LastRunTime, LastTaskResult (0 ok, 2 = gh unknown)
gh issue list -R Kivaste/sinceai --state all --limit 100      # closed vs open vs ready-for-human
git log --oneline -20 <integration-branch>
```

Then read the newest entries in `docs/decision-log.md`, and uninstall the task.

## Utilization monitor (maximum parallelism)

The watchdog only keeps the orchestrator alive; it does not notice an orchestrator that is busy but leaves work undispatched. `utilization-check.ps1` does, every 5 minutes (scheduled task `sinceai-utilization-monitor`, 14 h, 2-minute limit; it is separate from the watchdog and never touches its state).

- **Idle work** = (a) open `ready-for-agent` issues with no open native blockers (`issues/<n>/dependencies/blocked_by`), no live session whose title references them and no branch ahead of integration → *dispatch implementer*; (b) `origin/ticket/*` branches ahead of `integration/pets-release` whose issue is open, with no live session referencing them and a last commit older than 5 minutes → *dispatch review, or merge*.
- Session titles are classified implement / fix / review / merge (child sessions only). `#NN` is issue NN; a bare `NN` (or `22B`) is ticket NN, mapped through `.scratch/local-spec/issue-map.json`. Branches: `ticket/fuNN-*` is issue NN, `ticket/NN-*` is ticket NN. Excluded: issue #1 (spec), issue #32 / `ticket/31-llm` and `ticket/story-drafts` (side lane), `ready-for-human`, closed issues.
- **Nudge** (queued through `send-to-orchestrator.ps1`, one message listing every item and asking to dispatch all of them in one turn) only if idle work exists, mean CPU (3 samples) < 70%, live implement+fix sessions < 16, the last nudge was ≥ 10 minutes ago (`utilization-state.json`), phase is not `done`, and the orchestrator is not inactive-and-idle > 25 minutes (that case is the watchdog's).
- Every run writes one line to `.scratch/local-overnight/utilization.log`: action, reason, CPU, sessions by kind, idle items. Errors are logged and exit 3; a named mutex prevents overlapping runs. If a flagged item is blocked in a way GitHub doesn't record, the orchestrator should add the blocker as an issue dependency so the monitor stops flagging it.

### Main-checkout write guard (#123)

Before any utilization/network probes, each monitor cycle reads `git --no-optional-locks -C <main> status --porcelain=v1 -z --untracked-files=all`. The default `-MainCheckout` is explicitly `C:\Users\kivas\AI\sinceai-hackaton`, not whichever worktree contains the script. Git must identify that exact directory as its top-level. The only baseline paths are `tests/gen_fixtures/test_refusal_manifest_fixtures.py` and `tests/run/test_verify_assertion_rerun.py`; the first scan does **not** silently baseline other dirty paths.

New paths absent from both that baseline and the previous successful snapshot trigger a separate, content-free **steer** message through `send-to-orchestrator.ps1`. This bypasses utilization cooldown, CPU, phase and GitHub checks. The snapshot lives at `main-checkout-writes-<SHA256 of normalized checkout path>.json` in the monitor state directory, with the checkout identity, fixed baseline and previous paths. Failed delivery leaves it unchanged for retry. Git failures (including missing Git) and invalid snapshots produce an **unknown** alert, never clean, and do not advance state.

`-CheckoutCheckOnly` bypasses all capacity probes: exit 0 = no new paths (clean or previously reported), 1 = new dirty paths, 2 = unknown, 3 = delivery/runner failure. `-DryRun` prints the would-be message and writes the monitor log, but never sends or updates snapshots. Use an external `-StateDir` when checking the real main checkout from a worktree:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/utilization-check.ps1 -CheckoutCheckOnly -DryRun -MainCheckout C:\Users\kivas\AI\sinceai-hackaton -StateDir C:\Users\kivas\AI\sinceai-out\fu123\main-state
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-main-checkout-writes.ps1
```

This is path-transition polling, not a filesystem audit: it cannot detect a write restored entirely between cycles, another overwrite of an already-dirty path, ignored files, or attribute a write to an agent rather than the orchestrator. A committed clean orchestrator change produces no dirty path. A disappeared path alerts again if it reappears after an observed cycle without it. Deploying the merged script to the existing scheduled monitor remains the orchestrator's job; worktree tests never modify the live task.

### Session wait / idle guards (#125, #126)

After the checkout guard, but before CPU, GitHub, phase and cooldown checks, each cycle checks session health. A checkout alert does not suppress this scan. The monitor discovers idle workers by searching session titles for the heartbeat's running issue numbers (including `merge:N` entries), plus legacy ticket numbers resolved through the issue map. It follows session-list cursors, including workers under earlier or nested parents; `/api/session/active` alone omits idle sessions. `-IssueMapPath` overrides the normal `.scratch/local-spec/issue-map.json` for isolated runs.

- An idle implementer, fixer or merger on a running ticket is flagged when its newest assistant text lacks a `## Done-report`, `## Merger report` or `## Merge report` heading. Older reports cannot hide newer waiting text. Tool-only message pages are followed until the newest text is found.
- Every active session, including the root orchestrator, is checked for running shell tools. PowerShell command syntax identifies file/process polling loops, sleep loops, `Start-Sleep` over 120 seconds, `waitany` over two minutes (or without a bound), and `Wait-Process` targets absent from the local process inventory. Explicit wait patterns alert immediately; they do not wait ten minutes.
- Other shell calls older than ten minutes are flagged if their process tree has no live worker. The root is identified by tool PID metadata, or its command line; shell/sleep wrapper processes alone are not workers. A live pytest/Python/Git descendant is not a blocked wait. If process identity cannot be established, the result is **unknown**, not a guessed pass.

Alerts use the real `send-to-orchestrator.ps1` **steer** path, without utilization cooldown. They contain only session ID, ticket number (or `none`), status, a fixed pattern name and age; never assistant text, commands, process command lines or API diagnostics. No worker is killed or interrupted. API, response-shape, pagination-budget and process-probe failures report **unknown**. A failed delivery fails the run.

`-SessionCheckOnly` runs checkout and session guards without capacity/GitHub probes: exit 0 = healthy, 1 = flagged, 2 = unknown, 3 = runner/delivery failure (combined with the checkout result). `-DryRun` logs classifications and prints the would-be steer, but sends nothing. Use an external state directory containing a content-free heartbeat when probing from a worktree:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/utilization-check.ps1 -SessionCheckOnly -DryRun -StateDir C:\Users\kivas\AI\sinceai-out\fu125\state -IssueMapPath C:\Users\kivas\AI\sinceai-out\fu125\issue-map.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-session-waits.ps1 -Case workers
```

This is a monitor-cycle snapshot, not a proof of useful progress: it cannot predict writes from arbitrary external processes, interpret arbitrary programs, or see a wait that starts and ends between cycles. An unreadable probe remains unknown. Implementers and mergers must run tests and real runs in the foreground with a long timeout, never end their turn while background work runs, and finish with the template's report heading.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/utilization-check.ps1 -DryRun   # decision + message, nothing sent
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/install-utilization.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/uninstall-utilization.ps1
Get-Content .scratch/local-overnight/utilization.log -Tail 10
```

## Failure modes

| Covered | How |
|---|---|
| The orchestrator's turn ends and nobody wakes it | Idle fast path: nudge after 10 minutes |
| The orchestrator hangs mid-turn | Interrupt and nudge after 90 minutes with no heartbeat or commits |
| A subagent hangs | The orchestrator abandons and re-dispatches after 45 minutes (resume prompt). An active child holds off a restart only until the 90-minute limit |
| Vendor rate limit or error (`outcome=failed`) | Switch to the fallback model, then start a new session |
| Context window full or a wedged session | After 3 nudges with no progress, a new session with the full resume prompt |
| OpenCode service crash | `opencode api` restarts the service. If the API is still down, a detached `opencode run` guarded by the lock |
| Two watchdogs at once | Mutex |
| Two orchestrators | One tracked id; the old one is interrupted; PID lock |

| Not covered | Mitigation |
|---|---|
| Machine sleep or hibernate, lid closed, on battery | The `powercfg` commands above; stay on AC |
| A Windows Update reboot, or logging off (the task only runs while logged on) | Pause updates. After a reboot, log on: the task resumes, though OpenCode's own sessions persist only as far as the service persists them |
| A vendor-wide outage of both the primary and the fallback model | The watchdog keeps nudging every 20 minutes or more; the work resumes when a vendor is back |
| GitHub or the network down | The watchdog takes no action (exit 2), because progress is impossible anyway |
| An orchestrator that is "busy" but making no progress while its heartbeat keeps going | Not detected. A heartbeat counts as liveness. Look at the decision log in the morning |
| Bad merges or wrong work | Out of scope. The reviews and gates in AGENTS.md cover this |
