<#
.SYNOPSIS
  Deterministic close gate (D31): a ticket may be closed only if its newest "## Done-report" comment carries the
  required evidence for the CURRENT head. Exit 0 = may close; exit 1 = missing evidence (listed); exit 2 = couldn't check.
  Missing, skipped or errored required checks are failures, never passes. Evidence for an older sha doesn't count.
.EXAMPLE
  powershell -NoProfile -File scripts/overnight/check-done-report.ps1 -Issue 61
#>
param([Parameter(Mandatory = $true)][int]$Issue, [string]$Repo = 'Kivaste/sinceai', [switch]$Quiet,
      [string]$BodyFile)   # test hook: check a local done-report file instead of the issue's comments
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$problems = New-Object System.Collections.Generic.List[string]
function Need([bool]$ok, [string]$what) { if (-not $ok) { $problems.Add($what) } }

$raw = $null
if ($BodyFile) {
  $raw = (@{ number = $Issue; title = '(local test)'; labels = @(); comments = @(@{ body = [IO.File]::ReadAllText((Resolve-Path $BodyFile).Path) }) } | ConvertTo-Json -Depth 5)
}
foreach ($try in 1..3) {
  if ($raw) { break }
  $raw = & gh issue view $Issue -R $Repo --json number,title,labels,comments 2>$null | Out-String
  if ($LASTEXITCODE -eq 0 -and $raw -match '^\s*\{') { break }
  $raw = $null; Start-Sleep -Seconds (2 * $try)
}
if (-not $raw) { "UNKNOWN: could not read issue #$Issue from GitHub"; exit 2 }
$iss = $raw | ConvertFrom-Json
$reports = @(foreach ($c in @($iss.comments)) { if ($c.body -match '(?m)^##\s*Done-report') { $c } })
if ($reports.Count -eq 0) { "FAIL #${Issue}: no '## Done-report' comment"; exit 1 }
$b = [string]$reports[-1].body
$labels = @($iss.labels | ForEach-Object { $_.name })

function Field([string]$name) { if ($b -match "(?mi)^\s*-\s*${name}:\s*(.+?)\s*$") { return $matches[1].Trim() } ; return $null }
$head = Field 'Head'; $branch = Field 'Branch'; $impl = Field 'Implementer'
Need ($head -match '^[0-9a-f]{40}$') 'Head: missing or not a full 40-char sha'
Need ([bool]$branch) 'Branch: missing'
Need ([bool]$impl) 'Implementer: missing'

# Head must be the real current head of the branch (or already merged into integration).
if ($head -match '^[0-9a-f]{40}$') {
  & git -C $RepoRoot fetch -q origin 2>$null
  $tip = $null; if ($branch) { $tip = (& git -C $RepoRoot rev-parse --verify -q "origin/$branch" 2>$null) }
  $inInteg = $false; & git -C $RepoRoot merge-base --is-ancestor $head origin/integration/pets-release 2>$null; if ($LASTEXITCODE -eq 0) { $inInteg = $true }
  Need (($tip -and $tip.Trim() -eq $head) -or $inInteg) "Head $head is neither the current origin/$branch tip nor merged into integration (stale evidence)"
}

# TDD evidence: at least one Rule with a Red line (or an explicit 'No red observed') and a Green line.
$hasRule = $b -match '(?mi)^\s*-\s*Rule:\s*\S'
$hasRed = $b -match '(?mi)Red:\s*`[^`]+`\s*(?:\u2192|->)\s*exit\s*[1-9]' -or $b -match '(?mi)No red observed:\s*\S'
$hasGreen = $b -match '(?mi)Green:\s*`[^`]+`\s*(?:\u2192|->)\s*exit\s*0'
$docsOnly = $labels -contains 'docs-only'
if (-not $docsOnly) {
  Need $hasRule 'TDD evidence: no "- Rule:" entry'
  Need $hasRed 'TDD evidence: no red run (exit != 0) and no explicit "No red observed: <why>"'
  Need $hasGreen 'TDD evidence: no green run (exit 0)'
}

# Affected tests must have run and passed.
Need ($b -match '(?mi)affected-tests\.ps1[^\r\n]*(?:\u2192|->)\s*exit\s*0') 'Affected tests: no affected-tests.ps1 run with exit 0'

# Real-run evidence: revision == head and an artefact path that exists, unless explicitly N/A with a reason.
$rev = Field 'Revision'; $art = Field 'Artefacts'; $outc = Field 'Outcome'
if ($outc -and $outc -match '^N/A:\s*\S') { }
else {
  Need ($rev -and $head -and $rev.StartsWith($head.Substring(0, [Math]::Min(12, $head.Length)))) 'Real-run evidence: Revision missing or not the reported Head'
  Need ($art -and (Test-Path -LiteralPath $art)) "Real-run evidence: Artefacts path missing or not found on disk ($art)"
  Need ($outc -and $outc -notmatch '(?i)\b(skipp|error|not run|unknown|timeout)') 'Real-run evidence: Outcome missing or reports skipped/errored/not-run checks'
}

# Reviews: a Standards APPROVE and a Spec APPROVE on this head, from families other than the implementer's.
function Family([string]$m) { if ($m -match '(?i)grok|xai') { 'xai' } elseif ($m -match '(?i)gpt|sol|openai|luna') { 'openai' } elseif ($m -match '(?i)claude|opus|sonnet|haiku') { 'anthropic' } elseif ($m -match '(?i)gemini') { 'google' } elseif ($m -match '(?i)deepseek') { 'deepseek' } elseif ($m -match '(?i)glm') { 'zhipu' } else { 'unknown' } }
$implFam = Family $impl
foreach ($axis in 'Standards', 'Spec') {
  $line = $null; if ($b -match "(?mi)^\s*-\s*${axis}:\s*(.+?)\s*$") { $line = $matches[1] }
  if (-not $line) { $problems.Add("Reviews: no $axis verdict line"); continue }
  Need ($line -match '(?i)\bAPPROVE\b' -and $line -notmatch '(?i)CHANGES') "Reviews: $axis is not APPROVE ($line)"
  if ($head) { Need ($line -match [regex]::Escape($head.Substring(0, 7))) "Reviews: $axis verdict is not pinned to head $($head.Substring(0,7))" }
  $fam = Family $line
  Need ($fam -ne 'unknown') "Reviews: $axis reviewer model not recognisable"
  Need ($fam -ne $implFam) "Reviews: $axis reviewer is the implementer's family ($fam)"
}

# Unknowns must be none.
$unk = $null; if ($b -match '(?ms)^###\s*Unknowns\s*\r?\n(.*?)(\r?\n###|\z)') { $unk = $matches[1] }
Need ($unk -and $unk -match '(?mi)^\s*-\s*none\b') 'Unknowns: section missing or not "- none" (skipped/errored/not-run required checks block the close)'

if ($problems.Count -eq 0) { if (-not $Quiet) { "PASS #${Issue} ($($iss.title)): done-report evidence complete for head $head" }; exit 0 }
"FAIL #${Issue} ($($iss.title)): $($problems.Count) evidence gap(s)"
$problems | ForEach-Object { "  - $_" }
exit 1
