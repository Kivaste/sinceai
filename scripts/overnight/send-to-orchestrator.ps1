<#
.SYNOPSIS
  Queue a message to the tracked orchestrator session (or -SessionId) via the OpenCode API.
  The message is read from a UTF-8 file so Windows PowerShell 5.1 never mangles JSON quoting.
  Delivery is "queue": the running turn is not interrupted; the message is handled next.
.EXAMPLE
  powershell -NoProfile -File scripts/overnight/send-to-orchestrator.ps1 -MessageFile $env:TEMP\msg.md
#>
param(
  [Parameter(Mandatory = $true)][string]$MessageFile,
  [string]$SessionId,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$hbPath = Join-Path $RepoRoot '.scratch\local-overnight\heartbeat.json'

function Quote-Arg([string]$a) {
  # MSVCRT / CommandLineToArgvW quoting (same as watchdog.ps1).
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

if (-not $SessionId) {
  if (-not (Test-Path $hbPath)) { Write-Error "no heartbeat at $hbPath and no -SessionId"; exit 2 }
  $SessionId = (Get-Content -Raw $hbPath | ConvertFrom-Json).session_id
  if (-not $SessionId) { Write-Error 'heartbeat has no session_id'; exit 2 }
}
$text = [IO.File]::ReadAllText((Resolve-Path $MessageFile).Path, [Text.Encoding]::UTF8)
$body = @{ text = $text; delivery = 'queue' } | ConvertTo-Json -Compress
$argv = @('api', 'post', "/api/session/$SessionId/prompt", '--data', $body)
if ($DryRun) { "would send $($text.Length) chars to $SessionId"; exit 0 }

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = (Get-Command opencode).Source
$psi.Arguments = ($argv | ForEach-Object { Quote-Arg $_ }) -join ' '
$psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
$psi.WorkingDirectory = $RepoRoot
$p = [System.Diagnostics.Process]::Start($psi)
$o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
if (-not $p.WaitForExit(60000)) { try { $p.Kill() } catch {}; Write-Error 'timeout'; exit 2 }
$p.WaitForExit()
"exit=$($p.ExitCode) session=$SessionId"
if ($o.Result) { $o.Result.Substring(0, [Math]::Min(400, $o.Result.Length)) }
if ($p.ExitCode -ne 0 -and $e.Result) { $e.Result.Substring(0, [Math]::Min(400, $e.Result.Length)) }
exit $p.ExitCode
