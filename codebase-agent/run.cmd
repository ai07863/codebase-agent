@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [提示] 8000 端口已经有一个服务在运行，无需重复启动。
  echo        直接打开: http://127.0.0.1:8000/ui/
  echo        若想用本窗口启动，请先关闭已经在运行的那个服务窗口。
  exit /b 0
)
"C:\Users\Tim\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn web.main:app --host 127.0.0.1 --port 8000 --reload