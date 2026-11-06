<#
.SYNOPSIS
  Pester-free self-test: runs watchdog.ps1 -DryRun against throwaway scenarios in %TEMP% and checks
  each decision. Never touches the real heartbeat, the real OpenCode sessions or the scheduled task.
  Exit 0 only if every case ran and matched.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-watchdog.ps1
#>
$ErrorActionPreference = 'Stop'
$wd = Join-Path $PSScriptRoot 'watchdog.ps1'
$hbScript = Join-Path $PSScriptRoot 'heartbeat.ps1'
$root = Join-Path $env:TEMP ("overnight-test-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$repo = Join-Path $root 'repo'
New-Item -ItemType Directory -Force -Path $repo | Out-Null

# Throwaway git repo with a ticket branch whose only commit is 40 minutes old (synthetic, content-free).
$old = (Get-Date).AddMinutes(-40).ToString('yyyy-MM-ddTHH:mm:ssK')
& git -C $repo init -q -b main 2>$null
$env:GIT_AUTHOR_DATE = $old; $env:GIT_COMMITTER_DATE = $old
& git -C $repo -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m init
& git -C $repo branch ticket/1-demo
Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE

$results = @(); $fail = 0
function New-Case([string]$name) { $d = Join-Path $root $name; New-Item -ItemType Directory -Force -Path $d | Out-Null; return $d }
function Set-Hb($dir, [double]$minAgo, [string]$session = 'ses_testorchestrator') {
  $o = [ordered]@{ timestamp = (Get-Date).ToUniversalTime().AddMinutes(-$minAgo).ToString('o'); phase = 'test'; running = @(); tickets = @(); session_id = $session }
  $o | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $dir 'heartbeat.json')
}
function Set-Fx($dir, $fx) { $p = Join-Path $dir 'fixture.json'; $fx | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii $p; return $p }
function Run-Case([string]$name, [string]$dir, [string]$fixture, [string]$expect, [int]$expectExit = 0) {
  $args2 = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $wd, '-RepoRoot', $repo, '-StateDir', $dir, '-DryRun', '-NoFetch')
  if ($fixture) { $args2 += @('-Fixture', $fixture) }
  $out = & powershell.exe @args2 2>&1 | Out-String
  $code = $LASTEXITCODE
  $m = [regex]::Match($out, 'action=([a-z\-]+)')
  $got = if ($m.Success) { $m.Groups[1].Value } else { '<none>' }
  $ok = ($got -eq $expect) -and ($code -eq $expectExit)
  if (-not $ok) { $script:fail++ }
  $line = ($out -split "`r?`n" | Where-Object { $_ -match 'action=' } | Select-Object -Last 1)
  $script:results += [pscustomobject]@{ case = $name; expect = $expect; got = $got; exit = $code; pass = $ok }
  Write-Output ('[{0}] {1}: expect={2} got={3} exit={4}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $name, $expect, $got, $code)
  Write-Output ('       ' + ($line -replace '^.*?\] (\[DRYRUN\] )?', ''))
  if (-not $ok) { Write-Output $out }
}
$open3 = @{ open = 3; closed = 2; parked = 0 }
$ocIdle = { param($age) @{ reachable = $true; exists = $true; active = $false; child_active = $false; updated_age = $age; outcome = 'succeeded' } }

# 1. Stale heartbeat + stale commits (real git: ticket branch 40m old) + idle session -> nudge same session
$d = New-Case 'stale'; Set-Hb $d 40
Run-Case 'stale heartbeat, commits 40m (real git), session idle' $d (Set-Fx $d @{ tickets = $open3; opencode = (& $ocIdle 40) }) 'nudge'

# 2. Fresh heartbeat -> alive, no action
$d = New-Case 'fresh'; Set-Hb $d 2
Run-Case 'fresh heartbeat (2m), session running' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = @{ reachable = $true; exists = $true; active = $true; child_active = $true; updated_age = 1 } }) 'alive'

# 3. Orchestrator idle, nothing running, heartbeat 12m -> fast-path nudge before the 25m stall threshold
$d = New-Case 'idle'; Set-Hb $d 12
Run-Case 'turn ended, no subagent running, hb 12m' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 12; opencode = (& $ocIdle 12) }) 'nudge'

# 4. Orchestrator waiting on running subagents, hb 30m but child session updated 3m ago -> alive
$d = New-Case 'busychild'; Set-Hb $d 30
Run-Case 'hb 30m, child subagent active (updated 3m)' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 30; opencode = @{ reachable = $true; exists = $true; active = $false; child_active = $true; updated_age = 3 } }) 'alive'

# 5. Held lock: fallback orchestrator process alive (this test PID + its real start time), API down -> do not start a second one
$d = New-Case 'heldlock'; Set-Hb $d 40
$me = Get-Process -Id $PID
@{ kind = 'process'; pid = $PID; start_utc = $me.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'orchestrator.lock')
Run-Case 'stale hb, API down, orchestrator.lock held by live PID' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = @{ reachable = $false } }) 'alive-lock'

# 6. Stale lock (dead PID), API down -> start fallback process
$d = New-Case 'stalelock'; Set-Hb $d 40
@{ kind = 'process'; pid = 999999; start_utc = (Get-Date).ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'orchestrator.lock')
Run-Case 'stale hb, API down, lock PID dead' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = @{ reachable = $false } }) 'start-process'

# 7. Escalation step 3 (three nudges did not help) -> new session via API
$d = New-Case 'escalate'; Set-Hb $d 90
@{ step = 3; last_action_utc = (Get-Date).ToUniversalTime().AddMinutes(-30).ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'watchdog-state.json')
Run-Case 'stale after 3 nudges' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 90; opencode = (& $ocIdle 90) }) 'new-session'

# 8. Cooldown: intervened 5m ago -> wait
$d = New-Case 'cooldown'; Set-Hb $d 40
@{ step = 1; last_action_utc = (Get-Date).ToUniversalTime().AddMinutes(-5).ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'watchdog-state.json')
Run-Case 'stale but nudged 5m ago' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = (& $ocIdle 40) }) 'cooldown'

# 9. All tickets closed -> done, exit 0
$d = New-Case 'done'; Set-Hb $d 300
Run-Case 'all tickets closed' $d (Set-Fx $d @{ tickets = @{ open = 0; closed = 7; parked = 0 }; commit_min_ago = 300; opencode = (& $ocIdle 300) }) 'done'

# 10. gh unavailable -> unknown, no action, exit 2
$d = New-Case 'ghfail'; Set-Hb $d 40
Run-Case 'ticket counts unknown' $d (Set-Fx $d @{ tickets = 'error'; commit_min_ago = 40; opencode = (& $ocIdle 40) }) 'unknown' 2

# 11. Concurrent watchdog: mutex already held -> skip
$d = New-Case 'mutex'; Set-Hb $d 40
$sha = [System.Security.Cryptography.SHA1]::Create()
$key = ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($d.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join ''
$mx = New-Object System.Threading.Mutex($true, "Local\sinceai-overnight-watchdog-$($key.Substring(0,12))")
Run-Case 'second watchdog while one runs' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = (& $ocIdle 40) }) 'skip'
$mx.ReleaseMutex(); $mx.Dispose()

# 12. heartbeat.ps1 round trip: write a real heartbeat into a temp state dir, watchdog sees it as fresh
$d = New-Case 'hbscript'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hbScript -Phase dispatch -Running '12,14' -Spec 9 -Tickets '10 11 12 13 14' -SessionId ses_testorchestrator -StateDir $d | Out-Null
$hb = Get-Content -Raw (Join-Path $d 'heartbeat.json') | ConvertFrom-Json
$hbOk = ($hb.running -join ',') -eq '12,14' -and ($hb.tickets.Count -eq 5) -and $hb.session_id -eq 'ses_testorchestrator'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hbScript -Phase merged -SessionId ses_other -StateDir $d 2>$null | Out-Null
$hb2 = Get-Content -Raw (Join-Path $d 'heartbeat.json') | ConvertFrom-Json
$hbOk = $hbOk -and $hb2.session_id -eq 'ses_testorchestrator' -and ($hb2.running -join ',') -eq '12,14' -and $hb2.phase -eq 'merged'
if (-not $hbOk) { $fail++ }
Write-Output ('[{0}] heartbeat.ps1 merge/keep-session semantics' -f $(if ($hbOk) { 'PASS' } else { 'FAIL' }))
Run-Case 'heartbeat.ps1 output is read as fresh' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 40; opencode = @{ reachable = $true; exists = $true; active = $true; child_active = $false; updated_age = 40 } }) 'alive'

# 13-14. 3-minute cadence: still stalled 18m after a nudge -> cooldown (no spam); 21m after -> next nudge
$d = New-Case 'cadence18'; Set-Hb $d 45
@{ step = 1; last_action_utc = (Get-Date).ToUniversalTime().AddMinutes(-18).ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'watchdog-state.json')
Run-Case '3-min cadence: stalled, nudged 18m ago' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 45; opencode = (& $ocIdle 45) }) 'cooldown'
$d = New-Case 'cadence21'; Set-Hb $d 45
@{ step = 1; last_action_utc = (Get-Date).ToUniversalTime().AddMinutes(-21).ToString('o') } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $d 'watchdog-state.json')
Run-Case '3-min cadence: stalled, nudged 21m ago' $d (Set-Fx $d @{ tickets = $open3; commit_min_ago = 45; opencode = (& $ocIdle 45) }) 'nudge'

# 15. Parameter defaults (parsed, not executed): install every 3 min; watchdog keeps 25/90/20; launcher model.
function Get-Default([string]$file, [string]$name) {
  $ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$null, [ref]$null)
  $p = $ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq $name }
  if ($p -and $p.DefaultValue) { return $p.DefaultValue.SafeGetValue() } return $null
}
$inst = Join-Path $PSScriptRoot 'install-watchdog.ps1'; $start = Join-Path $PSScriptRoot 'start-orchestrator.ps1'
$defOk = (Get-Default $inst 'EveryMinutes') -eq 3 -and (Get-Default $wd 'StaleMinutes') -eq 25 -and (Get-Default $wd 'HungMinutes') -eq 90 -and `
  (Get-Default $wd 'CooldownMinutes') -ge 20 -and (Get-Default $start 'Model') -eq 'claude-agent/opus'
if (-not $defOk) { $fail++ }
Write-Output ('[{0}] defaults: install 3 min, stale 25, hung 90, cooldown >= 20, launcher claude-agent/opus' -f $(if ($defOk) { 'PASS' } else { 'FAIL' }))

Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
Write-Output ''
Write-Output ('{0} cases, {1} failed' -f ($results.Count + 2), $fail)
if ($fail -gt 0) { exit 1 } else { exit 0 }
