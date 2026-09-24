Option Explicit

Dim shell, fso, projectRoot, pythonwPath, configPath, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = projectRoot & "\.venv\Scripts\pythonw.exe"
configPath = projectRoot & "\config.local.yaml"

shell.CurrentDirectory = projectRoot

If fso.FileExists(pythonwPath) And fso.FileExists(configPath) Then
    shell.Environment("Process")("PYTHONPATH") = projectRoot & "\src"
    command = Chr(34) & pythonwPath & Chr(34) & _
        " -m wecom_sales_webhook_bot.cli desktop-gui --config " & _
        Chr(34) & configPath & Chr(34)
    shell.Run command, 0, False
Else
    command = "cmd.exe /c " & Chr(34) & _
        Chr(34) & projectRoot & "\一键安装并启动GUI.cmd" & Chr(34) & _
        Chr(34)
    shell.Run command, 1, False
End If
