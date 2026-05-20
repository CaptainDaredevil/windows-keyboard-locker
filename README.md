# Keyboard Locker for Windows

Small Windows keyboard locker built in Python.

It runs in the background, lets you lock the keyboard with a hotkey, unlock it with a typed phrase or emergency hotkey, and supports autostart on Windows login.

## Features

- Lock keyboard with `Ctrl+Alt+L`
- Unlock with the physical `U N L O C K` key sequence
- Emergency unlock with `Ctrl+Alt+U`
- Exit with `Ctrl+Alt+Q`
- Windows autostart helper scripts
- Runtime state file for diagnostics
- Status and healthcheck commands
- Service regression test for `stop/start/restart`

## Files

- `keyboard_locker.py`: main app
- `scripts/`: helper scripts for autostart, status, healthcheck, service control, and tests

## Requirements

- Windows
- Python 3.13 or newer recommended
- PowerShell

No third-party Python packages are required.

## Quick Start

Run the locker in the current session:

```powershell
py .\keyboard_locker.py
```

Install autostart:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1
```

## User Hotkeys

- `Ctrl+Alt+L`: lock keyboard
- `unlock`: unlock
- `Ctrl+Alt+U`: emergency unlock
- `Ctrl+Alt+Q`: exit locker

## Operations

Check status:

```powershell
py .\keyboard_locker.py --status
```

Check health:

```powershell
py .\keyboard_locker.py --healthcheck
```

Start:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-keyboard-locker.ps1
```

Stop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-keyboard-locker.ps1
```

Restart:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart-keyboard-locker.ps1
```

Uninstall autostart:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-autostart.ps1
```

## Emergency Recovery

If the keyboard becomes unusable while the locker is active:

- Double-click `PANIC-UNLOCK.vbs`
- or double-click `PANIC-UNLOCK.bat`

These files stop the running background locker process and force runtime state back to `stopped`.

## Testing

Core self-test:

```powershell
py .\keyboard_locker.py --self-test
```

Operational service test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\service-test-keyboard-locker.ps1
```

## Runtime Files

Generated locally and ignored by git:

- `keyboard_locker.log`
- `keyboard_locker.log.1`
- `keyboard_locker.state.json`

## Diagnostics

Trace locked-mode events:

```powershell
py .\keyboard_locker.py --clear-log --trace-events
```

Then lock the keyboard, press the problematic keys, and inspect `keyboard_locker.log`.

## Known Limitations

- Some laptop vendor keys and hardware action keys can bypass normal user-mode keyboard interception.
- Surface and other OEM devices may route brightness, mic mute, or backlight keys outside the standard keyboard path.
- For those keys, `--trace-events` is the first diagnostic step.

## License

MIT
