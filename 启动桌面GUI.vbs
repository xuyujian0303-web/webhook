Option Explicit

Dim shell, fso, projectRoot, exePath, setupPath, command, exeName, setupName
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

exeName = ChrW(&H4F01) & ChrW(&H4E1A) & ChrW(&H5FAE) & ChrW(&H4FE1) & _
    ChrW(&H9500) & ChrW(&H552E) & ChrW(&H63A8) & ChrW(&H9001) & ".exe"
setupName = ChrW(&H4E00) & ChrW(&H952E) & ChrW(&H5B89) & ChrW(&H88C5) & _
    ChrW(&H5E76) & ChrW(&H542F) & ChrW(&H52A8) & "GUI.cmd"

projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = projectRoot & "\" & exeName
setupPath = projectRoot & "\" & setupName
shell.CurrentDirectory = projectRoot

If fso.FileExists(exePath) Then
    shell.Run Chr(34) & exePath & Chr(34), 1, False
Else
    command = "cmd.exe /c " & Chr(34) & Chr(34) & setupPath & Chr(34) & Chr(34)
    shell.Run command, 1, False
End If
