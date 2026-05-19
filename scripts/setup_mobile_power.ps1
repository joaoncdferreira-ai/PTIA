$ErrorActionPreference = "Stop"

Write-Host "Configuring Windows power settings for PTIA mobile dashboard..."
Write-Host "Screen may turn off, but sleep/hibernate will be disabled while plugged in."

powercfg /change monitor-timeout-ac 10
powercfg /change standby-timeout-ac 0
powercfg /hibernate off

Write-Host "Done."
Write-Host "Recommended: keep the PC plugged in when using PTIA from mobile."
