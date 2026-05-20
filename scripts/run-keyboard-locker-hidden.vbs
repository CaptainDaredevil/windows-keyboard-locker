Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
command = "cmd /c cd /d """ & projectRoot & """ && pyw """ & projectRoot & "\keyboard_locker.py"""

shell.Run command, 0, False
