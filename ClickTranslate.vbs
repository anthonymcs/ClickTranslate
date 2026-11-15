Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Ejecuta el lanzador bat en modo visible u oculto según preferencia
' Si deseas ver los logs de inicio usa 1, si deseas que sea 100% silencioso usa 0.
WshShell.CurrentDirectory = strPath
WshShell.Run Chr(34) & strPath & "\Iniciar ClickTranslate.bat" & Chr(34), 1, False
