@echo off
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File ".\build_and_deploy.ps1"
pause
