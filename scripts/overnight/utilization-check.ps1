<#
.SYNOPSIS
  "Maximum parallelism" monitor for the overnight run. Run every 5 minutes by the scheduled task
  (install-utilization.ps1). Finds idle work and, when the machine has headroom, queues ONE nudge to the
  orchestrator asking it to dispatch all of it in one turn. Read-only apart from the nudge, its state file
  and its log. Never touches watchdog state; liveness / restarts stay the watchdog's job.

.DESCRIPTION
  Idle work =
    (a) open ready-for-agent issues with no open native blockers (issue dependencies) and no live session
        referencing them                                                   -> dispatch implementer
    (b) origin/ticket/* branches ahead of the integration branch by >= 1, whose issue is open, with no live
        session referencing them and a last commit older than BranchQuietMinutes -> dispatch review / merge
  Nudge only when: idle work exists AND mean CPU < MaxCpu AND live implement+fix sessions < MaxWorkers AND
  the last nudge was >= CooldownMinutes ago AND phase != done AND the orchestrator is not dead-idle
  (session not active and idle > DeadIdleMinutes: that is the watchdog's case).
  Session titles -> kind (implement / fix / review / merge / other) and references:
    "#NN"           -> issue NN
    bare NN or NNx ("22B"; 1-2 digits, not glued to letters before, not after pass/round/step/part/v) -> ticket NN -> issue via .scratch/local-spec/issue-map.json
  Branch names: ticket/fuNN-* -> issue NN; ticket/NN-* -> ticket NN -> issue via the map.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/utilization-check.ps1 -DryRun
#>
[CmdletBinding()]
param(
  [string]$Repo = 'Kivaste/sinceai',
  [string]$TicketLabel = 'ready-for-agent',
  [string]$ParkLabel = 'ready-for-human',
  [string]$IntegrationBranch = 'integration/pets-release',
  [int[]]$ExcludeIssues = @(1, 32),                                  # spec; ticket 31 LLM (side lane)
  [string[]]$ExcludeBranches = @('ticket/story-drafts', 'ticket/31-llm'),  # side lane
  [double]$MaxCpu = 70,
  [int]$MaxWorkers = 16,
  [int]$CooldownMinutes = 10,
  [int]$BranchQuietMinutes = 5,
  [int]$DeadIdleMinutes = 25,
  [int]$BudgetSeconds = 90,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot '.scratch\local-overnight'
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$LogPath = Join-Path $StateDir 'utilization.log'
$StatePath = Join-Path $StateDir 'utilization-state.json'
$HbPath = Join-Path $StateDir 'heartbeat.json'
$MapPath = Join-Path $RepoRoot '.scratch\local-spec\issue-map.json'
$NowUtc = (Get-Date).ToUniversalTime()
$Clock = [Diagnostics.Stopwatch]::StartNew()

# ---------- helpers (same patterns as watchdog.ps1) ----------
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
function Invoke-Exe([string]$file, [string[]]$argv, [int]$timeoutSec = 30) {
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
function Need([string]$what) {
  # Hard stop if the run budget is gone: a partial picture must not produce a nudge.
  if ($Clock.Elapsed.TotalSeconds -gt ($BudgetSeconds - 10)) { throw "time budget exhausted before: $what" }
}
function Must($r, [string]$what) { if ($r.code -ne 0) { throw ('{0} failed code={1}: {2}' -f $what, $r.code, (($r.err -replace '\s+', ' ').Trim())) } return $r.out }
function JsonList([string]$text) {
  # PS 5.1 emits a JSON array as ONE pipeline object; enumerate it explicitly.
  $parsed = $text | ConvertFrom-Json
  return @(foreach ($x in $parsed) { $x })
}
$OcExe = (Get-Command opencode -ErrorAction Stop).Source
$GhExe = (Get-Command gh -ErrorAction Stop).Source
$GitExe = (Get-Command git -ErrorAction Stop).Source
function OcApi([string]$path) { return ((Must (Invoke-Exe $OcExe @('api', 'get', $path) 30) "opencode api get $path") | ConvertFrom-Json) }

# ---------- one run at a time ----------
$sha = [System.Security.Cryptography.SHA1]::Create()
$key = ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($StateDir.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join ''
$mutex = New-Object System.Threading.Mutex($false, "Local\sinceai-utilization-$($key.Substring(0,12))")
$owned = $false
try { $owned = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { Write-Log 'action=skip reason="another utilization run holds the mutex"'; exit 0 }

try {
  # ---------- inputs ----------
  $hb = Read-Json $HbPath
  if (-not $hb) { throw "heartbeat missing or unreadable: $HbPath" }
  $map = Read-Json $MapPath
  if (-not $map) { throw "issue map missing or unreadable: $MapPath" }
  function TicketToIssue([string]$t) {
    $k = '{0:D2}' -f [int]$t
    if (Has $map $k) { return [int]$map.$k }
    return $null
  }

  # ---------- CPU (3 samples) ----------
  $cpu = $null
  try {
    $samples = Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 3 -ErrorAction Stop
    $cpu = [Math]::Round((@($samples | ForEach-Object { $_.CounterSamples[0].CookedValue }) | Measure-Object -Average).Average, 1)
  } catch {
    # Localised counter names: fall back to WMI load percentage, 3 samples.
    $vals = for ($i = 0; $i -lt 3; $i++) { (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average; if ($i -lt 2) { Start-Sleep -Seconds 1 } }
    $cpu = [Math]::Round((@($vals) | Measure-Object -Average).Average, 1)
  }

  # ---------- live sessions ----------
  Need 'sessions'
  $act = OcApi '/api/session/active'
  $activeIds = @(); if (Has $act 'data') { $activeIds = @($act.data.PSObject.Properties.Name) }
  $sessions = @()
  $refIssues = @{}   # issue number -> session title
  $orch = $null
  foreach ($id in $activeIds) {
    Need "session $id"
    $d = (OcApi "/api/session/$id").data
    if (-not $d) { continue }
    $t = [string]$d.title
    $kind = 'other'
    if ($t -match '(?i)\bImplement') { $kind = 'implement' }
    elseif ($t -match '(?i)\bFix') { $kind = 'fix' }
    elseif ($t -match '(?i)\bMerge') { $kind = 'merge' }
    elseif ($t -match '(?i)\bReview') { $kind = 'review' }
    if (-not $d.parentID) { $kind = 'other' }   # root sessions (side-lane leads, chats) are not workers
    if ($id -eq $hb.session_id) { $kind = 'orchestrator' }
    $sessions += [pscustomobject]@{ id = $id; kind = $kind; title = $t }
    if ($kind -eq 'orchestrator') { continue }
    foreach ($m in [regex]::Matches($t, '#(\d+)')) { $refIssues[[int]$m.Groups[1].Value] = $t }
    $bare = [regex]::Replace($t, '#\d+', ' ')
    $bare = [regex]::Replace($bare, '(?i)\b(pass|round|step|part|v)\s*\d+', ' ')
    foreach ($m in [regex]::Matches($bare, '(?<![\w.])(\d{1,2})[A-Za-z]?(?![\w.])')) {
      $iss = TicketToIssue $m.Groups[1].Value
      if ($iss) { $refIssues[$iss] = $t }
    }
  }
  $byKind = @{}; foreach ($k in 'implement', 'fix', 'review', 'merge', 'other') { $byKind[$k] = @($sessions | Where-Object { $_.kind -eq $k }).Count }
  $workers = $byKind['implement'] + $byKind['fix']

  # Orchestrator dead-idle? (watchdog's job, not ours)
  $orchActive = $activeIds -contains $hb.session_id
  $orchIdleMin = $null
  if ($hb.session_id) {
    try { $od = (OcApi "/api/session/$($hb.session_id)").data; $orchIdleMin = [Math]::Round(($NowUtc - [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$od.time.updated).UtcDateTime).TotalMinutes, 1) } catch { $orchIdleMin = $null }
  }

  # ---------- issues ----------
  Need 'issues'
  $issuesOut = Must (Invoke-Exe $GhExe @('issue', 'list', '-R', $Repo, '--state', 'open', '--limit', '300', '--json', 'number,title,labels') 40) 'gh issue list'
  $openIssues = @{}
  foreach ($i in (JsonList $issuesOut)) {
    $labels = @($i.labels | ForEach-Object { $_.name })
    $openIssues[[int]$i.number] = [pscustomobject]@{ number = [int]$i.number; title = [string]$i.title; agent = ($labels -contains $TicketLabel); parked = ($labels -contains $ParkLabel) }
  }
  function Eligible([int]$n) { $x = $openIssues[$n]; return ($null -ne $x) -and $x.agent -and -not $x.parked -and ($ExcludeIssues -notcontains $n) }

  # ---------- branches ahead of integration ----------
  Need 'branches'
  $refsOut = Must (Invoke-Exe $GitExe @('-C', $RepoRoot, 'for-each-ref', '--format=%(refname:short) %(committerdate:unix)', 'refs/remotes/origin/ticket/') 20) 'git for-each-ref'
  $branchByIssue = @{}
  $idle = New-Object System.Collections.ArrayList
  foreach ($line in @($refsOut -split "`r?`n" | Where-Object { $_ -match '^origin/ticket/\S+ \d+$' })) {
    $ref, $ts = $line.Split(' ')
    $name = $ref.Substring('origin/'.Length)
    if ($ExcludeBranches -contains $name) { continue }
    $iss = $null
    if ($name -match '^ticket/fu(\d+)') { $iss = [int]$matches[1] }
    elseif ($name -match '^ticket/(\d{1,2})(?!\d)') { $iss = TicketToIssue $matches[1] }
    if (-not $iss -or -not (Eligible $iss)) { continue }   # closed / parked / excluded issue: leftover, not idle work
    Need "rev-list $name"
    $ahead = [int](Must (Invoke-Exe $GitExe @('-C', $RepoRoot, 'rev-list', '--count', "origin/$IntegrationBranch..$ref") 20) "git rev-list $name").Trim()
    if ($ahead -lt 1) { continue }
    $branchByIssue[$iss] = $true
    $age = [Math]::Round(($NowUtc - [DateTimeOffset]::FromUnixTimeSeconds([int64]$ts).UtcDateTime).TotalMinutes, 0)
    if ($refIssues.ContainsKey($iss) -or $age -lt $BranchQuietMinutes) { continue }
    [void]$idle.Add([pscustomobject]@{ kind = 'branch'; issue = $iss; text = ('{0} (issue #{1}): {2} commit(s) ahead of {3}, last commit {4} min ago, no live session on it -> dispatch review, or merge if its required reviews already passed' -f $name, $iss, $ahead, $IntegrationBranch, $age) })
  }

  # ---------- ready issues with no open blockers ----------
  foreach ($n in @($openIssues.Keys | Sort-Object)) {
    if (-not (Eligible $n) -or $refIssues.ContainsKey($n) -or $branchByIssue.ContainsKey($n)) { continue }
    Need "blockers #$n"
    $bOut = Must (Invoke-Exe $GhExe @('api', "repos/$Repo/issues/$n/dependencies/blocked_by") 20) "gh blocked_by #$n"
    $openB = @(JsonList $bOut | Where-Object { $_.state -eq 'open' } | ForEach-Object { [int]$_.number })
    if ($openB.Count -gt 0) { continue }
    [void]$idle.Add([pscustomobject]@{ kind = 'issue'; issue = $n; text = ('#{0} {1}: ready-for-agent, no open blockers, no live session, no branch ahead of integration -> dispatch implementer' -f $n, $openIssues[$n].title) })
  }

  # ---------- decide ----------
  $state = Read-Json $StatePath
  $sinceNudge = $null
  if ($state -and (Has $state 'last_nudge_utc') -and $state.last_nudge_utc) { $sinceNudge = [Math]::Round(($NowUtc - [DateTime]::Parse($state.last_nudge_utc).ToUniversalTime()).TotalMinutes, 1) }
  $action = 'none'; $reason = ''
  if ($hb.phase -eq 'done') { $action = 'none'; $reason = 'phase done' }
  elseif (-not $orchActive -and ($null -eq $orchIdleMin -or $orchIdleMin -gt $DeadIdleMinutes)) { $action = 'none'; $reason = "orchestrator inactive and idle $orchIdleMin min (watchdog's job)" }
  elseif ($idle.Count -eq 0) { $reason = 'no idle work' }
  elseif ($cpu -ge $MaxCpu) { $reason = "cpu $cpu% >= $MaxCpu%" }
  elseif ($workers -ge $MaxWorkers) { $reason = "implement+fix sessions $workers >= $MaxWorkers" }
  elseif ($null -ne $sinceNudge -and $sinceNudge -lt $CooldownMinutes) { $action = 'cooldown'; $reason = "last nudge $sinceNudge min ago" }
  else { $action = 'nudge'; $reason = "$($idle.Count) idle item(s) with headroom" }

  $idleList = ($idle | ForEach-Object { '{0}:{1}' -f $_.kind, $_.issue }) -join ','
  Write-Log ('action={0} reason="{1}" cpu={2}% sessions=impl:{3},fix:{4},review:{5},merge:{6},other:{7} workers={8} idle={9} [{10}] orch_active={11} orch_idle={12}m elapsed={13:N0}s' -f `
      $action, $reason, $cpu, $byKind['implement'], $byKind['fix'], $byKind['review'], $byKind['merge'], $byKind['other'], $workers, $idle.Count, $idleList, $orchActive, $orchIdleMin, $Clock.Elapsed.TotalSeconds)

  if ($idle.Count -gt 0 -and ($action -eq 'nudge' -or $DryRun)) {
    $msg = New-Object System.Text.StringBuilder
    [void]$msg.AppendLine("[utilization monitor $($NowUtc.ToString('o'))] Capacity is idle: CPU $cpu% (limit $MaxCpu%), live implement+fix sessions $workers of $MaxWorkers (review $($byKind['review']), merge $($byKind['merge'])).")
    [void]$msg.AppendLine("These $($idle.Count) item(s) have no live session working on them:")
    foreach ($it in $idle) { [void]$msg.AppendLine("- $($it.text)") }
    [void]$msg.AppendLine('')
    [void]$msg.AppendLine('Dispatch ALL of them now, in ONE turn (parallel background subagents), respecting labels, Merge after, review rules and the 16-worker cap. If an item is not actually dispatchable (blocked in a way not recorded as a GitHub dependency, or already handled), say why in the decision log and record the blocker on the issue so this monitor stops flagging it. Then write a heartbeat.')
    $text = $msg.ToString()
    if ($DryRun) { Write-Output '----- message (dry run, not sent) -----'; Write-Output $text }
    else {
      $tmp = Join-Path $env:TEMP ('utilization-nudge-{0}.md' -f [guid]::NewGuid().ToString('N'))
      [IO.File]::WriteAllText($tmp, $text, (New-Object System.Text.UTF8Encoding($false)))
      try {
        $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'send-to-orchestrator.ps1') -MessageFile $tmp 2>&1 | Out-String
        $rc = $LASTEXITCODE
      } finally { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
      if ($rc -ne 0) { throw ('send-to-orchestrator failed rc={0}: {1}' -f $rc, (($out -replace '\s+', ' ').Trim())) }
      Write-JsonAtomic $StatePath ([ordered]@{ last_nudge_utc = $NowUtc.ToString('o'); items = $idleList; session_id = $hb.session_id })
      Write-Log ('nudged session={0} items={1}' -f $hb.session_id, $idle.Count)
    }
  }
  exit 0
}
catch {
  try { Write-Log ('ERROR utilization check failed: {0} at {1}' -f $_.Exception.Message, ($_.InvocationInfo.PositionMessage -replace '\s+', ' ')) } catch {}
  exit 3
}
finally {
  if ($owned) { try { $mutex.ReleaseMutex() } catch {} }
  $mutex.Dispose()
}
