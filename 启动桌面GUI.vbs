Option Explicit

Dim shell, fso, projectRoot, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c " & Chr(34) & "cd /d " & Chr(34) & projectRoot & Chr(34) & " && set PYTHONPATH=" & projectRoot & "\src && if exist .venv\Scripts\pythonw.exe ( .venv\Scripts\pythonw.exe -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml ) else ( pythonw.exe -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml )" & Chr(34)
shell.Run command, 0, False
