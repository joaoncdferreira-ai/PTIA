param(
    [switch]$CompileOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Scheduler = Join-Path $RepoRoot "scripts\auto_newsletter_scheduler.py"
$LogPath = Join-Path $RepoRoot "data\newsletter_scheduler.log"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
}

Set-Location -LiteralPath $RepoRoot
Add-Content -LiteralPath $LogPath -Value "`n[$(Get-Date -Format o)] Starting newsletter scheduler"
$SchedulerArgs = @($Scheduler, "--hour", "9", "--minute", "0")
if (-not $CompileOnly) {
    $SchedulerArgs += "--live"
    $SchedulerArgs += "--require-linkedin-import"
    $SchedulerArgs += "--linkedin-export-max-age-days"
    $SchedulerArgs += "7"
}
$SchedulerOutput = & $Python @SchedulerArgs 2>&1
$ExitCode = $LASTEXITCODE
$SchedulerOutput | Out-File -LiteralPath $LogPath -Append -Encoding utf8
Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Scheduler exited with code $ExitCode"
exit $ExitCode
