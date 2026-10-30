@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-V7.ps1" -Mode resume
set "V7_EXIT=%ERRORLEVEL%"
echo.
echo V7 exit code: %V7_EXIT%
pause
exit /b %V7_EXIT%
