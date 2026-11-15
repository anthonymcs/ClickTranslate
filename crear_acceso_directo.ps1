$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$CurrentDir = Split-Path -Parent $PSCommandPath
if (-not $CurrentDir) { $CurrentDir = Get-Location }

$ShortcutPath = Join-Path $DesktopPath "ClickTranslate.lnk"
$VbsLauncher = Join-Path $CurrentDir "ClickTranslate.vbs"
$IconFile = Join-Path $CurrentDir "src-tauri\icons\icon.ico"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = "`"$VbsLauncher`""
$Shortcut.WorkingDirectory = "$CurrentDir"
$Shortcut.IconLocation = "$IconFile,0"
$Shortcut.Description = "ClickTranslate - Traductor visual para cómics y mangas"
$Shortcut.Save()

Write-Host "Acceso directo silencioso creado exitosamente en: $ShortcutPath"
