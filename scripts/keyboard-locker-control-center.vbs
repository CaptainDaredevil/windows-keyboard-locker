Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell -ExecutionPolicy Bypass -NoProfile -File """ & scriptDir & "\keyboard-locker-control-center.ps1"""

shell.Run command, 1, False
