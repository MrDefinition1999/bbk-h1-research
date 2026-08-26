@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-h2.ps1" %*
exit /b %errorlevel%
