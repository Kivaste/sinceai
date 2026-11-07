# Read-only session classification. API text/commands stay local; callers emit only these records.
function Test-ShortRetry($Loop) {
  $count = 0; $counter = $null
  if ($Loop -is [Management.Automation.Language.ForStatementAst]) {
    if ($Loop.Initializer.Extent.Text -notmatch '^\$(\w+)\s*=\s*(\d+)$') { return $false }
    $counter = $matches[1]; $first = [long]$matches[2]
    if ($Loop.Condition.Extent.Text -notmatch ('^\$' + [regex]::Escape($counter) + '\s+-lt\s+(\d+)$')) { return $false }
    $count = [long]$matches[1] - $first
    if ($Loop.Iterator.Extent.Text -notmatch ('^\$' + [regex]::Escape($counter) + '\+\+$')) { return $false }
  } elseif ($Loop -is [Management.Automation.Language.ForEachStatementAst]) {
    if ($Loop.Condition.Extent.Text -notmatch '^(\d+)\.\.(\d+)$') { return $false }
    $count = [Math]::Abs([long]$matches[2] - [long]$matches[1]) + 1
    $counter = $Loop.Variable.VariablePath.UserPath
  } else { return $false }
  if ($count -lt 1 -or $count -gt 120) { return $false }
  # Only prove simple retries: nested loops and writes to the iteration counter defeat the bound.
  $mutations = @($Loop.Body.FindAll({ param($node)
    $node -is [Management.Automation.Language.LoopStatementAst] -or
    ($node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -ieq ('$' + $counter)) -or
    ($node -is [Management.Automation.Language.UnaryExpressionAst] -and $node.Child.Extent.Text -ieq ('$' + $counter))
  }, $true))
  if ($mutations.Count) { return $false }
  $delay = 0.0
  foreach ($call in @($Loop.Body.FindAll({ param($node) $node -is [Management.Automation.Language.CommandAst] }, $true))) {
    $name = $call.GetCommandName()
    if ($name -in @('Set-Variable', 'Clear-Variable', 'Remove-Variable', 'Invoke-Expression')) { return $false }
    if ($name -ine 'Start-Sleep') { continue }
    if ($call.Extent.Text -match '(?i)^Start-Sleep\s+-(?:Milliseconds|m)\s+(\d+(?:\.\d+)?)$') { $delay += [double]$matches[1] / 1000 }
    elseif ($call.Extent.Text -match '(?i)^Start-Sleep\s+(?:-(?:Seconds|s)\s+)?(\d+(?:\.\d+)?)$') { $delay += [double]$matches[1] }
    else { return $false }
  }
  return ($count * $delay) -le 120
}

function Get-WaitPattern([string]$Command) {
  $tokens = $null; $errors = $null
  $ast = [Management.Automation.Language.Parser]::ParseInput($Command, [ref]$tokens, [ref]$errors)
  $commands = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.CommandAst] }, $true))
  foreach ($call in $commands) {
    $name = $call.GetCommandName()
    if (-not $name) { continue }
    $name = ($name -split '[/\\]')[-1]
    $argsText = $call.Extent.Text
    if ($name -ieq 'Start-Sleep') {
      if ($argsText -match '(?i)\s-(?:Milliseconds|m)\s+(\d+(?:\.\d+)?)' -and [double]$matches[1] -gt 120000) { return 'long-sleep' }
      if ($argsText -match '(?i)\bStart-Sleep\s+(?:-(?:Seconds|s)\s+)?(\d+(?:\.\d+)?)' -and [double]$matches[1] -gt 120) { return 'long-sleep' }
    }
    if ($name -ieq 'waitany.ps1' -or $name -ieq 'waitany') {
      if ($argsText -notmatch '(?i)-Minutes\s+(\d+(?:\.\d+)?)' -or [double]$matches[1] -gt 2) { return 'waitany' }
    }
    if ($name -ieq 'Wait-Process' -and $argsText -match '(?i)-Id\s+(\d+)') {
      $target = [long]$matches[1]
      $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
      if (-not @($processes | Where-Object { $_.ProcessId -eq $target }).Count) { return 'missing-target' }
    }
    if ($name -ieq 'Wait-Process' -and $argsText -match '(?i)-Name\s+([\w.-]+)') {
      $targetName = $matches[1] -replace '\.exe$', ''
      $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
      if (-not @($processes | Where-Object { ($_.Name -replace '\.exe$', '') -eq $targetName }).Count) { return 'missing-target' }
    }
    if ($name -in @('Test-Path', 'Get-Process', 'Start-Sleep')) {
      $parent = $call.Parent
      while ($parent) {
        if ($parent -is [Management.Automation.Language.LoopStatementAst]) {
          # Skip only the proven finite retry itself, never an enclosing unbounded loop.
          if (Test-ShortRetry $parent) { $parent = $parent.Parent; continue }
          if ($name -ieq 'Test-Path') { return 'file-poll' }
          if ($name -ieq 'Get-Process') { return 'process-poll' }
          # Sleep-only loops are waits too, not productive descendants.
          if ($parent.Extent.Text -notmatch '(?i)Test-Path|Get-Process') { return 'sleep-loop' }
        }
        $parent = $parent.Parent
      }
    }
  }
  return 'none'
}

function Get-ProcessBirth($Process) {
  if (-not $Process.CreationDate) { throw 'process birth unavailable' }
  return ([DateTimeOffset]$Process.CreationDate).UtcDateTime
}

function Test-LiveWorker($Processes, $Tool, [string]$Command, [long]$Started) {
  $toolStart = [DateTimeOffset]::FromUnixTimeMilliseconds($Started).UtcDateTime
  $roots = @($Processes | Where-Object {
    if ($Tool.state.metadata.pid) { $_.ProcessId -eq [long]$Tool.state.metadata.pid }
    else { $_.CommandLine -and $_.CommandLine.Contains($Command) }
  })
  # PID alone can be recycled. A shell must have been born when this tool started (5s spawn allowance).
  $roots = @($roots | Where-Object { [Math]::Abs(((Get-ProcessBirth $_) - $toolStart).TotalSeconds) -le 5 })
  if ($roots.Count -ne 1) { throw 'process identity unavailable' }
  $descendants = @{}
  $descendants[[long]$roots[0].ProcessId] = Get-ProcessBirth $roots[0]
  do {
    $added = 0
    foreach ($process in $Processes) {
      $id = [long]$process.ProcessId; $parentId = [long]$process.ParentProcessId
      if ($descendants.ContainsKey($parentId) -and -not $descendants.ContainsKey($id)) {
        $birth = Get-ProcessBirth $process
        # An older child belongs to a previous incarnation of its parent PID, not this tool.
        if ($birth -lt $descendants[$parentId] -or $birth -gt $NowUtc.AddSeconds(5)) { throw 'process edge unavailable' }
        $descendants[$id] = $birth; $added++
      }
    }
  } while ($added)
  return @($Processes | Where-Object { $descendants.ContainsKey([long]$_.ProcessId) -and $_.Name -notmatch '^(?i)(powershell|pwsh|cmd|conhost|sleep)(\.exe)?$' }).Count -gt 0
}

function Get-SessionHealth($Heartbeat) {
  if (-not $Heartbeat.session_id -or -not (Has $Heartbeat 'running')) { throw 'heartbeat unavailable' }
  $active = OcApi '/api/session/active'
  if (-not (Has $active 'data') -or $null -eq $active.data -or $active.data -isnot [pscustomobject]) { throw 'active state unavailable' }
  foreach ($entry in $active.data.PSObject.Properties) {
    if ($entry.Name -notmatch '^ses_[A-Za-z0-9]+$' -or $entry.Value.type -notin @('running', 'idle')) { throw 'active session state unavailable' }
  }
  $activeIds = @($active.data.PSObject.Properties | Where-Object { $_.Value.type -ne 'idle' } | ForEach-Object { $_.Name })
  $sessions = @{}
  $running = @()
  $runningEntries = @(foreach ($entry in @($Heartbeat.running)) {
    if ($entry -is [string]) { $entry.Split(',') | ForEach-Object { $_.Trim() } }
    else { $entry }
  })
  for ($index = 0; $index -lt $runningEntries.Count; $index++) {
    if ([string]$runningEntries[$index] -match '^(?:(?:merge:|review:|#)(\d+)|(\d+)[A-Za-z]*)$') {
      $running += $matches[1] + $matches[2]
    } else {
      # Index the unknown entry without forwarding its untrusted text; keep scanning known identities.
      [pscustomobject]@{ session = 'unknown'; ticket = 'unknown'; status = 'unknown'; pattern = "heartbeat-entry-$index"; age = 0 }
    }
  }
  $issueMap = Read-Json $MapPath
  if ((Test-Path -LiteralPath $MapPath) -and -not $issueMap) { throw 'issue map unavailable' }
  $searchTerms = @($running | ForEach-Object { '#' + $_ })
  foreach ($entry in @($issueMap.PSObject.Properties)) {
    if ($entry.Name -match '^\d+$' -and $running -contains [string]$entry.Value) { $searchTerms += [string][int]$entry.Name }
  }
  foreach ($term in @($searchTerms | Sort-Object -Unique)) {
    $prefix = '/api/session?archived=false&limit=100&search=' + [Uri]::EscapeDataString($term)
    $path = $prefix
    do {
      Need 'session discovery'
      $page = OcApi $path
      if ($page.data -isnot [array] -or -not (Has $page 'cursor')) { throw 'session list unavailable' }
      foreach ($session in $page.data) {
        if (-not $session.id) { throw 'session identity unavailable' }
        $sessions[$session.id] = $session
      }
      $path = $null
      if ($page.cursor.next) { $path = $prefix + '&cursor=' + [Uri]::EscapeDataString($page.cursor.next) }
    } while ($path)
  }
  foreach ($id in $activeIds) {
    if (-not $sessions.ContainsKey($id)) {
      Need 'active session'
      $session = (OcApi "/api/session/$id").data
      if (-not $session -or $session.id -ne $id) { throw 'session unavailable' }
      $sessions[$id] = $session
    }
  }
  foreach ($id in @($sessions.Keys | Sort-Object)) {
    $session = $sessions[$id]
    $tickets = @([regex]::Matches([string]$session.title, '#(\d+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $bare = [regex]::Replace([string]$session.title, '#\d+', ' ')
    $bare = [regex]::Replace($bare, '(?i)\b(pass|round|step|part|v|train)\s*\d+', ' ')
    foreach ($match in [regex]::Matches($bare, '(?<![\w.])(\d{1,2})[A-Za-z]?(?![\w.])')) {
      $key = '{0:D2}' -f [int]$match.Groups[1].Value
      if (Has $issueMap $key) { $tickets += [string]$issueMap.$key }
    }
    $tickets = @($tickets | Sort-Object -Unique)
    $runningTickets = @($tickets | Where-Object { $running -contains $_ })
    $idleCandidate = $session.parentID -and $session.title -match '(?i)\b(Implement|Fix|Merge)' -and $runningTickets.Count
    if (-not $idleCandidate -and $activeIds -notcontains $id) { continue }
    $reportTickets = $runningTickets
    if (-not $reportTickets.Count) { $reportTickets = $tickets }
    if (-not $reportTickets.Count) { $reportTickets = @('none') }
    $status = 'unknown'; $pattern = 'api-read'; $age = 0
    try {
      Need 'session messages'
      $messages = OcApi "/api/session/$id/message?type=assistant&order=desc&limit=20"
      if ($messages.data -isnot [array] -or -not (Has $messages 'cursor')) { throw 'messages unavailable' }
      $newestText = $null
      $textPage = $messages
      do {
        foreach ($message in $textPage.data) {
          $texts = @($message.content | Where-Object { $_.type -eq 'text' })
          if ($texts.Count) { $newestText = ($texts | ForEach-Object { $_.text }) -join "`n"; break }
        }
        if ($null -ne $newestText -or -not $textPage.cursor.next -or $activeIds -contains $id) { break }
        Need 'newest assistant text'
        $textPage = OcApi ("/api/session/$id/message?type=assistant&limit=20&cursor=" + [Uri]::EscapeDataString($textPage.cursor.next))
        if ($textPage.data -isnot [array] -or -not (Has $textPage 'cursor')) { throw 'message page unavailable' }
      } while ($true)
      $status = 'healthy'
      $pattern = 'none'; $age = 0
      if ($idleCandidate -and $activeIds -notcontains $id -and $newestText -notmatch '(?im)^##\s+(Done-report|Merger report|Merge report)\s*$') { $status = 'idle-without-report' }
      if ($activeIds -contains $id) {
        foreach ($tool in @($messages.data | ForEach-Object { $_.content } | Where-Object { $_.type -eq 'tool' -and $_.state.status -eq 'running' })) {
          if ($tool.name -notmatch '(^|[._])shell$') { continue }
          $command = [string]$tool.state.input.command
          $started = $tool.time.ran
          if (-not $started) { $started = $tool.time.created }
          if (-not $started) { throw 'tool age unavailable' }
          $age = [Math]::Round(($NowUtc - [DateTimeOffset]::FromUnixTimeMilliseconds([long]$started).UtcDateTime).TotalMinutes, 1)
          $waitPattern = Get-WaitPattern $command
          if ($waitPattern -eq 'none' -and $age -gt 10) {
            try {
              $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
              $hasWorker = Test-LiveWorker $processes $tool $command ([long]$started)
            } catch { $status = 'unknown'; $pattern = 'process-identity'; break }
            if (-not $hasWorker) { $waitPattern = 'no-live-worker' }
          }
          if ($waitPattern -ne 'none') {
            $status = 'blocked-wait'; $pattern = $waitPattern
            break
          }
        }
      }
    } catch {
      $status = 'unknown'; $pattern = 'api-read'
    }
    foreach ($ticket in $reportTickets) { [pscustomobject]@{ session = $id; ticket = $ticket; status = $status; pattern = $pattern; age = $age } }
  }
}
