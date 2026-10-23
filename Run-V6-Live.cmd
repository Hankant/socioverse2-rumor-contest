@echo off
chcp 65001 >nul
title SocioVerse V6 Live - D040_T02_C080_G075
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" "scripts\run_live_checked.py" --gap 0.4 --tg 2 --target 0.8 --gt 0.75 %*
echo.
echo The program has exited. Do not enter your API key at this command prompt.
pause
