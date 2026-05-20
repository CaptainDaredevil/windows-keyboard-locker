$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"
$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

py $scriptPath --status
py $scriptPath --healthcheck

try {
    $task = Get-ScheduledTask -TaskName KeyboardLocker -ErrorAction Stop
    $taskInfo = Get-ScheduledTaskInfo -TaskName KeyboardLocker -ErrorAction SilentlyContinue
    Write-Output "scheduled_task=present"
    Write-Output ("scheduled_task_state=" + $task.State)
    if ($taskInfo) {
        Write-Output ("scheduled_task_last_run=" + $taskInfo.LastRunTime)
        Write-Output ("scheduled_task_last_result=" + $taskInfo.LastTaskResult)
    }
}
catch {
    Write-Output "scheduled_task=missing_or_inaccessible"
}

try {
    $runValue = (Get-ItemProperty -Path $runKeyPath -Name KeyboardLocker -ErrorAction Stop).KeyboardLocker
    Write-Output "run_key=present"
    Write-Output ("run_key_command=" + $runValue)
}
catch {
    Write-Output "run_key=missing"
}

Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" } |
    Select-Object ProcessId,CreationDate,CommandLine
