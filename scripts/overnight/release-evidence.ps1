<#
.SYNOPSIS
  Produce revision-bound HEALTH-S1 evidence for check-release-evidence.py / the close gate.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight/release-evidence.ps1 -Sha <full-sha> -Out C:\Users\kivas\AI\sinceai-out\evidence-<short> -Measured
.NOTES
  Out must not exist. Protected CSVs MUST remain locally: the strict reader hashes
  every bindings.files entry. Retained: those CSVs, privacy_manifest.json, paired
  .scoring/gate_report.json, and release-evidence.log. Row maps, other scoring files
  and measured scratch are deleted, including on failure. Never upload the CSVs.

  Companion affected-tests run (separate worktree, so evidence stays immutable):
    git worktree add --detach C:\Users\kivas\AI\sinceai-wt\affected-<short> <full-sha>
    powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\kivas\AI\sinceai-hackaton\scripts\overnight\affected-tests.ps1 -Worktree C:\Users\kivas\AI\sinceai-wt\affected-<short> -Base <full-sha>^ -Run
    git worktree remove C:\Users\kivas\AI\sinceai-wt\affected-<short>
  Cite that command, its actual exit and selection in the done-report. This script
  does not claim affected tests ran. Python, Kit and WorktreeRoot are CLI boundary
  overrides for synthetic minikit tests / installations outside this workstation.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Sha,
  [Parameter(Mandatory = $true)][string]$Out,
  [switch]$Measured,
  [string]$Python,
  [string]$Kit,
  [string]$WorktreeRoot = 'C:\Users\kivas\AI\sinceai-wt'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ownedWorktree = $false
$ownedOutput = $false
$pushed = $false
$exitCode = 1
$keyText = $null
$keyForms = @()
$savedEnv = @{}
$envNames = @('PETS_HMAC_KEY', 'PETS_KIT', 'PYTHONPATH', 'PYTHONUTF8', 'TZ',
              'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE', 'SOURCE_DATE_EPOCH')
foreach ($name in $envNames) { $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$utf8 = New-Object Text.UTF8Encoding($false)

function Write-Log([string]$Text) {
  # Native stderr/stdout is captured in memory and scrubbed BEFORE any persistence.
  foreach ($form in $keyForms) { $Text = $Text.Replace($form, '[REDACTED]') }
  [IO.File]::AppendAllText($log, $Text + "`n", $utf8)
  Write-Host $Text
}

function Invoke-Step([string]$Name, [string[]]$Arguments) {
  $oldPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = $null
    $lines = @(& $Python @Arguments 2>&1)
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $oldPreference }
  foreach ($line in $lines) { Write-Log ([string]$line) }
  if ($null -eq $code) { throw 'command did not return an exit code' }
  Write-Log ('{0} exit={1}' -f $Name, $code)
  return [int]$code
}

try {
  $common = & git -C $repo rev-parse --path-format=absolute --git-common-dir 2>$null
  if ($LASTEXITCODE -ne 0) { throw 'repository unavailable' }
  $primary = Split-Path -Parent $common
  if (-not $Python) { $Python = Join-Path $primary '.venv\Scripts\python.exe' }
  if (-not $Kit) {
    $Kit = Join-Path $primary 'Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026'
  }
  $Python = (Resolve-Path -LiteralPath $Python).Path
  $Kit = (Resolve-Path -LiteralPath $Kit).Path
  $actual = & git -C $repo rev-parse --verify "$Sha^{commit}" 2>$null
  if ($LASTEXITCODE -ne 0 -or $actual -ne $Sha) { throw 'revision unavailable' }
  $worktree = Join-Path ([IO.Path]::GetFullPath($WorktreeRoot)) ('evidence-' + $Sha.Substring(0, 7))
  $Out = [IO.Path]::GetFullPath($Out)
  if ($Out -eq $worktree -or $Out.StartsWith($worktree + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'output must be outside the temporary worktree'
  }
  if (Test-Path -LiteralPath $Out) { throw 'output already exists' }
  if (Test-Path -LiteralPath $worktree) { throw 'worktree already exists' }
  New-Item -ItemType Directory -Path $Out | Out-Null
  $ownedOutput = $true
  $log = Join-Path $Out 'release-evidence.log'
  Write-Log ('revision=' + $Sha)
  # Do not reuse a planted worktree or trust a checkout by its filename.
  # Windows PowerShell turns even git's successful progress stderr into error
  # records; capture it without treating progress as a terminating exception.
  $ErrorActionPreference = 'Continue'
  $gitOutput = @(& git -C $repo worktree add --detach $worktree $Sha 2>&1)
  $gitExit = $LASTEXITCODE
  $ErrorActionPreference = 'Stop'
  if ($gitExit -ne 0) { throw 'detached worktree creation failed' }
  $ownedWorktree = $true
  $checked = & git -C $worktree rev-parse HEAD 2>$null
  if ($LASTEXITCODE -ne 0 -or $checked -ne $Sha) { throw 'worktree revision mismatch' }

  $bytes = New-Object byte[] 32
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  $keyText = -join ($bytes | ForEach-Object { $_.ToString('x2') })
  [Array]::Clear($bytes, 0, $bytes.Length)
  $keyForms = @($keyText, $keyText.ToUpperInvariant(),
               [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($keyText)))
  $env:PETS_HMAC_KEY = $keyText
  $env:PETS_KIT = $Kit
  $env:PYTHONPATH = Join-Path $worktree 'src'
  $env:PYTHONUTF8 = '1'
  $env:TZ = 'UTC'
  $env:PYTHONPYCACHEPREFIX = Join-Path $env:LOCALAPPDATA 'sinceai-pycache'
  Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
  $epoch = & git -C $worktree show -s --format=%ct HEAD
  if ($LASTEXITCODE -ne 0) { throw 'revision timestamp unavailable' }
  $env:SOURCE_DATE_EPOCH = $epoch
  $created = [DateTimeOffset]::FromUnixTimeSeconds([long]$epoch).UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
  $release = Join-Path $Out 'health-s1'
  $argsRun = @('--scenario', 'HEALTH-S1', '--out', $release, '--created', $created, '--kit', $Kit)
  Push-Location $worktree
  $pushed = $true
  if ($Measured) {
    $runExit = Invoke-Step 'run' (@('-m', 'pets_release.measure.wire') + $argsRun)
  } else {
    $runExit = Invoke-Step 'run' (@('-m', 'pets_release', 'run') + $argsRun)
  }
  if ($runExit -ne 0) { throw 'release failed' }
  # Both checks actually run, even if limited verification fails.
  $verifyExit = Invoke-Step 'verify' @('-m', 'pets_release', 'verify', $release)
  $fullExit = Invoke-Step 'verify-full' @('-m', 'pets_release', 'verify', '--full', '--kit', $Kit, $release)
  if ($verifyExit -ne 0 -or $fullExit -ne 0) { throw 'verification failed' }
  $exitCode = 0
} catch {
  # Exception messages can contain native arguments or input values. Never echo them.
  if ($ownedOutput) { Write-Log 'release-evidence failed (see actual step exits above)' }
  else { Write-Host 'release-evidence refused: revision/paths unavailable or already present' }
  $exitCode = 1
} finally {
  if ($pushed) { Pop-Location }
  foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
  $keyText = $null
  $keyForms = @()
  try {
    if ($ownedOutput) {
      $scoring = Join-Path $Out 'health-s1.scoring'
      if (Test-Path -LiteralPath $scoring) {
        Get-ChildItem -LiteralPath $scoring -Force | Where-Object { $_.Name -ne 'gate_report.json' } |
          Remove-Item -Recurse -Force
      }
      $measure = Join-Path $Out 'health-s1.measure'
      if (Test-Path -LiteralPath $measure) { Remove-Item -LiteralPath $measure -Recurse -Force }
    }
  } catch { Write-Host 'release-evidence artefact cleanup failed'; $exitCode = 1 }
  if ($ownedWorktree) {
    $cleanup = @(& git -C $repo worktree remove --force $worktree 2>&1)
    if ($LASTEXITCODE -ne 0) { Write-Host 'release-evidence worktree cleanup failed'; $exitCode = 1 }
  }
}
exit $exitCode
