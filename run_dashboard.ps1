$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

Write-Host "Starting MIRO dashboard on http://localhost:5055 ..." -ForegroundColor Cyan
& $python "agents\master_trader\miro_dashboard_server.py"
