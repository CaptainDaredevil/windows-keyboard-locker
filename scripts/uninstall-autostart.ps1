$taskName = "KeyboardLocker"
$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "KeyboardLocker"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"

Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
}
catch {
}

Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
py $scriptPath --write-state-stopped | Out-Null
py $scriptPath --restore-accessibility-hotkeys | Out-Null

Write-Output "Removed autostart and stopped running keyboard locker instances."
