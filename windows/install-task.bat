@echo off
setlocal
set "APP_DIR=%~dp0"
set "PY=%APP_DIR%python\python.exe"
set "RUN=%APP_DIR%run.bat"
set "CONFIG=%APP_DIR%config.json"
set "DATA=%APP_DIR%data"
if not exist "%PY%" echo Error: python\python.exe not found & exit /b 1
if not exist "%RUN%" echo Error: run.bat not found & exit /b 1
if not exist "%CONFIG%" copy "%APP_DIR%config.example.json" "%CONFIG%" >nul
if not exist "%DATA%" mkdir "%DATA%"
schtasks /create /f /tn "LawWatch Monitor" /tr "\"%RUN%\" --send" /sc MINUTE /mo 30 /ru "%USERNAME%"
echo Task "LawWatch Monitor" installed.
echo Fill config.json before first run.
