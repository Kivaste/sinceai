<#
.SYNOPSIS
  Keep agent test runs from starving the desktop, while the merge gate keeps priority.
  Every few seconds:
    - python processes that belong to the MERGER (their parent chain contains the integration worktree path,
      sinceai-wt\integration) are set to $MergerPriority (Normal): the merge gate is the one serial step.
    - all other python processes (agent test runs, xdist workers, CLI subprocesses) are set to $Priority (BelowNormal).
  The venv python.exe is only a launcher (the real interpreter runs from the base install), so all python is matched.
  Nothing is killed. Single instance via PID file; started via WMI so an OpenCode server restart can't kill it;
  the watchdog restarts it if it is gone.
#>
param([int]$IntervalSec = 10, [int]$Hours = 16, [string]$Priority = 'BelowNormal', [string]$MergerPriority = 'Normal',
      [string]$MergerMarker = 'sinceai-wt\integration')
$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dir = Join-Path $RepoRoot '.scratch\local-overnight'
$pidFile = Join-Path $dir 'deprioritize.pid'
if (Test-Path $pidFile) {
  $old = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { "already running (pid $old)"; exit 0 }
}
Set-Content $pidFile $PID
$log = Join-Path $dir 'watchdog.log'
$marker = $MergerMarker.ToLowerInvariant()
Add-Content $log ('{0} [{1}] deprioritize started: merger python -> {2}, other python -> {3}, every {4}s' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $PID, $MergerPriority, $Priority, $IntervalSec)
$until = (Get-Date).AddHours($Hours)
try {
  while ((Get-Date) -lt $until) {
    $all = @{}
    foreach ($w in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) { $all[[int]$w.ProcessId] = $w }
    foreach ($w in $all.Values) {
      if ($w.Name -ne 'python.exe' -and $w.Name -ne 'pythonw.exe') { continue }
      # Walk up to 6 ancestors: the merger's shell command line contains the integration worktree path.
      $isMerger = $false; $cur = $w; $hops = 0
      while ($cur -and $hops -lt 6) {
        if ($cur.CommandLine -and $cur.CommandLine.ToLowerInvariant().Contains($marker)) { $isMerger = $true; break }
        $cur = $all[[int]$cur.ParentProcessId]; $hops++
      }
      $want = if ($isMerger) { $MergerPriority } else { $Priority }
      try { $p = Get-Process -Id $w.ProcessId -ErrorAction Stop; if ([string]$p.PriorityClass -ne $want) { $p.PriorityClass = $want } } catch {}
    }
    Start-Sleep -Seconds $IntervalSec
  }
}
finally { Remove-Item $pidFile -ErrorAction SilentlyContinue }
