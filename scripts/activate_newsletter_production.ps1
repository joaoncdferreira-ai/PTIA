param(
    [switch]$SkipTests,
    [switch]$SkipRender,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$EnvPath = Join-Path $RepoRoot ".env.local"
$ProjectId = "ptia-content-engine-prod"
$StateApiUrl = "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/state_api"

Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found at $Python"
}
if (-not (Get-Command firebase -ErrorAction SilentlyContinue)) {
    throw "Firebase CLI is not installed."
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

function New-StateToken {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Require-Value {
    param(
        [hashtable]$Values,
        [string]$Name,
        [string]$Prompt,
        [switch]$Secret
    )
    $value = [string]$Values[$Name]
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = if ($Secret) {
            Read-SecretText -Prompt $Prompt
        }
        else {
            Read-Host -Prompt $Prompt
        }
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name is required."
    }
    Set-DotEnvValue -Name $Name -Value $value
    Set-Item -Path "Env:$Name" -Value $value
    return $value
}

function Set-FirebaseSecret {
    param(
        [string]$Name,
        [string]$Value,
        [switch]$Json
    )
    $tempPath = Join-Path ([IO.Path]::GetTempPath()) ("ptia-" + [guid]::NewGuid().ToString("N"))
    try {
        [IO.File]::WriteAllText($tempPath, $Value, [Text.UTF8Encoding]::new($false))
        $arguments = @(
            "functions:secrets:set",
            $Name,
            "--data-file",
            $tempPath,
            "--project",
            $ProjectId
        )
        if ($Json) {
            $arguments += @("--format", "json")
        }
        & firebase @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to configure Firebase secret $Name."
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
    }
}

$values = Read-DotEnv
$brevoApiKey = Require-Value $values "BREVO_API_KEY" "Brevo API key" -Secret
$brevoListIds = [string]$values["BREVO_LIST_IDS"]
if ([string]::IsNullOrWhiteSpace($brevoListIds)) {
    $brevoListIds = [string]$values["BREVO_LIST_ID"]
}
if ([string]::IsNullOrWhiteSpace($brevoListIds)) {
    Write-Host "Available Brevo lists and senders:"
    & $Python scripts\list_brevo_resources.py
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list Brevo resources with the supplied API key."
    }
    $brevoListIds = Read-Host -Prompt "Brevo subscriber List ID"
}
if ([string]::IsNullOrWhiteSpace($brevoListIds)) {
    throw "BREVO_LIST_IDS is required."
}
Set-DotEnvValue "BREVO_LIST_IDS" $brevoListIds
$env:BREVO_LIST_IDS = $brevoListIds
Set-DotEnvValue "BREVO_MAX_RECIPIENTS" "300"
$env:BREVO_MAX_RECIPIENTS = "300"

$fromEmail = Require-Value $values "PTIA_NEWSLETTER_FROM_EMAIL" "Verified sender email"
$replyTo = [string]$values["PTIA_NEWSLETTER_REPLY_TO"]
if ([string]::IsNullOrWhiteSpace($replyTo)) {
    $replyTo = $fromEmail
    Set-DotEnvValue "PTIA_NEWSLETTER_REPLY_TO" $replyTo
}
$env:PTIA_NEWSLETTER_REPLY_TO = $replyTo

$stateToken = [string]$values["PTIA_STATE_TOKEN"]
if ($stateToken.Length -lt 32) {
    $stateToken = New-StateToken
    Set-DotEnvValue "PTIA_STATE_TOKEN" $stateToken
}
$env:PTIA_STATE_TOKEN = $stateToken
$env:PTIA_STATE_API_URL = $StateApiUrl

if (-not $SkipTests) {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed."
    }
}

& $Python scripts\prepare_firebase_functions.py
if ($LASTEXITCODE -ne 0) {
    throw "Cloud Functions package preparation failed."
}

$validationJson = & $Python scripts\validate_brevo_production.py --ensure-doi-template --create-delete-draft --json
if ($LASTEXITCODE -ne 0) {
    throw "Brevo rejected the current sender, list or newsletter HTML."
}
$validation = $validationJson | ConvertFrom-Json
$doiTemplateId = [string]$validation.doi_template_id
if ([string]::IsNullOrWhiteSpace($doiTemplateId)) {
    throw "Brevo double opt-in template could not be resolved."
}
Set-DotEnvValue "BREVO_DOI_TEMPLATE_ID" $doiTemplateId
$env:BREVO_DOI_TEMPLATE_ID = $doiTemplateId
Write-Host (
    "Brevo contract validated; recipients: " +
    [string]$validation.recipient_count +
    "/300; sender: " +
    [string]$validation.sender
)

& $Python scripts\newsletter_production_preflight.py
if ($LASTEXITCODE -ne 0) {
    throw "Local newsletter preflight failed."
}

if (-not $SkipDeploy) {
    & firebase projects:list
    if ($LASTEXITCODE -ne 0) {
        throw "Firebase authentication failed. Run: firebase login --reauth"
    }

    $brevoConfig = @{
        BREVO_API_KEY = $brevoApiKey
        BREVO_LIST_IDS = $brevoListIds
        BREVO_MAX_RECIPIENTS = "300"
        BREVO_DOI_TEMPLATE_ID = $doiTemplateId
        PTIA_SUBSCRIBE_SALT = $stateToken
        PTIA_NEWSLETTER_FROM_EMAIL = $fromEmail
        PTIA_NEWSLETTER_FROM_NAME = "PTIA"
        PTIA_NEWSLETTER_REPLY_TO = $replyTo
    } | ConvertTo-Json -Compress

    Set-FirebaseSecret "PTIA_STATE_TOKEN" $stateToken
    Set-FirebaseSecret "PTIA_BREVO_CONFIG" $brevoConfig -Json

    $targets = (
        "firestore," +
        "functions:ptia-cloud:state_api," +
        "functions:ptia-cloud:newsletter_preflight," +
        "functions:ptia-cloud:newsletter_subscribe," +
        "functions:ptia-cloud:schedule_weekly_newsletter_cloud"
    )
    & firebase deploy --only $targets --project $ProjectId
    if ($LASTEXITCODE -ne 0) {
        throw "Firebase deploy failed. Confirm that the project is on the Blaze plan."
    }

    & $Python scripts\newsletter_production_preflight.py --online --skip-render-check
    if ($LASTEXITCODE -ne 0) {
        throw "Cloud newsletter preflight failed. Render was not enabled."
    }
}

if (-not $SkipRender) {
    $values = Read-DotEnv
    $renderApiKey = Require-Value $values "RENDER_API_KEY" "Render API key" -Secret
    $env:RENDER_API_KEY = $renderApiKey

    & $Python scripts\configure_render_cloud_state.py --enable
    if ($LASTEXITCODE -ne 0) {
        throw "Render configuration or deploy failed."
    }

    & $Python scripts\newsletter_production_preflight.py --online
    if ($LASTEXITCODE -ne 0) {
        throw "Final newsletter production preflight failed."
    }
}

Write-Host ""
Write-Host "PTIA newsletter cloud automation is active."
Write-Host "Schedule: Friday 08:45 Europe/Lisbon; Brevo delivery: 09:00."
