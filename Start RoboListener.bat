@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-windows.ps1"
if errorlevel 1 (
  echo.
  echo RoboListener could not start. Review the error above.
  pause
)
