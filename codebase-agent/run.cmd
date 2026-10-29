@echo off
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

set "PY="
if exist "C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe" set "PY=C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

rem start the Cloudflare tunnel if it is not already running
powershell -NoProfile -Command "if (-not (Get-Process cloudflared -ErrorAction SilentlyContinue)) { Start-Process 'C:\Program Files (x86)\cloudflared\cloudflared.exe' -ArgumentList 'tunnel','run','image-agent' -WindowStyle Hidden }"

powershell -NoProfile -Command "exit (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count"
if not "%errorlevel%"=="0" goto already_running

%PY% -m uvicorn web.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
goto :eof

:already_running
echo.
echo  8000 port already has a running service; skipping app start.
echo  Open: http://127.0.0.1:8000/ui/
echo.