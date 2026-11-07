<# Real monitor CLI; only external API/process probes use hand-made synthetic fixtures. #>
param([ValidateSet('idle', 'wait', 'long-waits', 'workers', 'discovery', 'reports', 'unknown', 'delivery', 'scope', 'unreadable', 'mapped', 'pagination', 'heartbeat-shapes', 'heartbeat-unknown', 'process-identity', 'bounded-retry', 'heartbeat-source')][string]$Case = 'idle')
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\wait-test-' + [guid]::NewGuid().ToString('N'))
$repo = Join-Path $root 'repo'; $state = Join-Path $root 'state'; $bin = Join-Path $root 'bin'
$routes = Join-Path $root 'routes'
New-Item -ItemType Directory -Force -Path $repo, $state, $bin, $routes | Out-Null
$mapPath = Join-Path $root 'issue-map.json'
$savedPath = $env:PATH; $savedRoot = $env:WAIT_TEST_ROOT
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Route([string]$Path, $Data) {
  [IO.File]::WriteAllText((Join-Path $routes ([Uri]::EscapeDataString($Path) + '.json')), ($Data | ConvertTo-Json -Depth 20))
}
function Check {
  param([switch]$Record)
  $env:WAIT_TEST_RECORD = $(if ($Record) { '1' } else { '' })
  $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'runner.ps1') 2>&1 | Out-String
  return [pscustomobject]@{ code = $LASTEXITCODE; output = $output }
}
function Tool([string]$Command, [int]$AgeSeconds = 720) {
  Route '/api/session/active' @{ data = @{ ses_idle = @{ type = 'running' } } }
  Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; time = @{ created = $now }; content = @(@{
    type = 'tool'; name = 'shell'; time = @{ created = $now - ($AgeSeconds * 1000); ran = $now - ($AgeSeconds * 1000) }
    state = @{ status = 'running'; input = @{ command = $Command }; metadata = @{ pid = 44000 } }
  }) }); cursor = @{ next = $null } }
}
try {
  & git -C $repo init -q -b main
  Assert ($LASTEXITCODE -eq 0) 'synthetic Git setup failed'
  [IO.File]::WriteAllText($mapPath, '{"12":125}')
  Add-Type -TypeDefinition @'
using System;
using System.IO;
public class FakeSessionApi {
  public static int Main(string[] args) {
    if (Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]) == "gh") {
      Console.WriteLine("[]"); return 0;
    }
    string root = Environment.GetEnvironmentVariable("WAIT_TEST_ROOT");
    File.AppendAllText(Path.Combine(root, "calls.txt"), string.Join(" ", args) + "\n");
    if (args.Length < 3) return 8;
    if (args[1] == "post") {
      File.AppendAllText(Path.Combine(root, "sent.txt"), string.Join(" ", args) + "\n");
      return Environment.GetEnvironmentVariable("WAIT_TEST_SEND_FAIL") == "1" ? 7 : 0;
    }
    string file = Path.Combine(root, "routes", Uri.EscapeDataString(args[2]) + ".json");
    if (!File.Exists(file)) return 9;
    Console.WriteLine(File.ReadAllText(file)); return 0;
  }
}
'@ -OutputAssembly (Join-Path $bin 'opencode.exe') -OutputType ConsoleApplication
  Copy-Item (Join-Path $bin 'opencode.exe') (Join-Path $bin 'gh.exe')
  $env:PATH = $bin + ';' + $savedPath; $env:WAIT_TEST_ROOT = $root
  $monitor = Join-Path $PSScriptRoot 'utilization-check.ps1'
  @"
function Get-CimInstance { `$processes = Get-Content -Raw '$root\processes.json' | ConvertFrom-Json; foreach (`$process in `$processes) { `$process } }
`$dry = `$env:WAIT_TEST_RECORD -ne '1'
& '$monitor' -DryRun:`$dry -SessionCheckOnly -MainCheckout '$repo' -StateDir '$state' -IssueMapPath '$mapPath'
exit `$LASTEXITCODE
"@ | Set-Content -Encoding utf8 (Join-Path $root 'runner.ps1')
  [IO.File]::WriteAllText((Join-Path $state 'heartbeat.json'), '{"session_id":"ses_orchestrator","running":["125"],"phase":"done"}')
  $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $worker = @{ id = 'ses_idle'; parentID = 'ses_orchestrator'; title = 'Implement #125'; time = @{ updated = $now; idle = $now } }
  Route '/api/session/active' @{ data = @{} }
  Route '/api/session/ses_orchestrator' @{ data = @{ id = 'ses_orchestrator'; time = @{ updated = $now } } }
  Route '/api/session?parentID=ses_orchestrator&limit=100' @{ data = @($worker); cursor = @{ next = $null } }
  Route '/api/session/ses_idle' @{ data = $worker }
  Route '/api/session?parentID=ses_idle&limit=100' @{ data = @(); cursor = @{ next = $null } }
  Route '/api/session?archived=false&limit=100&search=%23125' @{ data = @($worker); cursor = @{ next = $null } }
  Route '/api/session?archived=false&limit=100&search=12' @{ data = @(); cursor = @{ next = $null } }
  Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; time = @{ created = $now }; content = @(@{ type = 'text'; text = 'Waiting for the background run. SYNTHETIC_PRIVATE_TEXT' }) }); cursor = @{ next = $null } }
  [IO.File]::WriteAllText((Join-Path $root 'processes.json'), '[]')
  if ($Case -eq 'heartbeat-source') {
    # Rule: a live heartbeat can be read without putting monitor logs or snapshots beside it.
    # Failure row: a planted default heartbeat must not override the explicitly selected source.
    $source = Join-Path $root 'live-heartbeat.json'
    [IO.File]::WriteAllText($source, '{"session_id":"ses_orchestrator","running":"125","phase":"done"}')
    $before = [IO.File]::ReadAllText($source)
    [IO.File]::WriteAllText((Join-Path $state 'heartbeat.json'), '{"running":["SYNTHETIC_PRIVATE_TICKET"]}')
    $runner = Join-Path $root 'runner.ps1'
    $script = [IO.File]::ReadAllText($runner).Replace("-IssueMapPath '$mapPath'", "-IssueMapPath '$mapPath' -HeartbeatPath '$source'")
    [IO.File]::WriteAllText($runner, $script)
    $explicit = Check
    Assert ($explicit.code -eq 1 -and $explicit.output.Contains('session=ses_idle ticket=125 status=idle-without-report')) 'explicit heartbeat source must win over a planted default'
    Assert ([IO.File]::ReadAllText($source) -ceq $before) 'heartbeat input must remain unchanged'
    Assert (-not (Test-Path (Join-Path $root 'utilization.log'))) 'monitor log must stay in StateDir, not beside the heartbeat'
    Write-Output 'PASS heartbeat-source: explicit input read unchanged; output stays in separate state directory'
    exit 0
  }
  if ($Case -eq 'heartbeat-unknown') {
    # Rule: an unrecognized running entry is unknown only for that entry, not for every session.
    # Failure row: invalid entry beside valid identities -> known healthy and idle sessions both lost.
    [IO.File]::WriteAllText((Join-Path $state 'heartbeat.json'), '{"session_id":"ses_orchestrator","running":["125r","SYNTHETIC_PRIVATE_TICKET","#24"],"phase":"done"}')
    Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = '## Done-report' }) }); cursor = @{ next = $null } }
    Route '/api/session?archived=false&limit=100&search=%2324' @{ data = @(@{ id = 'ses_other'; parentID = 'ses_orchestrator'; title = 'Fix #24' }); cursor = @{ next = $null } }
    Route '/api/session/ses_other/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = 'Waiting. SYNTHETIC_PRIVATE_TEXT' }) }); cursor = @{ next = $null } }
    $partial = Check
    Assert ($partial.code -eq 2 -and $partial.output.Contains('session=unknown ticket=unknown status=unknown pattern=heartbeat-entry-1')) 'unrecognized entry must retain a content-free indexed unknown result'
    Assert ($partial.output.Contains('session=ses_idle ticket=125 status=healthy')) 'unrecognized entry must not hide a healthy session'
    Assert ($partial.output.Contains('session=ses_other ticket=24 status=idle-without-report')) 'unrecognized entry must not hide a flagged session'
    Assert (-not $partial.output.Contains('SYNTHETIC_PRIVATE')) 'unrecognized entry and assistant text must remain local'
    Write-Output 'PASS heartbeat-unknown: one indexed unknown preserves healthy and flagged session results'
    exit 0
  }
  if ($Case -eq 'heartbeat-shapes') {
    # Rule: known heartbeat forms resolve independently to their numeric issue identities.
    # Failure rows: letter suffix / review prefix -> whole scan unknown instead of healthy sessions.
    [IO.File]::WriteAllText((Join-Path $state 'heartbeat.json'), '{"session_id":"ses_orchestrator","running":["125r","32r","review:120","merge:7",24,"#8","30, 32,106"],"phase":"done"}')
    foreach ($ticket in @('125', '32', '120', '7', '24', '8', '30', '106')) {
      $session = @{ id = "ses_ticket$ticket"; parentID = 'ses_orchestrator'; title = "Implement #$ticket" }
      Route ('/api/session?archived=false&limit=100&search=' + [Uri]::EscapeDataString("#$ticket")) @{ data = @($session); cursor = @{ next = $null } }
      Route "/api/session/ses_ticket$ticket/message?type=assistant&order=desc&limit=20" @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = '## Done-report' }) }); cursor = @{ next = $null } }
    }
    $mixed = Check
    Assert ($mixed.code -eq 0) 'known mixed heartbeat identities must not collapse the scan to unknown'
    foreach ($ticket in @('125', '32', '120', '7', '24', '8', '30', '106')) {
      Assert ($mixed.output.Contains("session=ses_ticket$ticket ticket=$ticket status=healthy")) "known heartbeat form for issue $ticket must be classified"
    }
    Assert (-not $mixed.output.Contains('status=unknown')) 'known heartbeat identities must not produce unknown entries'
    [IO.File]::WriteAllText((Join-Path $state 'heartbeat.json'), '{"session_id":"ses_orchestrator","running":"30,32,106","phase":"done"}')
    $plain = Check
    Assert ($plain.code -eq 0) 'plain comma-separated heartbeat must classify known sessions'
    foreach ($ticket in @('30', '32', '106')) {
      Assert ($plain.output.Contains("session=ses_ticket$ticket ticket=$ticket status=healthy")) "plain heartbeat issue $ticket must be classified"
    }
    Write-Output 'PASS heartbeat-shapes: comma-separated scalar, lists, numbers, suffix, review, merge and hash forms classified'
    exit 0
  }
  if ($Case -eq 'pagination') {
    # Rule: a text-free first page is not completion; follow the cursor to the newest text.
    # Failure row: idle session's report lies behind tool-only assistant messages -> unknown.
    Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @() }); cursor = @{ next = 'older-page' } }
    Route '/api/session/ses_idle/message?type=assistant&limit=20&cursor=older-page' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = '## Done-report' }) }); cursor = @{ next = $null } }
    $paged = Check
    Assert ($paged.code -eq 0 -and $paged.output.Contains('status=healthy')) 'newest text must be found across message pages'
    # Active tools do not need any earlier text to establish a healthy foreground run.
    Tool 'python -m pytest SYNTHETIC_PRIVATE_TEST' 30
    Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'tool'; name = 'shell'; time = @{ ran = $now }; state = @{ status = 'running'; input = @{ command = 'python -m pytest SYNTHETIC_PRIVATE_TEST' }; metadata = @{} } }) }); cursor = @{ next = 'older-page' } }
    $active = Check
    Assert ($active.code -eq 0 -and $active.output.Contains('status=healthy')) 'healthy active work must not require earlier text pages'
    Write-Output 'PASS pagination: newest idle text found across pages; healthy foreground work classified'
    exit 0
  }
  if ($Case -eq 'unreadable') {
    # Rule: an unreadable worker's messages retain its identity in an unknown alert.
    Remove-Item -LiteralPath (Join-Path $routes ([Uri]::EscapeDataString('/api/session/ses_idle/message?type=assistant&order=desc&limit=20') + '.json'))
    $missing = Check
    Assert ($missing.code -eq 2 -and $missing.output.Contains('session=ses_idle ticket=125 status=unknown')) 'unreadable session messages must report unknown with the session and ticket'
    Write-Output 'PASS unreadable: per-session API error reports identity without response content'
    exit 0
  }
  if ($Case -eq 'mapped') {
    # Rule: legacy bare ticket titles map to heartbeat issue numbers, excluding train/round numbers.
    $worker.title = 'Fix 12 round 2'
    Route '/api/session?archived=false&limit=100&search=%23125' @{ data = @(); cursor = @{ next = $null } }
    Route '/api/session?archived=false&limit=100&search=12' @{ data = @($worker); cursor = @{ next = $null } }
    $mapped = Check
    Assert ($mapped.code -eq 1 -and $mapped.output.Contains('session=ses_idle ticket=125 status=idle-without-report')) 'bare ticket title must map to its running issue'
    Write-Output 'PASS mapped: legacy ticket title resolves to running issue'
    exit 0
  }
  if ($Case -eq 'delivery') {
    # Rule: a non-dry alert really steers; failures do not silently become a successful cycle.
    $sent = Check -Record
    Assert ($sent.code -eq 1) 'delivered idle alert must retain flagged exit 1'
    $messages = [IO.File]::ReadAllText((Join-Path $root 'sent.txt'))
    Assert ($messages.Contains('steer') -and $messages.Contains('ses_orchestrator') -and $messages.Contains('session=ses_idle ticket=125')) 'real sender must steer the tracked orchestrator'
    Assert (-not $messages.Contains('SYNTHETIC_PRIVATE')) 'sender must never include assistant text'
    $env:WAIT_TEST_SEND_FAIL = '1'
    $failed = Check -Record
    Assert ($failed.code -eq 3) 'delivery failure must fail the monitor run'
    $env:WAIT_TEST_SEND_FAIL = ''
    $dry = Check
    Assert (@(Get-Content (Join-Path $root 'sent.txt')).Count -eq 2) 'dry run must not send'
    Write-Output 'PASS delivery: real steer sender, content-free payload, delivery failure and dry-run isolation'
    exit 0
  }
  if ($Case -eq 'scope') {
    # Rule: idle workers on a running ticket are found by title, even under an earlier/nested parent.
    # Failure row: API active omits idle session; it is not an immediate child -> invisible.
    Route '/api/session?parentID=ses_orchestrator&limit=100' @{ data = @(); cursor = @{ next = $null } }
    $worker.parentID = 'ses_earlier'
    Route '/api/session?archived=false&limit=100&search=%23125' @{ data = @($worker); cursor = @{ next = $null } }
    $nested = Check
    Assert ($nested.code -eq 1 -and $nested.output.Contains('session=ses_idle ticket=125 status=idle-without-report')) 'idle session under a different parent must be discovered by its running ticket'
    Write-Output 'PASS scope: idle worker found across parent sessions'
    exit 0
  }
  if ($Case -eq 'discovery') {
    # Rule: explicit idle status is idle even if returned in the activity map.
    # Failure row: active-map key with type=idle -> treated as running -> no alert.
    Route '/api/session/active' @{ data = @{ ses_idle = @{ type = 'idle' } } }
    $idle = Check
    Assert ($idle.code -eq 1 -and $idle.output.Contains('status=idle-without-report')) 'explicit idle state must not count as a running turn'
    # Rule: any active agent can block on a wait, including the root orchestrator.
    # Failure row: root tool wait -> skipped because it is not an implementer child.
    $worker.parentID = $null; $worker.title = 'Orchestrator'
    Route '/api/session/ses_idle' @{ data = $worker }
    Route '/api/session?parentID=ses_orchestrator&limit=100' @{ data = @(); cursor = @{ next = $null } }
    Route '/api/session?archived=false&limit=100&search=%23125' @{ data = @(); cursor = @{ next = $null } }
    Tool 'while(-not (Test-Path SYNTHETIC_PRIVATE_FILE)){Start-Sleep 5}'
    $rootWait = Check
    Assert ($rootWait.code -eq 1 -and $rootWait.output.Contains('session=ses_idle ticket=none status=blocked-wait')) 'root agent wait must be flagged'
    Write-Output 'PASS discovery: explicit idle state and active root waits classified'
    exit 0
  }
  if ($Case -eq 'reports') {
    # Rule: only the newest assistant text can satisfy completion, not old reports or user text.
    foreach ($title in @('Implement #125', 'Fix #125', 'Merge #125')) {
      $worker.title = $title
      Route '/api/session?parentID=ses_orchestrator&limit=100' @{ data = @($worker); cursor = @{ next = $null } }
      Route '/api/session?archived=false&limit=100&search=%23125' @{ data = @($worker); cursor = @{ next = $null } }
      foreach ($report in @('## Done-report', '## Merger report')) {
        Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = $report }) }); cursor = @{ next = $null } }
        $done = Check
        Assert ($done.code -eq 0 -and $done.output.Contains('status=healthy')) 'newest completion report must be healthy'
      }
      Route '/api/session/ses_idle/message?type=assistant&order=desc&limit=20' @{ data = @(@{ type = 'assistant'; content = @(@{ type = 'text'; text = 'Waiting. SYNTHETIC_PRIVATE_TEXT' }) }, @{ type = 'assistant'; content = @(@{ type = 'text'; text = '## Done-report' }) }); cursor = @{ next = $null } }
      $stale = Check
      Assert ($stale.code -eq 1 -and $stale.output.Contains('status=idle-without-report')) 'old report must not mask a newer idle wait'
    }
    Write-Output 'PASS reports: implementer/fixer/merger newest text only; stale reports rejected'
    exit 0
  }
  if ($Case -eq 'unknown') {
    # Rule: API errors and malformed response bodies are unknown, never all-fine.
    foreach ($body in @('{', '{"data":null}', '{"data":[]}', '{"data":{"ses_idle":{}}}')) {
      [IO.File]::WriteAllText((Join-Path $routes ([Uri]::EscapeDataString('/api/session/active') + '.json')), $body)
      $r = Check
      Assert ($r.code -eq 2 -and $r.output.Contains('status=unknown') -and -not $r.output.Contains('session-health status=healthy')) 'malformed active-session response must report unknown'
    }
    Remove-Item -LiteralPath (Join-Path $routes ([Uri]::EscapeDataString('/api/session/active') + '.json'))
    $missing = Check
    Assert ($missing.code -eq 2 -and $missing.output.Contains('status=unknown')) 'API command failure must report unknown'
    Write-Output 'PASS unknown: malformed and failed API probes fail closed'
    exit 0
  }
  if ($Case -eq 'bounded-retry') {
    # Rule: short statically bounded retries are not unbounded polling; enclosing infinite loops still are.
    # Failure rows: finite for/foreach retry containing sleep or Test-Path -> false blocked-wait.
    $failures = 0
    foreach ($command in @(
      'for($i=0;$i -lt 20;$i++){try { Add-Content SYNTHETIC_PRIVATE_FILE ok; break } catch { Start-Sleep -Milliseconds 50 }}',
      'foreach($attempt in 1..3){if(Test-Path SYNTHETIC_PRIVATE_FILE){break}; Start-Sleep -Seconds 3}'
    )) {
      Tool $command 30
      $bounded = Check
      if ($bounded.code -ne 0 -or -not $bounded.output.Contains('status=healthy')) {
        Write-Output 'FAIL bounded-retry/finite'; $failures++
      }
    }
    Assert ($failures -eq 0) "$failures bounded retry loops were falsely flagged"
    foreach ($command in @(
      'while($true){for($i=0;$i -lt 3;$i++){Start-Sleep 5}}',
      'for($i=0;$i -lt 30;$i++){Start-Sleep 5}',
      'for($i=0;$i -lt 3;$i++){$i=0; Start-Sleep 5}'
    )) {
      Tool $command 30
      $unbounded = Check
      Assert ($unbounded.code -eq 1 -and $unbounded.output.Contains('status=blocked-wait')) 'unbounded, long or counter-mutating retries must remain flagged'
    }
    Write-Output 'PASS bounded-retry: finite short retries healthy; enclosing waits, long and counter-mutating loops flagged'
    exit 0
  }
  if ($Case -eq 'long-waits') {
    # Rule: explicit long waits are flagged immediately, not only after ten minutes.
    # Failure rows: sleep >120 s / waitany >2 min / process poll / missing target -> healthy.
    $rows = @(
      @('Start-Sleep -Seconds 121', 'long-sleep'),
      @('Start-Sleep -s 120.5', 'long-sleep'),
      @('Start-Sleep -Milliseconds 121000', 'long-sleep'),
      @('waitany.ps1 -Minutes 10', 'waitany'),
      @('waitany.ps1 -Minutes 2.5', 'waitany'),
      @('while(Get-Process -Id 45000 -ErrorAction SilentlyContinue){Start-Sleep 5}', 'process-poll'),
      @('Wait-Process -Id 45000 -Timeout 30', 'missing-target'),
      @('Wait-Process -Name synthetic-gone -Timeout 30', 'missing-target')
    )
    $failures = 0
    foreach ($row in $rows) {
      Tool $row[0] 30
      $r = Check
      if ($r.code -ne 1 -or -not $r.output.Contains('status=blocked-wait pattern=' + $row[1])) {
        Write-Output ('FAIL long-waits/' + $row[1]); $failures++
      }
    }
    Assert ($failures -eq 0) "$failures explicit wait patterns were missed"
    Write-Output 'PASS long-waits: all eight wait patterns flagged in one cycle'
    exit 0
  }
  if ($Case -eq 'workers') {
    # Rule: >10-minute shell with no live worker is flagged; a live pytest descendant is healthy.
    # Failure row: ordinary command with a lost worker -> silently healthy.
    Tool 'python -m pytest SYNTHETIC_PRIVATE_TEST'
    $created = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 720000).ToString('o')
    $rootProcess = @{ ProcessId = 44000; ParentProcessId = 1; Name = 'powershell.exe'; CreationDate = $created }
    [IO.File]::WriteAllText((Join-Path $root 'processes.json'), (ConvertTo-Json -InputObject @($rootProcess)))
    $lost = Check
    Assert ($lost.code -eq 1 -and $lost.output.Contains('pattern=no-live-worker')) '12-minute shell with no worker was not flagged'
    $child = @{ ProcessId = 44001; ParentProcessId = 44000; Name = 'python.exe'; CreationDate = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 710000).ToString('o') }
    $grandchild = @{ ProcessId = 44002; ParentProcessId = 44001; Name = 'python.exe'; CreationDate = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 700000).ToString('o') }
    [IO.File]::WriteAllText((Join-Path $root 'processes.json'), (ConvertTo-Json -InputObject @($rootProcess, $child, $grandchild)))
    $healthy = Check
    Write-Output $healthy.output
    Assert ($healthy.code -eq 0 -and $healthy.output.Contains('session=ses_idle ticket=125 status=healthy')) '12-minute pytest with live descendants must remain healthy'
    Tool 'Start-Sleep -Seconds 120' 30
    $bounded = Check
    Assert ($bounded.code -eq 0) 'a bounded two-minute wait must not be flagged'
    Tool 'Start-Sleep -Milliseconds 1000' 30
    $milliseconds = Check
    Assert ($milliseconds.code -eq 0) 'millisecond values must not be interpreted as seconds'
    Write-Output 'PASS workers: lost worker flagged; live pytest descendants and bounded sleep healthy'
    exit 0
  }
  if ($Case -eq 'process-identity') {
    # Rule: PID plus creation time identifies the shell and every parent-child edge.
    # Failure rows: reused root PID / missing birth time / stale child PID edge -> healthy from unrelated workers.
    Tool 'python -m pytest SYNTHETIC_PRIVATE_TEST'
    $started = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 720000).ToString('o')
    $recent = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 60000).ToString('o')
    $older = [DateTimeOffset]::FromUnixTimeMilliseconds($now - 800000).ToString('o')
    $failures = 0
    foreach ($row in @(
      @{ name = 'reused-root'; rootTime = $recent; childTime = $recent },
      @{ name = 'missing-root-time'; rootTime = $null; childTime = $recent },
      @{ name = 'stale-child-edge'; rootTime = $started; childTime = $older },
      @{ name = 'missing-child-time'; rootTime = $started; childTime = $null }
    )) {
      $tree = @(
        @{ ProcessId = 44000; ParentProcessId = 1; Name = 'powershell.exe'; CreationDate = $row.rootTime },
        @{ ProcessId = 44001; ParentProcessId = 44000; Name = 'python.exe'; CreationDate = $row.childTime }
      )
      [IO.File]::WriteAllText((Join-Path $root 'processes.json'), (ConvertTo-Json -InputObject $tree))
      $identity = Check
      if ($identity.code -ne 2 -or -not $identity.output.Contains('status=unknown pattern=process-identity')) {
        Write-Output ('FAIL process-identity/' + $row.name); $failures++
      }
    }
    Assert ($failures -eq 0) "$failures unproven process identities were not unknown"
    Write-Output 'PASS process-identity: reused PIDs and missing or stale creation times remain unknown'
    exit 0
  }
  if ($Case -eq 'wait') {
    Tool 'while(-not (Test-Path SYNTHETIC_PRIVATE_FILE)){Start-Sleep 5}'
  }
  # Rule: running ticket + idle implementer + newest text without report -> alert this cycle.
  # Failure row: an ended turn saying it is waiting for background work currently goes unnoticed.
  $result = Check
  Write-Output $result.output
  if ($Case -eq 'idle') {
    Assert ($result.output.Contains('session=ses_idle ticket=125 status=idle-without-report')) 'idle implementer was not reported within one monitor cycle'
  } else {
    Assert ($result.output.Contains('session=ses_idle ticket=125 status=blocked-wait pattern=file-poll') -and $result.output.Contains('age_minutes=12')) 'running 12-minute file poll with no worker was not flagged'
  }
  Assert ($result.code -eq 1) 'flagged session must return exit 1'
  Assert (-not $result.output.Contains('SYNTHETIC_PRIVATE')) 'session text or command must not escape into the monitor output'
  Assert (-not (Test-Path (Join-Path $root 'sent.txt'))) 'dry run must never send a message'
  Write-Output "PASS ${Case}: idle session reported content-free in one cycle"
} finally {
  $env:PATH = $savedPath; $env:WAIT_TEST_ROOT = $savedRoot
  Remove-Item Env:WAIT_TEST_RECORD, Env:WAIT_TEST_SEND_FAIL -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $root -Recurse -Force
}
