# register_task.ps1 - Register PrepSignal auto-start in Windows Task Scheduler
# Run this ONCE in PowerShell (as Administrator):
#   powershell -ExecutionPolicy Bypass -File "\\wsl$\Ubuntu\home\padiac\PrepSignal\register_task.ps1"

$taskName = "PrepSignal-AutoStart"
$batPath = "\\wsl$\Ubuntu\home\padiac\PrepSignal\start_prepsignal.bat"

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Keep WSL alive for PrepSignal (backend + cron via systemd)"

Write-Host "Done. Task '$taskName' registered. Runs at system startup (no login needed)."
Write-Host "To verify:  Get-ScheduledTask -TaskName '$taskName'"
Write-Host "To test:    Start-ScheduledTask -TaskName '$taskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
