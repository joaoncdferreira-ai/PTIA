$TaskName = "PTIA_Weekly_Newsletter"
$Description = "Import automatico do export LinkedIn, compilacao e agendamento autonomo da Weekly Briefing da PTIA na Brevo todas as sextas-feiras para envio as 09h00."
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $RepoRoot "scripts\run_newsletter_task.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "8:45AM"
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $Description `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force
Write-Host "Tarefa de agendamento automatico da newsletter registrada com sucesso no Windows Task Scheduler."
Write-Host "A tarefa corre as sextas as 08:45, importa o export LinkedIn mais recente e agenda a campanha Brevo para as 09:00."
