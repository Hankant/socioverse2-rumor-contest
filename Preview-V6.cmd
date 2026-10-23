@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" "app_v6\local_cli.py" preview %*
pause
