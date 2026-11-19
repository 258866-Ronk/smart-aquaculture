@echo off
setlocal

set "PROJ=%~dp0"
set "VENV=%PROJ%venv\Scripts\python.exe"

set "PYTHON="
where python >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON set "PYTHON=C:\Users\MEC\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if not exist "%VENV%" (
    echo Creating virtual environment...
    "%PYTHON%" -m venv "%PROJ%venv"
) else (
    echo Virtual environment already exists, skipping.
)

echo Installing dependencies (this may take a few minutes)...
"%VENV%" -m pip install -r "%PROJ%requirements.txt"

echo Initializing database and training models...
"%VENV%" "%PROJ%scripts\init_data.py"

echo Done. Now double-click start_all.bat to launch.
pause