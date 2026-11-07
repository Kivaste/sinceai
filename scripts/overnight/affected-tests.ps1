<#
.SYNOPSIS
  Pick the tests affected by the current branch's changes, so agents don't run the whole suite every time.
  Rules (known source files map to explicit test files; unknown files retain folder fallback):
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
# D62: explicit file-level seams. Keep imports/CLI consumers alongside package tests.
# New/unlisted source files still take the conservative folder path below. Do not
# infer a mapping from a planted test filename or silently use a partial mapping.
$releaseSmoke = @('tests/run/test_run.py', 'tests/verify/test_full.py', 'tests/e2e/test_e2e.py')
$writerConsumers = @('tests/writer/test_writer.py', 'tests/writer/test_assemble.py', 'tests/writer/test_policy_target.py', 'tests/writer/test_manifest_value_scan.py',
  'tests/run/test_manifest_number_scan.py', 'tests/run/test_self_scan_source_values.py', 'tests/run/test_recipient_cli.py',
  'tests/verify/test_recipient.py', 'tests/verify/test_planted.py', 'tests/verify/test_manifest_value_scan.py', 'tests/verify/test_policy_target.py') + $releaseSmoke
$perFile = @{
  'src/pets_release/writer/core.py' = $writerConsumers
  'src/pets_release/writer/assemble.py' = $writerConsumers
  'src/pets_release/writer/__init__.py' = $writerConsumers
  'src/pets_release/detect/signals.py' = @('tests/detect/test_detect.py') + $releaseSmoke
  'src/pets_release/detect/inventory.py' = @('tests/detect/test_detect.py', 'tests/run/test_detector_qi_cli.py') + $releaseSmoke
  'src/pets_release/detect/serialise.py' = @('tests/detect/test_detect.py') + $releaseSmoke
  'src/pets_release/detect/cli.py' = @('tests/detect/test_detect.py') + $releaseSmoke
  'src/pets_release/ladders/transforms.py' = @('tests/ladders/test_apply.py', 'tests/ladders/test_followup43.py', 'tests/ladders/test_review_fixes.py', 'tests/ladders/test_lab_rung.py') + $releaseSmoke
  'src/pets_release/ladders/rungs.py' = @('tests/ladders/test_rungs.py', 'tests/ladders/test_review_fixes.py', 'tests/ladders/test_lab_rung.py', 'tests/contract/test_generate.py', 'tests/manifest/test_rung_ladder_cli.py', 'tests/run/test_search_rung_step_cli.py') + $releaseSmoke
  'src/pets_release/ladders/apply.py' = @('tests/ladders/test_apply.py', 'tests/ladders/test_followup43.py', 'tests/ladders/test_review_fixes.py', 'tests/ladders/test_lab_rung.py', 'tests/run/test_recipient_cli.py') + $releaseSmoke
  'src/pets_release/pseudonym/normalise.py' = @('tests/pseudonym/test_normalise.py', 'tests/pseudonym/test_pseudonym.py', 'tests/pseudonym/test_kit_visit_keys.py', 'tests/pseudonym/test_fu85_visit_keys.py') + $releaseSmoke
  'src/pets_release/pseudonym/scope_id.py' = @('tests/pseudonym/test_pseudonym.py', 'tests/manifest/test_signature.py', 'tests/run/test_recipient_cli.py') + $releaseSmoke
  'src/pets_release/run/justify.py' = @('tests/run/test_justify.py', 'tests/run/test_disposition_purpose.py', 'tests/run/test_low_severity_risks.py') + $releaseSmoke
  'src/pets_release/run/narrative.py' = @('tests/run/test_low_severity_risks.py', 'tests/run/test_manifest_number_scan.py', 'tests/writer/test_assemble.py') + $releaseSmoke
  'src/pets_release/run/provenance.py' = @('tests/run/test_provenance_mapping_cli.py') + $releaseSmoke
  'src/pets_release/run/suppress.py' = @('tests/run/test_suppression_within_bound.py', 'tests/run/test_search_privacy.py', 'tests/run/test_run_search.py') + $releaseSmoke
  'src/pets_release/run/purpose.py' = @('tests/run/test_purpose_rule.py', 'tests/run/test_purpose_gate.py', 'tests/run/test_purpose_edges_cli.py', 'tests/run/test_disposition_purpose.py') + $releaseSmoke
  'src/pets_release/verify/revision.py' = @('tests/run/test_session_revision.py', 'tests/verify/test_full.py', 'tests/verify/test_recipient.py') + $releaseSmoke
  'src/pets_release/measure/ids.py' = @('tests/measure/test_ids.py', 'tests/measure/test_measure.py', 'tests/measure/test_person_k.py', 'tests/measure/test_followup52.py', 'tests/measure/test_real_kit.py', 'tests/run/test_wire.py', 'tests/run/test_wire_search.py')
  'src/pets_release/measure/baselines.py' = @('tests/measure/test_measure.py', 'tests/measure/test_followup52.py', 'tests/measure/test_real_kit.py', 'tests/run/test_wire.py', 'tests/run/test_wire_search.py')
  'src/pets_release/measure/k.py' = @('tests/measure/test_person_k.py', 'tests/measure/test_followup52.py', 'tests/measure/test_real_kit.py', 'tests/run/test_wire.py', 'tests/run/test_wire_search.py')
  'src/pets_release/measure/wire.py' = @('tests/run/test_wire.py', 'tests/run/test_wire_search.py', 'tests/run/test_manifest_number_scan.py', 'tests/run/test_search_summary_unmeasured.py')
  'src/pets_release/dashboard/templates.py' = @('tests/dashboard/test_dashboard.py', 'tests/dashboard/test_fu51.py') + $releaseSmoke
  'src/pets_release/dashboard/render.py' = @('tests/dashboard/test_dashboard.py', 'tests/dashboard/test_fu51.py') + $releaseSmoke
  'src/pets_release/dashboard/cli.py' = @('tests/dashboard/test_dashboard.py', 'tests/dashboard/test_fu51.py') + $releaseSmoke
}
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
  if ($perFile.ContainsKey($f)) {
    # Branches differ: main may not yet carry a mapped test. Report absent paths
    # and retain the old folder fallback instead of trusting incomplete coverage.
    $absent = @($perFile[$f] | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Worktree $_)) })
    if (-not $absent.Count) {
      foreach ($test in $perFile[$f]) { AddIf $test }
      continue
    }
    "per-file mapping incomplete for ${f}; folder fallback (absent: $($absent -join ' '))"
  }
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
