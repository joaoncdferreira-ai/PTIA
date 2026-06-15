$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logPath = Join-Path $repoRoot "data\daily_editorial_task.log"

Set-Location $repoRoot
$env:PYTHONPATH = Join-Path $repoRoot "src"

Get-Content (Join-Path $repoRoot ".env.local") | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]*)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

for ($attempt = 1; $attempt -le 3; $attempt++) {
    "[$(Get-Date -Format o)] Attempt $attempt/3" | Add-Content -Path $logPath
    & $python -m ptia_engine.cli editorial-auto --limit 6 *>> $logPath
}
