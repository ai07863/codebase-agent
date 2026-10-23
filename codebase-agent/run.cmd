@echo off
cd /d "%~dp0"
rem load the embedding model from the local cache (no network checks -> fast startup)
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [提示] 8000 端口已经有一个服务在运行，无需重复启动。
  echo        直接打开: http://127.0.0.1:8000/ui/
  exit /b 0
)
"C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn web.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5