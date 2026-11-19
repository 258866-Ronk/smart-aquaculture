@echo off
chcp 65001 >nul
cd /d %~dp0
if exist venv\Scripts\python.exe (
  set PY=venv\Scripts\python.exe
) else (
  set PY=python
)
echo [启动] 智慧渔业服务端（HTTP:5000 + TCP:9000）...
%PY% run_server.py
pause
