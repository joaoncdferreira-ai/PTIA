# Script de Registo de Alertas do Co-Piloto PTIA no Windows Task Scheduler (Atualizado)
# Este script cria e atualiza as tarefas agendadas de acordo com as preferencias personalizadas do Joao.

# Definir caminhos absolutos
$ScriptPath = "c:\Users\joaon\ptia-content-engine\scripts\trigger_toast.ps1"
$PowerShell = "powershell.exe"

# --- REMOVER TAREFAS ANTERIORES E A DIARIA QUE JA NAO E NECESSARIA ---
Unregister-ScheduledTask -TaskName "PTIA_Alert_Premium_Monday" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "PTIA_Alert_Newsletter_Friday" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "PTIA_Alert_Curation_Daily" -Confirm:$false -ErrorAction SilentlyContinue

# 1. Alerta de Prospeccao e Convites Premium (Segundas-feiras as 22:00)
$Action1 = New-ScheduledTaskAction -Execute $PowerShell -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" -Title `"PTIA Premium Check`" -Message `"Hora da ronda Premium! Ve quem nos visitou e envia convites a novos seguidores no LinkedIn.`""
$Trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 22:00
Register-ScheduledTask -TaskName "PTIA_Alert_Premium_Monday" -Action $Action1 -Trigger $Trigger1 -Description "Alerta semanal de prospeccao LinkedIn Premium as segundas a noite." -Force

Write-Host "=== ALERTAS PTIA ATUALIZADOS COM SUCESSO NO WINDOWS TASK SCHEDULER! ==="
Write-Host "1. PTIA_Alert_Premium_Monday   -> Segundas as 22:00 (LinkedIn Page Premium)"
Write-Host "[-] PTIA_Alert_Newsletter_Friday -> REMOVIDO; o scheduler alerta apenas apos resposta real da MailerLite."
Write-Host "[-] PTIA_Alert_Curation_Daily    -> REMOVIDO permanentemente."
