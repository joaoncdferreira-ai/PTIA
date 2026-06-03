$TaskName = "PTIA_Weekly_Newsletter"
$Description = "Compilação e agendamento autónomo da Weekly Briefing da PTIA todas as sextas-feiras às 10h00."
$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "c:\Users\joaon\ptia-content-engine\scripts\auto_newsletter_scheduler.py"
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "10:00AM"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Description $Description -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "Tarefa de agendamento automático da newsletter registrada com sucesso no Windows Task Scheduler!"
