$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

& $python "tools\system_health.py"
