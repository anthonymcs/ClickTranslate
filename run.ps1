$Host.UI.RawUI.WindowTitle = "ClickTranslate"
Set-Location $PSScriptRoot

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "          ClickTranslate - Iniciando Aplicacion        " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar entorno virtual de Python
$pythonExe = Join-Path $PSScriptRoot "backend\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "[1/3] Creando entorno virtual de Python..." -ForegroundColor Yellow
    python -m venv (Join-Path $PSScriptRoot "backend\venv")
    Write-Host "[1/3] Instalando dependencias de IA..." -ForegroundColor Yellow
    & $pythonExe -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
} else {
    Write-Host "[1/3] Entorno Python detectado correctamente." -ForegroundColor Green
}

# 2. Verificar dependencias de Node.js
$nodeModules = Join-Path $PSScriptRoot "node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "[2/3] Instalando modulos de Node.js..." -ForegroundColor Yellow
    & "C:\Program Files\nodejs\npm.cmd" install
} else {
    Write-Host "[2/3] Modulos de interfaz listos." -ForegroundColor Green
}

# 3. Comprobar Ollama
Write-Host "[3/3] Verificando conexion con Ollama local..." -ForegroundColor Gray
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[3/3] Ollama conectado exitosamente." -ForegroundColor Green
} catch {
    Write-Host "[AVISO] Ollama no detectado en puerto 11434. Intentando iniciar servicio..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
}

# 4. Iniciar Backend FastAPI en segundo plano
$backendRunning = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 1 -ErrorAction Stop
    if ($health.status -eq "ok") {
        $backendRunning = $true
        Write-Host "Backend FastAPI ya esta activo en http://127.0.0.1:8000" -ForegroundColor Green
    }
} catch {
    $backendRunning = $false
}

$backendProc = $null
if (-not $backendRunning) {
    Write-Host "Iniciando motor de traduccion en memoria RAM..." -ForegroundColor Cyan
    $backendDir = Join-Path $PSScriptRoot "backend"
    $backendProc = Start-Process -FilePath $pythonExe `
        -ArgumentList "-m uvicorn main:app --app-dir `"$backendDir`" --host 127.0.0.1 --port 8000" `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds 2
}

# 5. Iniciar la aplicacion de escritorio
Write-Host ""
Write-Host "Abriendo ventana de ClickTranslate..." -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

try {
    & "C:\Program Files\nodejs\npm.cmd" run tauri dev
} finally {
    # 6. Al salir, limpiar el backend si lo iniciamos nosotros
    Write-Host ""
    Write-Host "Cerrando backend y liberando memoria RAM..." -ForegroundColor Gray
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    # Asegurar que ningun uvicorn del venv quede huerfano
    Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like "*ClickTranslate\backend\venv*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
}
