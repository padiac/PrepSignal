# register_task.ps1 - Register PrepSignal auto-start in Windows Task Scheduler
# Run this ONCE in PowerShell (as Administrator):
#   powershell -ExecutionPolicy Bypass -File \\wsl$\Ubuntu\home\padiac\PrepSignal\register_task.ps1

$taskName = "PrepSignal-AutoStart"
$batPath = "\\wsl$\Ubuntu\home\padiac\PrepSignal\start_prepsignal.bat"

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Start PrepSignal backend + cron in WSL on login"

Write-Host "Done. Task '$taskName' registered. It will run at next login."
Write-Host "To verify:  Get-ScheduledTask -TaskName '$taskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
