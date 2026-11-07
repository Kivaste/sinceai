<#
.SYNOPSIS
  Exercise the real monitor's checkout-check CLI against synthetic temporary Git repositories.
  No OpenCode messages, scheduled tasks, or files in the real main checkout are touched.
#>
param([ValidateSet('planted', 'git-failure', 'identity', 'snapshot', 'delivery', 'unicode', 'all')][string]$Case = 'all')
$ErrorActionPreference = 'Stop'
$monitor = Join-Path $PSScriptRoot 'utilization-check.ps1'
$root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\fu123-test-' + [guid]::NewGuid().ToString('N'))
$repo = Join-Path $root 'repo with spaces'
$state = Join-Path $root 'state'
New-Item -ItemType Directory -Force -Path $repo | Out-Null
function Invoke-TestGit([string[]]$Arguments) {
  & git -C $repo @Arguments
  if ($LASTEXITCODE -ne 0) { throw 'synthetic repository setup failed' }
}
function Check([string]$Checkout = $repo, [switch]$Record) {
  $argv = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $monitor,
    '-MainCheckout', $Checkout, '-StateDir', $state, '-CheckoutCheckOnly')
  if (-not $Record) { $argv += '-DryRun' }
  try {
    $ErrorActionPreference = 'Continue' # Capture a failing native child's stderr instead of throwing in this harness.
    $output = & powershell.exe @argv 2>&1 | Out-String
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = 'Stop' }
  return [pscustomobject]@{ code = $code; output = $output }
}
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
  Invoke-TestGit @('init', '-q', '-b', 'main')
  Set-Content -Encoding ascii (Join-Path $repo 'tracked.txt') 'synthetic original'
  Invoke-TestGit @('add', 'tracked.txt')
  Invoke-TestGit @('-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'synthetic')
  if ($Case -in @('planted', 'all')) {
    # Rule: a newly dirty tracked path is reported in the next cycle, not silently baselined.
    # Failure row: clean snapshot -> script overwrites tracked.txt -> no alert.
    $before = Check -Record
    Assert ($before.code -eq 0) 'initial clean checkout check must succeed'
    Set-Content -Encoding ascii (Join-Path $repo 'tracked.txt') 'synthetic changed'
    $after = Check
    Assert ($after.code -eq 1 -and $after.output.Contains('tracked.txt')) 'planted tracked write was not reported within one cycle'
    Assert (-not $after.output.Contains('synthetic changed')) 'report must contain paths, not file contents'
    Write-Output 'PASS planted: next cycle reports tracked.txt, exit 1, content-free'
    Set-Content -Encoding ascii (Join-Path $repo 'tracked.txt') 'synthetic original'
  }
  if ($Case -in @('git-failure', 'all')) {
    # Rule: a failed Git probe is unknown and produces an alert, never a clean snapshot.
    # Failure row: target is not a Git repo -> no checkout alert is produced.
    $notRepo = Join-Path $root 'not-a-repository'
    New-Item -ItemType Directory -Path $notRepo | Out-Null
    $failed = Check $notRepo
    Assert ($failed.code -eq 2 -and $failed.output.Contains('[main-checkout writes] status=unknown')) 'Git failure must produce an unknown checkout alert (exit 2)'
    Assert (-not $failed.output.Contains('status=clean')) 'Git failure must not be reported as clean'
    Assert (-not $failed.output.Contains('fatal:')) 'Git diagnostics must not be included in the alert'
    Write-Output 'PASS git-failure: unknown alert, exit 2, no Git diagnostics'
    # Missing executables are also unknown, rather than a crash before the guard runs.
    $savedPath = $env:PATH
    try {
      $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
      $missing = Check
    } finally { $env:PATH = $savedPath }
    Assert ($missing.code -eq 2 -and $missing.output.Contains('[main-checkout writes] status=unknown')) 'missing Git executable must produce an unknown checkout alert (exit 2)'
    Write-Output 'PASS git-missing: unknown alert, exit 2'
  }
  if ($Case -in @('identity', 'all')) {
    # Rule: an explicitly selected checkout must be the Git top-level, not a planted nested path.
    # Failure row: directory under another repo -> Git silently probes the parent -> clean.
    $nested = Join-Path $repo 'planted-checkout'
    New-Item -ItemType Directory -Path $nested | Out-Null
    $wrongRoot = Check $nested
    Assert ($wrongRoot.code -eq 2 -and $wrongRoot.output.Contains('status=unknown')) 'a nested planted checkout must not select its parent repository'
    Write-Output 'PASS identity: planted nested checkout is unknown, exit 2'
  }
  if ($Case -in @('unicode', 'all')) {
    # Rule: Git's UTF-8 path bytes must be reported as the same path, not mojibake.
    $name = 'unicode-' + [char]0x00e9 + '.txt'
    [IO.File]::WriteAllText((Join-Path $repo $name), '')
    $unicode = Check
    Assert ($unicode.code -eq 1 -and $unicode.output.Contains($name)) 'non-ASCII dirty path must be reported without corruption'
    Remove-Item -LiteralPath (Join-Path $repo $name)
    Write-Output 'PASS unicode: literal non-ASCII path is preserved'
  }
  if ($Case -in @('snapshot', 'all')) {
    # Rule: corrupt, foreign or open-schema records are unknown, never silently accepted.
    # Failure rows: malformed JSON / extra key / different checkout / changed baseline / non-path previous entry -> clean.
    $initial = Check -Record
    Assert ($initial.code -eq 0) 'snapshot setup must run the real clean checker'
    $snapshotPath = @(Get-ChildItem -LiteralPath $state -Filter 'main-checkout-writes-*.json')[0].FullName
    $valid = [IO.File]::ReadAllText($snapshotPath)
    $badRecords = @{
      malformed = '{'
      extra_key = ($valid.TrimEnd() -replace '}$', ', "extra": true }')
      foreign_checkout = ($valid -replace '"checkout":\s*"[^"]*"', '"checkout": "C:\\foreign"')
      altered_baseline = ($valid -replace 'test_refusal_manifest_fixtures.py', 'other.py')
      invalid_previous = ($valid -replace '"previous_paths":\s*\[[^\]]*\]', '"previous_paths": [null]')
    }
    $failures = 0
    foreach ($name in @($badRecords.Keys | Sort-Object)) {
      [IO.File]::WriteAllText($snapshotPath, $badRecords[$name])
      $result = Check
      if ($result.code -ne 2 -or -not $result.output.Contains('status=unknown')) {
        $failures++; Write-Output "FAIL snapshot/$name`: invalid snapshot was not unknown"
      } else { Write-Output "PASS snapshot/$name`: unknown, exit 2" }
    }
    [IO.File]::WriteAllText($snapshotPath, $valid)
    Assert ($failures -eq 0) "$failures invalid snapshot cases were accepted"
    Write-Output 'PASS snapshot: all five invalid records fail closed'
  }
  if ($Case -in @('delivery', 'all')) {
    # Mock only the external OpenCode API executable. The monitor, Git, snapshot writer/reader,
    # send-to-orchestrator.ps1 and its quoting/delivery path are production code.
    $bin = Join-Path $root 'bin'
    New-Item -ItemType Directory -Path $bin | Out-Null
    Add-Type -TypeDefinition @'
using System;
using System.IO;
public class FakeOpenCode {
  public static int Main(string[] args) {
    File.AppendAllText(Environment.GetEnvironmentVariable("FU123_SEND_LOG"), string.Join(" ", args) + "\n");
    return int.Parse(Environment.GetEnvironmentVariable("FU123_SEND_EXIT"));
  }
}
'@ -OutputAssembly (Join-Path $bin 'opencode.exe') -OutputType ConsoleApplication
    $savedPath = $env:PATH
    $savedLog = $env:FU123_SEND_LOG; $savedExit = $env:FU123_SEND_EXIT
    try {
      $env:PATH = $bin + ';' + $savedPath
      $env:FU123_SEND_LOG = Join-Path $root 'sent.txt'; $env:FU123_SEND_EXIT = '7'
      New-Item -ItemType Directory -Force -Path $state | Out-Null
      '{"session_id":"ses_synthetic"}' | Set-Content -Encoding ascii (Join-Path $state 'heartbeat.json')
      foreach ($path in @('tests/gen_fixtures/test_refusal_manifest_fixtures.py', 'tests/run/test_verify_assertion_rerun.py')) {
        $fullPath = Join-Path $repo $path
        New-Item -ItemType Directory -Force -Path (Split-Path $fullPath) | Out-Null
        [IO.File]::WriteAllText($fullPath, '')
      }
      $baseline = Check -Record
      Assert ($baseline.code -eq 0 -and $baseline.output.Contains('status=clean')) 'known strays must be recorded as baseline, not alerted'
      $snapshotPath = @(Get-ChildItem -LiteralPath $state -Filter 'main-checkout-writes-*.json')[0].FullName
      $before = [IO.File]::ReadAllText($snapshotPath)
      Invoke-TestGit @('mv', 'tracked.txt', 'renamed path.txt')
      [IO.File]::WriteAllText((Join-Path $repo 'new path [1].txt'), 'synthetic only')
      $failedSend = Check -Record
      Assert ($failedSend.code -eq 3 -and [IO.File]::ReadAllText($snapshotPath) -ceq $before) 'failed delivery must not advance the snapshot'
      $env:FU123_SEND_EXIT = '0'
      $dry = Check
      Assert ($dry.code -eq 1 -and $dry.output.Contains('new path [1].txt') -and $dry.output.Contains('renamed path.txt') -and $dry.output.Contains('tracked.txt')) 'dry run must report literal untracked and both rename paths'
      Assert (@(Get-Content -LiteralPath $env:FU123_SEND_LOG).Count -eq 1 -and [IO.File]::ReadAllText($snapshotPath) -ceq $before) 'dry run must not send or advance state'
      $sent = Check -Record
      Assert ($sent.code -eq 1) 'successful alert must still return dirty exit 1'
      $snapshot = [IO.File]::ReadAllText($snapshotPath)
      $again = Check -Record
      Assert ($again.code -eq 0 -and $again.output.Contains('status=unchanged')) 'already reported paths must not alert again on the next cycle'
      $messages = @(Get-Content -LiteralPath $env:FU123_SEND_LOG)
      Assert ($messages.Count -eq 2 -and $messages[1].Contains('steer') -and $messages[1].Contains('ses_synthetic')) 'retry must use the real sender with steer delivery to the tracked session'
      Assert (-not $messages[1].Contains('synthetic only') -and -not $messages[1].Contains('test_refusal_manifest_fixtures.py')) 'message must contain new paths only, not contents or baseline paths'
      Move-Item -LiteralPath (Join-Path $repo '.git') -Destination (Join-Path $root 'disabled-git')
      try { $unknown = Check -Record }
      finally { Move-Item -LiteralPath (Join-Path $root 'disabled-git') -Destination (Join-Path $repo '.git') }
      Assert ($unknown.code -eq 2 -and @(Get-Content -LiteralPath $env:FU123_SEND_LOG).Count -eq 3 -and [IO.File]::ReadAllText($snapshotPath) -ceq $snapshot) 'unknown Git state must be sent and preserve the previous snapshot'
      Remove-Item -LiteralPath (Join-Path $repo 'new path [1].txt')
      Invoke-TestGit @('mv', 'renamed path.txt', 'tracked.txt')
      $clear = Check -Record
      Assert ($clear.code -eq 0) 'observed disappearance must advance the snapshot'
      [IO.File]::WriteAllText((Join-Path $repo 'new path [1].txt'), '')
      $reappeared = Check
      Assert ($reappeared.code -eq 1 -and $reappeared.output.Contains('new path [1].txt')) 'a path that reappears after an observed clean cycle must alert again'
      Write-Output 'PASS delivery: baseline, rename/untracked paths, failed-send retry, dry-run isolation, cycle suppression, unknown alert, reappearance'
    } finally {
      $env:PATH = $savedPath; $env:FU123_SEND_LOG = $savedLog; $env:FU123_SEND_EXIT = $savedExit
    }
  }
} finally {
  Remove-Item -LiteralPath $root -Recurse -Force
}
