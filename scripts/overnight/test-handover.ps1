<#
.SYNOPSIS
  REAL end-to-end test of the watchdog's context hand-over, isolated from the live overnight state.
  Creates a throwaway "old orchestrator" session (cheap model, harmless prompt), points a temp StateDir's
  heartbeat at it, runs watchdog.ps1 against that temp StateDir with -MaxContextTokens 1, and checks that a
  new session was created, briefed, recorded and the old one retired. Also checks the two negatives
  (context below the limit; hand-over cooldown). Never writes to .scratch\local-overnight, never prompts
  any session it did not create. Deletes its sessions and temp dir at the end. Exit 0 only if every check passed.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/test-handover.ps1
#>
param(
  [string]$Model = 'claude-agent/haiku',
  [int]$ReplyTimeoutSec = 120
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$wd = Join-Path $PSScriptRoot 'watchdog.ps1'
$hbScript = Join-Path $PSScriptRoot 'heartbeat.ps1'
$liveDir = Join-Path $RepoRoot '.scratch\local-overnight'
$liveHb = Join-Path $liveDir 'heartbeat.json'
$liveHo = Join-Path $liveDir 'last-handover.txt'
$tmp = Join-Path $env:TEMP ('handover-test-' + (Get-Date).ToString('yyyyMMddHHmmss'))
if ($tmp.TrimEnd('\').ToLowerInvariant() -eq $liveDir.TrimEnd('\').ToLowerInvariant()) { throw 'refusing: temp StateDir is the live StateDir' }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

function Quote-Arg([string]$a) {
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
$OcExe = (Get-Command opencode).Source
function OcApi([string[]]$argv) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $OcExe
  $psi.Arguments = ((@('api') + $argv) | ForEach-Object { Quote-Arg $_ }) -join ' '
  $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
  $psi.WorkingDirectory = $env:TEMP
  $p = [System.Diagnostics.Process]::Start($psi)
  $o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
  if (-not $p.WaitForExit(60000)) { try { $p.Kill() } catch {}; return $null }
  $p.WaitForExit()
  if ($p.ExitCode -ne 0) { return $null }
  if (-not $o.Result.Trim()) { return [pscustomobject]@{ ok = $true } }
  try { return ($o.Result | ConvertFrom-Json) } catch { return $null }
}
function Parse-Model([string]$m) {
  $variant = $null; if ($m -match '#') { $variant = $m.Split('#')[1]; $m = $m.Split('#')[0] }
  $ref = [ordered]@{ providerID = $m.Split('/')[0]; id = ($m.Split('/', 2)[1]) }
  if ($variant) { $ref.variant = $variant }
  return $ref
}
# Messages, newest first, each enumerated explicitly (PS 5.1 ConvertFrom-Json array quirk).
function Get-Msgs([string]$id) { $r = OcApi @('get', "/api/session/$id/message"); if (-not $r) { return @() }; return @(foreach ($m in $r.data) { $m }) }
function Text-Of($m) { return ((@(foreach ($c in $m.content) { if ($c.type -eq 'text') { $c.text } }) -join '').Trim()) }
function Wait-Reply([string]$id, [string]$afterUserMatch, [int]$timeoutSec) {
  # Newest assistant reply that is newer than the newest user message matching $afterUserMatch.
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  do {
    $msgs = Get-Msgs $id
    $u = $msgs | Where-Object { $_.type -eq 'user' -and $_.text -match $afterUserMatch } | Select-Object -First 1
    if ($u) {
      $a = $msgs | Where-Object { $_.type -eq 'assistant' -and $_.tokens -and $_.time.completed -and [int64]$_.time.created -gt [int64]$u.time.created } | Select-Object -First 1
      if ($a) { return [pscustomobject]@{ user = $u; reply = (Text-Of $a) } }
    }
    Start-Sleep -Seconds 3
  } while ((Get-Date) -lt $deadline)
  return [pscustomobject]@{ user = $u; reply = $null }
}
function Run-Watchdog([string[]]$extra) {
  $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $wd, '-StateDir', $tmp, '-NoFetch', '-SkipHelpers', '-HandoverModel', $Model, '-HandoverPromptFile', $promptFile) + $extra
  $out = & powershell.exe @a 2>&1 | Out-String
  return [pscustomobject]@{ code = $LASTEXITCODE; out = $out }
}
$fail = 0; $checks = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
  $script:checks++; if (-not $ok) { $script:fail++ }
  Write-Output ('[{0}] {1}{2}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $name, $(if ($detail) { " ($detail)" } else { '' }))
}
function Live-Id { if (Test-Path $liveHb) { try { return (Get-Content -Raw $liveHb | ConvertFrom-Json).session_id } catch { return '<unreadable>' } } return '<none>' }
function Live-Ho { if (Test-Path $liveHo) { return (Get-Item $liveHo).LastWriteTimeUtc.Ticks.ToString() + ':' + (Get-Content -Raw $liveHo) } return '<none>' }

$created = @()
$liveBefore = Live-Id; $liveHoBefore = Live-Ho
Write-Output "live heartbeat session before: $liveBefore"
Write-Output "temp StateDir: $tmp"
$promptFile = Join-Path $tmp 'handover-test-prompt.md'
[IO.File]::WriteAllText($promptFile, 'This is a hand-over test. Reply with exactly: new-orchestrator-ok. Use no tools.', (New-Object System.Text.UTF8Encoding($false)))

try {
  # b. throwaway old orchestrator
  $body = @{ title = 'handover-test old'; agent = 'build'; model = (Parse-Model $Model); location = @{ directory = $env:TEMP } } | ConvertTo-Json -Compress -Depth 4
  $c = OcApi @('post', '/api/session', '--data', $body)
  if (-not ($c -and $c.data.id)) { throw 'could not create the old test session' }
  $oldId = $c.data.id; $created += $oldId
  Write-Output "old test session: $oldId"
  [void](OcApi @('post', "/api/session/$oldId/prompt", '--data', (@{ text = 'Reply with exactly: ready'; delivery = 'queue' } | ConvertTo-Json -Compress)))
  $r0 = Wait-Reply $oldId '^Reply with exactly: ready' $ReplyTimeoutSec
  Check 'old session has an assistant reply with token counts' ($null -ne $r0.reply) "reply='$($r0.reply)'"

  # c. heartbeat in the temp StateDir names the old session
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hbScript -StateDir $tmp -SessionId $oldId -ClaimSession -Phase test | Out-Null
  $hb0 = Get-Content -Raw (Join-Path $tmp 'heartbeat.json') | ConvertFrom-Json
  Check 'temp heartbeat names the old session' ($hb0.session_id -eq $oldId)

  # f1. negative: context below the limit -> no hand-over
  $n1 = Run-Watchdog @('-MaxContextTokens', '10000000', '-HandoverCooldownMinutes', '0')
  Check 'negative: context below limit -> no hand-over' (($n1.out -notmatch 'action=handover') -and -not (Test-Path (Join-Path $tmp 'last-handover.txt'))) ("exit=$($n1.code) " + (([regex]::Match($n1.out, 'action=[a-z\-]+')).Value))

  # d. hand-over
  $w = Run-Watchdog @('-MaxContextTokens', '1', '-HandoverCooldownMinutes', '0')
  $log = Get-Content -Raw (Join-Path $tmp 'watchdog.log')
  Check 'temp watchdog.log contains action=handover' ($log -match 'action=handover') "exit=$($w.code)"
  Check 'hand-over watchdog run exited 0' ($w.code -eq 0) "exit=$($w.code)"
  if ($w.code -ne 0) { Write-Output '--- watchdog output ---'; Write-Output $w.out; Write-Output '--- temp watchdog.log ---'; Write-Output $log }
  $m = [regex]::Match($log, 'created session (ses_[A-Za-z0-9]+)')
  $newId = $null; if ($m.Success) { $newId = $m.Groups[1].Value; $created += $newId }
  $newExists = $false; if ($newId) { $s = OcApi @('get', "/api/session/$newId"); $newExists = [bool]($s -and $s.data.id -eq $newId) }
  Check 'a new session was created' ($newId -and $newId -ne $oldId -and $newExists) "new=$newId"
  $hb1 = Get-Content -Raw (Join-Path $tmp 'heartbeat.json') | ConvertFrom-Json
  # Clean up whatever session the hand-over recorded, even if the log line is missing.
  if ($hb1.session_id -and $hb1.session_id -ne $oldId -and $created -notcontains $hb1.session_id) { $created += $hb1.session_id }
  Check 'temp heartbeat.json session_id == new session' ($newId -and $hb1.session_id -eq $newId) "hb=$($hb1.session_id)"
  $st1 = Get-Content -Raw (Join-Path $tmp 'watchdog-state.json') | ConvertFrom-Json
  Check 'temp watchdog-state.json session_id == new session' ($newId -and $st1.session_id -eq $newId)
  if ($newId) {
    $rn = Wait-Reply $newId 'This is a hand-over test' $ReplyTimeoutSec
    Check 'new session received the test prompt' ($null -ne $rn.user)
    Check 'new session replied new-orchestrator-ok' ($rn.reply -match '^new-orchestrator-ok\.?$') "reply='$($rn.reply)'"
  } else { Check 'new session received the test prompt' $false; Check 'new session replied new-orchestrator-ok' $false }
  $rr = Wait-Reply $oldId '^RETIRED at' 90
  Check 'old session received the RETIRED notice' ($null -ne $rr.user)
  Check 'old session newest reply is retired' ($rr.reply -match "^'?retired'?\.?$") "reply='$($rr.reply)'"
  Check 'cooldown file written in the temp StateDir' (Test-Path (Join-Path $tmp 'last-handover.txt'))
  Check 'live last-handover.txt untouched' ((Live-Ho) -eq $liveHoBefore)

  # f2. negative: cooldown active right after the hand-over -> no second hand-over
  $n2 = Run-Watchdog @('-MaxContextTokens', '1', '-HandoverCooldownMinutes', '30')
  $hb2 = Get-Content -Raw (Join-Path $tmp 'heartbeat.json') | ConvertFrom-Json
  Check 'negative: cooldown active -> no second hand-over' (($n2.out -notmatch 'action=handover') -and $hb2.session_id -eq $newId) ("exit=$($n2.code) " + (([regex]::Match($n2.out, 'action=[a-z\-]+')).Value))
}
catch { Check "test ran to completion" $false $_.Exception.Message }
finally {
  $liveAfter = Live-Id
  Write-Output "live heartbeat session after:  $liveAfter"
  Check 'live heartbeat session_id unchanged' ($liveAfter -eq $liveBefore)
  foreach ($id in $created) {
    [void](OcApi @('post', "/api/session/$id/interrupt", '--data', '{}'))
    $d = OcApi @('delete', "/api/session/$id")
    Write-Output "cleanup $id deleted=$([bool]$d)"
  }
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
Write-Output ''
Write-Output ('{0} checks, {1} failed' -f $checks, $fail)
if ($fail -gt 0) { exit 1 } else { exit 0 }
