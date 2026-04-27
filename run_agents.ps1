$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

Write-Host "Starting full MIRO agent orchestra..." -ForegroundColor Cyan
& $python "launch.py"
