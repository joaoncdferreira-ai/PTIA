$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$env:PYTHONPATH = "src"

Write-Host "Starting PTIA dashboard for mobile access..."
Write-Host "Local URL:   http://127.0.0.1:8765"
Write-Host "Network URL: http://<PC-IP-OR-TAILSCALE-IP>:8765"
Write-Host ""
Write-Host "Keep this window/process running while using the mobile dashboard."

python -m ptia_engine.cli dashboard --host 0.0.0.0 --port 8765
