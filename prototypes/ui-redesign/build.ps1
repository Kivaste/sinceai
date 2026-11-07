# PROTOTYPE build: extract aggregates from the manifests and inline them into prototype.html
param(
  [string]$Measured = 'C:\Users\kivas\AI\sinceai-out\proof-5b260ec\health-s1-measured\privacy_manifest.json',
  [string]$Plain = 'C:\Users\kivas\AI\sinceai-out\proof-5b260ec\health-s1-plain\privacy_manifest.json'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$env:PYTHONUTF8 = '1'
python -I "$here\extract_aggregates.py" $Measured $Plain "$here\data.js"
if ($LASTEXITCODE -ne 0) { throw 'extract failed' }
$src = [IO.File]::ReadAllText("$here\prototype.src.html")
$data = [IO.File]::ReadAllText("$here\data.js")
[IO.File]::WriteAllText("$here\prototype.html", $src.Replace('/*__DATA__*/', $data), (New-Object Text.UTF8Encoding $false))
