@echo off
chcp 65001 >nul
cd /d %~dp0
if exist venv\Scripts\python.exe (
  set PY=venv\Scripts\python.exe
) else (
  set PY=python
)
echo [启动] PyQt5 模型调试界面（需先启动 run_server.py）...
%PY% pyqt_app\main.py
pause
