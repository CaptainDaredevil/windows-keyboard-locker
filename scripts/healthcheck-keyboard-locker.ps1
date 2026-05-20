$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$scriptPath = Join-Path $projectRoot "keyboard_locker.py"

py $scriptPath --healthcheck
