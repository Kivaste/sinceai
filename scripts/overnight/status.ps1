<#
.SYNOPSIS
  One-screen status of the overnight run: live agent sessions (what each is doing, how recently it acted),
  worktree activity, tickets, machine load, watchdog. Read-only.
.EXAMPLE
  powershell -NoProfile -File scripts/overnight/status.ps1
#>
$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$wtRoot = Join-Path (Split-Path $RepoRoot -Parent) 'sinceai-wt'
"=== {0}" -f (Get-Date -Format 'ddd HH:mm:ss')

$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$active = (opencode api get /api/session/active 2>$null | Out-String | ConvertFrom-Json).data
$ids = @($active.PSObject.Properties.Name)
$rows = foreach ($id in $ids) {
  $d = ((opencode api get "/api/session/$id" 2>$null | Out-String) | ConvertFrom-Json).data
  if (-not $d) { continue }
  $kind = if ($d.title -like 'Implement*') { 'implement' } elseif ($d.title -like 'Review*') { 'review' } elseif ($d.title -like '*orchestrator*') { 'orchestrator' } else { 'other' }
  [pscustomobject]@{ kind = $kind; title = $d.title.Substring(0, [Math]::Min(46, $d.title.Length)); model = "$($d.model.providerID)/$($d.model.id)"; 'idle(min)' = [math]::Round(($now - $d.time.updated) / 60000, 1) }
}
$hb = Get-Content -Raw (Join-Path $RepoRoot '.scratch\local-overnight\heartbeat.json') -ErrorAction SilentlyContinue | ConvertFrom-Json
"--- sessions: {0} running  (implementers {1}, reviewers {2}); orchestrator heartbeat {3:N1} min ago, phase '{4}'" -f $ids.Count, @($rows | Where-Object kind -eq 'implement').Count, @($rows | Where-Object kind -eq 'review').Count, ((Get-Date).ToUniversalTime() - [DateTime]::Parse($hb.timestamp).ToUniversalTime()).TotalMinutes, $hb.phase
$rows | Sort-Object kind, 'idle(min)' | Format-Table -AutoSize | Out-String -Width 160

"--- worktrees: files written in the last 5 min / commits ahead of integration"
if (Test-Path $wtRoot) {
  Get-ChildItem $wtRoot -Directory | ForEach-Object {
    $n = @(Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\\.git\\' -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-5) }).Count
    $ahead = git -C $_.FullName rev-list --count origin/integration/pets-release..HEAD 2>$null
    "  {0,-22} files={1,-4} ahead={2}" -f $_.Name, $n, $ahead
  }
}

"--- tickets"
$closed = gh issue list -R Kivaste/sinceai --state closed --limit 200 --json number,title -q '.[] | .title' 2>$null
"  closed ({0}): {1}" -f @($closed).Count, ((@($closed) | ForEach-Object { $_.Substring(0, 2) }) -join ', ')
"  open: {0}" -f (gh issue list -R Kivaste/sinceai --state open --limit 200 --json number -q 'length' 2>$null)
"  integration: {0}" -f (git -C $RepoRoot log -1 --format='%h %cr %s' origin/integration/pets-release 2>$null)

"--- machine"
$cpu = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3).CounterSamples.CookedValue
$os = Get-CimInstance Win32_OperatingSystem
"  CPU {0}% (3 samples)   RAM {1:N0}/{2:N0} GB   python procs {3}   on AC: {4}" -f (($cpu | ForEach-Object { [math]::Round($_) }) -join '/'), (($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB), ($os.TotalVisibleMemorySize / 1MB), @(Get-Process python -ErrorAction SilentlyContinue).Count, (Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus -ErrorAction SilentlyContinue | Select-Object -First 1).PowerOnline
$ka = Get-Content (Join-Path $RepoRoot '.scratch\local-overnight\keep-awake.pid') -ErrorAction SilentlyContinue
"  keep-awake: {0}" -f $(if ($ka -and (Get-Process -Id $ka -ErrorAction SilentlyContinue)) { "running (pid $ka)" } else { 'NOT running' })
"--- watchdog (last 2)"
Get-Content (Join-Path $RepoRoot '.scratch\local-overnight\watchdog.log') -Tail 2
