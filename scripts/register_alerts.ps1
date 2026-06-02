# Script de Registo de Alertas do Co-Piloto PTIA no Windows Task Scheduler
# Este script cria tarefas agendadas que disparam popups nativos no ecra do utilizador nos momentos criticos.

# Definir caminhos absolutos
$ScriptPath = "c:\Users\joaon\ptia-content-engine\scripts\trigger_toast.ps1"
$PowerShell = "powershell.exe"

# 1. Alerta de Prospeccao e Convites Premium (Segundas-feiras as 10:00)
$Action1 = New-ScheduledTaskAction -Execute $PowerShell -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" -Title `"PTIA Premium Check`" -Message `"Hora da ronda Premium! Ve quem nos visitou e envia convites a novos seguidores no LinkedIn.`""
$Trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10:00
Register-ScheduledTask -TaskName "PTIA_Alert_Premium_Monday" -Action $Action1 -Trigger $Trigger1 -Description "Alerta semanal para ronda de prospeccao e convites LinkedIn Premium." -Force

# 2. Alerta de Revisao da Newsletter Weekly Briefing (Sextas-feiras as 09:30)
$Action2 = New-ScheduledTaskAction -Execute $PowerShell -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" -Title `"PTIA Newsletter Check`" -Message `"A Weekly Briefing sai as 10:00. Entra no Dashboard para validar o rascunho de hoje!`""
$Trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 09:30
Register-ScheduledTask -TaskName "PTIA_Alert_Newsletter_Friday" -Action $Action2 -Trigger $Trigger2 -Description "Alerta semanal para revisao da newsletter." -Force

# 3. Alerta Diario de Curadoria e Aprovacao (Segunda a Sexta as 15:00)
$Action3 = New-ScheduledTaskAction -Execute $PowerShell -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" -Title `"PTIA Curadoria`" -Message `"Verifica se os posts das 16:00 e 21:00 de hoje ja estao aprovados (final ok) no Dashboard.`""
$Trigger3 = New-ScheduledTaskTrigger -Daily -At 15:00
Register-ScheduledTask -TaskName "PTIA_Alert_Curation_Daily" -Action $Action3 -Trigger $Trigger3 -Description "Alerta diario para curadoria e aprovacao de posts sociais." -Force

Write-Host "=== ALERTAS PTIA CONFIGURADOS COM SUCESSO NO WINDOWS TASK SCHEDULER! ==="
Write-Host "1. PTIA_Alert_Premium_Monday   -> Segundas as 10:00 (LinkedIn Page Premium)"
Write-Host "2. PTIA_Alert_Newsletter_Friday -> Sextas as 09:30 (Revisao de Newsletter)"
Write-Host "3. PTIA_Alert_Curation_Daily    -> Diario as 15:00 (Aprovacao de Posts Sociais)"
