Option Explicit

Dim shell, fso, projectRoot, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c " & Chr(34) & Chr(34) & projectRoot & "\一键安装并启动GUI.cmd" & Chr(34) & Chr(34)
shell.Run command, 0, False
