@echo off
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

set "PY="
if exist "C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe" set "PY=C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

powershell -NoProfile -Command "exit (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count"
if not "%errorlevel%"=="0" goto already_running

%PY% -m uvicorn web.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
goto :eof

:already_running
echo.
echo  8000 端口已经有一个服务在运行，无需重复启动。
echo  直接打开: http://127.0.0.1:8000/ui/
echo.