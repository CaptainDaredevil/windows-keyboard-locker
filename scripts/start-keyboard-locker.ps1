$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonwPath = Join-Path (Split-Path (Get-Command python.exe).Source -Parent) "pythonw.exe"
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"

$running = @(Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" })

if ($running.Count -gt 0) {
    Write-Output "Keyboard locker is already running."
    $running | Select-Object ProcessId,CreationDate,CommandLine
    exit 0
}

py $scriptPath --restore-accessibility-hotkeys | Out-Null
Start-Process -FilePath $pythonwPath -ArgumentList "`"$scriptPath`"" -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Sleep -Seconds 1

for ($i = 0; $i -lt 30; $i++) {
    $health = py $scriptPath --healthcheck 2>$null
    if ($LASTEXITCODE -eq 0) {
        break
    }
    Start-Sleep -Milliseconds 200
}

Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" } |
    Select-Object ProcessId,CreationDate,CommandLine
