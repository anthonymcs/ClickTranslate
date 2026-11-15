$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$CurrentDir = Split-Path -Parent $PSCommandPath
if (-not $CurrentDir) { $CurrentDir = Get-Location }

$ShortcutPath = Join-Path $DesktopPath "ClickTranslate.lnk"
$TargetFile = Join-Path $CurrentDir "Iniciar ClickTranslate.bat"
$IconFile = Join-Path $CurrentDir "src-tauri\icons\icon.ico"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetFile
$Shortcut.WorkingDirectory = "$CurrentDir"
$Shortcut.IconLocation = "$IconFile,0"
$Shortcut.Description = "ClickTranslate - Traductor visual para cómics y mangas"
$Shortcut.Save()

Write-Host "Acceso directo verificado exitosamente en: $ShortcutPath"
