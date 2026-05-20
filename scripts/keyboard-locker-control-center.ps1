Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $projectRoot "keyboard_locker.py"

function Invoke-Tool {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    $outputBox.AppendText("`r`n=== $Label ===`r`n")
    try {
        $result = & $Action 2>&1 | Out-String
        if ([string]::IsNullOrWhiteSpace($result)) {
            $result = "(no output)`r`n"
        }
        $outputBox.AppendText($result.TrimEnd() + "`r`n")
    }
    catch {
        $outputBox.AppendText("ERROR: " + $_.Exception.Message + "`r`n")
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "KeyboardLocker Control Center"
$form.Size = New-Object System.Drawing.Size(980, 700)
$form.StartPosition = "CenterScreen"
$form.TopMost = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = "KeyboardLocker Control Center"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(20, 15)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Mouse-friendly control panel for start, stop, autostart, panic unlock, and diagnostics."
$subtitle.AutoSize = $true
$subtitle.Location = New-Object System.Drawing.Point(22, 50)
$form.Controls.Add($subtitle)

$outputBox = New-Object System.Windows.Forms.TextBox
$outputBox.Multiline = $true
$outputBox.ScrollBars = "Vertical"
$outputBox.ReadOnly = $true
$outputBox.Font = New-Object System.Drawing.Font("Consolas", 10)
$outputBox.Location = New-Object System.Drawing.Point(20, 170)
$outputBox.Size = New-Object System.Drawing.Size(920, 460)
$form.Controls.Add($outputBox)

$buttons = @(
    @{ Text = "Start"; X = 20; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "start-keyboard-locker.ps1") } },
    @{ Text = "Stop"; X = 140; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "stop-keyboard-locker.ps1") } },
    @{ Text = "Restart"; X = 260; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "restart-keyboard-locker.ps1") } },
    @{ Text = "Panic Unlock"; X = 380; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "stop-keyboard-locker.ps1") } },
    @{ Text = "Enable Autostart"; X = 540; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "install-autostart.ps1") } },
    @{ Text = "Disable Autostart"; X = 720; Y = 90; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "uninstall-autostart.ps1") } },
    @{ Text = "Status"; X = 20; Y = 125; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "status-keyboard-locker.ps1") } },
    @{ Text = "Healthcheck"; X = 140; Y = 125; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "healthcheck-keyboard-locker.ps1") } },
    @{ Text = "Service Test"; X = 260; Y = 125; Action = { powershell -ExecutionPolicy Bypass -File (Join-Path $scriptDir "service-test-keyboard-locker.ps1") } },
    @{ Text = "Open Folder"; X = 380; Y = 125; Action = { Start-Process explorer.exe $projectRoot; "Opened project folder." } },
    @{ Text = "Clear Output"; X = 540; Y = 125; Action = { $outputBox.Clear(); "Output cleared." } }
)

foreach ($item in $buttons) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $item.Text
    $button.Size = New-Object System.Drawing.Size(140, 28)
    $button.Location = New-Object System.Drawing.Point($item.X, $item.Y)
    $action = $item.Action
    $label = $item.Text
    $button.Add_Click({
        Invoke-Tool -Label $label -Action $action
    })
    $form.Controls.Add($button)
}

$outputBox.AppendText("Ready.`r`n")
$outputBox.AppendText("Recommended buttons:`r`n")
$outputBox.AppendText("- Start`r`n")
$outputBox.AppendText("- Stop`r`n")
$outputBox.AppendText("- Panic Unlock`r`n")
$outputBox.AppendText("- Enable Autostart / Disable Autostart`r`n")
$outputBox.AppendText("- Status / Healthcheck`r`n")

[void]$form.ShowDialog()
