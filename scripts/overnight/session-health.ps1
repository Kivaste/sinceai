# Read-only session classification. API text/commands stay local; callers emit only these records.
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

function Get-SessionHealth($Heartbeat) {
  if (-not $Heartbeat.session_id -or -not (Has $Heartbeat 'running')) { throw 'heartbeat unavailable' }
  $active = OcApi '/api/session/active'
  if (-not (Has $active 'data') -or $null -eq $active.data -or $active.data -isnot [pscustomobject]) { throw 'active state unavailable' }
  foreach ($entry in $active.data.PSObject.Properties) {
    if ($entry.Name -notmatch '^ses_[A-Za-z0-9]+$' -or $entry.Value.type -notin @('running', 'idle')) { throw 'active session state unavailable' }
  }
  $activeIds = @($active.data.PSObject.Properties | Where-Object { $_.Value.type -ne 'idle' } | ForEach-Object { $_.Name })
  $sessions = @{}
  $running = @($Heartbeat.running | ForEach-Object { if ([string]$_ -match '^(?:merge:|#)?(\d+)$') { $matches[1] } else { throw 'running ticket identity unavailable' } })
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
            $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
            $rootIds = @()
            if ($tool.state.metadata.pid) { $rootIds = @([long]$tool.state.metadata.pid) }
            else {
              $rootIds = @($processes | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($command) } | ForEach-Object { [long]$_.ProcessId })
            }
            if (-not $rootIds.Count) { $status = 'unknown'; $pattern = 'process-identity'; break }
            $descendantIds = @($rootIds)
            do {
              $children = @($processes | Where-Object { $descendantIds -contains $_.ParentProcessId -and $descendantIds -notcontains $_.ProcessId } | ForEach-Object { [long]$_.ProcessId })
              $descendantIds += $children
            } while ($children.Count)
            $workers = @($processes | Where-Object { $descendantIds -contains $_.ProcessId -and $_.Name -notmatch '^(?i)(powershell|pwsh|cmd|conhost|sleep)(\.exe)?$' })
            if (-not $workers.Count) { $waitPattern = 'no-live-worker' }
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
