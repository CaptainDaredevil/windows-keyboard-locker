$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $projectRoot "keyboard_locker.py"
$stopScript = Join-Path $scriptDir "stop-keyboard-locker.ps1"
$startScript = Join-Path $scriptDir "start-keyboard-locker.ps1"
$restartScript = Join-Path $scriptDir "restart-keyboard-locker.ps1"

function Invoke-Healthcheck {
    py $pythonScript --healthcheck | Out-Host
    return $LASTEXITCODE
}

function Assert-ExitCode {
    param(
        [int]$Actual,
        [int]$Expected,
        [string]$Label
    )

    if ($Actual -ne $Expected) {
        throw "$Label failed. Expected exit code $Expected but got $Actual."
    }

    Write-Output "PASS $Label"
}

function Assert-StatusContains {
    param(
        [string]$Needle,
        [string]$Label
    )

    $statusOutput = (py $pythonScript --status) -join "`n"
    if ($statusOutput -notmatch [regex]::Escape($Needle)) {
        throw "$Label failed. Missing status marker: $Needle"
    }

    Write-Output "PASS $Label"
}

Write-Output "STEP stop"
powershell -ExecutionPolicy Bypass -File $stopScript | Out-Null
$code = Invoke-Healthcheck
Assert-ExitCode -Actual $code -Expected 1 -Label "healthcheck after stop"
Assert-StatusContains -Needle "running_instances=0" -Label "status shows zero instances after stop"
Assert-StatusContains -Needle "runtime_status=stopped" -Label "status shows stopped runtime after stop"

Write-Output "STEP start"
powershell -ExecutionPolicy Bypass -File $startScript | Out-Null
$code = Invoke-Healthcheck
Assert-ExitCode -Actual $code -Expected 0 -Label "healthcheck after start"
Assert-StatusContains -Needle "running_instances=1" -Label "status shows one instance after start"
Assert-StatusContains -Needle "runtime_stale=no" -Label "status is non-stale after start"
Assert-StatusContains -Needle "runtime_status=running" -Label "status shows running runtime after start"

Write-Output "STEP restart"
powershell -ExecutionPolicy Bypass -File $restartScript | Out-Null
$code = Invoke-Healthcheck
Assert-ExitCode -Actual $code -Expected 0 -Label "healthcheck after restart"
Assert-StatusContains -Needle "runtime_stale=no" -Label "status shows non-stale runtime after restart"
Assert-StatusContains -Needle "runtime_status=running" -Label "status shows running runtime after restart"

Write-Output "Service test passed."
