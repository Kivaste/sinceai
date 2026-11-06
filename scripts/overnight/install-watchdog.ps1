<#
.SYNOPSIS
  Register the overnight watchdog as a Scheduled Task for the current user: every 10 minutes,
  only while the user is logged on (no stored password, no credential prompt), hidden window.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/install-watchdog.ps1
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'sinceai-overnight-watchdog',
  [int]$EveryMinutes = 10,
  [int]$Hours = 16
)
$ErrorActionPreference = 'Stop'
$watchdog = (Resolve-Path (Join-Path $PSScriptRoot 'watchdog.ps1')).Path
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$action = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
  -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $watchdog)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration (New-TimeSpan -Hours $Hours)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 9)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
  -Description 'sinceai: wake/resume the OpenCode /implement-spec orchestrator if it stalls' -Force | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName
Write-Output "Registered task '$TaskName' (state: $($t.State)); first run in ~1 min, then every $EveryMinutes min for $Hours h."
Write-Output "Log: $repo\.scratch\local-overnight\watchdog.log"
Write-Output ''
Write-Output 'Keep the machine awake overnight (NOT done by this script; run yourself, plugged in to AC):'
Write-Output '  powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE   # note the current AC value first'
Write-Output '  powercfg /change standby-timeout-ac 0                  # never sleep on AC'
Write-Output '  powercfg /change hibernate-timeout-ac 0                # never hibernate on AC'
Write-Output 'Restore in the morning (Windows defaults are usually 30 / 0 minutes; use the values you noted):'
Write-Output '  powercfg /change standby-timeout-ac 30'
Write-Output 'Also: keep the lid open or set "lid close on AC = Do nothing"; pause Windows Update for a day'
Write-Output '(Settings > Windows Update > Pause updates) so it cannot reboot overnight; stay logged on (locking is fine).'
