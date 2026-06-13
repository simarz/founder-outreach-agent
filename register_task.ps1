# Registers a Windows Scheduled Task to run the agent every day at 8:00 AM.
# Re-run this to change the time (edit -At below first).
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$bat = Join-Path $PSScriptRoot "run_agent.bat"
$action = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "FounderFollowupAgent" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily founder follow-up tracker" -Force

Write-Host ""
Write-Host "Scheduled 'FounderFollowupAgent' to run daily at 8:00 AM." -ForegroundColor Green
Write-Host "Manage it in Task Scheduler, or run now with:  Start-ScheduledTask -TaskName FounderFollowupAgent"
