@echo off
setlocal

set "PROJ=%~dp0"
set "VENV=%PROJ%venv\Scripts\python.exe"

if not exist "%VENV%" (
    echo [ERROR] Virtual environment not found. Please run setup_once.bat first.
    pause
    exit /b 1
)

rem Check if server already running on port 5000
netstat -ano 2>nul | findstr ":5000" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo Server is already running. Opening browser...
    start "" "http://127.0.0.1:5000/"
    echo If the browser did not open, visit http://127.0.0.1:5000/ manually.
    pause
    exit /b 0
)

echo Starting backend server (Flask :5000 + TCP :9000)...
start "sa-server" "%VENV%" "%PROJ%run_server.py"

echo Starting sensor simulator...
start "sa-simulator" "%VENV%" "%PROJ%run_simulator.py"

echo Waiting for services to start (about 6 seconds)...
timeout /t 6 /nobreak >nul

start "" "http://127.0.0.1:5000/"
echo Done. If the page is blank, press F5 to refresh.
echo To stop the services, run stop_all.bat
pause