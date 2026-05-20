$taskName = "KeyboardLocker"
$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "KeyboardLocker"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonwPath = Join-Path (Split-Path (Get-Command python.exe).Source -Parent) "pythonw.exe"
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"

if (-not (Test-Path -LiteralPath $pythonwPath)) {
    Write-Error "pythonw.exe not found at $pythonwPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Error "keyboard_locker.py not found at $scriptPath"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonwPath -Argument "`"$scriptPath`"" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest

$registeredTask = $false
$alreadyRunning = @(Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" }).Count -gt 0

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
    Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    if (-not $alreadyRunning) {
        Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    }
    $registeredTask = $true
}
catch {
    $runCommand = "`"$pythonwPath`" `"$scriptPath`""
    New-Item -Path $runKeyPath -Force | Out-Null
    Set-ItemProperty -Path $runKeyPath -Name $runValueName -Value $runCommand
}

if (-not $alreadyRunning) {
    Start-Process -FilePath $pythonwPath -ArgumentList "`"$scriptPath`"" -WorkingDirectory $projectRoot -WindowStyle Hidden
}

if ($registeredTask) {
    Write-Output "Installed and started scheduled task: $taskName"
}
else {
    Write-Output "Installed HKCU Run autostart entry: $runValueName"
}
