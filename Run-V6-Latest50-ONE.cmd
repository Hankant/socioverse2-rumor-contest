@echo off
chcp 65001 >nul
title SocioVerse V6 - Latest50 MBTI - ONE condition
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" "app_v6\local_cli.py" live --config "configs\one_latest50_mbti_test.json" --steps 10
echo.
echo Check status.json for completion or pause. Original experiments are preserved.
pause
