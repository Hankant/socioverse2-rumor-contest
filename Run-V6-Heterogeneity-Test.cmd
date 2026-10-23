@echo off
chcp 65001 >nul
title SocioVerse V6 Heterogeneity - SINGLE TEST
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u "scripts\run_live_checked.py" --gap 0.4 --tg 2 --target 0.8 --gt 0.75 --steps 10 --concurrency 2
echo.
echo The single study has exited. Do not enter a key at this command prompt.
pause
