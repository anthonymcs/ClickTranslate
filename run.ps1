Set-Location $PSScriptRoot

# 1. Verificar entorno virtual de Python
$pythonExe = Join-Path $PSScriptRoot "backend\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    python -m venv (Join-Path $PSScriptRoot "backend\venv")
    & $pythonExe -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
}

# 2. Verificar dependencias de Node.js
$nodeModules = Join-Path $PSScriptRoot "node_modules"
$npmExe = (Get-Command npm -ErrorAction SilentlyContinue)?.Source
if (-not $npmExe) { $npmExe = "C:\Program Files\nodejs\npm.cmd" }

if (-not (Test-Path $nodeModules)) {
    & $npmExe install
}

# 3. Comprobar Ollama de forma segura
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 1 -ErrorAction Stop
} catch {
    $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue)?.Source
    if (-not $ollamaExe) {
        $defaultOllama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
        if (Test-Path $defaultOllama) { $ollamaExe = $defaultOllama }
    }
    if ($ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    }
}

# 4. Iniciar Backend FastAPI en segundo plano si no está activo
$backendRunning = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 1 -ErrorAction Stop
    if ($health.status -eq "ok") {
        $backendRunning = $true
    }
} catch {
    $backendRunning = $false
}

$backendProc = $null
if (-not $backendRunning) {
    $backendDir = Join-Path $PSScriptRoot "backend"
    $backendProc = Start-Process -FilePath $pythonExe `
        -ArgumentList "-m uvicorn main:app --app-dir `"$backendDir`" --host 127.0.0.1 --port 8000" `
        -WindowStyle Hidden `
        -PassThru
}

# 5. Iniciar la aplicación de escritorio
try {
    & $npmExe run tauri dev
} finally {
    # 6. Al salir, cerrar el backend y liberar toda la memoria RAM
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like "*ClickTranslate\backend\venv*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
}
