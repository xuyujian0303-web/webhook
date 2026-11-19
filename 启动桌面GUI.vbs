Option Explicit

Dim shell, fso, projectRoot, exePath, setupPath, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = projectRoot & "\企业微信销售推送.exe"
setupPath = projectRoot & "\一键安装并启动GUI.cmd"

shell.CurrentDirectory = projectRoot

If fso.FileExists(exePath) Then
    shell.Run Chr(34) & exePath & Chr(34), 0, False
Else
    command = "cmd.exe /c " & Chr(34) & _
        Chr(34) & setupPath & Chr(34) & _
        Chr(34)
    shell.Run command, 1, False
End If
