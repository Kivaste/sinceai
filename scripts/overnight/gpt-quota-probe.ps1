<#
.SYNOPSIS
  Poll the ChatGPT-subscription model until its usage limit resets, then switch reviewers back to it.
  Every -IntervalMin minutes: one-word prompt to openai/gpt-6.1-sol via `opencode run` (fails in ~3 s while limited).
  On the first success: writes .scratch/local-overnight/gpt-available.json (the exact time), logs it, queues the
  switch-back message to the orchestrator (send-to-orchestrator.ps1) and exits. Single instance via PID file.
#>
param([int]$IntervalMin = 5, [int]$MaxHours = 6, [string]$Model = 'openai/gpt-6.1-sol#low', [switch]$Once,
      # Generic use (e.g. -Name go -Model opencode-go/gemini-4-argon#low -MessageFile go-switch-back-message.md):
      [string]$Name = 'gpt', [string]$MessageFile = 'gpt-switch-back-message.md')
$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dir = Join-Path $RepoRoot '.scratch\local-overnight'
$log = Join-Path $dir 'watchdog.log'
$pidFile = Join-Path $dir "$Name-probe.pid"
$flag = Join-Path $dir "$Name-available.json"
$msg = Join-Path $PSScriptRoot $MessageFile
function Log($t) { Add-Content -Path $log -Value ('{0} [{1}] {2}-probe {3}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $PID, $Name, $t) }

if (Test-Path $flag) { "already available since: " + (Get-Content -Raw $flag); exit 0 }
if (-not $Once -and (Test-Path $pidFile)) {
  $old = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { "probe already running (pid $old)"; exit 0 }
}
if (-not $Once) { Set-Content $pidFile $PID }
$probeDir = Join-Path $env:TEMP 'gptprobe'; New-Item -ItemType Directory -Force $probeDir | Out-Null
$until = (Get-Date).AddHours($MaxHours)
Log ("started: every {0} min until {1:HH:mm}, model {2}" -f $IntervalMin, $until, $Model)
try {
  while ((Get-Date) -lt $until) {
    Push-Location $probeDir
    $out = & opencode run -m $Model --title 'gpt quota probe' 'Reply with exactly the word OK and nothing else.' 2>&1 | Out-String
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -eq 0 -and $out -match '\bOK\b') {
      $at = Get-Date
      @{ available_at = $at.ToString('o'); model = $Model } | ConvertTo-Json | Set-Content -Path $flag -Encoding UTF8
      Log ("AVAILABLE at {0:HH:mm:ss}; queueing switch-back message to the orchestrator" -f $at)
      $r = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'send-to-orchestrator.ps1') -MessageFile $msg 2>&1 | Out-String
      Log ("switch-back message sent: " + (($r -split "`r?`n")[0]))
      exit 0
    }
    $reason = if ($out -match 'usage limit') { 'still limited' } else { 'probe failed: ' + (($out -replace '\x1b\[[0-9;]*m', '' -replace '\s+', ' ').Trim()).Substring(0, [Math]::Min(120, $out.Length)) }
    Log ("{0} (exit {1})" -f $reason, $code)
    if ($Once) { exit 1 }
    Start-Sleep -Seconds ($IntervalMin * 60)
  }
  Log 'gave up after MaxHours'
}
finally { if (-not $Once) { Remove-Item $pidFile -ErrorAction SilentlyContinue } }
