<#
.SYNOPSIS
  Register the utilization monitor (utilization-check.ps1) as a Scheduled Task for the current user:
  every 5 minutes for 14 hours, only while the user is logged on, hidden window, 2-minute run limit.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/install-utilization.ps1
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'sinceai-utilization-monitor',
  [int]$EveryMinutes = 5,
  [int]$Hours = 14
)
$ErrorActionPreference = 'Stop'
if ($EveryMinutes -lt 3) { throw 'EveryMinutes must be >= 3' }
$script = (Resolve-Path (Join-Path $PSScriptRoot 'utilization-check.ps1')).Path
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$action = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
  -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $script)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration (New-TimeSpan -Hours $Hours)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
  -Description 'sinceai: nudge the overnight orchestrator to dispatch idle work while CPU and worker slots are free' -Force | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName
Write-Output "Registered task '$TaskName' (state: $($t.State)); first run in ~1 min, then every $EveryMinutes min for $Hours h."
Write-Output "Log: $repo\.scratch\local-overnight\utilization.log"
