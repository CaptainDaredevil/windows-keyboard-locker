Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c cd /d """ & scriptDir & """ && powershell -ExecutionPolicy Bypass -File """ & scriptDir & "\scripts\stop-keyboard-locker.ps1"""

shell.Run command, 0, False
