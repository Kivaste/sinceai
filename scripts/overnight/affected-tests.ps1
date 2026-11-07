<#
.SYNOPSIS
  Pick the tests affected by the current branch's changes, so agents don't run the whole suite every time.
  Rules (src/pets_release/<pkg>/ maps to tests/<pkg>/):
    - any src/** change                        -> fixed repo-wide guards + test modules marked '# affected-tests: src-guard'
                                                     (branch-specific absent guards are explicitly reported)
    - affected-tests.ps1 or its test harness    -> tests/overnight/test_affected_tests.py
    - changed test files                         -> themselves
    - src/pets_release/<pkg>/**                  -> tests/<pkg> (checks -> checks, checks_producer, checks_text;
                                                    _offline_hook -> offline; package-root files -> scaffold, offline)
    - a core package changed (anything that feeds a release) -> also tests/run, tests/verify, tests/e2e (end-to-end consumers)
    - src/pets_attacker/**                       -> tests/pets_attacker
    - docs/story-kit/** -> tests/story_kit; other docs/** -> tests/docs
    - conftest.py, pyproject.toml, tests/fixtures/**, tests/gen_fixtures/** -> the whole fast suite
  The merger still runs the FULL suite on every merged result; this helper is for implementers, fixers and reviewers.
.EXAMPLE
  powershell -NoProfile -File <repo>\scripts\overnight\affected-tests.ps1            # print the selection
  powershell -NoProfile -File <repo>\scripts\overnight\affected-tests.ps1 -Run       # run it: pytest -n 2 -m "not slow"
#>
param(
  [string]$Worktree = (Get-Location).Path,
  [string]$Base = 'origin/integration/pets-release',
  [switch]$Run,
  [int]$Workers = 2
)
$ErrorActionPreference = 'Stop'
$changed = @(git -C $Worktree diff --name-only "$Base...HEAD" 2>$null) + @(git -C $Worktree diff --name-only HEAD 2>$null) + @(git -C $Worktree ls-files --others --exclude-standard 2>$null)
$changed = @($changed | Where-Object { $_ } | ForEach-Object { $_ -replace '\\', '/' } | Sort-Object -Unique)
$sel = New-Object System.Collections.Generic.HashSet[string]
$whole = $false
$core = 'checks', 'contract', 'manifest', 'writer', 'verify', 'run', 'pseudonym', 'ladders', 'policy', 'measure', 'kiteval', 'redactor', 'minimiser', 'recipient', 'detect', 'dashboard'
$coreHit = $false
function AddIf([string]$p) { if (Test-Path (Join-Path $Worktree $p)) { [void]$sel.Add($p) } }
# Legacy whole-source guards. Keep this fixed list in sync with test-affected-tests.ps1.
# New whole-source guard modules must include a standalone '# affected-tests: src-guard' comment.
# Discover markers in the selected worktree (not the helper's checkout); read errors fail closed.
$repoWideGuards = @('tests/policy', 'tests/offline/test_entrypoints.py', 'tests/run/test_context_keys.py', 'tests/pets_attacker/test_boundary.py')
if ($changed -match '^src/') {
  $absentGuards = @($repoWideGuards | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Worktree $_)) })
  if ($absentGuards.Count) { "repo-wide guards absent in checkout: $($absentGuards -join ' ')" }
  foreach ($guard in $repoWideGuards) { AddIf $guard }
  $testRoot = (Get-Item -LiteralPath (Join-Path $Worktree 'tests')).FullName
  foreach ($test in Get-ChildItem -LiteralPath $testRoot -Recurse -File -Filter 'test_*.py') {
    if (Select-String -LiteralPath $test.FullName -Pattern '^# affected-tests: src-guard\s*$' -Quiet) {
      AddIf ('tests/' + $test.FullName.Substring($testRoot.TrimEnd('\', '/').Length + 1).Replace('\', '/'))
    }
  }
}
foreach ($f in $changed) {
  if ($f -in @('scripts/overnight/affected-tests.ps1', 'scripts/overnight/test-affected-tests.ps1')) { AddIf 'tests/overnight/test_affected_tests.py'; continue }
  if ($f -eq 'tests/conftest.py' -or $f -eq 'conftest.py' -or $f -eq 'pyproject.toml' -or $f -match '^tests/(fixtures|gen_fixtures)/') { $whole = $true; continue }
  if ($f -match '^(tests/.+)/conftest\.py$') { AddIf $matches[1]; continue }          # nested conftest: its directory
  if ($f -match '^tests/.+\.py$') { AddIf $f; continue }
  if ($f -match '^src/pets_release/([^/]+)/') {
    $pkg = $matches[1]
    switch ($pkg) {
      'checks' { AddIf 'tests/checks'; AddIf 'tests/checks_producer'; AddIf 'tests/checks_text' }
      '_offline_hook' { AddIf 'tests/offline' }
      default { AddIf "tests/$pkg" }
    }
    if ($core -contains $pkg) { $coreHit = $true }
    continue
  }
  if ($f -match '^src/pets_release/[^/]+\.py$') { AddIf 'tests/scaffold'; AddIf 'tests/offline'; $coreHit = $true; continue }
  if ($f -match '^src/pets_attacker/') { AddIf 'tests/pets_attacker'; continue }
  if ($f -match '^docs/story-kit/') { AddIf 'tests/story_kit'; continue }
  if ($f -match '^docs/') { AddIf 'tests/docs'; continue }
}
if ($coreHit) { AddIf 'tests/run'; AddIf 'tests/verify'; AddIf 'tests/e2e' }
if ($sel.Count -eq 0 -and -not $whole) { AddIf 'tests/scaffold' }   # nothing mapped: cheap smoke test
# Drop entries already covered by a selected ancestor directory (no double collection).
$dirs = @($sel | Where-Object { $_ -notmatch '\.py$' })
# [string[]] so a one-element selection stays an array (an if-expression unrolls it to a scalar, which then splats wrongly).
[string[]]$paths = if ($whole) { @('tests') } else { @($sel | Where-Object { $p = $_; -not ($dirs | Where-Object { $_ -ne $p -and $p.StartsWith("$_/") }) } | Sort-Object) }
"changed files: $($changed.Count); selection: $($paths -join ' ')"
if ($Run) {
  # D30: bytecode cache OUTSIDE the repo instead of no cache (tree stays clean; modules aren't recompiled every run).
  # Child processes that still set PYTHONDONTWRITEBYTECODE=1 inherit the prefix and READ this cache.
  $env:PYTHONUTF8 = '1'; $env:TZ = 'UTC'; $env:PYTHONPATH = 'src'
  Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
  $env:PYTHONPYCACHEPREFIX = Join-Path $env:LOCALAPPDATA 'sinceai-pycache'
  $py = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path '.venv\Scripts\python.exe'
  Push-Location $Worktree
  try { & $py -m pytest -n $Workers -q -p no:cacheprovider -m 'not slow' @paths; exit $LASTEXITCODE } finally { Pop-Location }
}
