@echo off
setlocal
cd /d "%~dp0"
python start_local_webui.py
if errorlevel 1 (
  echo.
  echo 启动失败：请确认已安装 Python，并在仓库目录安装 requirements.txt。
  pause
)
