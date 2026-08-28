@echo off
setlocal
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"
set "LAWWATCH_CONFIG=%APP_DIR%config.json"
set "LAWWATCH_DATA_DIR=%APP_DIR%data"
"%APP_DIR%python\python.exe" -m monitor.run %*
