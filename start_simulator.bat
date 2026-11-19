@echo off
chcp 65001 >nul
cd /d %~dp0
if exist venv\Scripts\python.exe (
  set PY=venv\Scripts\python.exe
) else (
  set PY=python
)
echo [启动] 边缘网关 / 传感器模拟器...
%PY% run_simulator.py
pause
