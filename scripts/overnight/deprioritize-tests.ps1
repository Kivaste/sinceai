<#
.SYNOPSIS
  Keep agent test runs from starving the desktop: every few seconds, set python.exe processes started from the
  project venv (pytest and its xdist workers) to BelowNormal priority. Nothing is killed; tests just yield to the user.
  Single instance via PID file; started via WMI so an OpenCode server restart can't kill it; the watchdog restarts it.
#>
param([int]$IntervalSec = 10, [int]$Hours = 16, [string]$Priority = 'BelowNormal')
$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dir = Join-Path $RepoRoot '.scratch\local-overnight'
$pidFile = Join-Path $dir 'deprioritize.pid'
if (Test-Path $pidFile) {
  $old = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { "already running (pid $old)"; exit 0 }
}
Set-Content $pidFile $PID
$venvPy = (Join-Path $RepoRoot '.venv').ToLowerInvariant()
$log = Join-Path $dir 'watchdog.log'
Add-Content $log ('{0} [{1}] deprioritize started: all python -> {2}, every {3}s' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $PID, $Priority, $IntervalSec)
$until = (Get-Date).AddHours($Hours)
try {
  while ((Get-Date) -lt $until) {
    foreach ($p in @(Get-Process python, pythonw -ErrorAction SilentlyContinue)) {
      try {
        if ($p.PriorityClass -ne $Priority) { $p.PriorityClass = $Priority }   # all python: the venv python.exe is only a launcher; the real interpreter runs from the base install
      } catch {}
    }
    Start-Sleep -Seconds $IntervalSec
  }
}
finally { Remove-Item $pidFile -ErrorAction SilentlyContinue }
