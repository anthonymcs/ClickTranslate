$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "ClickTranslate.lnk"
$CurrentDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $CurrentDir "Iniciar ClickTranslate.bat"
$Shortcut.WorkingDirectory = $CurrentDir
$Shortcut.IconLocation = Join-Path $CurrentDir "src-tauri\icons\icon.ico"
$Shortcut.Description = "ClickTranslate - Traductor visual para cómics y mangas"
$Shortcut.Save()

Write-Host "Acceso directo creado exitosamente en: $ShortcutPath"
