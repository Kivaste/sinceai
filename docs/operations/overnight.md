# Overnight run: keeping the orchestrator from stalling

An unattended OpenCode orchestrator (`claude-agent/opus`) runs `/implement-spec`. It launches background implementer subagents (one worktree and one `ticket/*` branch per ticket), merges them into an integration branch, and repeats while there are ready tickets. A scheduled **watchdog** checks liveness every 10 minutes and wakes up, or replaces, the orchestrator when it stalls.

Files live in `scripts/overnight/`. State is in `.scratch/local-overnight/`, which is gitignored.

| File | Role |
|---|---|
| `heartbeat.ps1` | The orchestrator runs it after every event. It writes `heartbeat.json`: timestamp, phase, running tickets, spec, ticket list, integration branch, last merged commit and orchestrator session id. The write is atomic. |
| `watchdog.ps1` | The liveness check and its recovery actions. `-DryRun` reports what it would do without doing it. Every check is logged to `watchdog.log`. |
| `resume-prompt.md` | The prompt given to a fresh orchestrator. It covers claiming the session, reconciling worktrees and branches, abandoning stale branches after 45 minutes, max concurrency (10), the D13 roster and fallbacks, heartbeats, the decision log and parking tickets. |
| `install-watchdog.ps1` / `uninstall-watchdog.ps1` | Register or unregister the scheduled task `sinceai-overnight-watchdog`. |
| `test-watchdog.ps1` | A self-test with no Pester: 13 dry-run scenarios in `%TEMP%`. |

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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-watchdog.ps1      # expect "13 cases, 0 failed"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/watchdog.ps1 -DryRun   # real signals, no action
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/install-watchdog.ps1   # every 10 min for 16 h, hidden
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/uninstall-watchdog.ps1
```

The task runs as the current user, **only while that user is logged on**, so it stores no password. A locked screen is fine. Instances do not overlap, and each run has a 9-minute limit.

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
