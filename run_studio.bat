@echo off
REM ============================================================
REM  LSEC Studio - lanzador portable (100% offline)
REM  Doble clic para iniciar el servidor local y abrir el navegador.
REM ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist "python\python.exe" set "PY=python\python.exe"
if not defined PY set "PY=python"

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro Python. Incluya una carpeta "venv" o "python" junto a este archivo.
    pause
    exit /b 1
)

REM Usar solo recursos locales: sin descargas desde Internet
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONIOENCODING=utf-8

if "%LSEC_PORT%"=="" set LSEC_PORT=8000

echo Iniciando LSEC Studio en http://127.0.0.1:%LSEC_PORT%/studio
echo Cierre esta ventana para detener el servidor.
start "" /min cmd /c "timeout /t 6 >nul & start http://127.0.0.1:%LSEC_PORT%/studio"

%PY% -m uvicorn app.main:app --host 127.0.0.1 --port %LSEC_PORT%
endlocal
