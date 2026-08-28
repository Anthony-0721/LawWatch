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

echo Checking bundled Python dependencies...
"%PY%" -c "import requests, bs4" >nul 2>&1
if errorlevel 1 (
    echo Error: python\python.exe cannot import the required dependencies.
    echo Re-extract the full portable package into a fresh folder and try again.
    exit /b 1
)

set "CFG_STATE="
"%PY%" -c "import json,sys;c=json.loads(open(sys.argv[1],encoding='utf-8').read());v=[str(c.get(k,'')).strip() for k in ('smtp_user','smtp_auth_code','email_to')];n=sum(bool(x) for x in v);w=str(c.get('wecom_webhook','')).strip();print('incomplete' if 0<n<3 else ('empty' if n==0 and not w else 'complete'))" "%CONFIG%" > "%TEMP%\lw_cfg_state.txt" 2>nul
set /p CFG_STATE=<"%TEMP%\lw_cfg_state.txt" 2>nul
del "%TEMP%\lw_cfg_state.txt" >nul 2>&1
if "%CFG_STATE%"=="" (
    echo Error: config.json is missing or is not valid JSON.
    echo Fix config.json and run install-task.bat again.
    exit /b 1
)
if "%CFG_STATE%"=="incomplete" (
    echo Error: config.json notification settings are incomplete.
    echo smtp_user, smtp_auth_code and email_to must be filled in together,
    echo or all three may be left empty for the first baseline run.
    exit /b 1
)
if "%CFG_STATE%"=="empty" (
    echo Warning: no notification channel is configured yet.
    echo The first successful run only builds a baseline and does not notify.
    echo Fill smtp_user, smtp_auth_code and email_to and/or wecom_webhook
    echo in config.json when you are ready to receive notifications.
)

schtasks /create /f /tn "LawWatch Monitor" /tr "\"%RUN%\" --send" /sc MINUTE /mo 30 /it
if errorlevel 1 (
    echo Error: could not create the "LawWatch Monitor" scheduled task.
    exit /b 1
)
echo Task "LawWatch Monitor" installed.
echo The task runs only while this Windows user is logged on; no password is stored.
echo Fill config.json before the first run if you have not already done so.
