# Script de Notificacao Nativa PTIA para Windows e Telemovel (E-mail)
param(
    [string]$Title = "PTIA Co-Piloto",
    [string]$Message = "Hora de verificar o LinkedIn Premium e convidar novos seguidores!"
)

# 1. Disparar notificacao nativa no ecra do Windows
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $global:notification = New-Object System.Windows.Forms.NotifyIcon
    $global:notification.Icon = [System.Drawing.SystemIcons]::Information
    $global:notification.BalloonTipTitle = $Title
    $global:notification.BalloonTipText = $Message
    $global:notification.Visible = $True
    $global:notification.ShowBalloonTip(15000)
    
    Start-Sleep -Seconds 2
    $global:notification.Dispose()
} catch {
    # Ignorar silenciosamente se falhar no ecra (ex: sessao bloqueada)
}

# 2. Enviar email em background para o telemovel
try {
    $python = "python"
    $script = "c:\Users\joaon\ptia-content-engine\scripts\send_email_alert.py"
    Start-Process -FilePath $python -ArgumentList "`"$script`" `"$Title`" `"$Message`"" -WindowStyle Hidden
} catch {
    # Ignorar erro se falhar o envio de email
}
