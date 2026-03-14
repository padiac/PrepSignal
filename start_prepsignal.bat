@echo off
REM Keep WSL alive so systemd services (backend + cron) keep running.
REM Registered as a Windows Task Scheduler task (AtStartup).
REM
REM What this does:
REM   1. Launches WSL Ubuntu (if not already running)
REM   2. systemd auto-starts: prepsignal-backend.service + cron.service
REM   3. "sleep infinity" keeps the WSL VM from being reclaimed by Windows
REM
REM Backend crash recovery is handled by systemd (Restart=always).

wsl -d Ubuntu -e bash -lc "exec sleep infinity"
