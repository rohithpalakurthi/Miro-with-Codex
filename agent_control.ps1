$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$action = "status"
if ($args.Count -gt 0) {
  $action = $args[0]
}

& $python "tools\agent_supervisor.py" $action
