<#
.SYNOPSIS
  Unregister the overnight watchdog Scheduled Task. Leaves logs and state in .scratch/local-overnight.
#>
[CmdletBinding()]
param([string]$TaskName = 'sinceai-overnight-watchdog')
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Output "Unregistered task '$TaskName'."
} else {
  Write-Output "Task '$TaskName' not found; nothing to do."
}
Write-Output 'If you changed power settings for the night, restore them, e.g.:'
Write-Output '  powercfg /change standby-timeout-ac 30'
