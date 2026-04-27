$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "MIRO setup starting..." -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Fill your real keys before live integrations." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path "logs","paper_trading\logs","backtesting\reports","live_execution\bridge","runtime" | Out-Null

& ".\.venv\Scripts\python.exe" "tools\system_health.py"

Write-Host "Setup complete." -ForegroundColor Green
