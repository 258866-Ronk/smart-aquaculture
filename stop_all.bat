@echo off
setlocal

echo Stopping smart-aquaculture services...
taskkill /f /fi "WINDOWTITLE eq sa-server" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq sa-simulator" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":9000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
echo Services stopped.
pause