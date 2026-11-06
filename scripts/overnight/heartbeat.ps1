<#
.SYNOPSIS
  Write the overnight orchestrator heartbeat. Only the orchestrator calls this,
  after every event (dispatch, subagent done, merge, park, review, resume).

.EXAMPLE
  powershell -NoProfile -File scripts/overnight/heartbeat.ps1 -Phase dispatch -Running "12,14" -Spec 9 -Tickets "10,11,12,13,14" -IntegrationBranch integration/spec-9
  powershell -NoProfile -File scripts/overnight/heartbeat.ps1 -Phase resume -ClaimSession

.NOTES
  Unspecified fields keep their previous values, so later calls can be short:
    heartbeat.ps1 -Phase merged -Running "14" -Note "merged #12"
  The write is atomic (temp file + rename), so a concurrent watchdog never reads half a file.
  Content-free: ticket numbers, branch names, commit hashes and phase words only. Never data values.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Phase,
  # Ticket issue numbers with a running implementer, comma- or space-separated. "" or "none" clears it.
  [string]$Running,
  # Spec issue number.
  [int]$Spec = 0,
  # All ticket issue numbers for the spec, comma- or space-separated.
  [string]$Tickets,
  [string]$IntegrationBranch,
  # Defaults to `git rev-parse <IntegrationBranch>` when an integration branch is known.
  [string]$LastMerged,
  [string]$Note,
  # Defaults to $env:OPENCODE_SESSION_ID (set by OpenCode in agent shells).
  [string]$SessionId,
  # Overwrite the recorded orchestrator session id. Needed after a resume in a new session.
  [switch]$ClaimSession,
  [string]$StateDir
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $StateDir) { $StateDir = Join-Path $repo '.scratch\local-overnight' }
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$path = Join-Path $StateDir 'heartbeat.json'

function Split-Ids([string]$s) {
  if ($null -eq $s) { return $null }
  if ($s.Trim() -eq '' -or $s.Trim() -eq 'none') { return @() }
  return @($s -split '[,\s]+' | Where-Object { $_ } | ForEach-Object { ($_ -replace '^#', '') })
}

$prev = $null
if (Test-Path $path) { try { $prev = Get-Content -Raw $path | ConvertFrom-Json } catch { $prev = $null } }
function Prev($name) { if ($prev -and ($prev.PSObject.Properties.Name -contains $name)) { return $prev.$name } return $null }

if (-not $SessionId) { $SessionId = $env:OPENCODE_SESSION_ID }
$session = Prev 'session_id'
if ($SessionId -and ($ClaimSession -or -not $session)) { $session = $SessionId }
$warn = $null
if ($SessionId -and $session -and $SessionId -ne $session) {
  $warn = "caller session $SessionId is not the recorded orchestrator $session (pass -ClaimSession if you are the orchestrator now)"
}

$integ = if ($PSBoundParameters.ContainsKey('IntegrationBranch')) { $IntegrationBranch } else { Prev 'integration_branch' }
# NB: PowerShell variable names are case-insensitive, so locals must not reuse parameter names.
if ($PSBoundParameters.ContainsKey('Running')) { $runList = @(Split-Ids $Running) } else { $runList = @(@(Prev 'running') | Where-Object { $_ }) }
if ($PSBoundParameters.ContainsKey('Tickets')) { $ticketList = @(Split-Ids $Tickets) } else { $ticketList = @(@(Prev 'tickets') | Where-Object { $_ }) }
$specNo = if ($Spec -gt 0) { $Spec } else { Prev 'spec' }

if (-not $LastMerged -and $integ) {
  $h = & git -C $repo rev-parse --verify --quiet "$integ" 2>$null
  if ($LASTEXITCODE -eq 0 -and $h) { $LastMerged = $h.Trim() }
}
if (-not $LastMerged) { $LastMerged = Prev 'last_merged' }

$hb = [ordered]@{
  timestamp          = (Get-Date).ToUniversalTime().ToString('o')
  phase              = $Phase
  running            = $runList
  spec               = $specNo
  tickets            = $ticketList
  integration_branch = $integ
  last_merged        = $LastMerged
  session_id         = $session
  writer_session_id  = $SessionId
  writer_pid         = $PID
  note               = $Note
}
$tmp = Join-Path $StateDir ("heartbeat.{0}.{1}.tmp" -f $PID, [guid]::NewGuid().ToString('N'))
[IO.File]::WriteAllText($tmp, ($hb | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
for ($i = 0; $i -lt 10; $i++) {
  try { Move-Item -Force -LiteralPath $tmp -Destination $path; break } catch { Start-Sleep -Milliseconds 100 }
}
if (Test-Path $tmp) { Remove-Item -Force $tmp -ErrorAction SilentlyContinue; Write-Error "heartbeat write failed"; exit 1 }
if ($warn) { Write-Warning $warn }
Write-Output ("heartbeat {0} phase={1} running=[{2}] session={3}" -f $hb.timestamp, $Phase, ($runList -join ','), $session)
