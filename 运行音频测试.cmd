@echo off
setlocal
set "PYTHONUTF8=1"
set "MAKER_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "MAKER_PYTHON=%~dp0.venv\Scripts\python.exe"
"%MAKER_PYTHON%" "%~dp0scripts\audio_menu.py"
set "MAKER_RESULT=%errorlevel%"
echo Exit code: %MAKER_RESULT%
pause
exit /b %MAKER_RESULT%
