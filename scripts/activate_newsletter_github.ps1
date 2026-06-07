$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$EnvPath = Join-Path $RepoRoot ".env.local"

Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found at $Python"
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is not installed."
}

function Read-DotEnv {
    $values = @{}
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        return $values
    }
    foreach ($line in Get-Content -LiteralPath $EnvPath) {
        if ($line -match "^\s*([^#][A-Za-z0-9_]+)\s*=\s*(.*)$") {
            $values[$matches[1]] = $matches[2].Trim()
        }
    }
    return $values
}

function Set-DotEnvValue {
    param([string]$Name, [string]$Value)
    $lines = @()
    if (Test-Path -LiteralPath $EnvPath) {
        $lines = @(Get-Content -LiteralPath $EnvPath)
    }
    $escaped = [regex]::Escape($Name)
    $updated = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^\s*$escaped\s*=") {
            $lines[$index] = "$Name=$Value"
            $updated = $true
        }
    }
    if (-not $updated) {
        $lines += "$Name=$Value"
    }
    [IO.File]::WriteAllLines($EnvPath, $lines, [Text.UTF8Encoding]::new($false))
}

function Read-SecretText {
    param([string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Set-GitHubSecret {
    param([string]$Name, [string]$Value)
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "gh"
    $startInfo.Arguments = "secret set $Name"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $process = [Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($Value)
    $process.StandardInput.Close()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Failed to configure GitHub secret $Name."
    }
}

& gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI authentication is required. Run: gh auth login"
}

$values = Read-DotEnv
$apiKey = [string]$values["BREVO_API_KEY"]
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = [string]$values["Bravo_token"]
}
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Read-SecretText -Prompt "Brevo API key"
}
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "BREVO_API_KEY is required."
}
Set-DotEnvValue "BREVO_API_KEY" $apiKey
$env:BREVO_API_KEY = $apiKey

$listIds = [string]$values["BREVO_LIST_IDS"]
if ([string]::IsNullOrWhiteSpace($listIds)) {
    $listIds = [string]$values["BREVO_LIST_ID"]
}
if ([string]::IsNullOrWhiteSpace($listIds)) {
    & $Python scripts\list_brevo_resources.py
    if ($LASTEXITCODE -ne 0) {
        throw "Brevo rejected the API key. Generate a new v3 API key in SMTP & API."
    }
    $listIds = Read-Host -Prompt "Brevo subscriber List ID"
}
if ([string]::IsNullOrWhiteSpace($listIds)) {
    throw "BREVO_LIST_IDS is required."
}
Set-DotEnvValue "BREVO_LIST_IDS" $listIds
$env:BREVO_LIST_IDS = $listIds

$fromEmail = [string]$values["PTIA_NEWSLETTER_FROM_EMAIL"]
if ([string]::IsNullOrWhiteSpace($fromEmail)) {
    $fromEmail = "info@ptia.pt"
}
Set-DotEnvValue "PTIA_NEWSLETTER_FROM_EMAIL" $fromEmail
$env:PTIA_NEWSLETTER_FROM_EMAIL = $fromEmail

$replyTo = [string]$values["PTIA_NEWSLETTER_REPLY_TO"]
if ([string]::IsNullOrWhiteSpace($replyTo)) {
    $replyTo = $fromEmail
}
Set-DotEnvValue "PTIA_NEWSLETTER_REPLY_TO" $replyTo
$env:PTIA_NEWSLETTER_REPLY_TO = $replyTo
$env:BREVO_MAX_RECIPIENTS = "300"

& $Python scripts\list_brevo_resources.py
if ($LASTEXITCODE -ne 0) {
    throw "Brevo account validation failed."
}

& $Python scripts\github_newsletter_runner.py --json
if ($LASTEXITCODE -ne 0) {
    throw "Newsletter compilation preflight failed."
}

Set-GitHubSecret "BREVO_API_KEY" $apiKey
Set-GitHubSecret "BREVO_LIST_IDS" $listIds
Set-GitHubSecret "PTIA_NEWSLETTER_FROM_EMAIL" $fromEmail
Set-GitHubSecret "PTIA_NEWSLETTER_REPLY_TO" $replyTo

& gh workflow run weekly-newsletter.yml --ref main -f live=false
if ($LASTEXITCODE -ne 0) {
    throw "Could not start the GitHub newsletter preflight."
}

Start-Sleep -Seconds 3
$runId = & gh run list --workflow weekly-newsletter.yml --limit 1 --json databaseId --jq ".[0].databaseId"
if ([string]::IsNullOrWhiteSpace($runId)) {
    throw "Could not resolve the GitHub newsletter preflight run."
}
& gh run watch $runId --exit-status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub newsletter preflight failed."
}

Write-Host ""
Write-Host "PTIA newsletter GitHub automation is active."
Write-Host "Schedule: Friday 08:35 Europe/Lisbon; Brevo delivery: 09:00."
Write-Host "With zero recipients, the workflow validates and exits without creating a campaign."
