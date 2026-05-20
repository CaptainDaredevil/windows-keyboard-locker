$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"

Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

for ($i = 0; $i -lt 30; $i++) {
    $remaining = @(Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
        Where-Object { $_.CommandLine -like "*keyboard_locker.py*" })
    if ($remaining.Count -eq 0) {
        break
    }
    Start-Sleep -Milliseconds 100
}

py $scriptPath --write-state-stopped | Out-Null

Write-Output "Stopped running keyboard locker instances."
