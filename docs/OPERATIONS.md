# MIRO Operations Runbook

This project is designed to run from a clean source tree while keeping live state local and out of Git.

## One-command scripts

- `setup.ps1` creates `.venv`, installs dependencies, creates `.env` from `.env.example` if missing, prepares runtime folders, and runs a health check.
- `run_dashboard.ps1` starts the dashboard at `http://localhost:5055`.
- `run_agents.ps1` starts the full agent orchestra through `launch.py`.
- `agent_control.ps1 status|start|stop|restart` manages the supervised `launch.py` process.
- `python tools\watchdog.py --loop` watches health/runtime freshness and can auto-start or restart agents.
- `python tools\daily_routine.py` runs the daily maintenance checklist. Add `--execute-heavy` for heavier research jobs.
- `health_check.ps1` runs the same system health engine exposed in the dashboard.
- `protect_main.ps1` attempts to enable GitHub branch protection with `gh`; if unavailable, enable it in GitHub UI.

## Dashboard operations

Open `http://localhost:5055` and use **System Operations**:

- `Run Health` checks env vars, folders, stale runtime files, and local ports.
- `Test Telegram` sends a real Telegram message using `.env` credentials.
- `Reset Paper` backs up and resets paper trading state to `$10,000`.
- `Clear Runtime` backs up paper/runtime files, removes stale local runtime JSON, and should be followed by restarting agents.
- `Start/Stop/Restart Agents` controls the supervised background `launch.py` process and writes PID/status to `runtime/`.
- `Start/Stop/Watchdog Check` controls stale-agent auto-recovery.
- `Agent Log` and `Optimizer Log` show recent logs directly in the dashboard.
- `Daily Routine` runs the lightweight daily maintenance sequence.
- `Lock Live` and `Unlock Live 30m` manage the separate live-mode lock. Unlocking this does not bypass promotion, risk, circuit breaker, or manual override gates.

## Git safety

Runtime files, logs, generated reports, `.env`, compiled MQL files, and bridge state should not be committed.

Use this before pushing:

```powershell
git status --short
git diff --cached --name-only
python -m unittest discover tests
```

## Branch protection

Recommended GitHub settings for `main`:

- Require pull request before merging.
- Require at least 1 approval.
- Block force pushes.
- Require branches to be up to date before merging.
- Do not allow direct pushes to `main`.

## Live trading safety

Live execution must stay blocked unless paper/demo metrics pass the configured safety gates. The dashboard and live safety module can block execution; they do not guarantee profit or remove market risk.
