@echo off
title SocioVerse V6 Single Recovery - WAIT FOR CHAT APPROVAL
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u "scripts\run_single_recovery.py"
echo.
echo The recovery launcher has exited. Do not enter a key at this command prompt.
pause
