<#
.SYNOPSIS
  Unregister the utilization monitor Scheduled Task. Leaves utilization.log and its state file in .scratch/local-overnight.
#>
[CmdletBinding()]
param([string]$TaskName = 'sinceai-utilization-monitor')
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Output "Unregistered task '$TaskName'."
} else {
  Write-Output "Task '$TaskName' not found; nothing to do."
}
