# register_task_user.ps1 - Register PrepSignal auto-start as USER-level task
# Does NOT require Administrator privileges.
#
# Tradeoff vs register_task.ps1:
#   - Triggers at user LOGON instead of system BOOT
#   - Runs as current user instead of SYSTEM
#   - In practice equivalent: WSL needs your user session anyway
#
# Run ONCE in a normal (non-admin) PowerShell:
#   powershell -ExecutionPolicy Bypass -File "\\wsl$\Ubuntu\home\padiac\PrepSignal\register_task_user.ps1"

$taskName = "PrepSignal-KeepAlive-User"
$batPath  = "\\wsl$\Ubuntu\home\padiac\PrepSignal\start_prepsignal.bat"

$action    = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
# No -Principal => runs as current user, no admin needed.

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Keep WSL Ubuntu alive for PrepSignal (backend + cron via systemd). User-level, no admin required."

Write-Host ""
Write-Host "Done. Task '$taskName' registered."
Write-Host "It will run automatically each time you log in."
Write-Host ""
Write-Host "Start it now (so you don't need to log out):"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "Verify:  Get-ScheduledTask -TaskName '$taskName'"
Write-Host "Remove:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
