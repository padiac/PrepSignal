@echo off
REM Start PrepSignal services inside WSL on Windows boot/login.
REM Register this script as a Windows Task Scheduler task.

REM Start backend (checks if already running to avoid duplicates)
wsl -d Ubuntu -e bash -lc "cd /home/padiac/PrepSignal && if ! pgrep -f 'uvicorn main:app' > /dev/null; then ./run_backend_daemon.sh; else echo 'Backend already running'; fi"

REM Cron is auto-started by systemd; just verify
wsl -d Ubuntu -e bash -lc "pgrep cron > /dev/null && echo 'Cron OK' || sudo service cron start"
