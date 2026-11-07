<#
.SYNOPSIS
  Hold a Windows power request (system + display required) for as long as this process lives.
  On Modern Standby (S0 low-power idle) laptops, "Sleep after: Never" is NOT enough: when the display
  turns off (idle timeout, power button, screen-off key) the machine enters Modern Standby with the
  network disconnected and desktop apps throttled, so every agent stalls. ES_DISPLAY_REQUIRED stops the
  idle display-off path; the power/sleep button actions are set to "Do nothing" separately.
  Single instance via a PID file; the watchdog restarts it if it is gone.
#>
param([int]$Hours = 16)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dir = Join-Path $RepoRoot '.scratch\local-overnight'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$pidFile = Join-Path $dir 'keep-awake.pid'
if (Test-Path $pidFile) {
  $old = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { "keep-awake already running (pid $old)"; exit 0 }
}
Set-Content -Path $pidFile -Value $PID
Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$ES_CONTINUOUS = [uint32]'0x80000000'; $ES_SYSTEM_REQUIRED = [uint32]1; $ES_DISPLAY_REQUIRED = [uint32]2
$flags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED
$until = (Get-Date).AddHours($Hours)
$log = Join-Path $dir 'watchdog.log'
Add-Content -Path $log -Value ('{0} [{1}] keep-awake started (system+display required) until {2:HH:mm}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $PID, $until)
try {
  while ((Get-Date) -lt $until) {
    [void][Win32.Power]::SetThreadExecutionState($flags)   # re-assert every minute
    Start-Sleep -Seconds 60
  }
}
finally {
  [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
  Remove-Item $pidFile -ErrorAction SilentlyContinue
}
