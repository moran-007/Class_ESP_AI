@echo off
setlocal
set "PYTHONUTF8=1"
set "MAKER_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "MAKER_PYTHON=%~dp0.venv\Scripts\python.exe"
"%MAKER_PYTHON%" "%~dp0scripts\configure_hardware.py"
if errorlevel 1 pause
exit /b %errorlevel%
