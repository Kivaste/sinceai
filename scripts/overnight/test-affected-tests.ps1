<# Exercise the production selector CLI with synthetic changed-file lists from a temporary Git repo. #>
param([ValidateSet('planted', 'missing', 'marker', 'tooling', 'mapped', 'fallback', 'incomplete', 'clean', 'all')][string]$Case = 'all')
$ErrorActionPreference = 'Stop'
$selector = Join-Path $PSScriptRoot 'affected-tests.ps1'
if ($Case -eq 'clean') {
  # Exercise a full real harness run from a checkout with NO scratch ignore rule.
  # The checkout guard can observe transient writes, even if finally removes them.
  $outside = Join-Path $env:LOCALAPPDATA ('Temp\opencode\affected-clean-' + [guid]::NewGuid().ToString('N'))
  $invoking = Join-Path $outside 'checkout'
  $scripts = Join-Path $invoking 'scripts\overnight'
  New-Item -ItemType Directory -Force -Path $scripts | Out-Null
  function CleanGit([string[]]$Arguments) {
    $result = & git -C $invoking @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'clean-checkout regression setup/status failed' }
    return ($result | Out-String)
  }
  try {
    Copy-Item -LiteralPath $selector -Destination $scripts
    Copy-Item -LiteralPath $PSCommandPath -Destination $scripts
    [void](CleanGit @('init', '-q', '-b', 'main'))
    [void](CleanGit @('add', '.'))
    [void](CleanGit @('-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'synthetic invoking checkout'))
    $before = CleanGit @('status', '--porcelain', '--untracked-files=all')
    $harness = Join-Path $scripts 'test-affected-tests.ps1'
    $child = Start-Process powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $harness + '"'), '-Case', 'all') `
      -WorkingDirectory $invoking -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $outside 'stdout.txt') -RedirectStandardError (Join-Path $outside 'stderr.txt')
    $null = $child.Handle # Retain the process handle so Windows PowerShell preserves ExitCode.
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $dirty = $false
    while (-not $child.WaitForExit(50)) {
      if ((CleanGit @('status', '--porcelain', '--untracked-files=all')) -cne $before) { $dirty = $true }
      if ($clock.Elapsed.TotalSeconds -gt 65) {
        & taskkill.exe /PID $child.Id /T /F | Out-Null
        throw 'full harness cleanliness regression exceeded its 65-second bound'
      }
    }
    $child.WaitForExit()
    $after = CleanGit @('status', '--porcelain', '--untracked-files=all')
    if ($child.ExitCode -ne 0) { throw ('full harness failed: ' + (Get-Content (Join-Path $outside 'stdout.txt') -Raw) + (Get-Content (Join-Path $outside 'stderr.txt') -Raw)) }
    if ($dirty -or $after -cne $before) { throw 'full harness changed invoking checkout git status (transient or persistent scratch write)' }
    Write-Output 'PASS clean: full harness leaves invoking checkout status unchanged throughout and after the run'
  } finally {
    Remove-Item -LiteralPath $outside -Recurse -Force
  }
  exit 0
}
$root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\affected-tests-' + [guid]::NewGuid().ToString('N'))
$repo = Join-Path $root 'repo with spaces'
New-Item -ItemType Directory -Force -Path $repo | Out-Null
function Invoke-TestGit([string[]]$Arguments) {
  & git -C $repo @Arguments
  if ($LASTEXITCODE -ne 0) { throw 'synthetic repository setup failed' }
}
function Plant([string]$Path, [string]$Text = '') {
  $full = Join-Path $repo $Path
  New-Item -ItemType Directory -Force -Path (Split-Path $full) | Out-Null
  [IO.File]::WriteAllText($full, $Text)
}
function Select-Tests {
  try {
    $ErrorActionPreference = 'Continue'
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $selector -Worktree $repo -Base main 2>&1 | Out-String
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = 'Stop' }
  return [pscustomobject]@{ code = $code; output = $output }
}
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
  Invoke-TestGit @('init', '-q', '-b', 'main')
  # Independent acceptance list: deleting a production guard must fail this regression.
  $guards = @('tests/policy', 'tests/offline/test_entrypoints.py', 'tests/run/test_context_keys.py', 'tests/pets_attacker/test_boundary.py')
  foreach ($guard in $guards) {
    $file = if ($guard -eq 'tests/policy') { "$guard/test_policy.py" } else { $guard }
    Plant $file
  }
  Plant 'tests/scaffold/test_smoke.py'
  Plant 'tests/overnight/test_affected_tests.py'
  foreach ($path in @('tests/writer/test_writer.py', 'tests/writer/test_assemble.py', 'tests/writer/test_policy_target.py', 'tests/writer/test_manifest_value_scan.py',
    'tests/run/test_manifest_number_scan.py', 'tests/run/test_self_scan_source_values.py', 'tests/run/test_recipient_cli.py',
    'tests/verify/test_recipient.py', 'tests/verify/test_planted.py', 'tests/verify/test_manifest_value_scan.py', 'tests/verify/test_policy_target.py',
    'tests/run/test_run.py', 'tests/run/test_unrelated.py', 'tests/verify/test_full.py', 'tests/e2e/test_e2e.py')) { Plant $path }
  Invoke-TestGit @('add', '.')
  Invoke-TestGit @('-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'synthetic')
  if ($Case -in @('mapped', 'all')) {
    # Rule: a known source file selects its tests/CLI consumers, not whole folders.
    # Failure row: writer/core.py -> entire writer + run + verify + e2e folders.
    Plant 'src/pets_release/writer/core.py'
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    $selection = @(($result.output.Trim() -split 'selection: ')[-1] -split ' ')
    foreach ($path in @('tests/writer/test_writer.py', 'tests/run/test_run.py', 'tests/verify/test_full.py', 'tests/e2e/test_e2e.py') + $guards) {
      Assert ($selection -contains $path) "mapped writer change missed $path; $($result.output)"
    }
    foreach ($path in @('tests/writer', 'tests/run', 'tests/verify', 'tests/e2e', 'tests/run/test_unrelated.py')) {
      Assert ($selection -notcontains $path) "mapped writer change did not slim $path; $($result.output)"
    }
    Remove-Item -LiteralPath (Join-Path $repo 'src/pets_release/writer/core.py')
    Write-Output 'PASS mapped: per-file selection is a strict subset and retains CLI consumers and guards'
  }
  if ($Case -in @('fallback', 'all')) {
    # Rule: an unmapped source file retains the old folder/consumer fallback.
    Plant 'src/pets_release/writer/future_module.py'
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    $selection = @(($result.output.Trim() -split 'selection: ')[-1] -split ' ')
    foreach ($path in @('tests/writer', 'tests/run', 'tests/verify', 'tests/e2e')) {
      Assert ($selection -contains $path) "unmapped source did not fall back to $path; $($result.output)"
    }
    Remove-Item -LiteralPath (Join-Path $repo 'src/pets_release/writer/future_module.py')
    Write-Output 'PASS fallback: unmapped source retains folder and consumer fallback'
  }
  if ($Case -in @('incomplete', 'all')) {
    # A planted lookalike test cannot repair an absent exact mapped destination.
    Plant 'src/pets_release/writer/core.py'
    Remove-Item -LiteralPath (Join-Path $repo 'tests/writer/test_writer.py')
    Plant 'tests/writer/test_core.py'
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    Assert ($result.output.Contains('per-file mapping incomplete for src/pets_release/writer/core.py; folder fallback')) 'incomplete mapping did not report folder fallback'
    $selection = @(($result.output.Trim() -split 'selection: ')[-1] -split ' ')
    foreach ($path in @('tests/writer', 'tests/run', 'tests/verify', 'tests/e2e')) {
      Assert ($selection -contains $path) "incomplete mapping failed to retain $path; $($result.output)"
    }
    Remove-Item -LiteralPath (Join-Path $repo 'src/pets_release/writer/core.py')
    Plant 'tests/writer/test_writer.py'
    Write-Output 'PASS incomplete: missing exact destination retains fallback despite planted lookalike'
  }
  if ($Case -in @('planted', 'all')) {
    # Rule: ANY src change selects every whole-source guard, even an unmapped new package.
    # Failure row: synthetic changed list [src/pets_release/new_package/cli.py] -> smoke only.
    Plant 'src/pets_release/new_package/cli.py' "def main(argv=None):`n    return 0`n"
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    $selection = @(($result.output.Trim() -split 'selection: ')[-1] -split ' ')
    foreach ($guard in $guards) {
      Assert ($selection -contains $guard) "planted source change did not select $guard; $($result.output.Trim())"
    }
    Assert (-not $result.output.Contains('def main')) 'selection must contain paths, not source contents'
    Write-Output 'PASS planted: new package CLI selects all four repo-wide guards'
  }
  if ($Case -in @('missing', 'all')) {
    # Rule: legacy paths absent on main are explicitly reported, never silently dropped.
    # Failure row: src change + missing guard -> exit 0 without an absence diagnostic.
    Plant 'src/pets_release/new_package/cli.py'
    Remove-Item -LiteralPath (Join-Path $repo 'tests/offline/test_entrypoints.py')
    $result = Select-Tests
    Assert ($result.code -eq 0) "selection must tolerate an absent branch-specific guard: $($result.output)"
    Assert ($result.output.Contains('repo-wide guards absent in checkout: tests/offline/test_entrypoints.py')) 'missing legacy guard was not explicitly reported'
    Assert ($result.output.Contains('tests/run/test_context_keys.py')) 'an absent guard must not suppress guards that exist'
    Write-Output 'PASS missing: absent legacy guard explicitly reported; present guards retained'
  }
  if ($Case -in @('marker', 'all')) {
    # Rule: new whole-src scanners declare the src-guard marker and join the selection.
    # Failure row: new marked scanner in another test folder + src change -> scanner omitted.
    Plant 'tests/new_guard/test_whole_src.py' "# affected-tests: src-guard`nfrom pathlib import Path`ndef test_src():`n    assert list(Path('src').rglob('*.py'))`n"
    Invoke-TestGit @('add', 'tests/new_guard/test_whole_src.py')
    Invoke-TestGit @('-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'synthetic marked guard')
    Plant 'src/other_package/module.txt'
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    Assert ($result.output.Contains('tests/new_guard/test_whole_src.py')) 'new marked whole-src scanner was not selected'
    Write-Output 'PASS marker: new whole-src scanner selected via its marker for an arbitrary src path'
  }
  if ($Case -in @('tooling', 'all')) {
    # Rule: changes to the selector or its CLI harness select its own regression tests.
    # Failure row: changed helper script -> scaffold smoke instead of selector regressions.
    Plant 'scripts/overnight/affected-tests.ps1'
    $result = Select-Tests
    Assert ($result.code -eq 0) "selector failed: $($result.output)"
    Assert ($result.output.Contains('tests/overnight/test_affected_tests.py')) 'selector tooling change did not select its regression tests'
    Write-Output 'PASS tooling: selector tooling change selects its own regression tests'
  }
} finally {
  Remove-Item -LiteralPath $root -Recurse -Force
}
