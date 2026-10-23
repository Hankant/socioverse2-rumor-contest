@echo off
title SocioVerse V6 Batch54 - MiniMax
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" "scripts\batch54.py" run
echo.
echo The batch controller has exited. Read the status file for completion or errors.
echo Do not enter your API key at this command prompt.
pause
