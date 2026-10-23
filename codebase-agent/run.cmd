@echo off
cd /d "%~dp0"
rem load the embedding model from the local cache (no network checks -> fast startup)
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

rem pick a Python that has the project deps (venv > py launcher > python)
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY ( where py >nul 2>nul && set "PY=py -3.12" )
if not defined PY set "PY=python"

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [提示] 8000 端口已经有一个服务在运行，无需重复启动。
  echo        直接打开: http://127.0.0.1:8000/ui/
  exit /b 0
)
%PY% -m uvicorn web.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5