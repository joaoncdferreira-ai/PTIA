# Script de Notificação Nativa PTIA para Windows
param(
    [string]$Title = "PTIA Co-Piloto 🦁",
    [string]$Message = "Hora de verificar o LinkedIn Premium e convidar novos seguidores!"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$global:notification = New-Object System.Windows.Forms.NotifyIcon
$global:notification.Icon = [System.Drawing.SystemIcons]::Information
$global:notification.BalloonTipTitle = $Title
$global:notification.BalloonTipText = $Message
$global:notification.Visible = $True
$global:notification.ShowBalloonTip(15000)

# Manter vivo tempo suficiente para mostrar o balloon
Start-Sleep -Seconds 3
$global:notification.Dispose()
