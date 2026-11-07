<# Exercise the production selector CLI with synthetic changed-file lists from a temporary Git repo. #>
param([ValidateSet('planted', 'missing', 'marker', 'tooling', 'all')][string]$Case = 'all')
$ErrorActionPreference = 'Stop'
$selector = Join-Path $PSScriptRoot 'affected-tests.ps1'
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
  Invoke-TestGit @('add', '.')
  Invoke-TestGit @('-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'synthetic')
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
