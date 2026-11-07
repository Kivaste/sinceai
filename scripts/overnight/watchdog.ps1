<#
.SYNOPSIS
  Overnight watchdog for the OpenCode /implement-spec orchestrator. Run every 3 minutes
  by the scheduled task (install-watchdog.ps1). Safe to run by hand and concurrently.
  Thresholds are wall-clock and independent of the cadence; CooldownMinutes (20) keeps a
  3-minute cadence from sending more than one intervention per 20 minutes.

.DESCRIPTION
  Liveness signals:
    (a) heartbeat age     .scratch/local-overnight/heartbeat.json (written by heartbeat.ps1)
    (b) commit age        newest committer date on ticket/* and the integration branch, local + origin
    (c) ticket counts     open / closed / parked (ready-for-human) via gh
    (d) OpenCode activity orchestrator session + its child sessions: time.updated, active drains, last outcome
  Decision (first match wins):
    tickets unknown (gh failed)                         -> no action (exit 2)
    no open agent tickets                               -> done, exit quietly
    activity fresh (< StaleMinutes) and not idle-stuck  -> alive, reset escalation
    orchestrator idle, no active child, hb >= IdleMinutes-> nudge (fast path for "turn ended, nobody woke it")
    heartbeat AND commits >= StaleMinutes (and OpenCode activity stale, or both >= HungMinutes)
      -> escalate, at most once per CooldownMinutes:
         step 0-2 : prompt the same session via the HTTP API (queue delivery). If its last outcome
                    was "failed", switch it to -FallbackModel first. If it is running but hung
                    (>= HungMinutes), interrupt it first.
         step 3+  : interrupt the old session, create a NEW session via the API with the full
                    resume prompt (-Model; -FallbackModel from step 4 if the last outcome failed).
         API down : start `opencode run --file resume-prompt.md` as a detached process, guarded
                    by orchestrator.lock (PID + start time; stale when the PID is dead).
  Never two orchestrators: one tracked session id; the old one is interrupted before a new one
  is created; a live orchestrator.lock blocks new starts; a per-state-dir named mutex
  serialises watchdog runs.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/watchdog.ps1 -DryRun
#>
[CmdletBinding()]
param(
  [string]$RepoRoot,
  [string]$StateDir,
  [string]$Repo = 'Kivaste/sinceai',
  [string]$TicketLabel = 'ready-for-agent',
  [string]$ParkLabel = 'ready-for-human',
  [string]$IntegrationBranch,
  [int]$StaleMinutes = 25,
  [int]$IdleMinutes = 10,
  [int]$HungMinutes = 90,
  [int]$CooldownMinutes = 20,
  [int]$MaxContextTokens = 300000,   # hand over to a fresh orchestrator above this context size
  [int]$HandoverCooldownMinutes = 30,
  [string]$Model = 'claude-agent/opus#high',
  [string]$FallbackModel = 'openai/gpt-6.1-sol',
  # Hand-over overrides (test-handover.ps1). Empty = start-orchestrator.ps1 defaults (its -Model, resume-prompt.md).
  [string]$HandoverModel,
  [string]$HandoverPromptFile,
  # Test-only: do not (re)start the keep-awake / gpt-probe helpers.
  [switch]$SkipHelpers,
  [switch]$DryRun,
  [switch]$NoFetch,
  # Test hook: JSON file that replaces the gh / OpenCode / commit probes. See test-watchdog.ps1.
  [string]$Fixture
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (-not $StateDir) { $StateDir = Join-Path $RepoRoot '.scratch\local-overnight' }
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$LogPath = Join-Path $StateDir 'watchdog.log'
$HbPath = Join-Path $StateDir 'heartbeat.json'
$StatePath = Join-Path $StateDir 'watchdog-state.json'
$LockPath = Join-Path $StateDir 'orchestrator.lock'
$PromptPath = Join-Path $PSScriptRoot 'resume-prompt.md'
$NowUtc = (Get-Date).ToUniversalTime()
$fx = $null; if ($Fixture) { $fx = Get-Content -Raw $Fixture | ConvertFrom-Json }

# ---------- helpers ----------
function Write-Log([string]$msg) {
  $line = '{0} [{1}]{2} {3}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz'), $PID, $(if ($DryRun) { ' [DRYRUN]' } else { '' }), $msg
  for ($i = 0; $i -lt 20; $i++) {
    try { [IO.File]::AppendAllText($LogPath, $line + [Environment]::NewLine); break } catch { Start-Sleep -Milliseconds 50 }
  }
  Write-Output $line
}
function Has($o, $n) { return ($null -ne $o) -and ($o.PSObject.Properties.Name -contains $n) }
function Read-Json($p) { if (Test-Path $p) { try { return (Get-Content -Raw $p | ConvertFrom-Json) } catch { return $null } } return $null }
function Write-JsonAtomic($p, $obj) {
  $tmp = '{0}.{1}.{2}.tmp' -f $p, $PID, [guid]::NewGuid().ToString('N')
  [IO.File]::WriteAllText($tmp, ($obj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -Force -LiteralPath $tmp -Destination $p
}
function Quote-Arg([string]$a) {
  # MSVCRT / CommandLineToArgvW quoting (Windows PowerShell 5.1 mangles quotes for native exes).
  if ($a -ne '' -and $a -notmatch '[\s"]') { return $a }
  $sb = New-Object System.Text.StringBuilder; [void]$sb.Append('"'); $bs = 0
  foreach ($ch in $a.ToCharArray()) {
    if ($ch -eq '\') { $bs++; continue }
    if ($ch -eq '"') { [void]$sb.Append('\' * ($bs * 2 + 1)); [void]$sb.Append('"'); $bs = 0; continue }
    if ($bs) { [void]$sb.Append('\' * $bs); $bs = 0 }
    [void]$sb.Append($ch)
  }
  if ($bs) { [void]$sb.Append('\' * ($bs * 2)) }
  [void]$sb.Append('"'); return $sb.ToString()
}
function Invoke-Exe([string]$file, [string[]]$argv, [int]$timeoutSec = 60) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $file
  $psi.Arguments = ($argv | ForEach-Object { Quote-Arg $_ }) -join ' '
  $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
  $psi.WorkingDirectory = $RepoRoot
  try { $p = [System.Diagnostics.Process]::Start($psi) } catch { return [pscustomobject]@{ code = -1; out = ''; err = $_.Exception.Message } }
  $o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
  if (-not $p.WaitForExit($timeoutSec * 1000)) { try { $p.Kill() } catch {}; return [pscustomobject]@{ code = -2; out = ''; err = "timeout after ${timeoutSec}s" } }
  $p.WaitForExit()
  return [pscustomobject]@{ code = $p.ExitCode; out = $o.Result; err = $e.Result }
}
$OcExe = $null; $c = Get-Command opencode -ErrorAction SilentlyContinue; if ($c) { $OcExe = $c.Source }
$GhExe = $null; $c = Get-Command gh -ErrorAction SilentlyContinue; if ($c) { $GhExe = $c.Source }
$GitExe = (Get-Command git).Source
function OcApi([string[]]$argv) {
  if (-not $OcExe) { return $null }
  $r = Invoke-Exe $OcExe (@('api') + $argv) 60
  if ($r.code -ne 0) { return $null }
  try { return ($r.out | ConvertFrom-Json) } catch { return $null }
}
function Parse-Model([string]$m) {
  $variant = $null; if ($m -match '#') { $variant = $m.Split('#')[1]; $m = $m.Split('#')[0] }
  $ref = [ordered]@{ providerID = $m.Split('/')[0]; id = ($m.Split('/', 2)[1]) }
  if ($variant) { $ref.variant = $variant }
  return $ref
}
function MinutesSince($utc) { if ($null -eq $utc) { return $null } return [Math]::Round(($NowUtc - $utc).TotalMinutes, 1) }
function FromMs($ms) { return [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$ms).UtcDateTime }
function Fmt($m) { if ($null -eq $m) { return 'n/a' } return "${m}m" }

# ---------- one watchdog at a time (per state dir) ----------
$sha = [System.Security.Cryptography.SHA1]::Create()
$key = ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($StateDir.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join ''
$mutex = New-Object System.Threading.Mutex($false, "Local\sinceai-overnight-watchdog-$($key.Substring(0,12))")
$owned = $false
try { $owned = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { Write-Log 'action=skip reason="another watchdog run holds the mutex"'; exit 0 }

try {
  # ---------- (0) keep-awake + resume-from-suspend grace ----------
  if (-not $Fixture -and -not $DryRun) {
    $gapMin = 0; $lastLine = Get-Content $LogPath -Tail 1 -ErrorAction SilentlyContinue   # read BEFORE we log anything
    if ($lastLine -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)') { $gapMin = ((Get-Date) - [datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm:ss', $null)).TotalMinutes }
    # Helpers are started via WMI (Win32_Process.Create) so they are NOT children of this task or of the OpenCode
    # server: a server restart or task-scheduler job cleanup must not kill them.
    $helpers = @(@{ pid = 'keep-awake.pid'; script = 'keep-awake.ps1'; skipIf = $null },
                 @{ pid = 'gpt-probe.pid'; script = 'gpt-quota-probe.ps1'; skipIf = (Join-Path $StateDir 'gpt-available.json') },
                 @{ pid = 'deprioritize.pid'; script = 'deprioritize-tests.ps1'; skipIf = $null })
    if ($SkipHelpers) { $helpers = @() }
    foreach ($h in $helpers) {
      if ($h.skipIf -and (Test-Path $h.skipIf)) { continue }
      $hp = $null; $hf = Join-Path $StateDir $h.pid
      if (Test-Path $hf) { $hp = [int](Get-Content $hf -ErrorAction SilentlyContinue) }
      if (-not $hp -or -not (Get-Process -Id $hp -ErrorAction SilentlyContinue)) {
        $cmd = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $PSScriptRoot $h.script)
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $RepoRoot }
        Write-Log ('{0} was not running; started it via WMI (pid {1}, rc {2})' -f $h.script, $r.ProcessId, $r.ReturnValue)
      }
    }
    # If our own previous run is far older than the 3-min cadence, the machine was suspended: every age below is
    # inflated by the suspend, and the network may still be reconnecting. Log it and do not act this cycle.
    if ($gapMin -gt 10) { Write-Log ('action=grace reason="resumed after suspend or missed runs (gap {0:N0} min); not acting this cycle"' -f $gapMin); exit 0 }

    # Context hand-over: a long-running orchestrator degrades and slows far beyond ~150k tokens. Above the limit,
    # start a fresh one (start-orchestrator.ps1 -Force interrupts and retires the old session).
    $hbNow = Read-Json $HbPath
    if ($hbNow -and $hbNow.session_id) {
      $hoFile = Join-Path $StateDir 'last-handover.txt'
      $hoAge = 1e9; if (Test-Path $hoFile) { $hoAge = ((Get-Date) - [datetime](Get-Content $hoFile)).TotalMinutes }
      $msgs = OcApi @('get', "/api/session/$($hbNow.session_id)/message")
      $last = @($msgs.data) | Where-Object { $_.type -eq 'assistant' -and $_.tokens -and $_.tokens.cache } | Select-Object -First 1
      if ($last) {
        $ctx = [int64]$last.tokens.input + [int64]$last.tokens.cache.read + [int64]$last.tokens.cache.write
        if ($ctx -gt $MaxContextTokens -and $hoAge -gt $HandoverCooldownMinutes) {
          Write-Log ('action=handover reason="orchestrator context {0:N0} > {1:N0} tokens" session={2}' -f $ctx, $MaxContextTokens, $hbNow.session_id)
          Set-Content $hoFile (Get-Date).ToString('o')
          $soArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'start-orchestrator.ps1'), '-Force', '-StateDir', $StateDir)
          if ($HandoverModel) { $soArgs += @('-Model', $HandoverModel) }
          if ($HandoverPromptFile) { $soArgs += @('-PromptFile', $HandoverPromptFile) }
          # EAP Continue: under Stop, the child's first stderr line (e.g. a Write-Error) would crash this run and lose the result.
          $ErrorActionPreference = 'Continue'
          $out = & powershell.exe @soArgs 2>&1 | Out-String
          $ErrorActionPreference = 'Stop'
          Write-Log ('handover result: ' + (($out -split "`r?`n" | Where-Object { $_ -match 'created session|retirement|interrupting|error|WARN' }) -join ' | '))
          exit 0
        }
      }
    }
  }
  # ---------- (a) heartbeat ----------
  $hb = Read-Json $HbPath
  $hbAge = $null
  if ($hb -and (Has $hb 'timestamp')) { $hbAge = MinutesSince ([DateTime]::Parse($hb.timestamp).ToUniversalTime()) }
  $state = Read-Json $StatePath
  if (-not $state) { $state = [pscustomobject]@{ step = 0; last_action_utc = $null; session_id = $null; session_set_utc = $null } }
  foreach ($n in 'step', 'last_action_utc', 'session_id', 'session_set_utc') { if (-not (Has $state $n)) { $state | Add-Member -NotePropertyName $n -NotePropertyValue $null } }
  if ($null -eq $state.step) { $state.step = 0 }

  # Orchestrator session: heartbeat claim, unless the watchdog started a newer one since.
  $sessionId = $null
  if ($hb -and (Has $hb 'session_id')) { $sessionId = $hb.session_id }
  if ($state.session_id -and $state.session_set_utc) {
    $setAt = [DateTime]::Parse($state.session_set_utc).ToUniversalTime()
    $hbAt = $null; if ($hb -and (Has $hb 'timestamp')) { $hbAt = [DateTime]::Parse($hb.timestamp).ToUniversalTime() }
    if (-not $sessionId -or $null -eq $hbAt -or $setAt -gt $hbAt) { $sessionId = $state.session_id }
  }
  $integ = $IntegrationBranch; if (-not $integ -and $hb -and (Has $hb 'integration_branch')) { $integ = $hb.integration_branch }
  $ticketIds = @(); if ($hb -and (Has $hb 'tickets')) { $ticketIds = @($hb.tickets | Where-Object { $_ } | ForEach-Object { [int]$_ }) }

  # ---------- (c) tickets ----------
  $tk = $null
  if ($fx -and (Has $fx 'tickets')) {
    if ($fx.tickets -is [string]) { $tk = $null } else { $tk = [pscustomobject]@{ open = [int]$fx.tickets.open; closed = [int]$fx.tickets.closed; parked = [int]$fx.tickets.parked } }
  } elseif ($GhExe) {
    $ghArgs = @('issue', 'list', '-R', $Repo, '--state', 'all', '--limit', '300', '--json', 'number,state,labels')
    if ($ticketIds.Count -eq 0) { $ghArgs += @('--label', $TicketLabel) }
    $r = Invoke-Exe $GhExe $ghArgs 60
    if ($r.code -eq 0) {
      # PS 5.1 emits a JSON array as ONE pipeline object; enumerate it explicitly so each issue is its own element.
      $parsed = (@($r.out) -join "`n") | ConvertFrom-Json
      $issues = @(foreach ($i in $parsed) { $i })
      if ($ticketIds.Count -gt 0) { $issues = @($issues | Where-Object { $ticketIds -contains [int]$_.number }) }
      $open = @($issues | Where-Object { $_.state -eq 'OPEN' })
      $parked = @($open | Where-Object { @($_.labels | ForEach-Object { $_.name }) -contains $ParkLabel })
      $tk = [pscustomobject]@{ open = $open.Count - $parked.Count; closed = @($issues | Where-Object { $_.state -ne 'OPEN' }).Count; parked = $parked.Count }
    } else { Write-Log ('warn gh failed code={0}' -f $r.code) }
  }

  # ---------- (b) commits ----------
  $commitAge = $null; $branchCount = 0
  if ($fx -and (Has $fx 'commit_min_ago')) { $commitAge = $fx.commit_min_ago }
  else {
    if (-not $NoFetch -and -not $fx) {
      $r = Invoke-Exe $GitExe @('-C', $RepoRoot, 'fetch', '--quiet', '--prune', 'origin') 90
      if ($r.code -ne 0) { Write-Log ('warn git fetch failed code={0}' -f $r.code) }
    }
    $refs = @('refs/heads/ticket/', 'refs/remotes/origin/ticket/', 'refs/heads/integration*', 'refs/remotes/origin/integration*')
    if ($integ) { $refs += @("refs/heads/$integ", "refs/remotes/origin/$integ") }
    $r = Invoke-Exe $GitExe (@('-C', $RepoRoot, 'for-each-ref', '--format=%(committerdate:unix) %(refname)') + $refs) 30
    if ($r.code -eq 0) {
      $lines = @($r.out -split "`r?`n" | Where-Object { $_ -match '^\d+ ' })
      $branchCount = @($lines | Where-Object { $_ -match ' refs/heads/ticket/' }).Count
      if ($lines.Count -gt 0) {
        $newest = ($lines | ForEach-Object { [int64]($_.Split(' ')[0]) } | Measure-Object -Maximum).Maximum
        $commitAge = MinutesSince ([DateTimeOffset]::FromUnixTimeSeconds([int64]$newest).UtcDateTime)
      }
    }
  }

  # ---------- (d) OpenCode ----------
  $oc = [pscustomobject]@{ reachable = $false; exists = $false; active = $false; child_active = $false; updated_age = $null; outcome = $null }
  if ($fx -and (Has $fx 'opencode')) {
    foreach ($n in 'reachable', 'exists', 'active', 'child_active', 'updated_age', 'outcome') { if (Has $fx.opencode $n) { $oc.$n = $fx.opencode.$n } }
  } elseif ($OcExe) {
    $act = OcApi @('get', '/api/session/active')
    if ($act) {
      $oc.reachable = $true
      $activeIds = @(); if (Has $act 'data') { $activeIds = @($act.data.PSObject.Properties.Name) }
      if ($sessionId) {
        $s = OcApi @('get', "/api/session/$sessionId")
        if ($s -and (Has $s 'data')) {
          $oc.exists = $true
          $oc.active = $activeIds -contains $sessionId
          if (Has $s.data 'outcome') { $oc.outcome = $s.data.outcome }
          $upd = [int64]$s.data.time.updated
          $kids = OcApi @('get', '/api/session', '--param', "parentID=$sessionId", '--param', 'limit=50')
          if ($kids -and (Has $kids 'data')) {
            foreach ($k in @($kids.data)) {
              if ($k.parentID -ne $sessionId) { continue }
              if ([int64]$k.time.updated -gt $upd) { $upd = [int64]$k.time.updated }
              if ($activeIds -contains $k.id) { $oc.child_active = $true }
            }
          }
          $oc.updated_age = MinutesSince (FromMs $upd)
        }
      }
    }
  }

  # ---------- orchestrator.lock (process fallback) ----------
  $lock = Read-Json $LockPath
  $lockAlive = $false
  if ($lock -and (Has $lock 'pid') -and $lock.pid) {
    $p = Get-Process -Id ([int]$lock.pid) -ErrorAction SilentlyContinue
    if ($p) {
      try { $lockAlive = [Math]::Abs(($p.StartTime.ToUniversalTime() - [DateTime]::Parse($lock.start_utc).ToUniversalTime()).TotalSeconds) -lt 3 } catch { $lockAlive = $false }
    }
    if (-not $lockAlive) {
      Write-Log ('lock stale pid={0} (process gone or PID reused) -> removing' -f $lock.pid)
      if (-not $DryRun) { Remove-Item -Force $LockPath -ErrorAction SilentlyContinue }
      $lock = $null
    }
  }

  # ---------- decide ----------
  $hbA = $hbAge; if ($null -eq $hbA) { $hbA = [double]::PositiveInfinity }
  $cmA = $commitAge; if ($null -eq $cmA) { $cmA = [double]::PositiveInfinity }
  $ocA = $oc.updated_age; if ($null -eq $ocA) { $ocA = [double]::PositiveInfinity }
  $sinceAction = $null; if ($state.last_action_utc) { $sinceAction = MinutesSince ([DateTime]::Parse($state.last_action_utc).ToUniversalTime()) }
  $step = [int]$state.step
  $action = 'none'; $reason = ''
  $sessionUsable = $oc.reachable -and $oc.exists

  if ($null -eq $tk) { $action = 'unknown'; $reason = 'ticket counts unavailable (gh failed); not acting on unknown state' }
  elseif ($tk.open -le 0 -and $tk.closed -eq 0 -and $tk.parked -eq 0) { $action = 'no-tickets'; $reason = 'no tickets found for the spec/label yet' }
  elseif ($tk.open -le 0) { $action = 'done'; $reason = $(if ($tk.parked -gt 0) { "no open agent tickets; $($tk.parked) parked for a human" } else { 'all tickets closed' }) }
  else {
    $fresh = ($hbA -lt $StaleMinutes) -or ($cmA -lt $StaleMinutes) -or ($ocA -lt $StaleMinutes)
    $hung = ($hbA -ge $HungMinutes) -and ($cmA -ge $HungMinutes)
    $idleStuck = $sessionUsable -and (-not $oc.active) -and (-not $oc.child_active) -and ($hbA -ge $IdleMinutes) -and ($ocA -ge $IdleMinutes)
    $stalled = (($hbA -ge $StaleMinutes) -and ($cmA -ge $StaleMinutes) -and ($ocA -ge $StaleMinutes)) -or $hung
    if ($lockAlive -and -not $hung) { $action = 'alive-lock'; $reason = "fallback orchestrator process pid=$($lock.pid) is running" }
    elseif (-not $idleStuck -and -not $stalled -and $fresh) { $action = 'alive'; $reason = 'recent activity' }
    elseif ($null -ne $sinceAction -and $sinceAction -lt $CooldownMinutes) { $action = 'cooldown'; $reason = "last intervention $(Fmt $sinceAction) ago (< ${CooldownMinutes}m)" }
    else {
      $why = $(if ($idleStuck -and -not $stalled) { 'orchestrator idle with no running subagent' } elseif ($hung) { 'heartbeat and commits older than HungMinutes' } else { 'heartbeat and commits older than StaleMinutes' })
      if ($sessionUsable -and $step -lt 3) {
        $action = 'nudge'; $reason = $why
      } elseif ($oc.reachable) {
        $action = 'new-session'; $reason = "$why; escalation step $step$(if (-not $sessionUsable) { '; no usable orchestrator session' })"
      } elseif ($lockAlive) {
        $action = 'restart-process'; $reason = "$why; OpenCode API unreachable; fallback process pid=$($lock.pid) hung"
      } else {
        $action = 'start-process'; $reason = "$why; OpenCode API unreachable"
      }
    }
  }

  $summary = 'action={0} reason="{1}" hb={2} commits={3} oc={4} open={5} closed={6} parked={7} ticket_branches={8} session={9} active={10} child_active={11} outcome={12} step={13}' -f `
    $action, $reason, (Fmt $hbAge), (Fmt $commitAge), (Fmt $oc.updated_age), $(if ($tk) { $tk.open } else { '?' }), $(if ($tk) { $tk.closed } else { '?' }), $(if ($tk) { $tk.parked } else { '?' }), $branchCount, $(if ($sessionId) { $sessionId } else { 'none' }), $oc.active, $oc.child_active, $(if ($oc.outcome) { $oc.outcome } else { 'n/a' }), $step
  Write-Log $summary

  # ---------- act ----------
  $signals = 'Signals: heartbeat {0}, newest ticket/integration commit {1}, open agent tickets {2}.' -f (Fmt $hbAge), (Fmt $commitAge), $(if ($tk) { $tk.open } else { '?' })
  $nowIso = $NowUtc.ToString('o')
  $acted = $false
  switch ($action) {
    'alive' { if ($step -ne 0 -and -not $DryRun) { $state.step = 0; $state.last_action_utc = $null; Write-JsonAtomic $StatePath $state } }
    'nudge' {
      if ($oc.active -and $hung) { Write-Log "interrupt session=$sessionId (running but hung)"; if (-not $DryRun) { [void](OcApi @('post', "/api/session/$sessionId/interrupt", '--data', '{}')) } }
      if ($oc.outcome -eq 'failed' -and $step -ge 1) {
        Write-Log "switch-model session=$sessionId -> $FallbackModel (last outcome failed)"
        if (-not $DryRun) { [void](OcApi @('post', "/api/session/$sessionId/model", '--data', (@{ model = (Parse-Model $FallbackModel) } | ConvertTo-Json -Compress -Depth 4))) }
      }
      $text = "[overnight watchdog $nowIso] You appear stalled: $reason. $signals Re-read scripts/overnight/resume-prompt.md and follow it now: write a heartbeat, reconcile tickets/branches/worktrees, and keep /implement-spec going at full concurrency. Do not end your turn while ready tickets remain and nothing is running."
      Write-Log "prompt session=$sessionId delivery=queue"
      if (-not $DryRun) {
        $res = OcApi @('post', "/api/session/$sessionId/prompt", '--data', (@{ text = $text; delivery = 'queue' } | ConvertTo-Json -Compress))
        if (-not $res) { Write-Log 'error prompt failed; next run escalates' }
      }
      $acted = $true
    }
    'new-session' {
      $m = $Model; if ($oc.outcome -eq 'failed' -and $step -ge 4) { $m = $FallbackModel }
      if ($sessionUsable -and $oc.active) { Write-Log "interrupt old session=$sessionId before replacing it"; if (-not $DryRun) { [void](OcApi @('post', "/api/session/$sessionId/interrupt", '--data', '{}')) } }
      Write-Log "create session model=$m dir=$RepoRoot"
      if (-not $DryRun) {
        $body = @{ title = "overnight orchestrator (watchdog resume $($NowUtc.ToString('HH:mm'))Z)"; agent = 'build'; model = (Parse-Model $m); location = @{ directory = $RepoRoot } } | ConvertTo-Json -Compress -Depth 4
        $created = OcApi @('post', '/api/session', '--data', $body)
        if ($created -and (Has $created 'data')) {
          $newId = $created.data.id
          $text = "[overnight watchdog $nowIso] Resume reason: $reason. $signals Previous orchestrator session: $(if ($sessionId) { $sessionId } else { 'unknown' }) (do not use it; you replace it). Your first action: run scripts/overnight/heartbeat.ps1 -Phase resume -ClaimSession.`n`n" + (Get-Content -Raw $PromptPath)
          $res = OcApi @('post', "/api/session/$newId/prompt", '--data', (@{ text = $text; delivery = 'queue' } | ConvertTo-Json -Compress))
          Write-Log ('new session={0} prompt={1}' -f $newId, $(if ($res) { 'ok' } else { 'FAILED' }))
          $state.session_id = $newId; $state.session_set_utc = $nowIso
        } else { Write-Log 'error session create failed; next run escalates' }
      }
      $acted = $true
    }
    { $_ -in 'start-process', 'restart-process' } {
      if ($action -eq 'restart-process' -and $lock) { Write-Log "kill hung fallback pid=$($lock.pid)"; if (-not $DryRun) { Stop-Process -Id ([int]$lock.pid) -Force -ErrorAction SilentlyContinue; Remove-Item -Force $LockPath -ErrorAction SilentlyContinue } }
      Write-Log "start opencode run model=$Model --file resume-prompt.md (detached)"
      if (-not $DryRun -and $OcExe) {
        $runLog = Join-Path $StateDir ('orchestrator-run-{0}.jsonl' -f $NowUtc.ToString('yyyyMMddTHHmmss'))
        $msg = "[overnight watchdog $nowIso] Resume reason: $reason. $signals Follow the attached resume prompt. First action: scripts/overnight/heartbeat.ps1 -Phase resume -ClaimSession."
        $argStr = ((@('run', '--model', $Model, '--format', 'json', '--title', 'overnight orchestrator (watchdog fallback)', '--file', $PromptPath, $msg)) | ForEach-Object { Quote-Arg $_ }) -join ' '
        $p = Start-Process -FilePath $OcExe -ArgumentList $argStr -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $runLog -RedirectStandardError ($runLog + '.err') -PassThru
        Write-JsonAtomic $LockPath ([ordered]@{ kind = 'process'; pid = $p.Id; start_utc = $p.StartTime.ToUniversalTime().ToString('o'); model = $Model; log = $runLog; started_by_watchdog_pid = $PID })
        Write-Log "started pid=$($p.Id) log=$runLog"
      }
      $acted = $true
    }
  }
  if ($acted -and -not $DryRun) { $state.step = $step + 1; $state.last_action_utc = $nowIso; Write-JsonAtomic $StatePath $state }
  if ($action -eq 'unknown') { exit 2 }
  exit 0
}
catch {
  # Never fail silently: a crashed watchdog is an unsupervised night.
  try { Write-Log ('ERROR watchdog crashed: {0} at {1}' -f $_.Exception.Message, $_.InvocationInfo.PositionMessage -replace '\s+', ' ') } catch {}
  exit 3
}
finally {
  if ($owned) { try { $mutex.ReleaseMutex() } catch {} }
  $mutex.Dispose()
}
