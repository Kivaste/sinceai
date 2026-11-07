<#
.SYNOPSIS
  Start a fresh overnight orchestrator session through the OpenCode HTTP API and hand it
  resume-prompt.md as its first prompt (queue delivery). Records the session id where the
  watchdog looks (heartbeat.json + watchdog-state.json) and prints how to attach in the TUI.

.DESCRIPTION
  Refuses to start a second orchestrator: if the tracked session is running, or was updated
  less than -StaleMinutes ago, or a live orchestrator.lock process exists, it exits 1 unless
  -Force is given (then the old session is interrupted first).
  -DryRun performs only read-only probes and prints what it would send.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/start-orchestrator.ps1 -DryRun
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/start-orchestrator.ps1
#>
[CmdletBinding()]
param(
  [string]$RepoRoot,
  [string]$StateDir,
  [string]$Model = 'claude-agent/opus',
  [string]$Agent = 'build',
  [string]$Title,
  [int]$StaleMinutes = 25,
  # First prompt for the new session. Default: resume-prompt.md (test-handover.ps1 passes a harmless one).
  [string]$PromptFile,
  [switch]$Force,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (-not $StateDir) { $StateDir = Join-Path $RepoRoot '.scratch\local-overnight' }
$HbPath = Join-Path $StateDir 'heartbeat.json'
$StatePath = Join-Path $StateDir 'watchdog-state.json'
$LockPath = Join-Path $StateDir 'orchestrator.lock'
$PromptPath = Join-Path $PSScriptRoot 'resume-prompt.md'
if ($PromptFile) { $PromptPath = $PromptFile }
$HbScript = Join-Path $PSScriptRoot 'heartbeat.ps1'
$NowUtc = (Get-Date).ToUniversalTime()
$tag = $(if ($DryRun) { '[DRYRUN] ' } else { '' })
if (-not $Title) { $Title = "overnight orchestrator (start $($NowUtc.ToString('yyyy-MM-dd HH:mm'))Z)" }

function Has($o, $n) { return ($null -ne $o) -and ($o.PSObject.Properties.Name -contains $n) }
function Read-Json($p) { if (Test-Path $p) { try { return (Get-Content -Raw $p | ConvertFrom-Json) } catch { return $null } } return $null }
function Write-JsonAtomic($p, $obj) {
  $tmp = '{0}.{1}.{2}.tmp' -f $p, $PID, [guid]::NewGuid().ToString('N')
  [IO.File]::WriteAllText($tmp, ($obj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -Force -LiteralPath $tmp -Destination $p
}
function Quote-Arg([string]$a) {
  # MSVCRT quoting; Windows PowerShell 5.1 mangles embedded quotes for native exes.
  if ($a -ne '' -and $a -notmatch '[\s"]') { return $a }
  $sb = New-Object System.Text.StringBuilder; [void]$sb.Append('"'); $bs = 0
  foreach ($ch in $a.ToCharArray()) {
    if ($ch -eq '\') { $bs++; continue }
    if ($ch -eq '"') { [void]$sb.Append('\' * ($bs * 2 + 1)); [void]$sb.Append('"'); $bs = 0; continue }
    if ($bs) { [void]$sb.Append('\' * $bs); $bs = 0 }
    [void]$sb.Append($ch)
  }
  if ($bs) { [void]$sb.Append('\' * ($bs * 2)) }
  [void]$sb.Append('"'); return $sb.ToString()
}
$OcExe = (Get-Command opencode -ErrorAction SilentlyContinue).Source
if (-not $OcExe) { Write-Error 'opencode not found on PATH'; exit 1 }
function OcApi([string[]]$argv) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $OcExe
  $psi.Arguments = ((@('api') + $argv) | ForEach-Object { Quote-Arg $_ }) -join ' '
  $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
  $psi.WorkingDirectory = $RepoRoot
  $p = [System.Diagnostics.Process]::Start($psi)
  $o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
  if (-not $p.WaitForExit(60000)) { try { $p.Kill() } catch {}; return $null }
  $p.WaitForExit()
  if ($p.ExitCode -ne 0) { Write-Warning ("opencode api {0} {1} failed (code {2}): {3}" -f $argv[0], $argv[1], $p.ExitCode, $e.Result.Trim()); return $null }
  try { return ($o.Result | ConvertFrom-Json) } catch { return $null }
}
function Parse-Model([string]$m) {
  $variant = $null; if ($m -match '#') { $variant = $m.Split('#')[1]; $m = $m.Split('#')[0] }
  $ref = [ordered]@{ providerID = $m.Split('/')[0]; id = ($m.Split('/', 2)[1]) }
  if ($variant) { $ref.variant = $variant }
  return $ref
}

if (-not (Test-Path $PromptPath)) { Write-Error "missing $PromptPath"; exit 1 }

# ---------- never two orchestrators ----------
$act = OcApi @('get', '/api/session/active')
if (-not $act) { Write-Error 'OpenCode API unreachable (opencode api get /api/session/active failed)'; exit 1 }
$activeIds = @(); if (Has $act 'data') { $activeIds = @($act.data.PSObject.Properties.Name) }
$hb = Read-Json $HbPath; $st = Read-Json $StatePath
$oldId = $null
if ($st -and (Has $st 'session_id') -and $st.session_id) { $oldId = $st.session_id }
if ($hb -and (Has $hb 'session_id') -and $hb.session_id) {
  $useHb = $true
  if ($oldId -and (Has $st 'session_set_utc') -and $st.session_set_utc -and (Has $hb 'timestamp')) {
    $useHb = [DateTime]::Parse($hb.timestamp).ToUniversalTime() -ge [DateTime]::Parse($st.session_set_utc).ToUniversalTime()
  }
  if ($useHb) { $oldId = $hb.session_id }
}
$blockers = @()
if ($oldId) {
  $s = OcApi @('get', "/api/session/$oldId")
  if ($s -and (Has $s 'data')) {
    $age = [Math]::Round(($NowUtc - [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$s.data.time.updated).UtcDateTime).TotalMinutes, 1)
    if ($activeIds -contains $oldId) { $blockers += "tracked orchestrator $oldId is running" }
    elseif ($age -lt $StaleMinutes) { $blockers += "tracked orchestrator $oldId was updated ${age}m ago (< ${StaleMinutes}m)" }
    Write-Output "${tag}tracked orchestrator: $oldId (running=$($activeIds -contains $oldId), updated ${age}m ago)"
  } else { Write-Output "${tag}tracked orchestrator: $oldId (not found in OpenCode; ignoring)" }
} else { Write-Output "${tag}tracked orchestrator: none" }
$lock = Read-Json $LockPath
if ($lock -and (Has $lock 'pid') -and $lock.pid) {
  $p = Get-Process -Id ([int]$lock.pid) -ErrorAction SilentlyContinue
  if ($p) {
    $same = $false; try { $same = [Math]::Abs(($p.StartTime.ToUniversalTime() - [DateTime]::Parse($lock.start_utc).ToUniversalTime()).TotalSeconds) -lt 3 } catch {}
    if ($same) { $blockers += "fallback orchestrator process pid=$($lock.pid) is alive (orchestrator.lock)" }
  }
}
if ($blockers.Count -gt 0 -and -not $Force) {
  Write-Output "${tag}REFUSING to start a second orchestrator: $($blockers -join '; ')."
  Write-Output "Attach to it instead (opencode --session $oldId), or re-run with -Force to interrupt and replace it."
  exit 1
}

# ---------- build requests ----------
$body = [ordered]@{ title = $Title; agent = $Agent; model = (Parse-Model $Model); location = [ordered]@{ directory = $RepoRoot } } | ConvertTo-Json -Compress -Depth 4
$header = "[start-orchestrator $($NowUtc.ToString('o'))] Fresh orchestrator start. Previous tracked orchestrator: $(if ($oldId) { $oldId } else { 'none' }) (do not use it). Your first action: run scripts/overnight/heartbeat.ps1 -Phase resume -ClaimSession.`n`n"
# A custom -PromptFile is sent verbatim: the header tells the session to write the LIVE heartbeat, which a test must not do.
# ReadAllText, not Get-Content: a bare Get-Content string carries PSPath note properties that ConvertTo-Json serialises.
if ($PromptFile) { $text = [IO.File]::ReadAllText($PromptPath, [Text.Encoding]::UTF8) } else { $text = $header + (Get-Content -Raw $PromptPath) }
$promptBody = @{ text = $text; delivery = 'queue' } | ConvertTo-Json -Compress

if ($DryRun) {
  Write-Output "${tag}API reachable: yes ($($activeIds.Count) running session(s))"
  Write-Output "${tag}would interrupt old session: $(if ($Force -and $blockers.Count -gt 0 -and $oldId) { $oldId } else { 'no' })"
  Write-Output "${tag}would POST /api/session $body"
  Write-Output ("${tag}would POST /api/session/<new-id>/prompt delivery=queue text={0} chars ({1} lines of resume-prompt.md)" -f $text.Length, @(Get-Content $PromptPath).Count)
  Write-Output "${tag}would write heartbeat.json (-Phase launch -ClaimSession -SessionId <new-id>) and watchdog-state.json (session_id, step=0) in $StateDir"
  Write-Output "${tag}attach afterwards with: cd `"$RepoRoot`"; opencode --session <new-id>"
  exit 0
}

if ($Force -and $blockers.Count -gt 0 -and $oldId) {
  Write-Output "interrupting old orchestrator $oldId"
  [void](OcApi @('post', "/api/session/$oldId/interrupt", '--data', '{}'))
}
$created = OcApi @('post', '/api/session', '--data', $body)
if (-not ($created -and (Has $created 'data') -and $created.data.id)) { Write-Error 'session create failed'; exit 1 }
$newId = $created.data.id
Write-Output "created session $newId (model $Model, dir $RepoRoot)"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $HbScript -Phase launch -SessionId $newId -ClaimSession -IntegrationBranch 'integration/pets-release' -StateDir $StateDir -Note 'start-orchestrator.ps1' | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error 'heartbeat write failed'; exit 1 }
Write-JsonAtomic $StatePath ([ordered]@{ step = 0; last_action_utc = $null; session_id = $newId; session_set_utc = (Get-Date).ToUniversalTime().ToString('o') })

$res = OcApi @('post', "/api/session/$newId/prompt", '--data', $promptBody)
if (-not $res) { Write-Error "prompt to $newId failed; session exists but has no brief (the watchdog will nudge it, or re-run with -Force)"; exit 1 }
Write-Output "sent resume-prompt.md to $newId (delivery=queue)"

# Retire the old orchestrator explicitly: a finishing child can wake an interrupted parent session, and there must never
# be two orchestrators. The retirement notice is queued, so it is the first thing the old session reads if anything wakes it.
if ($Force -and $oldId -and $oldId -ne $newId) {
  $retire = "RETIRED at $((Get-Date).ToString('HH:mm')) EET: you have been replaced by orchestrator session $newId (heartbeat.json now names it). " +
            "Do NOT dispatch, review, merge, close, comment, push or edit anything from now on, even if a subagent reports back to you. " +
            "Reply with the single word 'retired' and end your turn. The new orchestrator picks up your in-flight sessions via the API."
  $rb = @{ text = $retire; delivery = 'queue' } | ConvertTo-Json -Compress
  if (OcApi @('post', "/api/session/$oldId/prompt", '--data', $rb)) { Write-Output "queued retirement notice to old orchestrator $oldId" } else { Write-Output "WARN: could not queue retirement notice to $oldId" }
}
Write-Output ''
Write-Output "Session id: $newId"
Write-Output "Attach in the TUI:  cd `"$RepoRoot`"; opencode --session $newId"
Write-Output "Watch status:       opencode api get /api/session/active"
exit 0
