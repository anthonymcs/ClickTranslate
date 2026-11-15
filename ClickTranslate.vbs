Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

WshShell.CurrentDirectory = strPath
' Ejecutar PowerShell 100% invisible (0 = SW_HIDE) sin ninguna ventana de terminal
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strPath & "\run.ps1""", 0, False
