@echo off
chcp 65001 >nul
title ClickTranslate - Cargando aplicación...
cls

echo =======================================================
echo          ⚡ ClickTranslate - Lanzador 1-Clic ⚡
echo =======================================================
echo.

cd /d "%~dp0"

:: 1. Verificar entorno virtual de Python
if not exist "backend\venv\Scripts\python.exe" (
    echo [1/3] Creando entorno virtual de Python (primera vez)...
    python -m venv backend\venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual. Asegúrate de tener Python instalado.
        pause
        exit /b 1
    )
    echo [1/3] Instalando dependencias de IA (OCR, Inpainting, FastAPI)...
    backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
) else (
    echo [1/3] Entorno Python detectado.
)

:: 2. Verificar dependencias de Node.js
if not exist "node_modules\" (
    echo [2/3] Instalando dependencias de interfaz React y Tauri...
    call "C:\Program Files\nodejs\npm.cmd" install
) else (
    echo [2/3] Módulos de interfaz listos.
)

:: 3. Verificar si Ollama está en ejecución
echo [3/3] Comprobando conexión con Ollama local...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama no parece estar iniciado.
    echo         Iniciando Ollama en segundo plano si está instalado...
    start /b "" ollama serve >nul 2>&1
) else (
    echo [3/3] Ollama conectado correctamente.
)

:: 4. Iniciar Backend FastAPI en segundo plano
echo.
echo Iniciando motor de procesamiento en memoria RAM...
start "ClickTranslate_Backend" /min "%CD%\backend\venv\Scripts\python.exe" -m uvicorn main:app --app-dir "%CD%\backend" --host 127.0.0.1 --port 8000

:: Esperar a que el servidor FastAPI esté respondiendo
timeout /t 2 /nobreak >nul

:: 5. Iniciar la aplicación de escritorio Tauri
echo.
echo Abriendo ventana de ClickTranslate...
echo =======================================================
echo.

call "C:\Program Files\nodejs\npm.cmd" run tauri dev

:: 6. Al cerrar la ventana, limpiar procesos en segundo plano
echo.
echo Cerrando servidor backend y liberando memoria RAM...
taskkill /f /fi "WINDOWTITLE eq ClickTranslate_Backend*" >nul 2>&1

exit /b 0
