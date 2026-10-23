@echo off
chcp 65001 >nul
title SocioVerse V6 - Resume Saved Run
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u "app_v6\local_cli.py" resume %*
echo.
echo Resume controller has exited. See the saved run status above.
pause
